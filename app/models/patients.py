"""View models for the dashboard and patient list."""

from pydantic import BaseModel

from app.models.common import Pager, SourceLabel


class DashboardTotals(BaseModel):
    patients: int
    encounters: int
    lab_results: int
    scanned_documents: int


class PatientRow(BaseModel):
    key: str
    name: str
    dob: str
    sex: str
    chart_id: str
    last_visit: str
    sources: list[SourceLabel]


class PatientSearch(BaseModel):
    """Echo of the search form plus per-field validation errors."""

    q: str = ""
    dob: str = ""
    chart: str = ""
    errors: dict[str, str] = {}

    @property
    def is_filtered(self) -> bool:
        return bool(self.q or self.dob or self.chart)

    def params(self) -> dict[str, str]:
        return {"q": self.q, "dob": self.dob, "chart": self.chart}


class PatientPage(BaseModel):
    search: PatientSearch
    rows: list[PatientRow]
    pager: Pager
    total_patients: int
