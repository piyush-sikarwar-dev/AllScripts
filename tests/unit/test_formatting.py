from datetime import date, datetime

import pytest

from app.crosswalk.keys import parse_patient_key
from app.formatting import age, date_us, initials, partial_date, person_name
from app.services.patients import parse_dob, parse_name_query


def test_date_us():
    assert date_us(date(2009, 3, 7)) == "03/07/2009"
    assert date_us(datetime(2009, 3, 7, 14, 5)) == "03/07/2009"
    assert date_us(None) == "—"


@pytest.mark.parametrize(
    ("precision", "expected"), [("full", "03/07/2009"), ("month_year", "03/2009"), ("year", "2009")]
)
def test_partial_date(precision, expected):
    assert partial_date(date(2009, 3, 7), precision) == expected


def test_person_name_and_initials():
    assert person_name("Sample", "Patient A", "Q") == "Sample, Patient A Q."
    assert person_name("Sample", None) == "Sample"
    assert person_name(None, None) == "—"
    assert initials("Sample", "Patient") == "PS"


def test_age():
    assert age(date(2000, 6, 15), today=date(2026, 6, 14)) == 25
    assert age(date(2000, 6, 15), today=date(2026, 6, 15)) == 26
    assert age(None) is None


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("Sample", ("Sample", None)),
        ("Sample, Patient", ("Sample", "Patient")),
        ("Sample Patient", ("Sample", "Patient")),
        ("  sample ,  pat ", ("sample", "pat")),
        ("", (None, None)),
    ],
)
def test_parse_name_query(q, expected):
    assert parse_name_query(q) == expected


def test_parse_dob():
    assert parse_dob("03/07/1962") == date(1962, 3, 7)
    assert parse_dob("1962-03-07") == date(1962, 3, 7)
    assert parse_dob("") is None
    with pytest.raises(ValueError):
        parse_dob("31/12/1962")


@pytest.mark.parametrize(
    ("raw", "ok"),
    [
        ("EMR:123", True),
        ("DMZ:9", True),
        ("EMR:0", False),
        ("emr:1", False),
        ("EMR:1;--", False),
        ("EMR:12345678901", False),
    ],
)
def test_parse_patient_key(raw, ok):
    assert (parse_patient_key(raw) is not None) is ok
