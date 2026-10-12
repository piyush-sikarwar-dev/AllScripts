"""In-memory stand-in for the source repositories (used when USE_FAKE_DATA=true and in unit tests).

Function names and return shapes are the contract the real `app/repositories/` modules implement
from Phase 4 on: plain dicts / lists of dicts with raw values.
"""

from datetime import date

from tests.fakes.data import PATIENTS, PATIENTS_BY_ID, FakePatient


def totals() -> dict[str, int]:
    return {
        "patients": len(PATIENTS),
        "encounters": sum(len(p.visits) for p in PATIENTS),
        "lab_results": sum(len(p.labs) for p in PATIENTS),
        "scanned_documents": sum(1 for p in PATIENTS for d in p.documents if d["kind"] == "scan"),
    }


def _summary(p: FakePatient) -> dict:
    return {
        "emr_id": p.emr_id,
        "last_name": p.last_name,
        "first_name": p.first_name,
        "middle_initial": p.middle_initial,
        "dob": p.dob,
        "sex": p.sex,
        "chart_id": p.chart_id,
        "deceased": p.deceased,
        "ntier_id": p.ntier_id,
        "dmz_id": p.dmz_id,
    }


def search_patients(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    def matches(p: FakePatient) -> bool:
        return (
            (last_name is None or p.last_name.lower().startswith(last_name.lower()))
            and (first_name is None or p.first_name.lower().startswith(first_name.lower()))
            and (dob is None or p.dob == dob)
            and (chart_id is None or p.chart_id == chart_id)
        )

    found = sorted(
        (p for p in PATIENTS if matches(p)), key=lambda p: (p.last_name, p.first_name, p.emr_id)
    )
    return [_summary(p) for p in found[offset : offset + limit]], len(found)


def last_visits(emr_ids: list[int]) -> dict[int, object]:
    result = {}
    for emr_id in emr_ids:
        visits = PATIENTS_BY_ID[emr_id].visits
        if visits:
            result[emr_id] = max(v["start"] for v in visits)
    return result


def get_patient(emr_id: int) -> dict | None:
    p = PATIENTS_BY_ID.get(emr_id)
    if p is None:
        return None
    return _summary(p) | {
        "phone": p.phone,
        "address": p.address,
        "city": p.city,
        "state": p.state,
        "zip": p.zip,
        "pm_account": p.pm_account,
        "primary_insurance": p.primary_insurance,
    }


def visits(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].visits)


def last_visit(emr_id: int) -> dict | None:
    visits = PATIENTS_BY_ID[emr_id].visits
    if not visits:
        return None
    v = max(visits, key=lambda v: v["start"])
    return {k: v[k] for k in ("start", "visit_type", "provider", "location")}


def visit(emr_id: int, contact_id: int) -> dict | None:
    return next((v for v in PATIENTS_BY_ID[emr_id].visits if v["contact_id"] == contact_id), None)


def visit_vitals(emr_id: int, contact_id: int) -> list[dict]:
    return [v for v in PATIENTS_BY_ID[emr_id].vitals if v["contact_id"] == contact_id]


def notes(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].notes)


def history(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].history)


def medications(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].medications)


def labs(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].labs)


def vitals(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].vitals)


def documents(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].documents)
