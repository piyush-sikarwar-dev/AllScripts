"""Real data for the separate "Pre-2010 records" section (DMZ legacy chart, 2002 – 2010).

Same function names and shapes as `tests/fakes/legacy.py`. Nothing here is used by the current
(EMR / PM) chart, patient list, totals or exports — the legacy chart is kept fully separate.
"""

from typing import Any

from app.documents.render import rtf_to_text
from app.formatting import sort_key
from app.repositories import dmz
from app.repositories.base import parallel
from app.repositories.cache import cached


def search(
    *,
    last_name: str | None,
    first_name: str | None,
    dob: Any,
    legacy_id: str | None,
    offset: int,
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    rows = dmz.legacy_patient_search(last_name, first_name, dob, legacy_id, offset, limit)
    total = int(rows[0]["total_count"]) if rows else 0
    return rows, total


@cached
def patient(person_key: int) -> dict[str, Any] | None:
    return dmz.legacy_patient(person_key)


@cached
def notes(person_key: int) -> list[dict[str, Any]]:
    """Chart-note headers, newest first (text is read one note at a time)."""
    rows = dmz.legacy_notes(person_key)
    rows.sort(key=lambda r: (sort_key(r["service_date"]), r["note_id"]), reverse=True)
    return rows


@cached
def note_text(person_key: int, note_id: int) -> dict[str, Any] | None:
    """One note's text (RTF converted to plain text). None when the note isn't this patient's."""
    rows = dmz.legacy_note_text(person_key, note_id)
    if not rows:
        return None
    parts = [rtf_to_text(r["note_text"] or "") for r in rows]
    return {
        "note_id": note_id,
        "service_date": rows[0]["service_date"],
        "text": "\n\n".join(p for p in parts if p),
    }


@cached
def problems(person_key: int) -> list[dict[str, Any]]:
    """Problem list, newest onset first."""
    rows = dmz.legacy_problems(person_key)
    rows.sort(key=lambda r: (sort_key(r["onset_date"]), r["problem_id"]), reverse=True)
    return rows


@cached
def allergies(person_key: int) -> list[dict[str, Any]]:
    """Allergies (newest first), each with its list of recorded reactions."""
    rows, reactions = parallel(
        lambda: dmz.legacy_allergies(person_key),
        lambda: dmz.legacy_allergy_reactions(person_key),
    )
    by_allergy: dict[int, list[str]] = {}
    for r in reactions:
        if r["reaction"]:
            by_allergy.setdefault(r["allergy_id"], []).append(r["reaction"])
    for r in rows:
        r["reactions"] = by_allergy.get(r["allergy_id"], [])
    rows.sort(key=lambda r: (sort_key(r["noted_date"]), r["allergy_id"]), reverse=True)
    return rows


@cached
def medications(person_key: int) -> list[dict[str, Any]]:
    """Medication entries, oldest first (the service groups them by med_id)."""
    rows = dmz.legacy_medications(person_key)
    rows.sort(key=lambda r: (sort_key(r["date_of_service"] or r["date_written"]), r["entry_id"]))
    return rows


@cached
def clinical_items(person_key: int) -> list[dict[str, Any]]:
    """Recorded lab and vital values, newest first."""
    rows = dmz.legacy_clinical_items(person_key)
    rows.sort(key=lambda r: (sort_key(r["service_datetime"]), r["item_id"]), reverse=True)
    return rows


@cached
def documents(person_key: int) -> list[dict[str, Any]]:
    """Scanned documents, newest document date first."""
    rows = dmz.legacy_documents(person_key)
    rows.sort(key=lambda r: (sort_key(r["doc_date"]), r["document_id"]), reverse=True)
    return rows


def document_file(person_key: int, document_id: int) -> dict[str, Any] | None:
    return dmz.legacy_document_file(person_key, document_id)


def _order_date(order: dict[str, Any]) -> Any:
    return order.get("service_date") or order.get("order_date") or order.get("result_date")


@cached
def lab_reports(person_key: int) -> list[dict[str, Any]]:
    """Lab orders (newest first), each with its tests; each test with its diagnoses and results;
    each result with its lab comment lines and staff follow-up comments."""
    orders, tests, results, lab_comments, task_comments, diagnoses = parallel(
        lambda: dmz.legacy_lab_orders(person_key),
        lambda: dmz.legacy_lab_tests(person_key),
        lambda: dmz.legacy_lab_results(person_key),
        lambda: dmz.legacy_lab_result_comments(person_key),
        lambda: dmz.legacy_lab_task_comments(person_key),
        lambda: dmz.legacy_lab_diagnoses(person_key),
    )
    by_result: dict[int, dict[str, list]] = {}
    for c in sorted(lab_comments, key=lambda c: c["line_no"] or 0):
        by_result.setdefault(c["result_id"], {"lab": [], "staff": []})["lab"].append(c["comment"])
    for c in sorted(task_comments, key=lambda c: (sort_key(c["created_at"]), c["line_no"] or 0)):
        by_result.setdefault(c["result_id"], {"lab": [], "staff": []})["staff"].append(
            {"comment": c["comment"], "created_at": c["created_at"]}
        )
    results_by_test: dict[int, list[dict[str, Any]]] = {}
    for r in sorted(results, key=lambda r: (r["sequence_num"] or 0, r["result_id"])):
        found = by_result.get(r["result_id"], {"lab": [], "staff": []})
        r["lab_comments"], r["staff_comments"] = found["lab"], found["staff"]
        results_by_test.setdefault(r["test_id"], []).append(r)
    dx_by_test: dict[int, list[dict[str, Any]]] = {}
    for d in sorted(diagnoses, key=lambda d: d["priority"] or 0):
        dx_by_test.setdefault(d["test_id"], []).append(d)
    tests_by_order: dict[int, list[dict[str, Any]]] = {}
    for t in sorted(tests, key=lambda t: t["test_id"]):
        t["results"] = results_by_test.get(t["test_id"], [])
        t["diagnoses"] = dx_by_test.get(t["test_id"], [])
        tests_by_order.setdefault(t["order_id"], []).append(t)
    for o in orders:
        o["tests"] = tests_by_order.get(o["order_id"], [])
    orders.sort(key=lambda o: (sort_key(_order_date(o)), o["order_id"]), reverse=True)
    return orders


@cached
def note_result_links(person_key: int) -> dict[int, list[int]]:
    """Chart note id → the lab test ids (Orders.LabTests.systestorderno) that note reports."""
    links: dict[int, list[int]] = {}
    for r in dmz.legacy_note_result_links(person_key):
        links.setdefault(int(r["note_id"]), []).append(int(r["test_id"]))
    return links


@cached
def about(person_key: int) -> dict[str, Any]:
    """External IDs, pharmacies and consent flags of the legacy patient."""
    ids, pharmacies, consent = parallel(
        lambda: dmz.legacy_external_ids(person_key),
        lambda: dmz.legacy_pharmacies(person_key),
        lambda: dmz.legacy_consent(person_key),
    )
    return {
        "external_ids": ids,
        "pharmacies": pharmacies,
        "consent": consent[0] if consent else None,
    }


def photo(person_key: int) -> bytes | None:
    return dmz.legacy_photo(person_key)


@cached
def past_history(person_key: int) -> list[dict[str, Any]]:
    """Past history entries, newest first (then in chart order)."""
    rows = dmz.legacy_past_history(person_key)
    rows.sort(key=lambda r: (sort_key(r["recorded_at"]), -(r["row_no"] or 0)), reverse=True)
    return rows


@cached
def procedures(person_key: int) -> list[dict[str, Any]]:
    rows = dmz.legacy_procedures(person_key)
    rows.sort(key=lambda r: (sort_key(r["date_of_service"]), r["procedure_id"]), reverse=True)
    return rows


@cached
def account_notes(person_key: int) -> list[dict[str, Any]]:
    """Account notes, newest first."""
    rows = dmz.legacy_account_notes(person_key)
    rows.sort(key=lambda r: (sort_key(r["entered_at"]), r["order_no"] or 0), reverse=True)
    return rows
