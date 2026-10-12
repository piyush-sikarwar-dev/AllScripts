"""Crosswalk lookups in the app database (no source-database access)."""

from sqlalchemy import select

from app.db.app import new_session
from app.repositories.appdb.models import PatientCrosswalk


def links_for_emr_ids(emr_ids: list[int]) -> dict[int, tuple[int | None, int | None]]:
    """emr_id → (ntier_id, dmz_id) for the given patients' own crosswalk rows."""
    if not emr_ids:
        return {}
    keys = [f"EMR:{i}" for i in emr_ids]
    with new_session() as db:
        rows = db.execute(
            select(PatientCrosswalk.emr_id, PatientCrosswalk.ntier_id, PatientCrosswalk.dmz_id)
            .where(PatientCrosswalk.patient_key.in_(keys))
            .where(PatientCrosswalk.match_method != "Merged")
        ).all()
    return {r.emr_id: (r.ntier_id, r.dmz_id) for r in rows}
