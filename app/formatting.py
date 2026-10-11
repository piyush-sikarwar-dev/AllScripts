"""Display formatting: US dates, partial dates, names, ages.

Phase 3 extends this with mask decoding (`config/date_masks.yaml`) and clinic-time-zone datetimes.
"""

from datetime import date, datetime
from typing import Literal

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
