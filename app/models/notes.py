"""View models for the Notes tab (Option A: type tiles + date range)."""

from datetime import date

from pydantic import BaseModel

from app.models.common import Pager, SourceLabel


class NotesState(BaseModel):
    """Everything the Notes tab's URL carries."""

    cat: str = "all"  # all | rx | visit | lab | letter
    range: str = "all"  # 12m | 3y | all | custom
    date_from: date | None = None
    date_to: date | None = None
    q: str = ""
    sort: str = "new"  # new | old
    page: int = 1
    note: str | None = None  # "document-123" | "transcription-9"
    view: str = "formatted"  # formatted | original

    def params(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "tab": "notes",
            "cat": self.cat,
            "range": self.range,
            "from": self.date_from.isoformat() if self.date_from else None,
            "to": self.date_to.isoformat() if self.date_to else None,
            "q": self.q,
            "sort": self.sort,
            "page": self.page,
            "note": self.note,
            "view": self.view,
        } | overrides
        # Dates only matter for a custom range; defaults are left out to keep URLs short.
        if values.get("range") != "custom":
            values["from"] = values["to"] = None
        for key, default in (("cat", "all"), ("range", "all"), ("sort", "new"),
                             ("view", "formatted")):  # fmt: skip
            if values.get(key) == default:
                values[key] = None
        return values


class TypeTile(BaseModel):
    key: str
    label: str
    count: int
    selected: bool


class RangeChip(BaseModel):
    key: str
    label: str
    selected: bool


class NoteFilters(BaseModel):
    tiles: list[TypeTile]
    chips: list[RangeChip]
    date_from: date  # the range actually applied (ISO for <input type=date>)
    date_to: date


class NoteRow(BaseModel):
    ref: str  # "document-123"
    date: str
    who: str
    category: str
    badge: str
    title: str
    subtitle: str


class NoteListPage(BaseModel):
    rows: list[NoteRow]
    pager: Pager
    context: str  # "Prescriptions · 01/01/2019 – 10/13/2026 · showing 25 of 118"


class NoteField(BaseModel):
    label: str
    value: str
    strong: bool = False


class NoteDetail(BaseModel):
    ref: str
    category: str
    badge: str
    title: str
    meta: str  # "06/03/2020 · Dr. M. Rivera · Clinical Module · EMR"
    source: SourceLabel
    view: str  # formatted | original (after any automatic fallback)
    fields: list[NoteField] = []  # formatted: label/value rows
    formatted_html: str | None = None  # formatted: sanitised document when it has no rows
    formatted_text: list[str] = []  # formatted: paragraphs of a plain-text note
    format_failed: bool = False  # "Couldn't format this note — showing the original."
    original_html: str | None = None  # sanitised (nh3)
    original_text: str | None = None  # shown escaped, pre-wrapped
    encounter_id: int | None = None
    in_export: bool = False
    attachment_name: str | None = None  # portal message with a downloadable attachment

    @property
    def has_content(self) -> bool:
        return bool(self.original_html or self.original_text or self.fields)
