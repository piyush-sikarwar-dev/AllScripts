"""Patient crosswalk: one patient key → all source IDs.

Phase 0 resolves against the fake repository. Phase 3 replaces this with the `patient_crosswalk`
table (+ merge redirects and an LRU cache) keeping the same `resolve()` signature.
"""

from dataclasses import dataclass

from app.crosswalk.keys import parse_patient_key
from app.repositories import source_repository
from app.services import NotFoundError, call


@dataclass(frozen=True)
class PatientRef:
    patient_key: str
    emr_id: int | None
    ntier_id: int | None
    dmz_id: int | None
    match_method: str


async def resolve(patient_key: str) -> PatientRef:
    key = parse_patient_key(patient_key)
    if key is None or key.source != "EMR":
        # TODO(Phase 10): DMZ-only keys.
        raise NotFoundError(patient_key)
    patient = await call(source_repository().get_patient, key.id)
    if patient is None:
        raise NotFoundError(patient_key)
    return PatientRef(
        patient_key=str(key),
        emr_id=key.id,
        ntier_id=patient["ntier_id"],
        dmz_id=patient["dmz_id"],
        match_method="ExactId" if patient["ntier_id"] is not None else "None",
    )
