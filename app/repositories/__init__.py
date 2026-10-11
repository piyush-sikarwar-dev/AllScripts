"""Read-only data access.

`source_repository()` returns the module that answers source-database queries. In Phase 0 that is
always the in-memory fake (`tests/fakes/repository.py`); the real EMR / Ntier / DMZ repositories
replace it from Phase 4 with the same function names and return shapes.
"""

from types import ModuleType

from app.config import get_settings


def source_repository() -> ModuleType:
    if get_settings().use_fake_data:
        from tests.fakes import repository

        return repository
    # TODO(Phase 4): return the real repositories (app/repositories/emr, ntier, dmz).
    raise RuntimeError("Real source repositories are not implemented yet; set USE_FAKE_DATA=true.")
