"""Lab results tab: list and single-test trend."""

from app.crosswalk import PatientRef
from app.formatting import date_us
from app.models.chart import LabFilters, LabRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call
from app.services.patients import parse_dob as parse_us_date

LAB_VIEWS = ("list", "trend")


def _num(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def lab_row(r: dict) -> LabRow:
    dec = r["decimals"]
    units = r["units"] or ""
    if r["low"] is None and r["high"] is None:
        ref_range = "—"
    elif not r["low"]:
        ref_range = f"< {_num(r['high'], dec)} {units}".strip()
    else:
        ref_range = f"{_num(r['low'], dec)}–{_num(r['high'], dec)} {units}".strip()
    return LabRow(
        date=date_us(r["date"]),
        test=r["test"],
        result=f"{_num(r['value'], dec)} {units}".strip(),
        reference_range=ref_range,
        flag=r["flag"],
        source=r["source"],
    )


def build_filters(
    date_from: str = "", date_to: str = "", test: str = "", view: str = ""
) -> LabFilters:
    filters = LabFilters(
        date_from=date_from.strip()[:10],
        date_to=date_to.strip()[:10],
        test=test.strip()[:100],
        view=view if view in LAB_VIEWS else "list",
    )
    for field in ("date_from", "date_to"):
        try:
            parse_us_date(getattr(filters, field))
        except ValueError:
            filters.errors[field] = "Enter the date as MM/DD/YYYY."
    return filters


async def labs_tab(
    ref: PatientRef, page: int | None, filters: LabFilters
) -> tuple[list[LabRow], Pager, list[str]]:
    """Rows for the current page, the pager, and every test name (for the test select)."""
    rows = await call(source_repository().labs, ref.emr_id)
    test_names = sorted({r["test"] for r in rows})
    if filters.view == "trend" and not filters.test and test_names:
        filters.test = test_names[0]
    if not filters.errors:
        start = parse_us_date(filters.date_from)
        end = parse_us_date(filters.date_to)
        rows = [
            r
            for r in rows
            if (start is None or r["date"].date() >= start)
            and (end is None or r["date"].date() <= end)
            and (not filters.test or r["test"] == filters.test)
        ]
    rows.sort(key=lambda r: (r["date"], r["test"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return [lab_row(r) for r in page_rows], pager, test_names
