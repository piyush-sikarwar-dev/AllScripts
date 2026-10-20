"""Patient chart header."""

from app.crosswalk import PatientRef
from app.formatting import EMPTY, age, initials, or_dash, partial_date_masked, person_name
from app.lookups import label
from app.models.chart import ChartHeader
from app.repositories import source_repository
from app.services import NotFoundError, call
from app.services.patients import record_sources


def _address(p: dict) -> str:
    street = (p.get("address") or "").strip()
    state_zip = " ".join(part for part in (p.get("state"), p.get("zip")) if part)
    city_line = ", ".join(part for part in (p.get("city"), state_zip) if part)
    if street and city_line:
        return f"{street}, {city_line}"
    return street or city_line or EMPTY


async def get_header(ref: PatientRef) -> ChartHeader:
    p = await call(source_repository().get_patient, ref.emr_id)
    if p is None:
        raise NotFoundError(ref.patient_key)
    return ChartHeader(
        key=ref.patient_key,
        name=person_name(p["last_name"], p["first_name"], p["middle_initial"]),
        initials=initials(p["last_name"], p["first_name"]),
        sources=record_sources(ref.ntier_id, ref.dmz_id),
        dob=partial_date_masked(p["dob"], p.get("dob_mask")),
        age=age(p["dob"]),
        sex=label("sex", p["sex"]),
        chart_id=or_dash(p["chart_id"]),
        pm_account=or_dash(p["pm_account"]),
        phone=or_dash(p["phone"]),
        address=_address(p),
        primary_insurance=or_dash(p["primary_insurance"]),
        deceased=bool(p["deceased"]),
        photo_url=f"/patients/{ref.patient_key}/photo" if p.get("has_photo") else None,
    )
