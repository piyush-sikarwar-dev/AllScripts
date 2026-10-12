"""Build the patient crosswalk (EMR ↔ Ntier, merges) into the app database.

Pure functions over ID rows so the rules are unit-tested without any database:
  - one row per EMR patient, key "EMR:<IMREDEM_CODE>";
  - no Ntier match            → ntier_id NULL, match_method "None";
  - exactly one Ntier match   → "ExactId";
  - several Ntier matches     → the one whose Active_Patient_ID = Patient_ID (else the lowest),
                                "ExactId-ambiguous";
  - merged-away EMR patients  → emr_id = surviving record (chains followed), "Merged".
DMZ matching is Phase 10.
"""

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.repositories.appdb.models import PatientCrosswalk


def _pick_ntier(candidates: list[tuple[int, int | None]]) -> tuple[int | None, str]:
    ids = sorted({ntier_id for ntier_id, _active in candidates})
    if not ids:
        return None, "None"
    if len(ids) == 1:
        return ids[0], "ExactId"
    active = sorted({ntier_id for ntier_id, act in candidates if act == ntier_id})
    return (active[0] if active else ids[0]), "ExactId-ambiguous"


def resolve_merges(merges: Iterable[tuple[int, int]]) -> dict[int, int]:
    """original → final surviving id, following chains (A→B→C) and ignoring cycles."""
    direct = {orig: cur for orig, cur in merges if orig != cur}
    final: dict[int, int] = {}
    for orig in direct:
        seen = {orig}
        current = direct[orig]
        while current in direct and current not in seen:
            seen.add(current)
            current = direct[current]
        final[orig] = current
    return final


def build_crosswalk_rows(
    link_rows: Iterable[dict[str, Any]],
    merge_rows: Iterable[dict[str, Any]],
    built_at: datetime,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    candidates: dict[int, list[tuple[int, int | None]]] = defaultdict(list)
    for row in link_rows:
        emr_id = int(row["emr_id"])
        candidates.setdefault(emr_id, [])
        if row.get("ntier_id") is not None:
            active = row.get("ntier_active_id")
            candidates[emr_id].append((int(row["ntier_id"]), int(active) if active else None))

    picked = {emr_id: _pick_ntier(c) for emr_id, c in candidates.items()}
    merged = resolve_merges((int(m["original_id"]), int(m["current_id"])) for m in merge_rows)

    rows: list[dict[str, Any]] = []
    summary: Counter[str] = Counter()
    for emr_id, (ntier_id, method) in sorted(picked.items()):
        survivor = merged.get(emr_id)
        if survivor is not None:
            ntier_id = picked.get(survivor, (None, "None"))[0]
            method = "Merged"
        rows.append(
            {
                "patient_key": f"EMR:{emr_id}",
                "emr_id": survivor if survivor is not None else emr_id,
                "ntier_id": ntier_id,
                "dmz_id": None,
                "match_method": method,
                "confidence": 1.0 if method in ("ExactId", "Merged") else None,
                "built_at": built_at,
            }
        )
        summary[method] += 1
    return rows, summary


def replace_crosswalk(db: Session, rows: list[dict[str, Any]]) -> None:
    """Swap the whole crosswalk in one transaction (readers never see a half-built table)."""
    with db.begin():
        db.execute(delete(PatientCrosswalk))
        if rows:
            db.execute(PatientCrosswalk.__table__.insert(), rows)
