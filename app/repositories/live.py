"""Real data source (USE_FAKE_DATA=false): same function names and shapes as tests/fakes/repository.

Implemented so far: dashboard totals and the patient list. Chart areas raise
NotConnectedError until their phase wires them, which renders a friendly page.
"""

import time
from datetime import date
from typing import Any

from app.repositories import emr
from app.repositories.appdb.crosswalk import links_for_emr_ids

TOTALS_TTL_SECONDS = 24 * 3600
_totals_cache: tuple[float, dict[str, int]] | None = None


class NotConnectedError(Exception):
    """This chart area is not yet wired to the source databases."""


def totals() -> dict[str, int]:
    """Catalog row counts (sys.partitions): no table data is read. Cached 24 h."""
    global _totals_cache
    now = time.monotonic()
    if _totals_cache and _totals_cache[0] > now:
        return _totals_cache[1]
    value = {
        "patients": emr.table_row_count("HPSITE", "DEMOGRAPHICS"),
        "encounters": emr.table_row_count("HPSITE", "ENCOUNTER"),
        "lab_results": emr.table_row_count("HPSITE", "LAB_RESULT"),
        "scanned_documents": emr.table_row_count("HPSITE", "SCAN_DOCUMENT"),
    }
    _totals_cache = (now + TOTALS_TTL_SECONDS, value)
    return value


def search_patients(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    rows = emr.patient_search(
        last_name=last_name,
        first_name=first_name,
        dob=dob,
        chart_id=chart_id,
        offset=offset,
        limit=limit,
    )
    total = int(rows[0]["total_count"]) if rows else 0
    ids = [int(r["emr_id"]) for r in rows]
    links = links_for_emr_ids(ids)
    mrns = emr.mrns(ids)
    result = []
    for r in rows:
        emr_id = int(r["emr_id"])
        ntier_id, dmz_id = links.get(emr_id, (None, None))
        result.append(
            {
                "emr_id": emr_id,
                "last_name": r["last_name"],
                "first_name": r["first_name"],
                "middle_initial": r["middle_initial"],
                "dob": r["dob"],
                "dob_mask": r["dob_mask"],
                "sex": r["sex_code"],
                "chart_id": mrns.get(emr_id),
                "deceased": bool(r["deceased"]),
                "ntier_id": ntier_id,
                "dmz_id": dmz_id,
            }
        )
    return result, total


def last_visits(emr_ids: list[int]) -> dict[int, Any]:
    return emr.last_visits(emr_ids)


def _not_connected(*_args: object, **_kwargs: object) -> Any:
    raise NotConnectedError


# Chart areas: wired in Phases 5–8.
get_patient = visits = visit = visit_vitals = notes = history = _not_connected
medications = labs = vitals = documents = _not_connected
