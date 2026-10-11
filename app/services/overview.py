"""Overview tab: active problems, allergies, current medications, last visit."""

import asyncio

from app.crosswalk import PatientRef
from app.formatting import date_us, or_dash, partial_date
from app.models.chart import LastVisit, Overview, OverviewItem
from app.repositories import source_repository
from app.services import call
from app.services.meds import medication_items
from app.services.problems import history_items

MAX_ITEMS = 8


async def _last_visit(ref: PatientRef) -> LastVisit | None:
    visits = await call(source_repository().visits, ref.emr_id)
    if not visits:
        return None
    v = max(visits, key=lambda v: v["start"])
    return LastVisit(
        date=date_us(v["start"]),
        type=or_dash(v["visit_type"]),
        provider=or_dash(v["provider"]),
        location=or_dash(v["location"]),
    )


async def overview(ref: PatientRef) -> Overview:
    history, meds, last_visit = await asyncio.gather(
        history_items(ref), medication_items(ref, active_only=True), _last_visit(ref)
    )
    problems = [h for h in history if h["group"] == "problem" and h["resolved"] is None]
    allergies = [h for h in history if h["group"] == "allergy"]
    return Overview(
        problems=[
            OverviewItem(
                name=h["title"], detail=f"Onset {partial_date(h['onset'], h['onset_precision'])}"
            )
            for h in problems[:MAX_ITEMS]
        ],
        allergies=[
            OverviewItem(name=h["title"], detail=or_dash(h["reaction"]))
            for h in allergies[:MAX_ITEMS]
        ],
        medications=[
            OverviewItem(name=m["name"], detail=or_dash(m["sig"])) for m in meds[:MAX_ITEMS]
        ],
        last_visit=last_visit,
    )
