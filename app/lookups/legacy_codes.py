"""Pre-2010 (DMZ) chart codes without a lookup table in the legacy database
(config/legacy_codes.yaml)."""

from functools import lru_cache

import yaml
from pydantic import BaseModel

from app.lookups import CONFIG_DIR, LookupConfigError


class LegacyCodes(BaseModel):
    problem_status: dict[int, str] = {}
    problem_voided: list[int] = []
    allergy_voided: list[int] = []
    severity_blank: list[str] = []
    vital_items: dict[str, str] = {}
    skip_item_prefixes: list[str] = []
    result_status: dict[str, str] = {}
    result_voided: list[str] = []

    def result_status_label(self, code: str | None) -> str:
        code = (code or "").strip()
        if not code:
            return "—"
        return self.result_status.get(code, f"Unknown (code {code})")

    def item_kind(self, name: str | None) -> str:
        """'vital' | 'lab' | 'skip' for a clinical item name."""
        upper = (name or "").strip().upper()
        if not upper or any(upper.startswith(p) for p in self.skip_item_prefixes):
            return "skip"
        return "vital" if upper in self.vital_columns() else "lab"

    def vital_columns(self) -> dict[str, str]:
        """Item name (upper case) → vitals column."""
        return {name.upper(): column for column, name in self.vital_items.items()}

    def problem_status_label(self, code: int | None) -> str:
        if code is None:
            return "—"
        return self.problem_status.get(int(code), f"Unknown (code {code})")


@lru_cache(maxsize=1)
def legacy_codes() -> LegacyCodes:
    path = CONFIG_DIR / "legacy_codes.yaml"
    try:
        return LegacyCodes.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise LookupConfigError(f"{path.name}: {exc}") from exc
