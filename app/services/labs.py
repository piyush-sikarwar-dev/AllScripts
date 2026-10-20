"""Lab results tab: list and single-test trend."""

from datetime import date, datetime

from app.crosswalk import PatientRef
from app.formatting import EMPTY, date_us, or_dash, person_name, to_clinic_time
from app.lookups import label
from app.models.chart import LabFilters, LabOrderRow, LabRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call
from app.services.patients import parse_dob as parse_us_date

LAB_VIEWS = ("list", "trend", "orders")
# LABORDERS.LABORDER_COMPLETIONSTATUS (ORDCOMP dictionary): 1 Ordered, 2 Preliminary, 5 Pending are
# open (18,408 orders); 6 Canceled (8,806); 3 Final / 4 Reviewed = resulted; 7 Erroneous hidden.
ORDER_OPEN, ORDER_CANCELED, ORDER_ERRONEOUS = {1, 2, 5}, {6}, {7}
ORDER_FILTERS = ("open", "canceled", "all")


def _num(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _day(value: object) -> date | None:
    return value.date() if isinstance(value, datetime) else value  # type: ignore[return-value]


def lab_row(r: dict) -> LabRow:
    if "result_text" in r:  # real data: values and ranges are free text
        return LabRow(
            date=date_us(r["date"]),
            test=r["test"],
            result=f"{r['result_text']} {r['units']}".strip() or "—",
            reference_range=r["range_text"] or "—",
            flag=r["flag"],
            source=r["source"],
        )
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
    date_from: str = "", date_to: str = "", test: str = "", view: str = "", status: str = ""
) -> LabFilters:
    filters = LabFilters(
        date_from=date_from.strip()[:10],
        date_to=date_to.strip()[:10],
        test=test.strip()[:100],
        view=view if view in LAB_VIEWS else "list",
        status=status if status in ORDER_FILTERS else "open",
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
            if (start is None or (_day(r["date"]) is not None and _day(r["date"]) >= start))
            and (end is None or (_day(r["date"]) is not None and _day(r["date"]) <= end))
            and (not filters.test or r["test"] == filters.test)
        ]
    rows.sort(key=lambda r: (_day(r["date"]) or date.min, r["test"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return [lab_row(r) for r in page_rows], pager, test_names


def _local_day(value: datetime | date | None) -> date | None:
    if isinstance(value, datetime):
        return (to_clinic_time(value) if value.tzinfo else value).date()
    return value


def order_group(status_code: object) -> str:
    code = int(status_code) if status_code is not None else None
    if code in ORDER_OPEN:
        return "open"
    if code in ORDER_CANCELED:
        return "canceled"
    return "resulted"


def lab_order_row(r: dict) -> LabOrderRow:
    name = person_name(r.get("provider_last"), r.get("provider_first"))
    title = (r.get("provider_title") or "").strip()
    dx = " ".join(x for x in ((r.get("diagnosis_code") or "").strip(),
                              (r.get("diagnosis") or "").strip()) if x)  # fmt: skip
    test = (r.get("test") or "").strip() or (r.get("catalog_name") or "").strip()
    return LabOrderRow(
        ordered=date_us(_local_day(r.get("ordered_at"))),
        test=test or EMPTY,
        status=label("lab_status", r.get("status_code")),
        status_group=order_group(r.get("status_code")),
        provider=f"{name}, {title}" if title and name != EMPTY else name,
        diagnosis=dx or EMPTY,
        reported=date_us(_local_day(r.get("reported_at"))),
        comment=or_dash((r.get("comment") or "").strip()),
    )


def _in_dates(r: dict, start: date | None, end: date | None) -> bool:
    day = _local_day(r.get("ordered_at"))
    return (start is None or (day is not None and day >= start)) and (
        end is None or (day is not None and day <= end)
    )


async def lab_orders(ref: PatientRef) -> list[dict]:
    """Every lab order except erroneous entries, newest first."""
    rows = await call(source_repository().lab_orders, ref.emr_id)
    return [r for r in rows if r.get("status_code") not in ORDER_ERRONEOUS]


async def lab_orders_tab(
    ref: PatientRef, page: int | None, filters: LabFilters
) -> tuple[list[LabOrderRow], Pager, dict[str, int]]:
    """Orders view: open (never resulted yet), canceled, or all orders, with a count per filter."""
    rows = await lab_orders(ref)
    if not filters.errors:
        start, end = parse_us_date(filters.date_from), parse_us_date(filters.date_to)
        rows = [r for r in rows if _in_dates(r, start, end)]
    counts = {"open": 0, "canceled": 0, "all": len(rows)}
    for r in rows:
        group = order_group(r.get("status_code"))
        if group in counts:
            counts[group] += 1
    if filters.status != "all":
        rows = [r for r in rows if order_group(r.get("status_code")) == filters.status]
    page_rows, pager = paginate(rows, page or 1)
    return [lab_order_row(r) for r in page_rows], pager, counts
