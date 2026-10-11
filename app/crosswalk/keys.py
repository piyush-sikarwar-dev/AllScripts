"""Patient key parsing: `EMR:<IMREDEM_CODE>` or `DMZ:<personkey>`."""

import re
from dataclasses import dataclass
from typing import Literal

_KEY_RE = re.compile(r"^(EMR|DMZ):([1-9][0-9]{0,9})$")


@dataclass(frozen=True)
class PatientKey:
    source: Literal["EMR", "DMZ"]
    id: int

    def __str__(self) -> str:
        return f"{self.source}:{self.id}"


def parse_patient_key(raw: str) -> PatientKey | None:
    """Return the parsed key, or None if it is not a valid patient key."""
    match = _KEY_RE.match(raw)
    if match is None:
        return None
    return PatientKey(source=match.group(1), id=int(match.group(2)))  # type: ignore[arg-type]
