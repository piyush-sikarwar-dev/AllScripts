"""Problems & allergies tab (Option B): section rail, entry list, entry detail, change history.

Entries come from the cached repository functions `history_entries` (current state, latest
revision per entry) and `history_changes` (all revisions of one entry). Sections come from
config/history_categories.yaml, code display and allergy types from config/history_codes.yaml.
Nothing here logs titles or comments — only ids and codes.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.crosswalk import PatientRef
from app.db.app import new_session
from app.formatting import EMPTY, date_us, partial_date, sort_key
from app.lookups import get_lookups
from app.lookups.history_codes import history_codes
from app.models.history import (
    ChangeLine,
    CodeView,
    EntryDetail,
    EntryField,
    EntryRow,
    HistoryState,
    SectionSummary,
)
from app.repositories import source_repository
from app.repositories.appdb import export_selection
from app.services import NotFoundError, call

log = logging.getLogger("app.history")

# (section key in URLs, group in history_categories.yaml, label) — rail order.
SECTIONS: list[tuple[str, str, str]] = [
    ("problems", "problem", "Problems"),
    ("allergies", "allergy", "Allergies"),
    ("surgical", "surgical", "Surgical history"),
    ("family", "family", "Family history"),
    ("social", "social", "Social history"),
    ("other", "other", "Other history"),
]
SECTION_KEYS = frozenset(k for k, _, _ in SECTIONS)
SECTION_LABELS = {k: label for k, _, label in SECTIONS}
GROUP_TO_SECTION = {group: k for k, group, _ in SECTIONS}
STATUSES = ("all", "active")
# Status filter default per section, until the user picks one (then remembered per session).
DEFAULT_STATUS = {"problems": "active"}
EXPORT_TYPE = "history_entry"
CHANGES_SHOWN = 20
STATUS_LABELS = {"active": "Active", "inactive": "Inactive", "resolved": "Resolved",
                 "error": "Entered in error", "unknown": "Unknown"}  # fmt: skip

_last_status: dict[str, str] = {}  # session id → last status choice (memory only)
_unmapped_logged: set[object] = set()


# --- state ---------------------------------------------------------------------------------------


def _int(raw: str | None) -> int | None:
    if raw is None or not raw.strip().isdigit() or len(raw.strip()) > 10:
        return None
    return int(raw)


def parse_state(
    params: Mapping[str, str], session_id: str | None = None
) -> tuple[HistoryState, bool]:
    """State from the URL; (state, section_given). A status the user picked is remembered for
    their session; otherwise each section has its own default."""
    sec = params.get("sec", "")
    section_given = sec in SECTION_KEYS
    sec = sec if section_given else "problems"
    status = params.get("status", "")
    if status in STATUSES:
        if session_id:
            if len(_last_status) > 1000:
                _last_status.clear()
            _last_status[session_id] = status
    else:
        status = _last_status.get(session_id or "") or DEFAULT_STATUS.get(sec, "all")
    return HistoryState(sec=sec, status=status, entry=_int(params.get("entry"))), section_given


# --- entries -------------------------------------------------------------------------------------


@dataclass
class Entry:
    id: int
    section: str
    title: str
    kind: str  # allergy type / relationship / social value / "" for problems
    status: str
    is_nka: bool
    onset: Any
    onset_precision: str
    resolved: Any
    recorded: Any
    raw: dict[str, Any]

    @property
    def is_active(self) -> bool:
        return self.status == "active"


def _status(raw: dict) -> str:
    code = raw["activity_code"]
    if code == 8:
        return "error"
    if raw["resolved"] is not None or code == 3:
        return "resolved"
    if code == 1:
        return "active"
    if code == 2:
        return "inactive"
    return "unknown"


def _section(category_code: object) -> str:
    lk = get_lookups()
    if category_code not in lk.history and category_code not in _unmapped_logged:
        _unmapped_logged.add(category_code)
        log.warning("history_category_unmapped code=%s", category_code)
    return GROUP_TO_SECTION.get(lk.history_category(category_code).group, "other")


def _attr_titles(raw: dict) -> list[str]:
    return [a["title"] or a["value"] for a in raw["attributes"] if a["title"] or a["value"]]


def _entry(raw: dict) -> Entry:
    section = _section(raw["category_code"])
    title = raw["title"] or raw["description"] or "Untitled"
    codes = history_codes()
    is_nka = section == "allergies" and codes.is_status_title(title)
    if section == "allergies":
        kind = codes.allergy_kind(title, raw["code_system"])
    elif section in ("family", "social"):
        kind = ", ".join(_attr_titles(raw))
    else:
        kind = ""
    return Entry(
        id=raw["id"],
        section=section,
        title=title,
        kind=kind,
        status=_status(raw),
        is_nka=is_nka,
        onset=raw["onset"],
        onset_precision=get_lookups().date_precision(raw["onset_mask"]),
        resolved=raw["resolved"],
        recorded=raw["recorded"],
        raw=raw,
    )


async def load_entries(ref: PatientRef) -> list[Entry]:
    return [_entry(r) for r in await call(source_repository().history_entries, ref.emr_id)]


def visible(entries: list[Entry], section: str, status: str) -> list[Entry]:
    """Entries of one section: Active filter = active only; All = everything (errors included).
    Active first, then the most recent onset / recording first."""
    rows = [e for e in entries if e.section == section
            and (e.is_active if status == "active" else True)]  # fmt: skip
    rows.sort(key=lambda e: (e.is_active, sort_key(e.onset or e.recorded)), reverse=True)
    return rows


def _real_active_allergies(entries: list[Entry]) -> int:
    return sum(1 for e in entries if e.section == "allergies" and e.is_active and not e.is_nka)


def default_section(entries: list[Entry]) -> str:
    """Allergies when the patient has an active allergy, else Problems."""
    return "allergies" if _real_active_allergies(entries) else "problems"


def sections(entries: list[Entry], state: HistoryState) -> list[SectionSummary]:
    out = []
    for key, _group, label in SECTIONS:
        rows = visible(entries, key, state.status)
        in_section = [e for e in entries if e.section == key]
        if key == "other" and not in_section:
            continue  # "Other history" only when it has entries
        summary = SectionSummary(key=key, label=label, count=len(rows),
                                 active_count=sum(1 for e in in_section if e.is_active),
                                 selected=key == state.sec)  # fmt: skip
        if key == "allergies":
            real = _real_active_allergies(entries)
            if real:
                summary.pill, summary.pill_kind = f"{real} active", "alert"
            elif any(e.is_nka and e.is_active for e in in_section):
                summary.pill = "NKA"
            else:
                summary.pill = "None active"  # never implies "no allergies"
        out.append(summary)
    return out


def _date_line(e: Entry) -> str:
    onset = partial_date(e.onset, e.onset_precision) if e.onset else None
    resolved = date_us(e.resolved) if e.resolved else None
    if onset and resolved:
        return f"Since {onset} · Resolved {resolved}"
    if onset:
        return f"Since {onset}"
    if resolved:
        return f"Resolved {resolved}"
    return "Date not recorded"


def entry_row(e: Entry) -> EntryRow:
    meta = " · ".join(x for x in (e.kind, _date_line(e)) if x)
    return EntryRow(id=e.id, title=e.title, meta=meta, status=e.status,
                    status_label=STATUS_LABELS[e.status])  # fmt: skip


# --- detail --------------------------------------------------------------------------------------


def code_view(code_system: str | None, code: str | None, imo_code: int | None) -> CodeView:
    """Real clinical code first ("ICD-9 250.00"); internal references only as small tags."""
    system = history_codes().system(code_system)
    view = CodeView()
    if code:
        if system.standard:
            view.standard = f"{system.label} {code}"
        else:
            view.tags.append(f"{system.label} {code}")
    if imo_code:
        view.tags.append(f"IMO {imo_code}")
    return view


def _decoded(kind: str, code: object) -> str | None:
    """Dictionary label, or None for the 'not set' values 0 ("*") and 9 (Undefined)."""
    if code in (None, 0, 9):
        return None
    return get_lookups().label(kind, code)


def _severity(raw: dict) -> str | None:
    codes = [a["severity_code"] for a in raw["attributes"] if a["severity_code"]]
    return get_lookups().label("hx_attr_severity", max(codes)) if codes else None


def build_detail(e: Entry, entries: list[Entry], in_export: bool = False) -> EntryDetail:
    raw = e.raw
    fields: list[EntryField] = []
    type_label = {"family": "Relationship", "social": "Details"}.get(e.section, "Type")
    if e.kind:
        fields.append(EntryField(label=type_label, value=e.kind))
    if e.section == "allergies" and not e.is_nka:
        reaction = ", ".join(_attr_titles(raw))
        fields.append(EntryField(label="Reaction", value=reaction or "Not recorded",
                                 muted=not reaction))  # fmt: skip
        severity = _severity(raw)
        if severity:
            fields.append(EntryField(label="Severity", value=severity))
    onset = partial_date(e.onset, e.onset_precision) if e.onset else None
    fields.append(EntryField(label="Onset", value=onset or "Not recorded", muted=not onset))
    if e.resolved:
        fields.append(EntryField(label="Resolved", value=date_us(e.resolved)))
    decoded = (
        ("Acuity", "hx_acuity", raw["acuity_code"]),
        ("Significance", "hx_significance", raw["significance_code"]),
    )
    for label, kind, code in decoded:
        value = _decoded(kind, code)
        if value:
            fields.append(EntryField(label=label, value=value))
    if raw["description"] and raw["description"] != e.title:
        fields.append(EntryField(label="Description", value=raw["description"]))
    comment = "\n\n".join(x for x in (raw["comments"], raw["basis"]) if x)[:2000] or None
    recorded_parts = [raw["provider"], date_us(e.recorded) if e.recorded else None, "EMR"]
    conflict = e.is_nka and e.is_active and _real_active_allergies(entries) > 0
    return EntryDetail(
        id=e.id,
        section=e.section,
        section_label=SECTION_LABELS[e.section],
        title=e.title,
        status=e.status,
        status_label=STATUS_LABELS[e.status],
        fields=fields,
        code=code_view(raw["code_system"], raw["code"], raw["imo_code"]),
        comment=comment,
        recorded=" · ".join(p for p in recorded_parts if p and p != EMPTY),
        conflict=conflict,
        in_export=in_export,
    )


def find_entry(entries: list[Entry], entry_id: int) -> Entry:
    found = next((e for e in entries if e.id == entry_id), None)
    if found is None:
        raise NotFoundError(f"history entry {entry_id}")
    return found


async def entry_detail(ref: PatientRef, entry_id: int, session_id: str | None) -> EntryDetail:
    entries = await load_entries(ref)
    entry = find_entry(entries, entry_id)
    selected = await selected_entry_ids(session_id, ref.patient_key)
    return build_detail(entry, entries, entry.id in selected)


# --- change history ------------------------------------------------------------------------------

_STATUS_TEXT = {"active": "Marked active", "inactive": "Marked inactive",
                "resolved": "Marked resolved", "error": "Marked as entered in error",
                "unknown": "Status cleared"}  # fmt: skip


def _rev_status(r: dict) -> str:
    return _status({"activity_code": r["activity_code"], "resolved": r["resolved"]})


def _rev_onset(r: dict) -> str | None:
    if r["onset"] is None:
        return None
    return partial_date(r["onset"], get_lookups().date_precision(r["onset_mask"]))


def describe_change(prev: dict | None, cur: dict) -> list[str]:
    """What changed from one revision to the next, as short sentences (pure; unit-tested)."""
    if prev is None:
        status = _rev_status(cur)
        return ["Added" if status == "active" else f"Added ({STATUS_LABELS[status].lower()})"]
    out = []
    if (prev["title"] or "") != (cur["title"] or "") and cur["title"]:
        out.append(f"Renamed to “{cur['title']}”")
    if _rev_status(prev) != _rev_status(cur):
        out.append(_STATUS_TEXT[_rev_status(cur)])
    if _rev_onset(prev) != _rev_onset(cur):
        out.append(f"Onset changed to {_rev_onset(cur)}" if _rev_onset(cur) else "Onset removed")
    if prev["resolved"] != cur["resolved"] and _rev_status(cur) == _rev_status(prev):
        out.append(f"Resolved date set to {date_us(cur['resolved'])}" if cur["resolved"]
                   else "Resolved date removed")  # fmt: skip
    if (prev["comments"] or "") != (cur["comments"] or ""):
        out.append("Comment added" if not prev["comments"]
                   else "Comment removed" if not cur["comments"] else "Comment edited")  # fmt: skip
    if prev["significance_code"] != cur["significance_code"]:
        sig = _decoded("hx_significance", cur["significance_code"])
        out.append(f"Significance changed to {sig}" if sig else "Significance cleared")
    return out


def change_lines(revisions: list[dict]) -> list[ChangeLine]:
    """Newest first; revisions that changed nothing visible are skipped."""
    ordered = sorted(revisions, key=lambda r: (r["revision"] or 0, sort_key(r["changed"])))
    lines, prev = [], None
    for cur in ordered:
        parts = describe_change(prev, cur)
        prev = cur
        if not parts:
            continue
        text = "; ".join(parts)
        if cur.get("reason"):
            text += f" — {cur['reason']}"
        if cur.get("provider"):
            text += f" · {cur['provider']}"
        lines.append(
            ChangeLine(date=date_us(cur["changed"]) if cur["changed"] else EMPTY, text=text)
        )
    return list(reversed(lines))


async def change_history(ref: PatientRef, entry_id: int) -> list[ChangeLine]:
    find_entry(await load_entries(ref), entry_id)  # 404 unless this patient's entry
    return change_lines(await call(source_repository().history_changes, ref.emr_id, entry_id))


# --- tab -----------------------------------------------------------------------------------------


@dataclass
class HistoryView:
    state: HistoryState
    rail: list[SectionSummary]
    rows: list[EntryRow]
    detail: EntryDetail | None
    selection_changed: bool


async def history_view(
    ref: PatientRef, params: Mapping[str, str], session_id: str | None
) -> HistoryView:
    state, section_given = parse_state(params, session_id)
    entries = await load_entries(ref)
    if not section_given:
        state.sec = default_section(entries)
        if "status" not in params and session_id not in _last_status:
            state.status = DEFAULT_STATUS.get(state.sec, "all")
    if state.sec == "other" and not any(e.section == "other" for e in entries):
        state.sec = "problems"
    rows = visible(entries, state.sec, state.status)
    wanted = state.entry
    chosen = next((e for e in rows if e.id == wanted), rows[0] if rows else None)
    detail = None
    if chosen is not None:
        selected = await selected_entry_ids(session_id, ref.patient_key)
        detail = build_detail(chosen, entries, chosen.id in selected)
    state.entry = chosen.id if chosen else None
    return HistoryView(state=state, rail=sections(entries, state),
                       rows=[entry_row(e) for e in rows], detail=detail,
                       selection_changed=state.entry != wanted)  # fmt: skip


def print_rows(entries: list[Entry], section: str) -> list[dict[str, str]]:
    rows = []
    for e in visible(entries, section, "all"):
        code = code_view(e.raw["code_system"], e.raw["code"], None).standard
        rows.append({"title": e.title, "type": e.kind or "—",
                     "onset": partial_date(e.onset, e.onset_precision) if e.onset else "—",
                     "resolved": date_us(e.resolved) if e.resolved else "—",
                     "status": STATUS_LABELS[e.status], "code": code or "—"})  # fmt: skip
    return rows


# --- "Add to export" -----------------------------------------------------------------------------


def _selected_sync(session_id: str, patient_key: str) -> set[int]:
    with new_session() as db:
        return export_selection.selected_ids(db, session_id, patient_key, EXPORT_TYPE)


def _toggle_sync(session_id: str, patient_key: str, entry_id: int) -> tuple[bool, int]:
    with new_session() as db:
        added = export_selection.toggle(db, session_id, patient_key, entry_id, EXPORT_TYPE)
        return added, export_selection.count_all(db, session_id, patient_key)


async def selected_entry_ids(session_id: str | None, patient_key: str) -> set[int]:
    if not session_id:
        return set()
    return await call(_selected_sync, session_id, patient_key)


async def toggle_entry_export(ref: PatientRef, session_id: str, entry_id: int) -> tuple[bool, int]:
    find_entry(await load_entries(ref), entry_id)
    return await call(_toggle_sync, session_id, ref.patient_key, entry_id)


async def entry_choices(ref: PatientRef, ids: set[int]) -> list[tuple[int, str]]:
    """(entry id, "Section · title") for the export dialog."""
    if not ids:
        return []
    entries = [e for e in await load_entries(ref) if e.id in ids]
    order = {k: i for i, (k, _, _) in enumerate(SECTIONS)}
    entries.sort(key=lambda e: (order[e.section], e.title.casefold()))
    return [(e.id, f"{SECTION_LABELS[e.section]} · {e.title}") for e in entries]


async def selected_entries_for_pdf(ref: PatientRef, ids: list[int]) -> list[dict[str, str]]:
    entries = [e for e in await load_entries(ref) if e.id in set(ids)]
    out = []
    for key, _group, label in SECTIONS:
        for row in print_rows([e for e in entries if e.section == key], key):
            out.append(row | {"section": label})
    return out
