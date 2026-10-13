"""How many items (visits + notes) the user picked with "Add to export" for this patient."""

from app.db.app import new_session
from app.repositories.appdb import export_selection
from app.services import call


def _count_sync(session_id: str, patient_key: str) -> int:
    with new_session() as db:
        return export_selection.count_all(db, session_id, patient_key)


async def export_item_count(session_id: str | None, patient_key: str) -> int:
    if not session_id:
        return 0
    return await call(_count_sync, session_id, patient_key)
