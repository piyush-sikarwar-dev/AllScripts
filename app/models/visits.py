"""View models for the Visits tab (Option C: activity strip + structured note)."""

from pydantic import BaseModel

from app.models.chart import DocumentLink
from app.models.common import Pager, SourceLabel


class VisitsState(BaseModel):
    """Everything the Visits tab's URL carries."""

    type: str = "office"  # office | all | phone | lab | annual
    year: int | None = None
    q: str = ""
    page: int = 1
    visit: int | None = None
    view: str = "structured"  # structured | original

    def params(self, **overrides: object) -> dict[str, object]:
        values = {
            "tab": "visits",
            "type": self.type,
            "year": self.year,
            "q": self.q,
            "page": self.page,
            "visit": self.visit,
            "view": self.view,
        } | overrides
        if values.get("type") == "office":
            values["type"] = None  # default, keep URLs short
        if values.get("view") == "structured":
            values["view"] = None
        return values


class YearBar(BaseModel):
    year: int
    count: int
    height: int  # px of the 70px bar area
    y: int  # 70 - height (SVG rect y attribute)
    selected: bool
    bar_class: str  # bar | bar bar--on | bar bar--dim


class VisitActivity(BaseModel):
    total: int
    last_visit: str
    top_provider: str
    top_diagnosis: str
    years: list[YearBar]
    selected_year: int | None


class VisitRow(BaseModel):
    id: int
    date: str
    type: str
    diagnoses: str
    provider_short: str


class VisitListPage(BaseModel):
    rows: list[VisitRow]
    pager: Pager
    context: str  # "All years · 123 visits"


class NoteSectionRow(BaseModel):
    """One labelled row of the Structured view."""

    label: str
    kind: str  # text | html | dx | list | links
    paragraphs: list[str] = []
    dx: list[tuple[str, str]] = []  # (code, title)
    items: list[str] = []
    html: str | None = None  # sanitised (nh3) only
    caption: str | None = None
    links: list[DocumentLink] = []


class OriginalBlock(BaseModel):
    title: str
    text: str | None = None  # shown escaped, pre-wrapped (never rendered as HTML)
    html: str | None = None  # sanitised clinical document (nh3)


class EncounterDetail(BaseModel):
    id: int
    title: str  # "12/20/2019 · Office visit"
    subline: str  # "Provider · Location · Signed"
    source: SourceLabel
    view: str
    rows: list[NoteSectionRow]
    original: list[OriginalBlock]
    in_export: bool = False
