"""Code → label lookups.

Phase 0: small static maps so the fake data renders. Phase 3 loads the real dictionaries from
hpsystem.DICTIONARIES_MASTER / HPSITE.DICTIONARIES_SITE and the YAML files in `config/`,
keeping this same `label(kind, code)` API.
"""

_STATIC: dict[str, dict[object, str]] = {
    "sex": {"F": "Female", "M": "Male", "U": "Unknown"},
}


def label(kind: str, code: object) -> str:
    """Decoded label, or 'Unknown (code N)' — never an error."""
    if code is None or code == "":
        return "—"
    return _STATIC.get(kind, {}).get(code, f"Unknown (code {code})")
