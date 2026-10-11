"""App database (PostgreSQL in dev/prod, in-memory SQLite in unit tests): engine + sessions."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_app_engine() -> Engine:
    url = get_settings().app_database_url
    if url.startswith("sqlite"):
        # Unit tests: one shared in-memory database across threads.
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_app_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one app-DB session per request."""
    db = new_session()
    try:
        yield db
    finally:
        db.close()
