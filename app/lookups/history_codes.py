"""Problems & allergies: code systems and allergy types (config/history_codes.yaml)."""

import re
from functools import lru_cache

import yaml
from pydantic import BaseModel, field_validator

from app.lookups import CONFIG_DIR, LookupConfigError


class CodeSystem(BaseModel):
    label: str
    standard: bool


class AllergyKinds(BaseModel):
    status_titles: list[str]
    by_source: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    default: str = "Other"

    @field_validator("status_titles")
    @classmethod
    def _compiles(cls, patterns: list[str]) -> list[str]:
        for p in patterns:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"bad regex {p!r}: {exc}") from exc
        return patterns


class HistoryCodes(BaseModel):
    sources: dict[str, CodeSystem]
    default: CodeSystem
    allergy_kinds: AllergyKinds

    def system(self, source: str | None) -> CodeSystem:
        return self.sources.get((source or "").strip().upper(), self.default)

    def is_status_title(self, title: str | None) -> bool:
        return any(re.search(p, title or "") for p in self.allergy_kinds.status_titles)

    def allergy_kind(self, title: str | None, source: str | None) -> str:
        """'Status' (NKA / NKDA), else by code system, else by title keywords, else default."""
        if self.is_status_title(title):
            return "Status"
        kinds = self.allergy_kinds
        by_source = kinds.by_source.get((source or "").strip().upper())
        if by_source:
            return by_source
        text = (title or "").casefold()
        for kind, words in kinds.keywords.items():
            if any(re.search(rf"\b{re.escape(w.casefold())}", text) for w in words):
                return kind
        return kinds.default


@lru_cache
def history_codes() -> HistoryCodes:
    path = CONFIG_DIR / "history_codes.yaml"
    try:
        return HistoryCodes.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise LookupConfigError(f"history_codes.yaml: {exc}") from exc
