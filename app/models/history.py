"""View models for the Problems & allergies tab (Option B: section rail + entry detail)."""

from pydantic import BaseModel

from app.models.common import SourceLabel


class HistoryState(BaseModel):
    """Everything the tab's URL carries (tab=problems)."""

    sec: str = "problems"  # problems | allergies | surgical | family | social | other
    status: str = "all"  # all | active
    entry: int | None = None

    def params(self, **overrides: object) -> dict[str, object]:
        return {"tab": "problems", "sec": self.sec, "status": self.status,
                "entry": self.entry} | overrides  # fmt: skip


class SectionSummary(BaseModel):
    key: str
    label: str
    count: int  # entries shown under the current status filter
    active_count: int
    pill: str | None = None  # Allergies: "2 active" | "NKA" | "None active"
    pill_kind: str = "neutral"  # alert | neutral
    selected: bool = False


class EntryRow(BaseModel):
    id: int
    title: str
    meta: str  # "Drug · Since 2012"
    status: str  # active | inactive | resolved | error | unknown
    status_label: str


class CodeView(BaseModel):
    standard: str | None = None  # "ICD-9 250.00"
    tags: list[str] = []  # internal references: "History 17354", "IMO 5678"


class EntryField(BaseModel):
    label: str
    value: str
    muted: bool = False  # "Not recorded"


class EntryDetail(BaseModel):
    id: int
    section: str
    section_label: str
    title: str
    status: str
    status_label: str
    fields: list[EntryField]
    code: CodeView
    comment: str | None = None
    recorded: str
    conflict: bool = False  # active NKA / NKDA next to active allergy entries
    source: SourceLabel = "EMR"
    in_export: bool = False


class ChangeLine(BaseModel):
    date: str
    text: str
