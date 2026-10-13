"""Notes tab formatting: title split, printout parsing, sections, decoding (synthetic fixtures)."""

import io
import zipfile
from pathlib import Path

import pytest

from app.services.note_format import (
    decode_document,
    html_to_lines,
    parse_rx,
    parse_sections,
    redact_ssn,
    split_rx_title,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "notes"


def _lines(name: str) -> list[str]:
    return html_to_lines((FIXTURES / name).read_text(encoding="utf-8"))


# --- split_rx_title ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "drug", "subtitle"),
    [
        ("metFORMIN HCl ER 500MG, 2 (two) Tablet ER 24HR daily, #270, 90 days starting 6/3/2020, "
         "Ref. x3.", "Metformin HCl ER 500 mg", "2 tablets daily · #270 · 90 days · 3 refills"),
        ("Glimepiride 4MG, 1 (one) Tablet daily, #90, 90 days, Ref. x1.",
         "Glimepiride 4 mg", "1 tablet daily · #90 · 90 days · 1 refill"),
        ("Phentermine HCl 37.5MG, 1 Tablet daily, #30, 30 days, Ref. x0.",
         "Phentermine HCl 37.5 mg", "1 tablet daily · #30 · 30 days · no refills"),
        ("NovoLOG FlexPen 100UNIT/ML, 10 units three times a day, #15, 30 days, Ref. x2.",
         "Novolog FlexPen 100 units/mL", "10 units three times a day · #15 · 30 days · 2 refills"),
        ("Victoza 18MG/3ML, 1.8 Solution Pen-injector daily, #9, 30 days, Ref. x5.",
         "Victoza 18 mg/3 mL", "1.8 Solution Pen-injector daily · #9 · 30 days · 5 refills"),
        ("Trulicity 1.5MG/0.5ML, 1 (one) Pen weekly, #4, 28 days",
         "Trulicity 1.5 mg/0.5 mL", "1 pen weekly · #4 · 28 days"),
        ("Synthroid 50MCG, 1 (one) Tablet daily, #90",
         "Synthroid 50 mcg", "1 tablet daily · #90"),
        ("BD Pen Needle Nano U/F 32G X 4MM, 1 (one) Miscellaneous daily, #100, 100 days, Ref. x11.",
         "BD Pen Needle Nano U/F 32G X 4MM",
         "1 Miscellaneous daily · #100 · 100 days · 11 refills"),
        ("Vitamin D (Ergocalciferol) 50000 UNIT, 1 (one) Capsule weekly, #12, 84 days",
         "Vitamin D (Ergocalciferol) 50000 units", "1 capsule weekly · #12 · 84 days"),
        ("Lantus SoloStar 100UNIT/ML, 20 units at bedtime, #15, Ref. x3.",
         "Lantus SoloStar 100 units/mL", "20 units at bedtime · #15 · 3 refills"),
        ("Testosterone Cypionate 200MG/ML, 1 mL every 2 weeks, #10",
         "Testosterone Cypionate 200 mg/mL", "1 mL every 2 weeks · #10"),
        ("Laboratory Requisitions", "Laboratory Requisitions", ""),
        ("", "", ""),
    ],
)  # fmt: skip
def test_split_rx_title(title, drug, subtitle):
    assert split_rx_title(title) == (drug, subtitle)


def test_split_rx_title_never_raises():
    for title in (None, ",", ",,,", "#", "x, #abc, Ref. x", "\x00, \x01"):
        drug, subtitle = split_rx_title(title)
        assert isinstance(drug, str) and isinstance(subtitle, str)


# --- parse_rx ------------------------------------------------------------------------------------


def test_parse_rx_newer_layout():
    rx = parse_rx(_lines("rx_newer.html"))
    assert rx is not None
    rows = {label: value for label, value, _strong in rx.rows()}
    assert rows == {
        "Medication": "Metformin HCl ER 500 mg Tablet ER 24HR",
        "Directions (SIG)": "2 tablets by mouth daily",
        "Dispense": "270 tablets · 90-day supply · substitution permitted",
        "Refills": "3 refills",
        "Pharmacist note": "1.5 with breakfast, 1.5 with dinner",
        "Diagnosis": "E11.65 · Type II diabetes mellitus, uncontrolled",
        "Sent to": "Sample Community Pharmacy #12 · prescribed by Sample Provider, DO "
        "on 06/03/2020",
    }
    assert rx.rows()[0][2] is True  # medication shown strong
    text = " ".join(v for _l, v, _s in rx.rows())
    assert "Sample A. Patient" not in text and "DEA" not in text and "01/02/1960" not in text


def test_parse_rx_older_layout():
    rx = parse_rx(_lines("rx_older.html"))
    assert rx is not None
    rows = {label: value for label, value, _strong in rx.rows("Example, Doctor DO")}
    assert rows["Medication"] == "Glimepiride 4 mg Tablet"
    assert rows["Dispense"] == "180 tablets · 90-day supply · substitution not permitted"
    assert rows["Refills"] == "No refills"
    assert rows["Diagnosis"] == "E11.9"  # ICD-9 dropped when an ICD-10 is present
    assert rows["Prescribed"] == "prescribed by Example, Doctor DO on June 3, 2015"
    assert "Pharmacist note" not in rows  # empty values are never shown


def test_parse_rx_returns_none_when_not_a_printout():
    assert parse_rx(_lines("letter.html")) is None
    assert parse_rx(["Medication: Sample", "Refill(s): x1"]) is None


# --- parse_sections ------------------------------------------------------------------------------


def test_parse_sections_skips_identity_and_joins_lines():
    sections = parse_sections(_lines("lab_report.html"))
    labels = [label for label, _ in sections]
    assert labels == ["Bill To", "Requisition Date", "Diagnosis", "Fasting", "Ordering Physician",
                      "Tests"]  # fmt: skip
    assert dict(sections)["Tests"] == "Hemoglobin A1c\nLipid panel"
    assert "Patient Name" not in labels and "SSN" not in labels


def test_parse_sections_plain_text():
    lines = [
        "Chief Complaint: Sample follow-up.",
        "  more text",
        "Plan: Continue.",
        "DOB: 01/01/1950",
    ]
    assert parse_sections(lines) == [
        ("Chief Complaint", "Sample follow-up.\nmore text"),
        ("Plan", "Continue."),
    ]


# --- decoding / sanitising -----------------------------------------------------------------------


def test_decode_html_is_sanitised():
    raw = (
        b"<html><body><p onclick='x()'>Hi</p><script>bad()</script>"
        b"<img src='https://example.invalid/x.png'></body></html>"
    )
    kind, html = decode_document(raw)
    assert kind == "html"
    assert "Hi" in html and "script" not in html and "onclick" not in html and "<img" not in html


def test_decode_rtf_utf16_package_and_garbage():
    kind, text = decode_document((FIXTURES / "dictation.rtf").read_bytes())
    assert kind == "rtf" and text == "Chief Complaint: Sample follow-up.\nPlan: Continue."
    kind, html = decode_document((FIXTURES / "utf16.html").read_bytes())
    assert kind == "html" and "Café sample note" in html
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CONTENT", "<p>Packaged note</p>")
    assert decode_document(buf.getvalue()) == ("html", "<p>Packaged note</p>")
    kind, text = decode_document((FIXTURES / "garbage.bin").read_bytes())  # never raises
    assert kind == "text" and "\x00" not in text
    assert decode_document(None) == ("text", "")


def test_html_to_lines_keeps_breaks():
    lines = html_to_lines(
        "<p>One<br>Two</p><div>Three   four</div><table><tr><td>a</td><td>b</td></tr></table>"
    )
    assert lines[:3] == ["One", "Two", ""] or lines[:2] == ["One", "Two"]
    assert "Three four" in lines and any(line.startswith("a") and "b" in line for line in lines)


def test_redact_ssn():
    assert redact_ssn("SSN: 123-45-6789") == "SSN: •••-••-••••"
    assert redact_ssn("SSN 123456789") == "SSN •••-••-••••"
    assert redact_ssn("ssn:</td><td>123 45 6789") == "ssn:</td><td>•••-••-••••"
    assert redact_ssn("Phone (555) 010-0000, ref 12-345") == "Phone (555) 010-0000, ref 12-345"
