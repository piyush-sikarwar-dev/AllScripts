"""Patient details beyond the chart header: every insurance policy (EMR + PM), race, ethnicity,
marital status, emergency contacts / health-care proxy, guarantor, care team and consents.
Shown on the Overview and in the PDF's "Demographics & insurance" section."""

from datetime import date, datetime
from decimal import Decimal

from app.crosswalk import PatientRef
from app.formatting import EMPTY, date_us, or_dash, person_name, sort_key, to_clinic_time
from app.lookups import label
from app.models.patient_details import (
    CareTeamMember,
    ConsentItem,
    ContactPerson,
    Guarantor,
    InsurancePolicy,
    PatientDetails,
)
from app.repositories import source_repository
from app.services import NotFoundError, call

_RANKS = ["Primary", "Secondary", "Tertiary"]
_PM_ORDER = {"P": 0, "S": 1, "T": 2}


def _text(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _join(*parts: str, sep: str = " · ") -> str:
    return sep.join(p for p in parts if p and p != EMPTY)


def _day(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return (to_clinic_time(value) if value.tzinfo else value).date()
    return value


def _address(street: object, city: object, state: object, zip_code: object) -> str:
    state_zip = _join(_text(state), _text(zip_code), sep=" ")
    city_line = _join(_text(city), state_zip, sep=", ")
    return _join(_text(street), city_line, sep=", ") or EMPTY


def _join_labels(kind: str, codes: list[object]) -> str:
    labels = [label(kind, c) for c in codes]
    return ", ".join(dict.fromkeys(x for x in labels if x and x != EMPTY)) or EMPTY


def _rank_label(rank: object) -> str:
    if rank is None:
        return EMPTY
    r = int(rank)
    return _RANKS[r] if 0 <= r < len(_RANKS) else f"Additional ({r + 1})"


def _holder(last: object, first: object, middle: object, dob: object) -> str:
    name = person_name(last, first, middle)  # type: ignore[arg-type]
    born = _day(dob)  # type: ignore[arg-type]
    return f"{name} (DOB {date_us(born)})" if born and name != EMPTY else name


def _emr_policy(r: dict) -> InsurancePolicy:
    plan = _join(label("plan_type", r.get("plan_type")), _text(r.get("plan_number")))
    if r.get("workers_comp"):
        plan = _join(plan, "Worker's comp")
    return InsurancePolicy(
        source="EMR",
        order=_rank_label(r.get("rank")),
        carrier=or_dash(_text(r.get("carrier"))),
        carrier_phone=or_dash(_text(r.get("carrier_phone"))),
        plan=plan or EMPTY,
        group=or_dash(_text(r.get("group_number"))),
        member_id=or_dash(_text(r.get("member_id"))),
        holder=_holder(
            r.get("subscriber_last"),
            r.get("subscriber_first"),
            r.get("subscriber_middle"),
            r.get("subscriber_dob"),
        ),
        relationship=label("relation", r.get("relation_code")),
        effective=date_us(_day(r.get("effective_date"))),
        ends=date_us(_day(r.get("termination_date"))),
        archived=bool(r.get("archived")),
    )


def _money(value: object) -> str:
    if value is None:
        return ""
    amount = Decimal(str(value))
    return f"${amount:,.2f}" if amount else ""


def _pm_policy(r: dict) -> InsurancePolicy:
    relationship = _text(r.get("relationship"))
    copay = _money(r.get("copay"))
    copay_text = f"Copay {copay}" if copay else ""
    plan = _join(_text(r.get("plan_name")), _text(r.get("group_name")), copay_text)
    return InsurancePolicy(
        source="PM",
        order=label("pm_coverage", _text(r.get("coverage"))),
        carrier=or_dash(_text(r.get("carrier"))),
        carrier_phone=or_dash(_text(r.get("carrier_phone"))),
        plan=plan or EMPTY,
        group=or_dash(_text(r.get("group_number"))),
        member_id=or_dash(_text(r.get("certificate_number"))),
        holder=_holder(
            r.get("holder_last"), r.get("holder_first"), r.get("holder_middle"), r.get("holder_dob")
        ),
        # Blank = the patient holds the policy (config/lookups_fallback.yaml pm_relationship).
        relationship="Self" if not relationship else label("pm_relationship", relationship),
        effective=date_us(_day(r.get("effective_date"))),
        ends=date_us(_day(r.get("expiration_date"))),
        archived=False,
    )


def _emr_order(r: dict) -> tuple:
    return (bool(r.get("archived")), r.get("rank") or 0, r.get("policy_id") or 0)


def _pm_order(r: dict) -> tuple:
    started = sort_key(r.get("effective_date"))
    return (_PM_ORDER.get(_text(r.get("coverage")), 9), -started.toordinal())


def _policies(details: dict, show_archived: bool) -> tuple[list[InsurancePolicy], int]:
    emr = sorted(details.get("insurances") or [], key=_emr_order)
    pm = sorted(details.get("pm_policies") or [], key=_pm_order)
    archived = sum(1 for r in emr if r.get("archived"))
    shown = [_emr_policy(r) for r in emr if show_archived or not r.get("archived")]
    return shown + [_pm_policy(r) for r in pm], archived


def _contact(r: dict) -> ContactPerson:
    roles = []
    if r.get("emergency"):
        roles.append("Emergency contact")
    if r.get("proxy"):
        roles.append("Health-care proxy")
    phones = dict.fromkeys(x for x in (_text(r.get("phone")), _text(r.get("mobile"))) if x)
    return ContactPerson(
        name=person_name(r.get("last_name"), r.get("first_name"), (r.get("middle_name") or "")[:1]),
        relationship=or_dash(_text(r.get("relationship"))),
        roles=roles,
        phone=" / ".join(phones) or EMPTY,
        address=_address(r.get("address"), r.get("city"), r.get("state"), r.get("zip")),
        email=or_dash(_text(r.get("email"))),
    )


def _guarantor(p: dict) -> Guarantor | None:
    name = person_name(p.get("guarantor_last"), p.get("guarantor_first"), p.get("guarantor_middle"))
    if name == EMPTY:
        return None
    return Guarantor(
        name=_join(name, _text(p.get("guarantor_suffix")), sep=" "),
        relationship=label("relation", p.get("guarantor_relation")),
        dob=date_us(_day(p.get("guarantor_dob"))),
        phone=or_dash(_text(p.get("guarantor_phone"))),
        address=_address(
            p.get("guarantor_address"),
            p.get("guarantor_city"),
            p.get("guarantor_state"),
            p.get("guarantor_zip"),
        ),
    )


def _care_member(r: dict) -> CareTeamMember:
    name = person_name(r.get("provider_last"), r.get("provider_first"))
    title = _text(r.get("provider_title"))
    return CareTeamMember(
        role=label("care_role", r.get("role_code")),
        name=f"{name}, {title}" if title and name != EMPTY else name,
        since=date_us(_day(r.get("added_at"))),
    )


def _consent(r: dict) -> ConsentItem:
    return ConsentItem(
        name=label("consent", r.get("consent_code")),
        answer=label("consent_answer", r.get("answer_code")),
        recorded=date_us(_day(r.get("recorded_at"))),
        expires=date_us(_day(r.get("expires"))),
    )


def _care_order(r: dict) -> tuple:
    return (r.get("role_code") or 99, sort_key(r.get("added_at")))


def _contact_order(r: dict) -> tuple:
    return (r.get("rank") or 0, r.get("contact_id") or 0)


async def patient_details(ref: PatientRef, show_archived: bool = False) -> PatientDetails:
    d = await call(source_repository().patient_details, ref.emr_id, ref.ntier_id)
    policies, archived = _policies(d, show_archived)
    profile = d.get("profile") or {}
    consents = sorted(
        d.get("consents") or [], key=lambda r: sort_key(r.get("recorded_at")), reverse=True
    )
    return PatientDetails(
        insurances=policies,
        archived_count=archived,
        show_archived=show_archived,
        race=_join_labels("race", d.get("race") or []),
        ethnicity=_join_labels("ethnicity", d.get("ethnicity") or []),
        marital_status=label("marital_status", profile.get("marital_status")),
        contacts=[_contact(r) for r in sorted(d.get("contacts") or [], key=_contact_order)],
        guarantor=_guarantor(profile),
        care_team=[_care_member(r) for r in sorted(d.get("care_team") or [], key=_care_order)],
        consents=[_consent(r) for r in consents],
        has_photo=bool(profile.get("has_photo")),
    )


async def patient_photo(ref: PatientRef) -> bytes:
    """The patient's photo; only JPEG / PNG bytes are served."""
    data = await call(source_repository().patient_photo, ref.emr_id)
    if not data or not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG")):
        raise NotFoundError(f"{ref.patient_key}/photo")
    return data
