"""Startup check: warn when the crosswalk has not been built (real-data mode)."""

import logging

from sqlalchemy import func, select

from app.db.app import new_session
from app.repositories.appdb.models import PatientCrosswalk

log = logging.getLogger("app.crosswalk")


def check_crosswalk() -> int:
    try:
        with new_session() as db:
            count = db.scalar(select(func.count()).select_from(PatientCrosswalk)) or 0
    except Exception:
        log.exception("crosswalk check failed (is the app database migrated?)")
        return 0
    if count == 0:
        log.warning("patient_crosswalk is empty: run `cli.py build-crosswalk`")
    return count
