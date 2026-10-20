"""The separate "Pre-2010 records" section: legacy patient search, chart header, chart notes.

Reads only the DMZ legacy chart (via `legacy_repository()`); it never touches the current EMR /
PM chart, and the current chart never reads from here (CLAUDE.md §4.3, FEATURE_LEGACY_DMZ).
"""

import re
from datetime import date, datetime

from app.config import get_settings
from app.formatting import EMPTY, age, date_us, initials, or_dash, person_name
from app.lookups import label
from app.models.common import PAGE_SIZE, Pager, clamp_page, paginate
from app.models.legacy import (
    LegacyHeader,
    LegacyNote,
    LegacyNotePage,
    LegacyNoteRow,
    LegacyPage,
    LegacyRow,
    LegacySearch,
)
from app.repositories import legacy_repository
from app.services import NotFoundError, call
from app.services.patients import parse_dob, parse_name_query

KEY_RE = re.compile(r"DMZ:(\d{1,10})")


def legacy_enabled() -> bool:
    settings = get_settings()
    return settings.feature_legacy_dmz or settings.use_fake_data


def person_key(key: str) -> int:
    """'DMZ:<personkey>' → personkey; NotFoundError for anything else."""
    match = KEY_RE.fullmatch(key)
    if not match:
        raise NotFoundError(key)
    return int(match.group(1))


def _day(value: date | datetime | None) -> date | None:
    return value.date() if isinstance(value, datetime) else value


def _time(value: date | datetime | None) -> str:
    """Legacy times are stored as clinic-local wall-clock times; midnight means 'no time'."""
    if not isinstance(value, datetime) or (value.hour, value.minute) == (0, 0):
        return ""
    return f"{value.hour % 12 or 12}:{value:%M} {value:%p}"


def _phone(area: str | None, number: str | None) -> str:
    digits = re.sub(r"\D", "", f"{area or ''}{number or ''}")
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 7:
        return f"{digits[:3]}-{digits[3:]}"
    return or_dash(" ".join(part for part in (area, number) if part))


def _address(p: dict) -> str:
    street = ", ".join(s.strip() for s in (p.get("street1"), p.get("street2")) if s and s.strip())
    state_zip = " ".join(part for part in (p.get("state"), p.get("zip")) if part)
    city_line = ", ".join(part for part in (p.get("city"), state_zip) if part)
    return ", ".join(part for part in (street, city_line) if part) or EMPTY


def _deceased(value: object) -> bool:
    return str(value or "").strip().upper() in {"Y", "1", "TRUE", "T"}


def _provider(r: dict) -> str:
    name = person_name(r.get("provider_last"), r.get("provider_first"))
    if name == EMPTY:
        return EMPTY
    title = (r.get("provider_title") or "").strip()
    return f"{name}, {title}" if title else name


def build_search(q: str = "", dob: str = "", legacy_id: str = "") -> LegacySearch:
    search = LegacySearch(q=q.strip()[:100], dob=dob.strip()[:10], legacy_id=legacy_id.strip()[:20])
    if search.dob:
        try:
            parse_dob(search.dob)
        except ValueError:
            search.errors["dob"] = "Enter the date of birth as MM/DD/YYYY."
    if search.legacy_id and not re.fullmatch(r"[A-Za-z0-9-]+", search.legacy_id):
        search.errors["legacy_id"] = "Legacy ID can contain only letters, numbers and dashes."
    return search


async def search_patients(search: LegacySearch, page: int | None) -> LegacyPage:
    page = clamp_page(page)
    if search.errors:
        return LegacyPage(search=search, rows=[], pager=Pager(page=1, total=0))
    last, first = parse_name_query(search.q)
    rows, total = await call(
        legacy_repository().search,
        last_name=last,
        first_name=first,
        dob=parse_dob(search.dob),
        legacy_id=search.legacy_id or None,
        offset=(page - 1) * PAGE_SIZE,
        limit=PAGE_SIZE,
    )
    return LegacyPage(
        search=search,
        rows=[
            LegacyRow(
                key=f"DMZ:{r['person_key']}",
                name=person_name(r["last_name"], r["first_name"], r["middle_initial"]),
                dob=date_us(_day(r["dob"])),
                sex=label("sex", r["sex"]),
                legacy_id=or_dash(r["legacy_id"]),
            )
            for r in rows
        ],
        pager=Pager(page=page, total=total),
    )


async def get_header(key: str) -> LegacyHeader:
    p = await call(legacy_repository().patient, person_key(key))
    if p is None:
        raise NotFoundError(key)
    name = person_name(p["last_name"], p["first_name"], p["middle_initial"])
    suffix = (p.get("suffix") or "").strip()
    return LegacyHeader(
        key=key,
        name=f"{name} {suffix}" if suffix and name != EMPTY else name,
        initials=initials(p["last_name"], p["first_name"]),
        dob=date_us(_day(p["dob"])),
        age=age(_day(p["dob"])),
        sex=label("sex", p["sex"]),
        legacy_id=or_dash(p["legacy_id"]),
        phone=_phone(p.get("home_area"), p.get("home_phone")),
        address=_address(p),
        deceased=_deceased(p.get("deceased")),
    )


def _note_row(r: dict) -> LegacyNoteRow:
    return LegacyNoteRow(
        id=int(r["note_id"]),
        date=date_us(_day(r["service_date"])),
        time=_time(r["service_date"]),
        provider=_provider(r),
        facility=or_dash(r.get("facility")),
        has_text=bool(r["has_text"]),
    )


def _year(r: dict) -> str:
    value = r["service_date"]
    return str(value.year) if value else ""


async def note_page(key: str, year: str = "", page: int | None = None) -> LegacyNotePage:
    rows = await call(legacy_repository().notes, person_key(key))
    years = sorted({_year(r) for r in rows if _year(r)}, reverse=True)
    if year not in years:
        year = ""
    chosen = [r for r in rows if not year or _year(r) == year]
    shown, pager = paginate(chosen, clamp_page(page))
    dated = [r["service_date"] for r in rows if r["service_date"]]
    return LegacyNotePage(
        rows=[_note_row(r) for r in shown],
        pager=pager,
        years=years,
        year=year,
        total_all=len(rows),
        first_date=date_us(_day(min(dated))) if dated else EMPTY,
        last_date=date_us(_day(max(dated))) if dated else EMPTY,
    )


async def get_note(key: str, note_id: int) -> LegacyNote:
    pkey = person_key(key)
    repo = legacy_repository()
    rows = await call(repo.notes, pkey)
    row = next((r for r in rows if int(r["note_id"]) == note_id), None)
    if row is None:
        raise NotFoundError(f"{key}/{note_id}")
    body = await call(repo.note_text, pkey, note_id) if row["has_text"] else None
    item = _note_row(row)
    return LegacyNote(
        id=item.id,
        date=item.date,
        time=item.time,
        provider=item.provider,
        facility=item.facility,
        text=(body or {}).get("text") or None,
    )
