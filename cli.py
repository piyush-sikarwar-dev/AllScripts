"""Management commands.

uv run python cli.py dbcheck                                  # source DBs: metadata only
uv run python cli.py create-user --email a@b.org --name "First Last"
uv run python cli.py reset-password --email a@b.org
uv run python cli.py deactivate-user --email a@b.org
uv run python cli.py build-crosswalk                          # EMR <-> Ntier IDs -> app DB
uv run python cli.py patient-list-check                       # real patient list: counts only
"""

import argparse
import getpass
import sys
from collections import Counter

from app.auth.passwords import hash_password, password_problem
from app.crosswalk.build import build_crosswalk_rows, replace_crosswalk
from app.db.app import new_session
from app.db.source import Source, configured_sources, database_name, dispose_engines
from app.repositories.appdb import sessions as session_repo
from app.repositories.appdb import users, utcnow
from app.repositories.base import run_query, run_scalar

# (source, schema, table, expected rows from the verified restore)
DBCHECK_TABLES: list[tuple[Source, str, str, int]] = [
    (Source.EMR, "HPSITE", "DEMOGRAPHICS", 21_384),
    (Source.EMR, "HPSITE", "ENCOUNTER", 2_565_968),
    (Source.EMR, "HPSITE", "LAB_RESULT", 1_603_126),
    (Source.EMR, "HPSITE", "SCAN_DOCUMENT", 626_325),
    (Source.NTIER, "PM", "Patients", 21_330),
    (Source.DMZ, "conv", "person", 9_868),
]

WRITE_FLAGS = ("is_sysadmin", "is_db_owner", "is_datawriter", "can_insert", "can_update",
               "can_delete", "can_alter")  # fmt: skip


def dbcheck() -> int:
    sources = configured_sources()
    if not sources:
        print("No source databases configured: set SQL_HOST / SQL_USER / SQL_PASSWORD in .env.")
        return 1
    failures = 0
    for source in sources:
        print(f"\n[{source.value}] database {database_name(source)}")
        try:
            info = run_query(source, "meta/server_info.sql")[0]
            print(f"  server   SQL Server {info['product_version']} ({info['edition']})")
            print(f"  database {info['database_name']}")
            perms = run_query(source, "meta/login_permissions.sql")[0]
            writable = [flag for flag in WRITE_FLAGS if perms.get(flag) == 1]
            if writable:
                print(f"  WARNING  login is not read-only here: {', '.join(writable)}")
            else:
                print("  login    read-only (no write permissions)")
            for src, schema, table, expected in DBCHECK_TABLES:
                if src is not source:
                    continue
                count = run_scalar(
                    source, "meta/table_row_count.sql", {"schema_name": schema, "table_name": table}
                )
                status = "ok" if count == expected else "DIFFERS"
                count_text = "missing" if count is None else f"{count:,}"
                print(
                    f"  {schema}.{table:<14} {count_text:>11}  expected {expected:>11,}  {status}"
                )
        except Exception as exc:  # report and continue with the next database
            failures += 1
            print(f"  ERROR    {type(exc).__name__}: {str(exc).splitlines()[0][:300]}")
    dispose_engines()
    return 1 if failures else 0


def prompt_new_password() -> str | None:
    """Ask twice; never echoed, never passed on the command line."""
    for _ in range(3):
        first = getpass.getpass("New password (min 12 characters): ")
        problem = password_problem(first)
        if problem:
            print(problem)
            continue
        if getpass.getpass("Repeat password: ") != first:
            print("Passwords do not match.")
            continue
        return first
    return None


def create_user(email: str, name: str) -> int:
    with new_session() as db:
        if users.get_by_email(db, email):
            print("A user with that email already exists.")
            return 1
        password = prompt_new_password()
        if password is None:
            return 1
        user = users.create(db, email=email, full_name=name, password_hash=hash_password(password))
        print(f"Created user id={user.id} ({user.email}).")
    return 0


def reset_password(email: str) -> int:
    with new_session() as db:
        user = users.get_by_email(db, email)
        if user is None:
            print("No user with that email.")
            return 1
        password = prompt_new_password()
        if password is None:
            return 1
        users.set_password(db, user, hash_password(password))
        session_repo.delete_for_user(db, user.id)  # sign out everywhere
        print(f"Password reset for {user.email}; existing sessions ended.")
    return 0


def deactivate_user(email: str) -> int:
    with new_session() as db:
        user = users.get_by_email(db, email)
        if user is None:
            print("No user with that email.")
            return 1
        users.set_active(db, user, False)
        session_repo.delete_for_user(db, user.id)
        print(f"Deactivated {user.email}; existing sessions ended.")
    return 0


def print_crosswalk_summary(summary: Counter[str]) -> None:
    """Counts only — no patient identifiers are printed."""
    total = sum(summary.values())
    print(f"Crosswalk rows: {total:,}")
    for method in ("ExactId", "ExactId-ambiguous", "None", "Merged"):
        print(f"  {method:<18} {summary.get(method, 0):>8,}")


def build_crosswalk() -> int:
    if Source.EMR not in configured_sources():
        print("EMR source not configured: set SQL_HOST / SQL_USER / SQL_PASSWORD in .env.")
        return 1
    print("Reading EMR <-> Ntier IDs (read-only)...")
    links = run_query(Source.EMR, "emr/crosswalk_emr_ntier.sql")
    merges = run_query(Source.EMR, "emr/patient_merges.sql")
    rows, summary = build_crosswalk_rows(links, merges, utcnow())
    with new_session() as db:
        replace_crosswalk(db, rows)
    dispose_engines()
    print_crosswalk_summary(summary)
    return 0


def patient_list_check() -> int:
    """Run the dashboard's patient-list queries once and print counts only (no PHI)."""
    from app.repositories import emr

    if Source.EMR not in configured_sources():
        print("EMR source not configured: set SQL_HOST / SQL_USER / SQL_PASSWORD in .env.")
        return 1
    try:
        rows = emr.patient_search(
            last_name=None, first_name=None, dob=None, chart_id=None, offset=0, limit=25
        )
        total = int(rows[0]["total_count"]) if rows else 0
        print(f"Patients (excluding merged-away): {total:,}")
        print(f"First page rows: {len(rows)}")
        print(f"  with date of birth: {sum(1 for r in rows if r['dob'] is not None)}")
        print(f"  with an MRN:        {len(emr.mrns([int(r['emr_id']) for r in rows]))}")
        codes = Counter(repr(r["sex_code"]) for r in rows)
        print(f"  sex codes on page:  {dict(codes)}")
        visits = emr.last_visits([int(r["emr_id"]) for r in rows])
        print(f"  with a last visit:  {len(visits)}")
        print("OK: the patient list queries work.")
        return 0
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {str(exc).splitlines()[0][:400]}")
        return 1
    finally:
        dispose_engines()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="cli.py", description="Legacy DEC & LR Records commands")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dbcheck", help="check source DB connections (metadata only)")
    create = sub.add_parser("create-user", help="create a staff account (prompts for password)")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    for cmd, text in (("reset-password", "set a new password"), ("deactivate-user", "disable")):
        sub.add_parser(cmd, help=text).add_argument("--email", required=True)
    sub.add_parser("build-crosswalk", help="rebuild EMR <-> Ntier patient links in the app DB")
    sub.add_parser("patient-list-check", help="run the patient list queries; print counts only")
    args = parser.parse_args(argv)
    if args.command == "patient-list-check":
        return patient_list_check()
    if args.command == "build-crosswalk":
        return build_crosswalk()
    if args.command == "dbcheck":
        return dbcheck()
    if args.command == "create-user":
        return create_user(args.email, args.name)
    if args.command == "reset-password":
        return reset_password(args.email)
    if args.command == "deactivate-user":
        return deactivate_user(args.email)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
