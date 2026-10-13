"""View models for the Appointments tab."""

from pydantic import BaseModel

from app.models.common import Pager


class AppointmentsState(BaseModel):
    status: str = "all"  # all | kept | cancelled | no_show | scheduled | other
    year: int | None = None
    page: int = 1

    def params(self, **overrides: object) -> dict[str, object]:
        values = {"status": self.status, "year": self.year, "page": self.page} | overrides
        if values.get("status") == "all":
            values["status"] = None
        return values


class AppointmentStat(BaseModel):
    label: str
    value: str
    caption: str = ""


class StatusChip(BaseModel):
    key: str
    label: str
    count: int
    selected: bool


class AppointmentRow(BaseModel):
    date: str
    time: str
    type: str
    provider: str
    location: str
    status: str  # filter group: kept | cancelled | no_show | scheduled | other
    status_label: str
    details: str  # "Arrived 9:24 AM · Left 10:42 AM" / "Reschedule" (cancellation reason)
    comment: str | None
    sources: list[str]


class AppointmentsPage(BaseModel):
    stats: list[AppointmentStat]
    chips: list[StatusChip]
    years: list[int]
    rows: list[AppointmentRow]
    pager: Pager
    context: str  # "All years · 34 appointments"
