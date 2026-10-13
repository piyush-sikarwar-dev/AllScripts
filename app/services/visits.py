"""Visits tab (Option C): activity strip, visit list (one visit = one encounter), structured note.

All data comes from the cached repository functions visits_page / visits_activity / encounter;
this module only shapes it into view models. Nothing here logs patient data.
"""

import asyncio
from collections.abc import Mapping

from app.crosswalk import PatientRef
from app.db.app import new_session
from app.formatting import date_us, or_dash, sort_key, time_local
from app.models.chart import DocumentLink
from app.models.common import PAGE_SIZE, Pager
from app.models.visits import (
    EncounterDetail,
    NoteSectionRow,
    OriginalBlock,
    VisitActivity,
    VisitListPage,
    VisitRow,
    VisitsState,
    YearBar,
)
from app.repositories import source_repository
from app.repositories.appdb import export_selection
from app.services import NotFoundError, call
from app.services.note_parser import original_text, parse_note
from app.services.vitals import vital_values

VISIT_TYPES: list[tuple[str, str]] = [
    ("office", "Office visits"),
    ("all", "All entries"),
    ("phone", "Phone encounters"),
    ("lab", "Lab reviews"),
    ("annual", "Annual exams"),
]
VISIT_TYPE_KEYS = frozenset(k for k, _ in VISIT_TYPES)
VIEWS = ("structured", "original")
BAR_AREA = 70


def _int(raw: str | None, low: int, high: int) -> int | None:
    if raw is None or not raw.strip().isdigit() or len(raw.strip()) > 9:
        return None
    value = int(raw)
    return value if low <= value <= high else None


def parse_state(params: Mapping[str, str]) -> VisitsState:
    vtype = params.get("type", "office")
    view = params.get("view", "structured")
    return VisitsState(
        type=vtype if vtype in VISIT_TYPE_KEYS else "office",
        year=_int(params.get("year"), 1900, 2200),
        q=" ".join((params.get("q") or "").split())[:100],
        page=_int(params.get("page"), 1, 100_000) or 1,
        visit=_int(params.get("visit"), 1, 2_000_000_000),
        view=view if view in VIEWS else "structured",
    )


def category(state: VisitsState) -> str | None:
    return None if state.type == "all" else state.type


# --- activity strip ------------------------------------------------------------------------------


def year_bars(counts: dict[int, int], selected: int | None) -> list[YearBar]:
    """One bar per year from the first to the last year with visits (gaps filled with 0)."""
    if not counts:
        return []
    busiest = max(counts.values()) or 1
    bars = []
    for year in range(min(counts), max(counts) + 1):
        count = counts.get(year, 0)
        height = max(3, round(count / busiest * BAR_AREA)) if count else 0
        css = "bar" if selected is None else ("bar bar--on" if year == selected else "bar bar--dim")
        bars.append(YearBar(year=year, count=count, height=height, y=BAR_AREA - height,
                            selected=year == selected, bar_class=css))  # fmt: skip
    return bars


async def activity(ref: PatientRef, state: VisitsState) -> VisitActivity:
    a = await call(source_repository().visits_activity, ref.emr_id, category(state))
    provider = f"{a['top_provider']} · {a['top_provider_count']}" if a["top_provider"] else "—"
    diagnosis = f"{a['top_diagnosis']} · {a['top_diagnosis_count']}" if a["top_diagnosis"] else "—"
    return VisitActivity(
        total=a["total"],
        last_visit=date_us(a["last_visit"]),
        top_provider=provider,
        top_diagnosis=diagnosis,
        years=year_bars(a["years"], state.year),
        selected_year=state.year,
    )


# --- visit list ----------------------------------------------------------------------------------


async def visit_list(ref: PatientRef, state: VisitsState) -> VisitListPage:
    data = await call(
        source_repository().visits_page, ref.emr_id, category(state), state.year,
        state.q or None, state.page,
    )  # fmt: skip
    pager = Pager(page=state.page, total=data["total"], page_size=PAGE_SIZE)
    noun = "visit" if data["total"] == 1 else "visits"
    years = f"Year {state.year}" if state.year else "All years"
    return VisitListPage(
        rows=[
            VisitRow(
                id=r["encounter_id"],
                date=date_us(r["date"]),
                type=or_dash(r["visit_type"]),
                diagnoses=", ".join(title for _code, title in r["diagnoses"]),
                provider_short=or_dash(r["provider_short"]),
            )
            for r in data["rows"]
        ],
        pager=pager,
        context=f"{years} · {data['total']:,} {noun}",
    )


async def newest_visit_id(ref: PatientRef, state: VisitsState) -> int | None:
    first = await call(
        source_repository().visits_page, ref.emr_id, category(state), state.year,
        state.q or None, 1,
    )  # fmt: skip
    return first["rows"][0]["encounter_id"] if first["rows"] else None


# --- visit detail --------------------------------------------------------------------------------


def _vitals_lines(readings: list[dict]) -> list[str]:
    lines = []
    for i, r in enumerate(readings):
        values = " · ".join(f"{v.label} {v.value}" for v in vital_values(r))
        if not values:
            continue
        if len(readings) > 1 and i > 0:
            values = f"{time_local(r['date'])}: {values}"
        lines.append(values)
    return lines


def _doc_meta(d: dict) -> str:
    parts = [date_us(d.get("created")), (d.get("author") or "").strip()]
    return " · ".join(p for p in parts if p and p != "—")


def build_detail(enc: dict, view: str, in_export: bool) -> EncounterDetail:
    rows: list[NoteSectionRow] = []
    # 1. Parsed text notes (chief complaint, history, other named sections, plain notes) in order.
    merged: dict[str, list[str]] = {}
    for raw in enc["text_notes"]:
        for section in parse_note(raw, encounter_id=enc["encounter_id"]).sections:
            merged.setdefault(section.title, []).extend(section.paragraphs)
    rows += [NoteSectionRow(label=t, kind="text", paragraphs=p) for t, p in merged.items() if p]
    # 2. The rendered clinical note documents (History & Physical) — sanitised HTML.
    rows += [
        NoteSectionRow(label="Clinical note", kind="html", html=d["html"],
                       caption=" · ".join(x for x in (d["title"], _doc_meta(d)) if x))
        for d in enc["note_documents"]
    ]  # fmt: skip
    vitals = _vitals_lines(enc["vitals"])
    if vitals:
        rows.append(NoteSectionRow(label="Vitals", kind="text", paragraphs=vitals))
    if enc["assessment"]:
        rows.append(NoteSectionRow(label="Assessment", kind="dx", dx=enc["assessment"]))
    if enc["plan"]:
        rows.append(NoteSectionRow(label="Plan", kind="list", items=enc["plan"]))
    if enc["addenda"]:
        rows.append(NoteSectionRow(label="Addenda", kind="text", paragraphs=enc["addenda"]))
    if enc["other_documents"]:
        rows.append(NoteSectionRow(label="Other documents", kind="links", links=[
            DocumentLink(kind="document", id=d["id"], title=d["title"], meta=_doc_meta(d))
            for d in enc["other_documents"]
        ]))  # fmt: skip

    original = [OriginalBlock(title="Visit note" if len(enc["text_notes"]) == 1
                              else f"Visit note {i}", text=original_text(raw))
                for i, raw in enumerate(enc["text_notes"], 1)]  # fmt: skip
    original += [
        OriginalBlock(title=" · ".join(x for x in (d["title"], _doc_meta(d)) if x), html=d["html"])
        for d in enc["note_documents"]
    ]
    signed = "Signed" if enc["signed"] else "Unsigned"
    subline = " · ".join(x for x in (enc["provider"], enc["location"], signed) if x and x != "—")
    return EncounterDetail(
        id=enc["encounter_id"],
        title=f"{date_us(enc['date'])} · {or_dash(enc['visit_type'])}",
        subline=subline,
        source=enc["source"],
        view=view if view in VIEWS else "structured",
        rows=rows,
        original=original,
        in_export=in_export,
    )


async def encounter_detail(
    ref: PatientRef, encounter_id: int, view: str, in_export: bool = False
) -> EncounterDetail:
    enc = await call(source_repository().encounter, ref.emr_id, encounter_id)
    if enc is None:
        raise NotFoundError(f"encounter {encounter_id}")
    return build_detail(enc, view, in_export)


async def visits_tab(ref: PatientRef, state: VisitsState, selection: set[int]) -> dict:
    """Everything the full Visits tab needs, loaded together."""
    act, page = await asyncio.gather(activity(ref, state), visit_list(ref, state))
    visit_id = state.visit
    if visit_id is None and page.rows:
        visit_id = page.rows[0].id
    detail = None
    if visit_id is not None:
        try:
            detail = await encounter_detail(ref, visit_id, state.view, visit_id in selection)
        except NotFoundError:
            detail = None
    state = state.model_copy(update={"visit": detail.id if detail else None})
    return {"visits_state": state, "activity": act, "visit_page": page, "detail": detail,
            "visit_types": VISIT_TYPES}  # fmt: skip


# --- "Add to export" selection (app DB, per session) ---------------------------------------------


def _selected_sync(session_id: str, patient_key: str) -> set[int]:
    with new_session() as db:
        return export_selection.selected_ids(db, session_id, patient_key)


def _toggle_sync(session_id: str, patient_key: str, encounter_id: int) -> tuple[bool, int]:
    with new_session() as db:
        added = export_selection.toggle(db, session_id, patient_key, encounter_id)
        return added, export_selection.count_all(db, session_id, patient_key)


async def selected_visit_ids(session_id: str | None, patient_key: str) -> set[int]:
    if not session_id:
        return set()
    return await call(_selected_sync, session_id, patient_key)


async def visit_choices(ref: PatientRef, ids: set[int]) -> list[tuple[int, str]]:
    """(encounter id, "date · type") for the export dialog, newest first."""
    repo = source_repository()
    encs = await asyncio.gather(*(call(repo.encounter, ref.emr_id, i) for i in ids))
    found = sorted((e for e in encs if e), key=lambda e: (sort_key(e["date"]), e["encounter_id"]),
                   reverse=True)  # fmt: skip
    return [(e["encounter_id"], f"{date_us(e['date'])} · {or_dash(e['visit_type'])}")
            for e in found]  # fmt: skip


async def toggle_export(ref: PatientRef, session_id: str, encounter_id: int) -> tuple[bool, int]:
    """Add/remove one visit of this patient; returns (now selected, items selected in total)."""
    enc = await call(source_repository().encounter, ref.emr_id, encounter_id)
    if enc is None:
        raise NotFoundError(f"encounter {encounter_id}")
    return await call(_toggle_sync, session_id, ref.patient_key, encounter_id)
