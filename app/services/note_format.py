"""Notes tab formatting: decode stored documents, split prescription titles, parse printouts.

Pure functions, no database. Nothing here logs note text — callers log only ids and reasons.
Prescription printouts come in two layouts (EMR discovery 2026-10-13):
  newer: Date / Patient block / Pharmacy block / RX / Medication / Date Written / Dispense, Days
         Supply / Substitution line / SIG / Notes for Pharmacist / Refill(s) / Associated Diagnosis
         / signature image / "-----" rule / prescriber / NPI / DEA
  older: Date / Name, Age, DOB / Address / Patient Allergies / Medication / Dispense / SIG /
         Comments (ICD-9 - ICD-10 codes) / Refill(s) / Substitution line / prescriber list
"""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.documents.render import (
    DocumentFormatError,
    decode_text,
    package_html,
    rtf_to_text,
    sanitize_html,
)

# --- decoding ------------------------------------------------------------------------------------


def decode_document(raw: bytes | None, datatype: int | None = None) -> tuple[str, str]:
    """Stored bytes → ('html' | 'rtf' | 'text', content). Never raises.

    html content is sanitised (nh3); rtf is converted to plain text."""
    data = raw or b""
    try:
        if data[:4] == b"PK\x03\x04":
            return "html", sanitize_html(package_html(data))
    except DocumentFormatError:
        return "text", ""
    text = decode_text(data)
    head = text.lstrip()[:2000].lower()
    if head.startswith("{\\rtf"):
        return "rtf", rtf_to_text(text)
    if any(tag in head for tag in ("<html", "<body", "<table", "<div", "<p>", "<p ", "<br")):
        return "html", sanitize_html(text)
    return "text", text.replace("\x00", "")


# --- HTML → lines --------------------------------------------------------------------------------


class _LineCollector(HTMLParser):
    _BLOCKS = ("br", "p", "div", "tr", "li", "table", "hr", "ul", "ol", "dt", "dd", "section")
    BREAK = frozenset((*_BLOCKS, "h1", "h2", "h3", "h4", "h5", "h6", "article", "header", "footer"))
    CELL = frozenset({"td", "th"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self.BREAK:
            self.parts.append("\n")
        elif tag in self.CELL:
            self.parts.append(CELL_SEP)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data.replace("\n", " ").replace("\r", " "))


_SPACES = re.compile(r"[ \t\xa0\u2007\u202f]+")
CELL_SEP = "\x1f"  # between table cells in html_to_lines output
_CELLS = re.compile(r"\s*\x1f[\s\x1f]*")


def html_to_lines(html: str) -> list[str]:
    """Sanitised text lines (breaks kept for <br>, <p>, <div>, <tr>…; one blank line at most)."""
    collector = _LineCollector()
    collector.feed(sanitize_html(html or ""))
    collector.close()
    lines: list[str] = []
    for raw in "".join(collector.parts).split("\n"):
        line = _CELLS.sub(CELL_SEP, _SPACES.sub(" ", raw)).strip(" " + CELL_SEP)
        if line or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def text_to_lines(text: str) -> list[str]:
    return [_SPACES.sub(" ", ln).strip() for ln in (text or "").replace("\r", "").split("\n")]


# --- SSN redaction -------------------------------------------------------------------------------
# Stored documents (lab requisitions) can print the patient's SSN. It is never shown (CLAUDE.md §4.4
# keeps SSNs out of the app): masked in the formatted and the original view alike.

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SSN_LABELLED = re.compile(r"(?i)(\bSSN\b\W{0,3}(?:<[^>]*>\s*)*)(\d[\d -]{7,10}\d)")


def redact_ssn(text: str) -> str:
    text = _SSN_LABELLED.sub(lambda m: m.group(1) + "•••-••-••••", text or "")
    return _SSN.sub("•••-••-••••", text)


# --- prescription titles -------------------------------------------------------------------------

_TALLMAN = re.compile(r"^[A-Za-z]*[a-z][A-Z]{3,}[a-z]*$|^[A-Z]{3,}[a-z]+[A-Z]*$")
_STRENGTH = re.compile(
    # No bare "G": "32G" in needle titles is a gauge, not grams.
    r"(\d+(?:\.\d+)?)\s?(MG|MCG|UNIT|UNITS|ML|MEQ|%)(?:/(\d+(?:\.\d+)?)?\s?(ML|MG|G|L|ACT))?(?![\w])",
    re.I,
)
_UNIT_TEXT = {"mg": "mg", "mcg": "mcg", "unit": "units", "units": "units", "ml": "mL", "g": "g",
              "gm": "g", "meq": "mEq", "%": "%", "l": "L", "act": "actuation"}  # fmt: skip
_NUMBER_WORDS = re.compile(r"\s*\((?:[a-z]+(?:[\s-][a-z]+)*)\)", re.I)
_FORMS = re.compile(
    r"\b(Tablet|Capsule|Pen|Patch|Syringe|Vial|Strip|Lancet|Packet|Suppository)s?\b(?!-)"
    r"(?:\s+(?:ER|DR|SR|XL|XR|EC|ODT|Chewable|Disintegrating|Delayed Release|\d+\s?HR))*",
    re.I,
)


def _drug_word(word: str) -> str:
    return word.capitalize() if _TALLMAN.match(word) else word


def drug_name(text: str) -> str:
    """'metFORMIN HCl ER 500MG' → 'Metformin HCl ER 500 mg' (tall-man letters, strengths)."""
    return _STRENGTH.sub(_strength, " ".join(_drug_word(w) for w in text.split()))


def _strength(m: re.Match) -> str:
    out = f"{m.group(1)} {_UNIT_TEXT[m.group(2).lower()]}"
    if m.group(4):
        per = _UNIT_TEXT[m.group(4).lower()]
        out += f"/{m.group(3)} {per}" if m.group(3) else f"/{per}"
    return out


def _amount(segment: str) -> str:
    """'2 (two) Tablet ER 24HR daily' → '2 tablets daily'."""
    text = _NUMBER_WORDS.sub("", segment).strip()
    number = re.match(r"(\d+(?:\.\d+)?)", text)
    plural = not (number and float(number.group(1)) == 1)

    def form(m: re.Match) -> str:
        word = m.group(1).lower()
        return word + ("s" if plural else "")

    return _SPACES.sub(" ", _FORMS.sub(form, text)).strip()


def split_rx_title(title: str | None) -> tuple[str, str]:
    """'metFORMIN HCl ER 500MG, 2 (two) Tablet ER 24HR daily, #270, 90 days …, Ref. x3.'
    → ('Metformin HCl ER 500 mg', '2 tablets daily · #270 · 90 days · 3 refills').
    Never raises: on anything unexpected the title is kept and the subtitle is empty."""
    original = (title or "").strip()
    try:
        if "," not in original:
            return original, ""
        head, rest = original.split(",", 1)
        drug = drug_name(head)
        segments = [s.strip() for s in rest.split(",") if s.strip()]
        parts: list[str] = []
        if segments and not segments[0].startswith("#"):
            parts.append(_amount(segments[0]))
        qty = re.search(r"#\s?(\d+(?:\.\d+)?)", rest)
        if qty:
            parts.append(f"#{qty.group(1)}")
        days = re.search(r"\b(\d+)\s+days?\b", rest, re.I)
        if days:
            parts.append(f"{days.group(1)} days")
        refills = re.search(r"\bRef\.?\s*x\s?(\d+)", rest, re.I)
        if refills:
            n = int(refills.group(1))
            parts.append("no refills" if n == 0 else f"{n} refill{'s' if n != 1 else ''}")
        return drug or original, " · ".join(p for p in parts if p)
    except (ValueError, IndexError, KeyError):
        return original, ""


# --- prescription printouts ----------------------------------------------------------------------


@dataclass
class RxView:
    medication: str | None = None
    date_written: str | None = None
    sig: str | None = None
    dispense: str | None = None
    refills: str | None = None
    pharmacist_note: str | None = None
    diagnosis: str | None = None
    pharmacy: str | None = None
    prescriber: str | None = None
    npi: str | None = None
    found: set[str] = field(default_factory=set)

    def rows(self, fallback_prescriber: str | None = None) -> list[tuple[str, str, bool]]:
        """(label, value, strong) rows; a row whose value was not found is left out."""
        prescriber = self.prescriber or fallback_prescriber
        sent = []
        if self.pharmacy:
            sent.append(self.pharmacy)
        by = " ".join(
            x
            for x in (
                f"prescribed by {prescriber}" if prescriber else "",
                f"on {self.date_written}" if self.date_written else "",
            )
            if x
        )
        if by:
            sent.append(by)
        rows = [
            ("Medication", self.medication, True),
            ("Directions (SIG)", self.sig, False),
            ("Dispense", self.dispense, False),
            ("Refills", self.refills, False),
            ("Pharmacist note", self.pharmacist_note, False),
            ("Diagnosis", self.diagnosis, False),
            ("Sent to" if self.pharmacy else "Prescribed", " · ".join(sent) or None, False),
        ]
        return [(label, value, strong) for label, value, strong in rows if value]


_LABEL = re.compile(r"^(?P<label>[A-Za-z][A-Za-z ()/#.]{0,40}?)\s*:\s*(?P<value>.*)$")
_BASE64ISH = re.compile(r"^[A-Za-z0-9+/=]{60,}$")
_RULE = re.compile(r"^[-_=]{8,}$")
_NUM_IN_WORDS = re.compile(r"\s*\((?:[a-z]+(?:[\s-][a-z]+)*)\)", re.I)
_ICD10 = re.compile(r"\b[A-TV-Z]\d{2}(?:\.[0-9A-Z]{1,4})?\b")
_ICD9 = re.compile(r"\b(?:V\d{2}|\d{3})(?:\.\d{1,2})?\b")


def _clean_amount(text: str) -> str:
    """'270 (two hundred seventy) Tablet' → '270 tablets'."""
    return _amount(text)


def _dispense(value: str, substitution: str | None) -> str:
    qty, _, supply = value.partition("Days Supply")
    parts = [_clean_amount(qty.strip().rstrip(",").strip())]
    days = re.search(r"(\d+)", supply)
    if days:
        parts.append(f"{days.group(1)}-day supply")
    if substitution:
        parts.append(substitution)
    return " · ".join(p for p in parts if p)


def _refills(value: str) -> str | None:
    m = re.search(r"x\s?(\d+)", value, re.I)
    if not m:
        return value.strip() or None
    n = int(m.group(1))
    return "No refills" if n == 0 else f"{n} refill{'s' if n != 1 else ''}"


def _diagnosis(value: str) -> str | None:
    """'Type II diabetes mellitus, uncontrolled (250.02 | E11.65)' → 'E11.65 · Type II …'."""
    text = value.strip()
    if not text:
        return None
    icd10 = _ICD10.findall(text)
    title = re.sub(r"\([^)]*\)", "", text)
    title = _ICD10.sub("", title)
    title = _ICD9.sub("", title) if icd10 else title
    title = re.sub(r"\s*[-|·]\s*$|^\s*[-|·]\s*", "", _SPACES.sub(" ", title)).strip(" ,;-")
    if title.lower() in ("no diagnosis", "none", ""):
        title = ""
    if icd10:
        return " · ".join(x for x in (", ".join(dict.fromkeys(icd10)), title) if x)
    return title or None


def _is_noise(line: str) -> bool:
    return bool(_BASE64ISH.match(line.replace(" ", "")) and " " not in line.strip())


def parse_rx(lines: list[str]) -> RxView | None:
    """Label-anchored parse of a prescription printout. None when fewer than 3 of Medication /
    SIG / Dispense / Refill(s) were found."""
    rx = RxView()
    clean = [ln.replace(CELL_SEP, " ").strip() for ln in lines]
    substitution = None
    after_rule = False
    in_pharmacy = False
    expect_dx = False
    for line in clean:
        if not line or _is_noise(line):
            continue
        low = line.lower()
        if _RULE.match(line):
            after_rule = True
            continue
        if after_rule:
            if rx.prescriber is None and ":" not in line:
                rx.prescriber = line
            elif low.startswith("npi"):
                rx.npi = line.split(":", 1)[-1].strip().lstrip("#").strip() or None
            continue
        if expect_dx:
            expect_dx = False
            rx.diagnosis = _diagnosis(line)
            if rx.diagnosis:
                rx.found.add("diagnosis")
            continue
        if low.startswith("substitution") or low.startswith("dispense as written"):
            substitution = "substitution permitted" if "permissible" in low and "not" not in low \
                else "substitution not permitted"  # fmt: skip
            continue
        if low.startswith("associated diagnos"):
            rest = line.split(":", 1)[1].strip() if ":" in line else ""
            if rest:
                rx.diagnosis = _diagnosis(rest)
            else:
                expect_dx = True
            continue
        if low.startswith("refill"):
            rx.refills = _refills(re.sub(r"(?i)^refill\(?s?\)?\s*:?", "", line))
            rx.found.add("refills")
            continue
        m = _LABEL.match(line)
        if not m:
            continue
        label = m.group("label").strip().lower()
        value = m.group("value").strip()
        if label == "pharmacy":
            rx.pharmacy = value or None
            in_pharmacy = True
            continue
        if label in ("address", "phone") and in_pharmacy:
            continue
        in_pharmacy = False
        if label == "medication":
            rx.medication = drug_name(value) or None
            rx.found.add("medication")
        elif label == "date written" or (label == "date" and rx.date_written is None):
            rx.date_written = value or None
        elif label == "sig":
            rx.sig = _amount(value) or None
            rx.found.add("sig")
        elif label == "dispense":
            rx.dispense = value
            rx.found.add("dispense")
        elif label in ("notes for pharmacist", "note to pharmacist", "pharmacist notes"):
            rx.pharmacist_note = value or None
        elif label == "comments" and value:
            rx.diagnosis = rx.diagnosis or _diagnosis(value)
    if rx.dispense is not None:
        rx.dispense = _dispense(rx.dispense, substitution) or None
    if len(rx.found & {"medication", "sig", "dispense", "refills"}) < 3:
        return None
    return rx


# --- generic sections ----------------------------------------------------------------------------

IDENTITY_LABELS = frozenset({
    "patient", "patient name", "name", "phone", "address", "dob", "date of birth", "gender", "sex",
    "ssn", "mrn", "patient #", "patient id", "age", "race", "employer", "relationship to insured",
    "home phone", "work phone", "cell phone", "email", "insured", "subscriber", "guarantor",
})  # fmt: skip
_SECTION = re.compile(r"^(?P<label>[A-Z][A-Za-z0-9 #/()&.,'\-]{0,39}?)\s*:\s*(?P<value>.*)$")


def parse_sections(lines: list[str]) -> list[tuple[str, str]]:
    """'Label: value' lines start a section; following unlabeled lines append to it. Patient
    identity labels are skipped (the chart header shows who the patient is)."""
    sections: list[list[str]] = []
    skipping = False
    for raw in lines:
        line = raw.strip().strip("|\t\x1f ").strip()
        if not line or _is_noise(line) or _RULE.match(line):
            continue
        for cell in [c.strip() for c in re.split(r"\x1f|\t+|\s\|\s", line) if c.strip()]:
            m = _SECTION.match(cell)
            if m:
                label = m.group("label").strip()
                skipping = label.lower() in IDENTITY_LABELS
                if not skipping:
                    sections.append([label, m.group("value").strip()])
            elif sections and not skipping:
                sections[-1][1] = f"{sections[-1][1]}\n{cell}".strip()
    return [(label, value) for label, value in sections if value]
