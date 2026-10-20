"""View models for the separate "Pre-2010 records" section (DMZ legacy chart)."""

from pydantic import BaseModel

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


class LegacyNotePage(BaseModel):
    rows: list[LegacyNoteRow]
    pager: Pager
    years: list[str]
    year: str
    total_all: int
    first_date: str
    last_date: str

    def params(self, **override: object) -> dict[str, object]:
        values: dict[str, object] = {"year": self.year, "page": self.pager.page}
        values.update(override)
        return {k: v for k, v in values.items() if v not in (None, "")}


class LegacyNote(BaseModel):
    id: int
    date: str
    time: str
    provider: str
    facility: str
    text: str | None
