# Legacy Records Viewer

Read-only web viewer for the retired Allscripts EHR (EMR, practice management and pre-2010 records).
See `CLAUDE.md` for the full specification and `BUILD_PROMPTS.md` for the build phases.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

1. **Settings:** `cp .env.example .env` and fill it in. `.env` is git-ignored. Never put real
   credentials in `.env.example`.
2. **Dependencies:** `uv sync`
3. **App database (PostgreSQL 16)**, either:
   - Docker: `docker compose up -d postgres` (listens on `127.0.0.1:5433`), or
   - a local or portable PostgreSQL 16 on port 5433.

   Then set `APP_DATABASE_URL=postgresql+psycopg://legacy:<password>@127.0.0.1:5433/legacy_viewer`.
4. **Create tables:** `uv run python -m alembic upgrade head`
5. **Create your account** (prompts for the password twice, minimum 12 characters):
   `uv run python cli.py create-user --email you@clinic.org --name "First Last"`
6. **Run:** `uv run uvicorn app.main:app --reload`, then open http://127.0.0.1:8000.
   Use `COOKIE_SECURE=false` only for local http.

`USE_FAKE_DATA=true` (the default) shows obviously fake patients ("Sample, Patient A"). The real
source databases are used once their repositories are wired in.

## Management commands

| Command | Purpose |
|---|---|
| `uv run python cli.py create-user --email E --name N` | Add a staff account (no sign-up page) |
| `uv run python cli.py reset-password --email E` | Set a new password and end that user's sessions |
| `uv run python cli.py deactivate-user --email E` | Disable an account and end its sessions |
| `uv run python cli.py dbcheck` | Source SQL Server check: versions, login permissions, row counts (metadata only) |

## Checks

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest -m "not integration"
RUN_INTEGRATION=1 uv run pytest -m integration    # needs ODBC Driver 18 + SQL Server access
```

## Safety

- Source databases are read-only. Every statement is checked by `app/db/readonly.py`, which
  refuses anything but a single `SELECT`. The SQL login should also have only `db_datareader`.
- `audit_log` and `release_log` are append-only, enforced by a database trigger.
- No PHI in logs, URLs (beyond IDs), audit details or test fixtures.
