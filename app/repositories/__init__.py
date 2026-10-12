"""Read-only data access.

`source_repository()` returns the module that answers source-database queries:
the in-memory fake (`tests/fakes/repository.py`) when USE_FAKE_DATA=true, otherwise
`app/repositories/live.py` (real EMR / Ntier / DMZ, same function names and return shapes).
"""

from types import ModuleType

from app.config import get_settings


def source_repository() -> ModuleType:
    if get_settings().use_fake_data:
        from tests.fakes import repository

        return repository
    from app.repositories import live

    return live
