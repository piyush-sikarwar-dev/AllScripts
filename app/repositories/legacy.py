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
