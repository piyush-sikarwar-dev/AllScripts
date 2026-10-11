"""Alembic environment: migrates the app database (never the source SQL Server databases)."""

import app.repositories.appdb.models  # noqa: F401  (registers tables on Base.metadata)
from alembic import context
from app.db.app import Base, get_app_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_app_engine().url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with get_app_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
