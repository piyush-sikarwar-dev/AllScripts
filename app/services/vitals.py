"""Vitals tab."""

from app.crosswalk import PatientRef
from app.formatting import EMPTY, date_us
from app.models.chart import LabeledValue, VitalRow
from app.models.common import Pager, paginate
from app.repositories import source_repository
from app.services import call


def _num(value: object, unit: str = "") -> str:
    if value is None:
        return EMPTY
    return f"{value} {unit}".strip()


def _bp(v: dict) -> str:
    if v["systolic"] is None or v["diastolic"] is None:
        return EMPTY
    return f"{v['systolic']}/{v['diastolic']}"


def vital_row(v: dict) -> VitalRow:
    return VitalRow(
        date=date_us(v["date"]),
        bp=_bp(v),
        pulse=_num(v["pulse"]),
        temp=_num(v["temp"], v["temp_unit"]),
        weight=_num(v["weight"], v["weight_unit"]),
        height=_num(v["height"], v["height_unit"]),
        spo2=_num(v["spo2"], "%") if v["spo2"] is not None else EMPTY,
        pain=f"{v['pain']}/10" if v["pain"] is not None else EMPTY,
        source=v["source"],
    )


def vital_values(v: dict) -> list[LabeledValue]:
    """Compact label/value list for the visit detail panel."""
    row = vital_row(v)
    pairs = [
        ("BP", row.bp),
        ("Pulse", row.pulse),
        ("Temp", row.temp),
        ("Weight", row.weight),
        ("SpO2", row.spo2),
    ]
    return [LabeledValue(label=k, value=val) for k, val in pairs if val != EMPTY]


async def vitals_tab(ref: PatientRef, page: int | None) -> tuple[list[VitalRow], Pager]:
    rows = await call(source_repository().vitals, ref.emr_id)
    rows.sort(key=lambda v: (v["date"] is not None, v["date"]), reverse=True)
    page_rows, pager = paginate(rows, page or 1)
    return [vital_row(v) for v in page_rows], pager
