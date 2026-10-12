"""Display formatting: US dates, partial dates, clinic-time datetimes, names, ages."""

import re
from datetime import date, datetime
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

from app.config import get_settings

DatePrecision = Literal["full", "month_year", "year"]

EMPTY = "—"


def date_us(value: date | datetime | None) -> str:
    """MM/DD/YYYY, or an em dash when missing."""
    if value is None:
        return EMPTY
    return value.strftime("%m/%d/%Y")


def partial_date(value: date | datetime | None, precision: DatePrecision = "full") -> str:
    """Format a date that may only be known to the month or year."""
    if value is None:
        return EMPTY
    if precision == "year":
        return value.strftime("%Y")
    if precision == "month_year":
        return value.strftime("%m/%Y")
    return date_us(value)


def partial_date_masked(value: date | datetime | None, mask: object) -> str:
    """Partial date using a source *DATEMASK value (decoded via config/date_masks.yaml)."""
    from app.lookups import get_lookups

    return partial_date(value, get_lookups().date_precision(mask))


@lru_cache
def clinic_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_tz)


def to_clinic_time(value: datetime) -> datetime:
    """Aware datetimes convert to CLINIC_TZ; naive ones are assumed to already be clinic time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=clinic_tz())
    return value.astimezone(clinic_tz())


def datetime_local(value: datetime | None) -> str:
    """MM/DD/YYYY h:mm AM/PM in the clinic time zone."""
    if value is None:
        return EMPTY
    local = to_clinic_time(value)
    return f"{local:%m/%d/%Y} {local.hour % 12 or 12}:{local:%M} {local:%p}"


def time_local(value: datetime | None) -> str:
    if value is None:
        return EMPTY
    local = to_clinic_time(value)
    return f"{local.hour % 12 or 12}:{local:%M} {local:%p}"


def mask_ssn(value: str | None) -> str:
    """Only the last 4 digits, if ever needed (SSN columns are never selected by default)."""
    digits = re.sub(r"\D", "", value or "")
    return f"***-**-{digits[-4:]}" if len(digits) >= 4 else EMPTY


def person_name(last: str | None, first: str | None, middle_initial: str | None = None) -> str:
    """'Last, First M.' with missing parts left out."""
    last = (last or "").strip()
    first = (first or "").strip()
    mi = (middle_initial or "").strip()
    given = f"{first} {mi}." if first and mi else first
    if last and given:
        return f"{last}, {given}"
    return last or given or EMPTY


def initials(last: str | None, first: str | None) -> str:
    """Two-letter avatar initials: first-name initial then last-name initial."""
    letters = [(first or "").strip()[:1], (last or "").strip()[:1]]
    return "".join(letters).upper() or "?"


def age(dob: date | None, today: date | None = None) -> int | None:
    if dob is None:
        return None
    today = today or date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def or_dash(value: object) -> str:
    """Stringify, using an em dash for None / empty strings."""
    if value is None:
        return EMPTY
    text = str(value).strip()
    return text or EMPTY
