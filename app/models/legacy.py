"""View models for the separate "Pre-2010 records" section (DMZ legacy chart)."""

from pydantic import BaseModel

from app.formatting import EMPTY
from app.models.common import Pager


class LegacySearch(BaseModel):
    """Echo of the legacy search form plus per-field validation errors."""

    q: str = ""
    dob: str = ""
    legacy_id: str = ""
    errors: dict[str, str] = {}

    @property
    def is_filtered(self) -> bool:
        return bool(self.q or self.dob or self.legacy_id)

    def params(self) -> dict[str, str]:
        return {"q": self.q, "dob": self.dob, "legacy_id": self.legacy_id}

    def fields_used(self) -> list[str]:
        """For the audit log: which fields were filled in — never their values."""
        return [name for name, value in (("name", self.q), ("dob", self.dob),
                                         ("legacy_id", self.legacy_id)) if value]  # fmt: skip


class LegacyRow(BaseModel):
    key: str
    name: str
    dob: str
    sex: str
    legacy_id: str


class LegacyPage(BaseModel):
    search: LegacySearch
    rows: list[LegacyRow]
    pager: Pager


class LegacyHeader(BaseModel):
    key: str
    name: str
    initials: str
    dob: str
    age: int | None
    sex: str
    legacy_id: str
    phone: str
    address: str
    deceased: bool


class LegacyNoteRow(BaseModel):
    id: int
    date: str
    time: str
    provider: str
    facility: str
    has_text: bool

    @property
    def byline(self) -> str:
        """'Provider · Facility' without the parts that were not recorded."""
        return " · ".join(x for x in (self.provider, self.facility) if x and x != EMPTY)


class LegacyNotePage(BaseModel):
    rows: list[LegacyNoteRow]
    pager: Pager
    years: list[str]
    year: str
    total_all: int
    first_date: str
    last_date: str

    def params(self, **override: object) -> dict[str, object]:
        values: dict[str, object] = {"tab": "notes", "year": self.year, "page": self.pager.page}
        values.update(override)
        return {k: v for k, v in values.items() if v not in (None, "")}


class LegacyNote(BaseModel):
    id: int
    date: str
    time: str
    provider: str
    facility: str
    text: str | None

    @property
    def byline(self) -> str:
        """'Provider · Facility' without the parts that were not recorded."""
        return " · ".join(x for x in (self.provider, self.facility) if x and x != EMPTY)


class LegacyProblem(BaseModel):
    id: int
    name: str
    code: str
    onset: str
    resolved: str
    status: str
    provider: str
    comment: str
    active: bool
    voided: bool


class LegacyAllergy(BaseModel):
    id: int
    allergen: str
    detail: str
    category: str
    reactions: str
    severity: str
    status: str
    noted: str
    provider: str
    comment: str
    active: bool
    voided: bool


class LegacyHistory(BaseModel):
    problems: list[LegacyProblem]
    allergies: list[LegacyAllergy]
    show_voided: bool
    voided_count: int


class LegacyMedEntry(BaseModel):
    date: str
    status: str
    sig: str
    quantity: str
    refills: str
    stopped: str
    provider: str


class LegacyMedication(BaseModel):
    id: int
    name: str
    sig: str
    reason: str
    comment: str
    started: str
    last_update: str
    stopped: str
    status: str
    provider: str
    quantity: str
    refills: str
    voided: bool
    entries: list[LegacyMedEntry]


class LegacyMedications(BaseModel):
    active: list[LegacyMedication]
    past: list[LegacyMedication]
    voided: list[LegacyMedication]
    show_voided: bool


class LegacyLabRow(BaseModel):
    date: str
    test: str
    result: str
    range: str
    flag: str | None
    comment: str
    note_id: int | None


class LegacyLabPage(BaseModel):
    rows: list[LegacyLabRow]
    pager: Pager
    tests: list[str]
    test: str
    years: list[str]
    year: str

    def params(self, **override: object) -> dict[str, object]:
        values: dict[str, object] = {"tab": "labs", "test": self.test, "year": self.year,
                                     "page": self.pager.page}  # fmt: skip
        values.update(override)
        return {k: v for k, v in values.items() if v not in (None, "")}


class LegacyVitalsRow(BaseModel):
    date: str
    time: str
    bp: str
    pulse: str
    temp: str
    resp: str
    weight: str
    height: str
    bmi: str
    waist: str
    note_id: int | None


class LegacyVitalsPage(BaseModel):
    rows: list[LegacyVitalsRow]
    pager: Pager


class LegacyDocRow(BaseModel):
    id: int
    date: str
    type: str
    pages: int
    file_type: str
    provider: str
    note_id: int | None


class LegacyDocViewer(BaseModel):
    id: int
    title: str
    meta: str
    page: int
    pages: int
    image_url: str | None
    note_id: int | None


class LegacyDocPage(BaseModel):
    rows: list[LegacyDocRow]
    pager: Pager
    types: list[str]
    type: str
    store_ready: bool
    viewer: LegacyDocViewer | None

    def params(self, **override: object) -> dict[str, object]:
        values: dict[str, object] = {"tab": "docs", "type": self.type, "page": self.pager.page}
        values.update(override)
        return {k: v for k, v in values.items() if v not in (None, "")}


class LegacyOverviewItem(BaseModel):
    name: str
    detail: str


class LegacyOverview(BaseModel):
    problems: list[LegacyOverviewItem]
    allergies: list[LegacyOverviewItem]
    medications: list[LegacyOverviewItem]
    last_note: LegacyNoteRow | None
    counts: dict[str, int]
