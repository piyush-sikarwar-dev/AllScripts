"""Dashboard totals and patient search."""

import re
from datetime import date, datetime

from app.config import get_settings
from app.formatting import date_us, person_name
from app.lookups import label
from app.models.common import PAGE_SIZE, Pager, SourceLabel, clamp_page
from app.models.patients import DashboardTotals, PatientPage, PatientRow, PatientSearch
from app.repositories import source_repository
from app.services import call

_DOB_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def record_sources(ntier_id: int | None, dmz_id: int | None) -> list[SourceLabel]:
    """'Records in' badges: EMR always, PM when linked, Pre-2010 when linked and enabled."""
    sources: list[SourceLabel] = ["EMR"]
    if ntier_id is not None:
        sources.append("PM")
    settings = get_settings()
    if dmz_id is not None and (settings.feature_legacy_dmz or settings.use_fake_data):
        sources.append("Pre-2010")
    return sources


def parse_name_query(q: str) -> tuple[str | None, str | None]:
    """Accept 'Last', 'Last, First' or 'Last First' → (last, first)."""
    q = " ".join(q.split())
    if not q:
        return None, None
    if "," in q:
        last, _, first = q.partition(",")
    else:
        last, _, first = q.partition(" ")
    return last.strip() or None, first.strip() or None


def parse_dob(raw: str) -> date | None:
    """Parse MM/DD/YYYY (or ISO). Raises ValueError on a bad format."""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(raw)


def build_search(q: str = "", dob: str = "", chart: str = "") -> PatientSearch:
    search = PatientSearch(q=q.strip()[:100], dob=dob.strip()[:10], chart=chart.strip()[:20])
    if search.dob:
        try:
            parse_dob(search.dob)
        except ValueError:
            search.errors["dob"] = "Enter the date of birth as MM/DD/YYYY."
    if search.chart and not re.fullmatch(r"[A-Za-z0-9-]+", search.chart):
        search.errors["chart"] = "Chart ID can contain only letters, numbers and dashes."
    return search


async def dashboard_totals() -> DashboardTotals:
    repo = source_repository()
    return DashboardTotals(**await call(repo.totals))


async def search_patients(search: PatientSearch, page: int | None) -> PatientPage:
    repo = source_repository()
    total_patients = (await call(repo.totals))["patients"]
    page = clamp_page(page)
    if search.errors:
        return PatientPage(
            search=search,
            rows=[],
            pager=Pager(page=1, total=0),
            total_patients=total_patients,
        )
    last, first = parse_name_query(search.q)
    rows, total = await call(
        repo.search_patients,
        last_name=last,
        first_name=first,
        dob=parse_dob(search.dob),
        chart_id=search.chart or None,
        offset=(page - 1) * PAGE_SIZE,
        limit=PAGE_SIZE,
    )
    last_visits = await call(repo.last_visits, [r["emr_id"] for r in rows]) if rows else {}
    return PatientPage(
        search=search,
        rows=[
            PatientRow(
                key=f"EMR:{r['emr_id']}",
                name=person_name(r["last_name"], r["first_name"], r["middle_initial"]),
                dob=date_us(r["dob"]),
                sex=label("sex", r["sex"]),
                chart_id=r["chart_id"] or "—",
                last_visit=date_us(last_visits.get(r["emr_id"])),
                sources=record_sources(r["ntier_id"], r["dmz_id"]),
            )
            for r in rows
        ],
        pager=Pager(page=page, total=total),
        total_patients=total_patients,
    )
