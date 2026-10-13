"""In-memory cache for per-patient source data (docs/PERFORMANCE_PLAN.md #6).

The archive is read-only and never changes, so a cached result is exactly what the database would
return. Entries expire after SOURCE_CACHE_TTL_SECONDS (default 10 min); at most
SOURCE_CACHE_MAX_ITEMS are kept (least recently used dropped first). Callers always receive a
deep copy, so a screen that sorts or edits its rows can never change another screen's data.
Only successful results are cached. Memory only — nothing is written to disk.
"""

import copy
import functools
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from app.config import get_settings

_entries: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0}


def clear() -> None:
    with _lock:
        _entries.clear()
        _stats.update(hits=0, misses=0)


def stats() -> dict[str, int]:
    with _lock:
        return {**_stats, "items": len(_entries)}


def cached[F: Callable[..., Any]](func: F) -> F:
    """Cache a repository function's result by (function, arguments)."""
    name = f"{func.__module__}.{func.__qualname__}"

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        settings = get_settings()
        ttl = settings.source_cache_ttl_seconds
        if ttl <= 0:
            return func(*args, **kwargs)
        key = (name, args, tuple(sorted(kwargs.items())))
        now = time.monotonic()
        with _lock:
            hit = _entries.get(key)
            if hit is not None and hit[0] > now:
                _entries.move_to_end(key)
                _stats["hits"] += 1
                return copy.deepcopy(hit[1])
        value = func(*args, **kwargs)  # outside the lock: other patients are not blocked
        with _lock:
            _stats["misses"] += 1
            _entries[key] = (now + ttl, copy.deepcopy(value))
            _entries.move_to_end(key)
            while len(_entries) > max(settings.source_cache_max_items, 1):
                _entries.popitem(last=False)
        return value

    return wrapper  # type: ignore[return-value]
