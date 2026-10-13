"""Shared helpers for source repositories: run one .sql file, return plain dicts.

Logs the SQL file name, row count and duration only — never parameter values (they may be PHI).
"""

import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.db.source import Source, get_engine
from app.db.sql_loader import load_sql

log = logging.getLogger("app.sql")

# Independent queries of one screen run side by side (docs/PERFORMANCE_PLAN.md #2). Each query
# still runs on its own pooled connection exactly as before; only the waiting overlaps.
_executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix="sql")


def parallel(*calls: Callable[[], Any]) -> list[Any]:
    """Run zero-argument callables concurrently; results in the same order; errors re-raised."""
    if len(calls) <= 1:
        return [call() for call in calls]
    futures = [_executor.submit(call) for call in calls]
    return [future.result() for future in futures]


def run_query(
    source: Source,
    sql_name: str,
    params: Mapping[str, Any] | None = None,
    *,
    expanding: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    clause = load_sql(sql_name, expanding)
    started = time.perf_counter()
    with get_engine(source).connect() as conn:
        rows = [dict(r) for r in conn.execute(clause, dict(params or {})).mappings()]
    log.info("sql=%s rows=%d ms=%.0f", sql_name, len(rows), (time.perf_counter() - started) * 1000)
    return rows


def run_scalar(
    source: Source,
    sql_name: str,
    params: Mapping[str, Any] | None = None,
    *,
    expanding: tuple[str, ...] = (),
) -> Any:
    clause = load_sql(sql_name, expanding)
    started = time.perf_counter()
    with get_engine(source).connect() as conn:
        value = conn.execute(clause, dict(params or {})).scalar()
    log.info("sql=%s rows=1 ms=%.0f", sql_name, (time.perf_counter() - started) * 1000)
    return value
