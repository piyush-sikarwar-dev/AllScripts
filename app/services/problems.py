"""Problems & allergies tab (HX_DIAGNOSIS grouped by history category)."""

from app.crosswalk import PatientRef
from app.formatting import EMPTY, date_us, partial_date
from app.models.chart import ProblemGroup, ProblemRow
from app.repositories import source_repository
from app.services import call

# Display order and labels. Phase 3 maps CATEGORY_CODE → group via config/history_categories.yaml.
GROUPS: list[tuple[str, str]] = [
    ("problem", "Problems"),
    ("allergy", "Allergies"),
    ("surgical", "Surgical history"),
    ("family", "Family history"),
    ("social", "Social history"),
    ("other", "Other history"),
]


def problem_row(h: dict) -> ProblemRow:
    code = " ".join(part for part in (h["code_system"], h["code"]) if part) or EMPTY
    return ProblemRow(
        title=h["title"],
        detail=h["reaction"],
        code=code,
        onset=partial_date(h["onset"], h["onset_precision"]),
        resolved=date_us(h["resolved"]),
        status=h["status"] or EMPTY,
        source=h["source"],
    )


async def history_items(ref: PatientRef) -> list[dict]:
    rows = await call(source_repository().history, ref.emr_id)
    known = {key for key, _ in GROUPS}
    for h in rows:
        if h["group"] not in known:
            h["group"] = "other"
    # Newest onset first; undated last.
    rows.sort(key=lambda h: (h["onset"] is not None, h["onset"]), reverse=True)
    return rows


async def problem_groups(ref: PatientRef) -> list[ProblemGroup]:
    rows = await history_items(ref)
    return [
        ProblemGroup(key=key, label=label, rows=[problem_row(h) for h in rows if h["group"] == key])
        for key, label in GROUPS
    ]
