"""Code → label lookups, loaded once at startup and cached in memory.

Sources, in order of preference:
  1. Allscripts dictionaries (hpsystem.DICTIONARIES_MASTER / HPSITE.DICTIONARIES_SITE).
     TODO(Phase 3): wire once their column layout is confirmed (schema query pending).
  2. config/*.yaml — fallbacks and the mappings for still-unknown codes (CLAUDE.md §4.5).

Unknown codes never raise: they render as "Unknown (code N)".
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

HistoryGroup = Literal["problem", "allergy", "surgical", "family", "social", "other"]
HISTORY_GROUPS: tuple[str, ...] = ("problem", "allergy", "surgical", "family", "social", "other")
Precision = Literal["full", "month_year", "year"]
PRECISIONS: tuple[str, ...] = ("full", "month_year", "year")


@dataclass(frozen=True)
class HistoryCategory:
    label: str
    group: HistoryGroup


@dataclass(frozen=True)
class VisitType:
    label: str
    is_office_visit: bool


class LookupConfigError(RuntimeError):
    """A config/*.yaml file is malformed (fail fast at startup)."""


def _read_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise LookupConfigError(f"{name}: expected a mapping at the top level")
    return data


def _key(code: object) -> object:
    """Normalise codes so 21, '21' and 21.0 all match."""
    if isinstance(code, bool):
        return code
    if isinstance(code, float) and code.is_integer():
        return int(code)
    if isinstance(code, str) and code.strip().lstrip("-").isdigit():
        return int(code.strip())
    return code.strip() if isinstance(code, str) else code


class Lookups:
    def __init__(self) -> None:
        self.labels: dict[str, dict[object, str]] = {}
        self.history: dict[object, HistoryCategory] = {}
        self.history_default_group: HistoryGroup = "other"
        self.visit_types: dict[object, VisitType] = {}
        self.visit_default_office = True
        self.masks: dict[object, Precision] = {}
        self.mask_default: Precision = "full"

    # -- loading ----------------------------------------------------------------------------

    def load_config(self) -> "Lookups":
        fallback = _read_yaml("lookups_fallback.yaml")
        self.labels = {
            kind: {_key(c): str(v) for c, v in (mapping or {}).items()}
            for kind, mapping in fallback.items()
        }

        hist = _read_yaml("history_categories.yaml")
        self.history_default_group = self._group(hist.get("default_group", "other"), "default")
        self.history = {}
        for code, entry in (hist.get("categories") or {}).items():
            entry = entry or {}
            self.history[_key(code)] = HistoryCategory(
                label=str(entry.get("label") or f"History (code {code})"),
                group=self._group(entry.get("group", self.history_default_group), code),
            )

        visits = _read_yaml("visit_types.yaml")
        self.visit_default_office = bool((visits.get("default") or {}).get("is_office_visit", True))
        self.visit_types = {
            _key(code): VisitType(
                label=str((e or {}).get("label") or f"Visit type {code}"),
                is_office_visit=bool((e or {}).get("is_office_visit", self.visit_default_office)),
            )
            for code, e in (visits.get("visit_types") or {}).items()
        }

        masks = _read_yaml("date_masks.yaml")
        self.mask_default = self._precision(masks.get("default", "full"), "default")
        self.masks = {
            _key(code): self._precision(p, code) for code, p in (masks.get("masks") or {}).items()
        }
        return self

    def merge_dictionary(self, kind: str, mapping: dict[object, str]) -> None:
        """Overlay labels read from the Allscripts dictionaries (DB wins over YAML)."""
        self.labels.setdefault(kind, {}).update({_key(c): v for c, v in mapping.items()})

    @staticmethod
    def _group(value: object, code: object) -> HistoryGroup:
        if value not in HISTORY_GROUPS:
            raise LookupConfigError(f"history_categories.yaml: bad group {value!r} for {code}")
        return value  # type: ignore[return-value]

    @staticmethod
    def _precision(value: object, code: object) -> Precision:
        if value not in PRECISIONS:
            raise LookupConfigError(f"date_masks.yaml: bad precision {value!r} for {code}")
        return value  # type: ignore[return-value]

    # -- queries ----------------------------------------------------------------------------

    def label(self, kind: str, code: object) -> str:
        if code is None or code == "":
            return "—"
        return self.labels.get(kind, {}).get(_key(code), f"Unknown (code {code})")

    def history_category(self, code: object) -> HistoryCategory:
        found = self.history.get(_key(code))
        if found:
            return found
        label = f"History (code {code})" if code is not None else "History"
        return HistoryCategory(label=label, group=self.history_default_group)

    def visit_type(self, code: object) -> VisitType:
        found = self.visit_types.get(_key(code))
        if found:
            return found
        label = f"Visit type {code}" if code is not None else "Visit"
        return VisitType(label=label, is_office_visit=self.visit_default_office)

    def date_precision(self, mask: object) -> Precision:
        if mask is None or mask == "":
            return "full"
        return self.masks.get(_key(mask), self.mask_default)


_lookups: Lookups | None = None


def get_lookups() -> Lookups:
    global _lookups
    if _lookups is None:
        _lookups = Lookups().load_config()
    return _lookups


def load() -> Lookups:
    """Called from the app lifespan: (re)load config so malformed YAML fails at startup."""
    global _lookups
    _lookups = Lookups().load_config()
    return _lookups


def label(kind: str, code: object) -> str:
    """Decoded label, or 'Unknown (code N)' — never an error."""
    return get_lookups().label(kind, code)
