"""View models for the patient details shown on the Overview and in the PDF: insurance, race and
ethnicity, emergency contacts / health-care proxy, guarantor, care team, consents."""

from pydantic import BaseModel

from app.models.common import SourceLabel


class InsurancePolicy(BaseModel):
    source: SourceLabel
    order: str
    carrier: str
    carrier_phone: str
    plan: str
    group: str
    member_id: str
    holder: str
    relationship: str
    effective: str
    ends: str
    archived: bool


class ContactPerson(BaseModel):
    name: str
    relationship: str
    roles: list[str]
    phone: str
    address: str
    email: str


class Guarantor(BaseModel):
    name: str
    relationship: str
    dob: str
    phone: str
    address: str


class CareTeamMember(BaseModel):
    role: str
    name: str
    since: str


class ConsentItem(BaseModel):
    name: str
    answer: str
    recorded: str
    expires: str


class PatientDetails(BaseModel):
    insurances: list[InsurancePolicy]
    archived_count: int
    show_archived: bool
    race: str
    ethnicity: str
    marital_status: str
    contacts: list[ContactPerson]
    guarantor: Guarantor | None
    care_team: list[CareTeamMember]
    consents: list[ConsentItem]
    has_photo: bool
