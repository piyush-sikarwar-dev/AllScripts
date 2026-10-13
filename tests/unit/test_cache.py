"""Perf #6: per-patient source-data cache."""

import pytest

from app.config import get_settings
from app.repositories import cache


@pytest.fixture
def counter():
    calls = []

    @cache.cached
    def load(patient: int, kind: str = "all") -> list[dict]:
        calls.append((patient, kind))
        return [{"patient": patient, "kind": kind, "rows": [3, 1, 2]}]

    return load, calls


def test_second_call_is_served_from_cache(counter):
    load, calls = counter
    assert load(1) == load(1)
    assert calls == [(1, "all")]
    assert cache.stats()["hits"] == 1


def test_arguments_are_part_of_the_key(counter):
    load, calls = counter
    load(1)
    load(2)
    load(1, kind="office")
    assert len(calls) == 3


def test_callers_get_independent_copies(counter):
    load, _ = counter
    first = load(1)
    first[0]["rows"].sort()
    first.append("mutated")
    assert load(1) == [{"patient": 1, "kind": "all", "rows": [3, 1, 2]}]


def test_errors_are_not_cached():
    calls = []

    @cache.cached
    def flaky(x: int) -> int:
        calls.append(x)
        if len(calls) == 1:
            raise RuntimeError("db down")
        return x

    with pytest.raises(RuntimeError):
        flaky(5)
    assert flaky(5) == 5 and len(calls) == 2


def test_expiry_and_size_limit(counter, monkeypatch):
    load, calls = counter
    settings = get_settings().model_copy(update={"source_cache_max_items": 2})
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    load(1)
    load(2)
    load(3)  # evicts 1 (least recently used)
    load(1)
    assert calls.count((1, "all")) == 2
    clock = [1000.0]
    monkeypatch.setattr(cache.time, "monotonic", lambda: clock[0])
    cache.clear()
    load(7)
    clock[0] += settings.source_cache_ttl_seconds + 1
    load(7)
    assert calls.count((7, "all")) == 2


def test_disabled_when_ttl_is_zero(counter, monkeypatch):
    load, calls = counter
    settings = get_settings().model_copy(update={"source_cache_ttl_seconds": 0})
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    load(1)
    load(1)
    assert len(calls) == 2


def test_real_mode_tab_revisit_hits_cache(monkeypatch):
    """Opening Labs twice loads the lab rows from the database once."""
    from app.repositories import emr, live

    calls = []
    monkeypatch.setattr(emr, "lab_results", lambda emr_id: calls.append(emr_id) or [])
    live.labs(11)
    live.labs(11)
    assert calls == [11]
