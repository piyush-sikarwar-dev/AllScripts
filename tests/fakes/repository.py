"""In-memory stand-in for the source repositories (used when USE_FAKE_DATA=true and in unit tests).

Function names and return shapes are the contract the real `app/repositories/` modules implement
from Phase 4 on: plain dicts / lists of dicts with raw values.
"""

from datetime import date

from app.documents.render import sanitize_html
from tests.fakes.data import PATIENTS, PATIENTS_BY_ID, FakePatient


def totals() -> dict[str, int]:
    return {
        "patients": len(PATIENTS),
        "encounters": sum(len(p.visits) for p in PATIENTS),
        "lab_results": sum(len(p.labs) for p in PATIENTS),
        "scanned_documents": sum(1 for p in PATIENTS for d in p.documents if d["kind"] == "scan"),
    }


def _summary(p: FakePatient) -> dict:
    return {
        "emr_id": p.emr_id,
        "last_name": p.last_name,
        "first_name": p.first_name,
        "middle_initial": p.middle_initial,
        "dob": p.dob,
        "sex": p.sex,
        "chart_id": p.chart_id,
        "deceased": p.deceased,
        "ntier_id": p.ntier_id,
        "dmz_id": p.dmz_id,
    }


def search_patients(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: date | None,
    chart_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    def matches(p: FakePatient) -> bool:
        return (
            (last_name is None or p.last_name.lower().startswith(last_name.lower()))
            and (first_name is None or p.first_name.lower().startswith(first_name.lower()))
            and (dob is None or p.dob == dob)
            and (chart_id is None or p.chart_id == chart_id)
        )

    found = sorted(
        (p for p in PATIENTS if matches(p)), key=lambda p: (p.last_name, p.first_name, p.emr_id)
    )
    return [_summary(p) for p in found[offset : offset + limit]], len(found)


def last_visits(emr_ids: list[int]) -> dict[int, object]:
    result = {}
    for emr_id in emr_ids:
        visits = PATIENTS_BY_ID[emr_id].visits
        if visits:
            result[emr_id] = max(v["start"] for v in visits)
    return result


def get_patient(emr_id: int) -> dict | None:
    p = PATIENTS_BY_ID.get(emr_id)
    if p is None:
        return None
    return _summary(p) | {
        "phone": p.phone,
        "address": p.address,
        "city": p.city,
        "state": p.state,
        "zip": p.zip,
        "pm_account": p.pm_account,
        "primary_insurance": p.primary_insurance,
    }


def patient_names(emr_ids: list[int]) -> dict[int, str]:
    return {
        i: f"{PATIENTS_BY_ID[i].last_name}, {PATIENTS_BY_ID[i].first_name}"
        for i in emr_ids
        if i in PATIENTS_BY_ID
    }


def visits(emr_id: int, office_only: bool = False) -> list[dict]:
    rows = list(PATIENTS_BY_ID[emr_id].visits)
    return [v for v in rows if v["is_office_visit"]] if office_only else rows


def last_visit(emr_id: int) -> dict | None:
    visits = PATIENTS_BY_ID[emr_id].visits
    if not visits:
        return None
    v = max(visits, key=lambda v: v["start"])
    return {k: v[k] for k in ("start", "visit_type", "provider", "location")}


def visit(emr_id: int, contact_id: int) -> dict | None:
    return next((v for v in PATIENTS_BY_ID[emr_id].visits if v["contact_id"] == contact_id), None)


def visit_vitals(emr_id: int, contact_id: int) -> list[dict]:
    rows = [v for v in PATIENTS_BY_ID[emr_id].vitals if v["contact_id"] == contact_id]
    return sorted(rows, key=lambda v: (v["date"], v["id"]))


def notes(emr_id: int) -> list[dict]:
    return [n | {"kind": "document"} for n in PATIENTS_BY_ID[emr_id].notes]


def note_index(emr_id: int) -> list[dict]:
    """Notes tab index: the synthetic clinical notes + the older fake notes (as documents)."""
    p = PATIENTS_BY_ID[emr_id]
    rows = [{k: v for k, v in n.items() if k not in ("html", "text")} for n in p.clinical_notes]
    rows += [
        {"kind": "document", "id": n["id"], "date": n["date"], "title": n["title"],
         "who": n["author"], "app_source": None, "map_sources": [], "source": n["source"],
         "encounter_id": None}
        for n in p.notes
    ]  # fmt: skip
    return rows


def note(emr_id: int, kind: str, note_id: int) -> dict | None:
    p = PATIENTS_BY_ID[emr_id]
    synthetic = next(
        (n for n in p.clinical_notes if n["kind"] == kind and n["id"] == note_id), None
    )
    if synthetic is not None:
        html = sanitize_html(synthetic["html"]) if synthetic.get("html") else None
        return synthetic | {"html": html, "text": synthetic.get("text"), "author": synthetic["who"]}
    found = next((n for n in PATIENTS_BY_ID[emr_id].notes if n["id"] == note_id), None)
    if found is None or kind != "document":
        return None
    text = "Placeholder note text generated for interface review only."
    return found | {"kind": kind, "html": None, "text": text}


def history(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].history)


def medications(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].medications)


def labs(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].labs)


def vitals(emr_id: int) -> list[dict]:
    return list(PATIENTS_BY_ID[emr_id].vitals)


def documents(emr_id: int) -> list[dict]:
    return [
        d | {"kind": "scan" if d["kind"] == "scan" else "document"}
        for d in PATIENTS_BY_ID[emr_id].documents
    ]


def document_pages(emr_id: int, document_id: int) -> dict | None:
    d = next((d for d in PATIENTS_BY_ID[emr_id].documents if d["id"] == document_id), None)
    if d is None or d["kind"] != "scan":
        return None
    pages = [
        {
            "page_id": document_id * 100 + n,
            "location": f"\\\\amhs-db1\\hmscan\\fake\\{document_id}-{n}",
        }
        for n in range(1, d["pages"] + 1)
    ]
    return {
        "id": document_id,
        "date": d["date"],
        "type": d["type"],
        "title": d["title"],
        "pages": pages,
        "source": "EMR",
    }


# --- Visits tab (Option C): fake data has one contact per encounter -------------------------


def _fake_category(v: dict) -> str:
    return "office" if v["is_office_visit"] else "other"


def _fake_encounters(emr_id: int, category: str | None) -> list[dict]:
    rows = [
        v
        for v in PATIENTS_BY_ID[emr_id].visits
        if category is None or _fake_category(v) == category
    ]
    return sorted(rows, key=lambda v: (v["start"], v["encounter_id"]), reverse=True)


def _fake_summary(v: dict) -> dict:
    last, _, first = v["provider"].partition(", ")
    return {
        "encounter_id": v["encounter_id"],
        "date": v["start"],
        "visit_type": v["visit_type"],
        "category": _fake_category(v),
        "signed": v["signed"],
        "provider": v["provider"],
        "provider_short": f"{first[:1]}. {last}" if first else last,
        "location": v["location"],
        "source": "EMR",
    }


def visits_page(
    emr_id: int, category: str | None, year: int | None, q: str | None, page: int
) -> dict:
    rows = _fake_encounters(emr_id, category)
    if year is not None:
        rows = [v for v in rows if v["start"].year == year]
    if q:
        needle = q.lower()
        rows = [
            v
            for v in rows
            if needle in v["provider"].lower()
            or any(needle in t.lower() or needle in c.lower() for t, c in v["diagnoses"])
        ]
    start = (page - 1) * 25
    return {
        "total": len(rows),
        "rows": [
            _fake_summary(v) | {"diagnoses": [(c, t) for t, c in v["diagnoses"]]}
            for v in rows[start : start + 25]
        ],
    }


def visits_activity(emr_id: int, category: str | None) -> dict:
    rows = _fake_encounters(emr_id, category)
    years: dict[int, int] = {}
    providers: dict[str, list] = {}
    diagnoses: dict[tuple[str, str], list] = {}
    for v in rows:
        years[v["start"].year] = years.get(v["start"].year, 0) + 1
        providers.setdefault(v["provider"], []).append(v["start"])
        for title, code in v["diagnoses"]:
            diagnoses.setdefault((code, title), []).append(v["start"])
    top_p = max(providers.items(), key=lambda kv: (len(kv[1]), max(kv[1])), default=None)
    top_d = max(diagnoses.items(), key=lambda kv: (len(kv[1]), max(kv[1])), default=None)
    return {
        "years": years,
        "total": len(rows),
        "last_visit": rows[0]["start"] if rows else None,
        "top_provider": top_p[0] if top_p else None,
        "top_provider_count": len(top_p[1]) if top_p else 0,
        "top_diagnosis": top_d[0][1] if top_d else None,
        "top_diagnosis_code": top_d[0][0] if top_d else None,
        "top_diagnosis_count": len(top_d[1]) if top_d else 0,
    }


def encounter(emr_id: int, encounter_id: int) -> dict | None:
    v = next((v for v in PATIENTS_BY_ID[emr_id].visits if v["encounter_id"] == encounter_id), None)
    if v is None:
        return None
    readings = [r for r in PATIENTS_BY_ID[emr_id].vitals if r["contact_id"] == v["contact_id"]]
    return _fake_summary(v) | {
        "assessment": [(c, t) for t, c in v["diagnoses"]],
        "plan": list(v["plan"]),
        "addenda": list(v["addenda"]),
        "note_documents": [],
        "other_documents": [],
        "text_notes": [v["note_text"]] if v["note_text"] else [],
        "vitals": sorted(readings, key=lambda r: (r["date"], r["id"])),
    }


# --- Problems & allergies tab (Option B) ---------------------------------------------------------


def history_entries(emr_id: int) -> list[dict]:
    return [dict(e) for e in PATIENTS_BY_ID[emr_id].hx_entries]


def history_changes(emr_id: int, hx_id: int) -> list[dict]:
    return [dict(r) for r in PATIENTS_BY_ID[emr_id].hx_revisions.get(hx_id, [])]


def appointments(emr_id: int, ntier_id: int | None) -> list[dict]:
    return [dict(a) for a in PATIENTS_BY_ID[emr_id].appointments]
