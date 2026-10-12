"""Patient crosswalk: one patient key → all source IDs.

Real mode reads the `patient_crosswalk` table (built by `cli.py build-crosswalk`) with a
10-minute in-memory cache. Fake mode resolves against the fake repository.
Merged-away EMR patients resolve to the surviving record: `PatientRef.patient_key` is then the
survivor's key, and callers redirect to it.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass

from app.config import get_settings
from app.crosswalk.keys import parse_patient_key
from app.db.app import new_session
from app.repositories import source_repository
from app.repositories.appdb.models import PatientCrosswalk
from app.services import NotFoundError, call

CACHE_TTL_SECONDS = 600
CACHE_MAX = 2048


@dataclass(frozen=True)
class PatientRef:
    patient_key: str  # canonical key (the survivor's, for merged-away patients)
    emr_id: int | None
    ntier_id: int | None
    dmz_id: int | None
    match_method: str


_cache: OrderedDict[str, tuple[float, PatientRef | None]] = OrderedDict()


def clear_cache() -> None:
    _cache.clear()


def _lookup_table(patient_key: str) -> PatientRef | None:
    with new_session() as db:
        row = db.get(PatientCrosswalk, patient_key)
        if row is None:
            return None
        canonical = patient_key
        if row.match_method == "Merged" and row.emr_id is not None:
            canonical = f"EMR:{row.emr_id}"
            survivor = db.get(PatientCrosswalk, canonical)
            if survivor is not None:
                row = survivor
        return PatientRef(
            patient_key=canonical,
            emr_id=row.emr_id,
            ntier_id=row.ntier_id,
            dmz_id=row.dmz_id,
            match_method=row.match_method,
        )


async def _resolve_fake(patient_key: str, source: str, source_id: int) -> PatientRef | None:
    if source != "EMR":
        return None
    patient = await call(source_repository().get_patient, source_id)
    if patient is None:
        return None
    return PatientRef(
        patient_key=patient_key,
        emr_id=source_id,
        ntier_id=patient["ntier_id"],
        dmz_id=patient["dmz_id"],
        match_method="ExactId" if patient["ntier_id"] is not None else "None",
    )


async def resolve(patient_key: str) -> PatientRef:
    key = parse_patient_key(patient_key)
    if key is None:
        raise NotFoundError(patient_key)
    canonical = str(key)

    if get_settings().use_fake_data:
        ref = await _resolve_fake(canonical, key.source, key.id)
    else:
        now = time.monotonic()
        cached = _cache.get(canonical)
        if cached and cached[0] > now:
            _cache.move_to_end(canonical)
            ref = cached[1]
        else:
            ref = await call(_lookup_table, canonical)
            _cache[canonical] = (now + CACHE_TTL_SECONDS, ref)
            while len(_cache) > CACHE_MAX:
                _cache.popitem(last=False)
    if ref is None:
        raise NotFoundError(patient_key)
    return ref
