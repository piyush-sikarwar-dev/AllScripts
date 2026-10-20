"""Chart tab registry: builds the template context for one tab from its query parameters."""

import asyncio
from collections.abc import Mapping
from typing import Any

from app.crosswalk import PatientRef
from app.services import NotFoundError
from app.services.appointments import appointments_tab
from app.services.documents import (
    document_viewer,
    documents_tab,
    parse_doc_ref,
    scan_store_configured,
)
from app.services.history_service import history_view
from app.services.labs import build_filters, labs_tab
from app.services.meds import meds_tab
from app.services.notes_service import notes_tab
from app.services.notes_service import parse_state as parse_notes_state
from app.services.overview import overview
from app.services.patient_details import patient_details
from app.services.visits import parse_state, selected_visit_ids, visits_tab
from app.services.vitals import vitals_tab

TABS: list[tuple[str, str]] = [
    ("overview", "Overview"),
    ("visits", "Visits"),
    ("appointments", "Appointments"),
    ("notes", "Notes"),
    ("problems", "Problems & allergies"),
    ("meds", "Medications"),
    ("labs", "Lab results"),
    ("vitals", "Vitals"),
    ("docs", "Documents"),
]
TAB_NAMES = frozenset(name for name, _ in TABS)
TAB_LABELS = dict(TABS)


def _int(raw: str | None) -> int | None:
    if raw is None or not raw.isdigit() or len(raw) > 9:
        return None
    return int(raw)


async def tab_context(
    ref: PatientRef, name: str, params: Mapping[str, str], session_id: str | None = None
) -> dict[str, Any]:
    """Context for `partials/tab_<name>.html`.

    `state` holds the query parameters that describe the tab's current view; it is used for pager
    links and for the URL pushed into the browser history (`/patients/<key>?tab=<name>&...`).
    """
    page = _int(params.get("page"))
    ctx: dict[str, Any] = {}
    state: dict[str, Any] = {}

    if name == "overview":
        show_archived = params.get("archived") == "1"
        ctx["overview"], ctx["details"] = await asyncio.gather(
            overview(ref), patient_details(ref, show_archived)
        )
        state = {"archived": "1"} if show_archived else {}
    elif name == "visits":
        selection = await selected_visit_ids(session_id, ref.patient_key)
        ctx.update(await visits_tab(ref, parse_state(params), selection))
        state = ctx["visits_state"].params(tab=None)
    elif name == "appointments":
        ctx.update(await appointments_tab(ref, params))
        state = ctx["appts_state"].params()
    elif name == "notes":
        ctx.update(await notes_tab(ref, parse_notes_state(params), session_id))
        state = ctx["notes_state"].params(tab=None)
    elif name == "problems":
        view = await history_view(ref, params, session_id)
        ctx.update(history_state=view.state, history_rail=view.rail, history_rows=view.rows,
                   history_detail=view.detail)  # fmt: skip
        state = view.state.params(tab=None)
    elif name == "meds":
        ctx["meds"], ctx["pager"], med_filter = await meds_tab(ref, page, params.get("filter", ""))
        state = {"filter": med_filter}
    elif name == "labs":
        filters = build_filters(
            params.get("from", ""),
            params.get("to", ""),
            params.get("test", ""),
            params.get("view", ""),
        )
        ctx["labs"], ctx["pager"], ctx["test_names"] = await labs_tab(ref, page, filters)
        ctx["filters"] = filters
        state = {
            "view": filters.view,
            "test": filters.test,
            "from": filters.date_from,
            "to": filters.date_to,
        }
    elif name == "vitals":
        ctx["vitals"], ctx["pager"] = await vitals_tab(ref, page)
    elif name == "docs":
        (ctx["documents"], ctx["pager"], ctx["doc_types"], doc_type, doc_source,
         ctx["doc_sources"]) = await documents_tab(
            ref, page, params.get("type", ""), params.get("src", "")
        )  # fmt: skip
        ctx["doc_type"], ctx["doc_source"] = doc_type, doc_source
        ctx["scan_store_configured"] = scan_store_configured()
        state = {"type": doc_type, "src": doc_source}
        selected = parse_doc_ref(params.get("doc"))
        if selected is None and ctx["documents"]:
            selected = (ctx["documents"][0].kind, ctx["documents"][0].id)
        ctx["viewer"] = None
        if selected is not None:
            try:
                ctx["viewer"] = await document_viewer(
                    ref, *selected, _int(params.get("docpage")) or 1
                )
            except NotFoundError:
                ctx["viewer"] = None
    else:
        raise KeyError(name)

    ctx["state"] = {k: v for k, v in state.items() if v}
    return ctx
