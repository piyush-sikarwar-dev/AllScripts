"""View models for the patient chart (header + tabs)."""

from pydantic import BaseModel

from app.models.common import Pager, SourceLabel


class ChartHeader(BaseModel):
    key: str
    name: str
    initials: str
    sources: list[SourceLabel]
    dob: str
    age: int | None
    sex: str
    chart_id: str
    pm_account: str
    phone: str
    address: str
    primary_insurance: str
    deceased: bool = False


# --- Overview -----------------------------------------------------------------------------------


class OverviewItem(BaseModel):
    name: str
    detail: str


class LastVisit(BaseModel):
    date: str
    type: str
    provider: str
    location: str


class Overview(BaseModel):
    problems: list[OverviewItem]
    allergies: list[OverviewItem]
    medications: list[OverviewItem]
    last_visit: LastVisit | None


# --- Visits -------------------------------------------------------------------------------------


class VisitSummary(BaseModel):
    id: int
    source: SourceLabel
    date: str
    type: str
    provider: str
    location: str
    diagnoses: str
    signed: bool


class LabeledValue(BaseModel):
    label: str
    value: str


class DocumentLink(BaseModel):
    kind: str
    id: int
    title: str
    meta: str


class RenderedDocument(BaseModel):
    title: str
    meta: str
    # Sanitised HTML only (app.documents.render / nh3) — rendered with |safe.
    html: str


class VisitDetail(BaseModel):
    visit: VisitSummary
    assessment: list[LabeledValue]
    plan: list[str]
    vitals: list[LabeledValue]
    addenda: list[str]
    note_text: str | None
    documents: list[RenderedDocument] = []
    other_documents: list[DocumentLink] = []


class VisitList(BaseModel):
    visits: list[VisitSummary]
    pager: Pager
    filter: str  # "office" | "all"
    selected: VisitDetail | None


# --- Other tabs ---------------------------------------------------------------------------------


class NoteRow(BaseModel):
    kind: str
    id: int
    date: str
    title: str
    author: str
    source: SourceLabel


class NoteDetail(BaseModel):
    kind: str
    id: int
    title: str
    meta: str
    source: SourceLabel
    # Sanitised HTML only (app.documents.render / nh3) — rendered with |safe.
    html: str | None
    text: str | None


class ProblemRow(BaseModel):
    title: str
    detail: str | None = None  # e.g. allergy reaction
    code: str
    onset: str
    resolved: str
    status: str
    source: SourceLabel


class ProblemGroup(BaseModel):
    key: str
    label: str
    rows: list[ProblemRow]


class MedicationRow(BaseModel):
    name: str
    instructions: str
    start: str
    end: str
    status: str
    source: SourceLabel


class LabRow(BaseModel):
    date: str
    test: str
    result: str
    reference_range: str
    flag: str | None
    source: SourceLabel


class LabFilters(BaseModel):
    date_from: str = ""
    date_to: str = ""
    test: str = ""
    view: str = "list"  # "list" | "trend"
    errors: dict[str, str] = {}


class VitalRow(BaseModel):
    date: str
    bp: str
    pulse: str
    temp: str
    weight: str
    height: str
    spo2: str
    pain: str
    source: SourceLabel


class DocumentRow(BaseModel):
    id: int
    date: str
    type: str
    title: str
    pages: str
    source: SourceLabel
    viewable: bool
