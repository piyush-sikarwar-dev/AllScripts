"""Notes tab (Option A): type tiles, date range, searchable list, formatted / original note.

The patient's note index (metadata only) comes from the cached repository function `note_index`;
classification, filtering, counts, search, sort and paging happen here in Python (patients have
hundreds of notes, not millions). Nothing here logs note text or titles — only ids and reasons.
"""

import logging
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.crosswalk import PatientRef
from app.db.app import new_session
from app.formatting import date_us, sort_key, to_clinic_time
from app.lookups.note_categories import NOTE_CATEGORIES, note_categories
from app.models.common import PAGE_SIZE, Pager
from app.models.notes import (
    NoteDetail,
    NoteField,
    NoteFilters,
    NoteListPage,
    NoteRow,
    NotesState,
    RangeChip,
    TypeTile,
)
from app.repositories import source_repository
from app.repositories.appdb import export_selection
from app.services import NotFoundError, call
from app.services.note_format import (
    html_to_lines,
    parse_rx,
    parse_sections,
    redact_ssn,
    split_rx_title,
    text_to_lines,
)

log = logging.getLogger("app.notes")

CATEGORY_KEYS = ("all", *NOTE_CATEGORIES)
RANGES: list[tuple[str, str]] = [("12m", "Last 12 months"), ("3y", "Last 3 years"),
                                 ("all", "All time")]  # fmt: skip
RANGE_KEYS = frozenset(k for k, _ in RANGES) | {"custom"}
SORTS: list[tuple[str, str]] = [("new", "Newest first"), ("old", "Oldest first")]
VIEWS = ("formatted", "original")
NOTE_KINDS = ("document", "transcription")
# export_selection.item_type per note kind (column is 16 characters wide)
EXPORT_TYPES = {"document": "note_doc", "transcription": "note_trans"}


# --- URL state -----------------------------------------------------------------------------------


def parse_note_ref(raw: str | None) -> tuple[str, int] | None:
    """'document-123' → ('document', 123); anything else → None."""
    if not raw or "-" not in raw:
        return None
    kind, _, ident = raw.rpartition("-")
    if kind not in NOTE_KINDS or not ident.isdigit() or len(ident) > 10:
        return None
    return kind, int(ident)


def _date(raw: str | None) -> date | None:
    """ISO (from <input type=date>) or MM/DD/YYYY; anything invalid → None (ignored)."""
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            value = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return value if 1900 <= value.year <= 2200 else None
    return None


def _int(raw: str | None, low: int, high: int) -> int | None:
    if raw is None or not raw.strip().isdigit() or len(raw.strip()) > 9:
        return None
    value = int(raw)
    return value if low <= value <= high else None


def parse_state(params: Mapping[str, str]) -> NotesState:
    cat = params.get("cat", "all")
    rng = params.get("range", "")
    date_from, date_to = _date(params.get("from")), _date(params.get("to"))
    if rng not in RANGE_KEYS:
        rng = "custom" if (date_from or date_to) else "all"
    if rng != "custom":
        date_from = date_to = None
    elif date_from and date_to and date_from > date_to:  # swapped silently
        date_from, date_to = date_to, date_from
    note = params.get("note")
    view = params.get("view", "formatted")
    sort = params.get("sort", "new")
    return NotesState(
        cat=cat if cat in CATEGORY_KEYS else "all",
        range=rng,
        date_from=date_from,
        date_to=date_to,
        q=" ".join((params.get("q") or "").split())[:100],
        sort=sort if sort in ("new", "old") else "new",
        page=_int(params.get("page"), 1, 100_000) or 1,
        note=note if parse_note_ref(note) else None,
        view=view if view in VIEWS else "formatted",
    )


def _today() -> date:
    return to_clinic_time(datetime.now().astimezone()).date()


def _years_ago(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def date_range(
    state: NotesState, earliest: date | None, today: date | None = None
) -> tuple[date, date]:
    """The range applied: chips relative to today; All time = earliest note … today."""
    today = today or _today()
    start = earliest or today
    if state.range == "12m":
        return _years_ago(today, 1) + timedelta(days=1), today
    if state.range == "3y":
        return _years_ago(today, 3) + timedelta(days=1), today
    if state.range == "custom":
        lo, hi = state.date_from or start, state.date_to or max(today, start)
        return (lo, hi) if lo <= hi else (hi, lo)
    return min(start, today), max(today, start)


# --- the note index ------------------------------------------------------------------------------


@dataclass
class NoteMeta:
    ref: str
    kind: str
    id: int
    day: date | None
    sort_key: datetime
    category: str
    title: str  # display title (drug name for prescriptions)
    subtitle: str
    who: str
    app_source: str
    source: str
    encounter_id: int | None
    search_text: str


def _fold(text: str) -> str:
    """Case- and accent-insensitive form for search."""
    normal = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in normal if not unicodedata.combining(c)).casefold()


def _local_day(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return to_clinic_time(value).date() if value.tzinfo else value.date()
    return value


def _meta(n: dict) -> NoteMeta:
    cats = note_categories()
    if n.get("source") == "Pre-2010":  # legacy chart notes (FEATURE_LEGACY_DMZ) are visit notes
        category = "visit"
    else:
        category = cats.classify(n["title"], set(n["map_sources"]), n["kind"] == "transcription")
    title, subtitle = n["title"], ""
    if category == "rx":
        title, subtitle = split_rx_title(n["title"])
    elif n["kind"] == "transcription":
        subtitle = "Dictation"
    else:
        subtitle = n.get("app_source") or ""
    who = n.get("who") or n.get("app_source") or "—"
    app_source = n.get("app_source") or ""
    return NoteMeta(
        ref=f"{n['kind']}-{n['id']}",
        kind=n["kind"],
        id=n["id"],
        day=_local_day(n["date"]),
        sort_key=sort_key(n["date"]),
        category=category,
        title=title,
        subtitle=subtitle,
        who=who,
        app_source=app_source,
        source=n.get("source") or "EMR",
        encounter_id=n.get("encounter_id"),
        search_text=_fold(" ".join((title, subtitle, who, app_source))),
    )


async def note_index(ref: PatientRef) -> list[NoteMeta]:
    rows = await call(source_repository().note_index, ref.emr_id)
    return [_meta(n) for n in rows]


def _in_range(m: NoteMeta, lo: date, hi: date) -> bool:
    return m.day is not None and lo <= m.day <= hi


def _matches(m: NoteMeta, needle: str) -> bool:
    return not needle or all(word in m.search_text for word in needle.split())


def counts_by_category(notes: list[NoteMeta], lo: date, hi: date, q: str) -> dict[str, int]:
    """Tile counts: respect the date range and the search, not the selected type."""
    needle = _fold(q)
    counts = dict.fromkeys(CATEGORY_KEYS, 0)
    for m in notes:
        if _in_range(m, lo, hi) and _matches(m, needle):
            counts["all"] += 1
            counts[m.category] += 1
    return counts


def filtered(notes: list[NoteMeta], state: NotesState, lo: date, hi: date) -> list[NoteMeta]:
    needle = _fold(state.q)
    rows = [m for m in notes if (state.cat == "all" or m.category == state.cat)
            and _in_range(m, lo, hi) and _matches(m, needle)]  # fmt: skip
    rows.sort(key=lambda m: (m.sort_key, m.kind, m.id), reverse=state.sort == "new")
    return rows


# --- tab pieces ----------------------------------------------------------------------------------


def _tile_label(key: str) -> str:
    return "All notes" if key == "all" else note_categories().label(key)


def build_filters(state: NotesState, counts: dict[str, int], lo: date, hi: date) -> NoteFilters:
    return NoteFilters(
        tiles=[
            TypeTile(key=k, label=_tile_label(k), count=counts[k], selected=state.cat == k)
            for k in CATEGORY_KEYS
        ],
        chips=[RangeChip(key=k, label=label, selected=state.range == k) for k, label in RANGES],
        date_from=lo,
        date_to=hi,
    )


def _row(m: NoteMeta) -> NoteRow:
    return NoteRow(ref=m.ref, date=date_us(m.day), who=m.who, category=m.category,
                   badge=note_categories().badge(m.category), title=m.title,
                   subtitle=m.subtitle)  # fmt: skip


def build_list(rows: list[NoteMeta], state: NotesState, lo: date, hi: date) -> NoteListPage:
    pager = Pager(page=state.page, total=len(rows), page_size=PAGE_SIZE)
    if pager.page > pager.pages:
        pager = Pager(page=pager.pages, total=len(rows), page_size=PAGE_SIZE)
    page_rows = rows[pager.offset : pager.offset + PAGE_SIZE]
    context = (f"{_tile_label(state.cat)} · {date_us(lo)} – {date_us(hi)} · "
               f"showing {len(page_rows)} of {len(rows):,}")  # fmt: skip
    return NoteListPage(rows=[_row(m) for m in page_rows], pager=pager, context=context)


@dataclass
class NotesView:
    state: NotesState
    filters: NoteFilters
    page: NoteListPage
    selected: str | None  # the note shown on the right (kept if still in the result)
    selection_changed: bool  # the requested note is no longer in the result


async def notes_view(ref: PatientRef, state: NotesState) -> NotesView:
    notes = await note_index(ref)
    earliest = min((m.day for m in notes if m.day), default=None)
    lo, hi = date_range(state, earliest)
    rows = filtered(notes, state, lo, hi)
    page = build_list(rows, state, lo, hi)
    state = state.model_copy(update={"page": page.pager.page})
    in_result = {m.ref for m in rows}
    selected = state.note if state.note in in_result else (page.rows[0].ref if page.rows else None)
    return NotesView(
        state=state.model_copy(update={"note": selected}),
        filters=build_filters(state, counts_by_category(notes, lo, hi, state.q), lo, hi),
        page=page,
        selected=selected,
        selection_changed=selected != state.note,
    )


# --- one note ------------------------------------------------------------------------------------


def _formatted(meta: NoteMeta, html: str | None, text: str | None) -> dict:
    """Formatted view pieces; format_failed when a prescription printout cannot be parsed."""
    lines = html_to_lines(html) if html else text_to_lines(text or "")
    if meta.category == "rx":
        rx = parse_rx(lines)
        if rx is None:
            log.info("note_format_fallback note=%s reason=rx_unparsed", meta.ref)
            return {"format_failed": True}
        prescriber = meta.who if meta.who != meta.app_source else None
        return {"fields": [NoteField(label=label, value=value, strong=strong)
                           for label, value, strong in rx.rows(prescriber)]}  # fmt: skip
    sections = parse_sections(lines)
    if len(sections) >= 2 and not html:
        return {"fields": [NoteField(label=label, value=value) for label, value in sections]}
    if html:
        return {"formatted_html": html}
    paragraphs = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    if not paragraphs:
        log.info("note_format_fallback note=%s reason=empty", meta.ref)
        return {"format_failed": True}
    return {"formatted_text": paragraphs}


def find_note(notes: list[NoteMeta], note_ref: str) -> NoteMeta:
    meta = next((m for m in notes if m.ref == note_ref), None)
    if meta is None:
        raise NotFoundError(f"note {note_ref}")
    return meta


async def note_detail(
    ref: PatientRef, note_ref: str, view: str = "formatted", in_export: bool = False
) -> NoteDetail:
    """One note of this patient (404 for anything else) with its formatted and original views."""
    if parse_note_ref(note_ref) is None:
        raise NotFoundError(f"note {note_ref}")
    meta = find_note(await note_index(ref), note_ref)
    content = await call(source_repository().note, ref.emr_id, meta.kind, meta.id)
    html = redact_ssn(content["html"]) if content and content.get("html") else None
    text = redact_ssn(content["text"]) if content and content.get("text") else None
    parts = _formatted(meta, html, text) if (html or text) else {}
    view = view if view in VIEWS else "formatted"
    if parts.get("format_failed"):
        view = "original"
    meta_line = " · ".join(x for x in (date_us(meta.day), meta.who,
                                       meta.app_source if meta.app_source != meta.who else "",
                                       meta.source) if x and x != "—")  # fmt: skip
    return NoteDetail(
        ref=meta.ref,
        category=meta.category,
        badge=note_categories().badge(meta.category),
        title=meta.title,
        meta=meta_line,
        source=meta.source,
        view=view,
        original_html=html,
        original_text=text,
        encounter_id=meta.encounter_id,
        in_export=in_export,
        **parts,
    )


# --- "Add to export" selection -------------------------------------------------------------------


def _selected_sync(session_id: str, patient_key: str) -> set[str]:
    with new_session() as db:
        refs = set()
        for kind, item_type in EXPORT_TYPES.items():
            ids = export_selection.selected_ids(db, session_id, patient_key, item_type)
            refs |= {f"{kind}-{i}" for i in ids}
        return refs


def _toggle_sync(session_id: str, patient_key: str, kind: str, item_id: int) -> tuple[bool, int]:
    with new_session() as db:
        added = export_selection.toggle(db, session_id, patient_key, item_id, EXPORT_TYPES[kind])
        return added, export_selection.count_all(db, session_id, patient_key)


async def selected_note_refs(session_id: str | None, patient_key: str) -> set[str]:
    if not session_id:
        return set()
    return await call(_selected_sync, session_id, patient_key)


async def toggle_note_export(ref: PatientRef, session_id: str, note_ref: str) -> tuple[bool, int]:
    """Add / remove one note of this patient; returns (now selected, items selected in total)."""
    parsed = parse_note_ref(note_ref)
    if parsed is None:
        raise NotFoundError(f"note {note_ref}")
    find_note(await note_index(ref), note_ref)
    return await call(_toggle_sync, session_id, ref.patient_key, *parsed)


async def note_choices(ref: PatientRef, refs: set[str]) -> list[tuple[str, str]]:
    """(note ref, "date · type · title") for the export dialog, newest first."""
    if not refs:
        return []
    found = [m for m in await note_index(ref) if m.ref in refs]
    found.sort(key=lambda m: (m.sort_key, m.kind, m.id), reverse=True)
    cats = note_categories()
    return [(m.ref, f"{date_us(m.day)} · {cats.badge(m.category)} · {m.title}") for m in found]


async def notes_tab(ref: PatientRef, state: NotesState, session_id: str | None) -> dict:
    """Everything the full Notes tab needs."""
    view = await notes_view(ref, state)
    detail = None
    if view.selected:
        selection = await selected_note_refs(session_id, ref.patient_key)
        try:
            detail = await note_detail(ref, view.selected, state.view, view.selected in selection)
        except NotFoundError:
            detail = None
    return {"notes_state": view.state, "note_filters": view.filters, "note_page": view.page,
            "note": detail, "note_sorts": SORTS}  # fmt: skip
