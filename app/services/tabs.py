"""Chart tab registry: builds the template context for one tab from its query parameters."""

from collections.abc import Mapping
from typing import Any

from app.crosswalk import PatientRef
from app.services import NotFoundError
from app.services.documents import documents_tab, scan_store_configured
from app.services.labs import build_filters, labs_tab
from app.services.meds import meds_tab
from app.services.notes import note_detail, notes_tab, parse_note_ref
from app.services.overview import overview
from app.services.problems import problem_groups
from app.services.visits import visit_list
from app.services.vitals import vitals_tab

TABS: list[tuple[str, str]] = [
    ("overview", "Overview"),
    ("visits", "Visits"),
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


async def tab_context(ref: PatientRef, name: str, params: Mapping[str, str]) -> dict[str, Any]:
    """Context for `partials/tab_<name>.html`.

    `state` holds the query parameters that describe the tab's current view; it is used for pager
    links and for the URL pushed into the browser history (`/patients/<key>?tab=<name>&...`).
    """
    page = _int(params.get("page"))
    ctx: dict[str, Any] = {}
    state: dict[str, Any] = {}

    if name == "overview":
        ctx["overview"] = await overview(ref)
    elif name == "visits":
        vl = await visit_list(ref, page, params.get("filter", "office"), _int(params.get("visit")))
        ctx["visit_list"] = vl
        state = {"filter": vl.filter}
    elif name == "notes":
        ctx["notes"], ctx["pager"] = await notes_tab(ref, page)
        selected = parse_note_ref(params.get("note"))
        if selected is None and ctx["notes"]:
            selected = (ctx["notes"][0].kind, ctx["notes"][0].id)
        ctx["selected_note"] = None
        if selected is not None:
            try:
                ctx["selected_note"] = await note_detail(ref, *selected)
            except NotFoundError:
                ctx["selected_note"] = None
    elif name == "problems":
        ctx["groups"] = await problem_groups(ref)
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
        ctx["documents"], ctx["pager"], ctx["doc_types"], doc_type = await documents_tab(
            ref, page, params.get("type", "")
        )
        ctx["doc_type"] = doc_type
        ctx["scan_store_configured"] = scan_store_configured()
        state = {"type": doc_type}
    else:
        raise KeyError(name)

    ctx["state"] = {k: v for k, v in state.items() if v}
    return ctx
