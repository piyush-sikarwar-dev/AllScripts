"""Notes tab categories (config/note_categories.yaml), validated with pydantic and cached."""

import re
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator

from app.lookups import CONFIG_DIR, LookupConfigError

NoteCategory = Literal["rx", "lab", "visit", "message", "letter"]
NOTE_CATEGORIES: tuple[str, ...] = ("rx", "visit", "lab", "message", "letter")  # tile order


class CategoryRule(BaseModel):
    label: str
    badge: str
    map_sources: list[str] = []
    title_regex: list[str] = []
    title_exclude: list[str] = []
    transcription: bool = False
    kinds: list[str] = []
    default: bool = False

    @field_validator("title_regex", "title_exclude")
    @classmethod
    def _compiles(cls, patterns: list[str]) -> list[str]:
        for p in patterns:
            try:
                re.compile(p)
            except re.error as exc:
                raise ValueError(f"bad regex {p!r}: {exc}") from exc
        return patterns


class NoteCategories(BaseModel):
    categories: dict[NoteCategory, CategoryRule]

    @model_validator(mode="after")
    def _one_default(self) -> "NoteCategories":
        if [k for k, r in self.categories.items() if r.default] != ["letter"]:
            raise ValueError("exactly one default category (letter) is required")
        if set(self.categories) != set(NOTE_CATEGORIES):
            raise ValueError(f"categories must be exactly {NOTE_CATEGORIES}")
        return self

    def map_sources(self) -> list[str]:
        return sorted({s for r in self.categories.values() for s in r.map_sources})

    def classify(
        self, title: str | None, sources: set[str], transcription: bool = False, kind: str = ""
    ) -> str:
        """First match wins: note kind, then map sources (all categories, in file order), then
        title rules."""
        for key, rule in self.categories.items():
            if kind and kind in rule.kinds:
                return key
        for key, rule in self.categories.items():
            if transcription and rule.transcription:
                return key
            if sources.intersection(rule.map_sources):
                return key
        text = title or ""
        for key, rule in self.categories.items():
            if any(re.search(p, text) for p in rule.title_exclude):
                continue
            if any(re.search(p, text) for p in rule.title_regex):
                return key
        return "letter"

    def label(self, key: str) -> str:
        return self.categories[key].label  # type: ignore[index]

    def badge(self, key: str) -> str:
        return self.categories[key].badge  # type: ignore[index]


@lru_cache
def note_categories() -> NoteCategories:
    path = CONFIG_DIR / "note_categories.yaml"
    try:
        return NoteCategories.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise LookupConfigError(f"note_categories.yaml: {exc}") from exc
