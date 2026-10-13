"""Turn stored visit-note text into readable sections (Visits tab "Structured" view).

NOTES_TEXTDATA.NOTE_TEXT often holds free text followed by Allscripts XML, e.g.
    <?xml version="1.0" encoding="ISO-8859-1"?><reasonsForVisit>…<chiefComplaint><rfvItem
    kndgName="diabetes"><hpStatement>…</hpStatement>…<lexiconNarrative>…|......|…</lexiconNarrative>
    </rfvItem></chiefComplaint><sectionEnctInfo description="History of Present Illness">…
Rules (see the Visits "Option C" spec):
  - XML is parsed only with defusedxml (no DTDs, no entities, no external references).
  - Chief complaint = rfvItem/@kndgName values; history = hpStatement text (else lexiconNarrative),
    titled by sectionEnctInfo/@description when present.
  - Metadata tags are never shown; "|......|" separators are removed; paragraphs are kept.
  - Plain text before the XML is dropped when it repeats the history, otherwise shown as "Note".
  - No XML → the whole text is one "Note". XML that fails to parse → tags stripped, shown as
    "Note", parse_ok=False and a log line with the encounter id only (never note text).
Nothing in this module logs or returns anything but the note's own content.
"""

import logging
import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element

from defusedxml import ElementTree as SafeET
from defusedxml import minidom as safe_minidom
from defusedxml.common import DefusedXmlException

log = logging.getLogger("app.notes")

METADATA_TAGS = frozenset(
    {"patientDemLine", "kndgLimits", "itemEnctInfo", "lineId", "hpLinkText", "hpLinkTextDetail",
     "attendingCaregiver", "datetimeStamp", "isFromTemplate", "hasRFV", "sectionEnctInfo"}
)  # fmt: skip
STRUCTURAL_TAGS = frozenset({"reasonsForVisit", "chiefComplaint", "rfvItem"})
HISTORY_TAGS = ("hpStatement", "lexiconNarrative")
DEFAULT_HISTORY_TITLE = "History of present illness"

_DECL_RE = re.compile(r"<\?xml[^>]*\?>", re.I)
_OPEN_TAG_RE = re.compile(r"<([A-Za-z_][\w.\-]*)(\s[^<>]*)?>")
_SEPARATOR_RE = re.compile(r"\|[|.]*\|?")
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


@dataclass(frozen=True)
class NoteSection:
    title: str
    paragraphs: list[str]


@dataclass
class ParsedNote:
    sections: list[NoteSection] = field(default_factory=list)
    raw_text: str = ""
    parse_ok: bool = True


# --- text helpers --------------------------------------------------------------------------------


def clean_text(text: str) -> list[str]:
    """Remove '|......|' separators, collapse spaces, keep paragraph breaks."""
    text = _SEPARATOR_RE.sub(" ", text or "")
    paragraphs = []
    for block in re.split(r"\n\s*\n|\r\n\s*\r\n", text):
        lines = [_WS_RE.sub(" ", ln).strip() for ln in block.splitlines()]
        para = "\n".join(ln for ln in lines if ln)
        if para:
            paragraphs.append(para)
    return paragraphs


def _normalise(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text).strip().lower()


def _capitalise(value: str) -> str:
    value = value.strip()
    return value[:1].upper() + value[1:] if value else value


# --- XML fragment discovery ----------------------------------------------------------------------


def split_fragments(raw: str) -> list[tuple[str, str]]:
    """Split note text into ("text", …) and ("xml", …) pieces, in order."""
    pieces: list[tuple[str, str]] = []
    pos = 0
    while pos < len(raw):
        decl = _DECL_RE.search(raw, pos)
        tag = _OPEN_TAG_RE.search(raw, pos)
        start = None
        if decl and (tag is None or decl.start() <= tag.start()):
            start = decl.start()
            root = _OPEN_TAG_RE.search(raw, decl.end())
        else:
            root = tag
            if root is not None and f"</{root.group(1)}>" in raw[root.end() :]:
                start = root.start()
        if start is None or root is None:
            break
        close = f"</{root.group(1)}>"
        end_at = raw.rfind(close, root.end())
        nxt = _DECL_RE.search(raw, root.end())
        if nxt is not None:  # several fragments: stop at the last close tag before the next one
            bounded = raw.rfind(close, root.end(), nxt.start())
            end_at = bounded if bounded != -1 else end_at
        if root.group(2) and root.group(2).rstrip().endswith("/"):
            end = root.end()  # self-closing root
        elif end_at == -1:
            end = len(raw)  # unterminated: let the parser fail → safe fallback
        else:
            end = end_at + len(close)
        if raw[pos:start].strip():
            pieces.append(("text", raw[pos:start]))
        pieces.append(("xml", raw[start:end]))
        pos = end
    if raw[pos:].strip():
        pieces.append(("text", raw[pos:]))
    return pieces


def _parse_xml(fragment: str) -> Element:
    body = _DECL_RE.sub("", fragment, count=1).strip()
    return SafeET.fromstring(body, forbid_dtd=True)


def _element_text(el: Element) -> str:
    return "".join(el.itertext())


# --- extraction ----------------------------------------------------------------------------------


def _sections_from_xml(root: Element) -> tuple[list[str], str | None, list[str], list[str]]:
    """(chief complaints, history title, history paragraphs, other paragraphs)."""
    complaints: list[str] = []
    for item in root.iter("rfvItem"):
        name = (item.get("kndgName") or "").strip()
        if name and name.lower() not in {c.lower() for c in complaints}:
            complaints.append(_capitalise(name))
    title = None
    for info in root.iter("sectionEnctInfo"):
        if (info.get("description") or "").strip():
            title = info.get("description").strip()
            break
    history: list[str] = []
    for tag in HISTORY_TAGS:
        for el in root.iter(tag):
            history += clean_text(_element_text(el))
        if history:
            break
    other: list[str] = []

    def walk(el: Element) -> None:
        if el.tag in METADATA_TAGS or el.tag in HISTORY_TAGS:
            return
        if el.tag not in STRUCTURAL_TAGS and el.text and el.text.strip():
            other.extend(clean_text(el.text))
        for child in el:
            walk(child)
            if child.tail and child.tail.strip():
                other.extend(clean_text(child.tail))

    walk(root)
    return complaints, title, history, other


def parse_note(raw: str | None, *, encounter_id: int | None = None) -> ParsedNote:
    raw = raw or ""
    if not raw.strip():
        return ParsedNote(raw_text=raw)
    pieces = split_fragments(raw)
    if not any(kind == "xml" for kind, _ in pieces):
        return ParsedNote(sections=[NoteSection("Note", clean_text(raw))], raw_text=raw)

    complaints: list[str] = []
    history_title: str | None = None
    history: list[str] = []
    other: list[str] = []
    plain: list[str] = []
    try:
        for kind, chunk in pieces:
            if kind == "text":
                plain += clean_text(chunk)
                continue
            c, t, h, o = _sections_from_xml(_parse_xml(chunk))
            complaints += [x for x in c if x.lower() not in {y.lower() for y in complaints}]
            history_title = history_title or t
            history += h
            other += o
    except (SafeET.ParseError, DefusedXmlException, ValueError):
        log.warning("note_parse_fallback encounter=%s", encounter_id)
        stripped = clean_text(_TAG_RE.sub(" ", _DECL_RE.sub(" ", raw)))
        return ParsedNote(sections=[NoteSection("Note", stripped)] if stripped else [],
                          raw_text=raw, parse_ok=False)  # fmt: skip

    sections: list[NoteSection] = []
    history_norm = _normalise(" ".join(history))
    plain = [p for p in plain if not history_norm or _normalise(p) not in history_norm]
    if complaints:
        sections.append(NoteSection("Chief complaint", [", ".join(complaints)]))
    if history:
        sections.append(NoteSection(history_title or DEFAULT_HISTORY_TITLE, history))
    if other:
        sections.append(NoteSection("Additional details", other))
    if plain:
        sections.append(NoteSection("Note", plain))
    return ParsedNote(sections=sections, raw_text=raw)


def original_text(raw: str | None) -> str:
    """The note exactly as stored, with XML pretty-printed when it parses (for the Original view).
    The caller must HTML-escape it (Jinja autoescape); it is never rendered as HTML."""
    raw = raw or ""
    out: list[str] = []
    pretty_any = False
    for kind, chunk in split_fragments(raw):
        if kind == "text":
            out.append(chunk.strip("\n"))
            continue
        try:
            body = _DECL_RE.sub("", chunk, count=1).strip()
            pretty = safe_minidom.parseString(body, forbid_dtd=True).toprettyxml(indent="  ")
            lines = [ln for ln in pretty.splitlines()[1:] if ln.strip()]  # drop <?xml …?>
            out.append("\n".join(lines))
            pretty_any = True
        except Exception:  # not parseable: keep it exactly as stored
            out.append(chunk)
    return "\n".join(out) if pretty_any else raw
