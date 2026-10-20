"""DocumentStore: where scanned page files are read from (CLAUDE.md §4.5).

SCAN_DOCUMENTPAGE.FILELOCATION holds UNC paths such as \\\\amhs-db1\\hmscan\\201922\\a0567031.
- FileShareStore replaces the configured UNC prefix (SCAN_UNC_PREFIX) with SCAN_ROOT, a mounted
  copy of the share, and refuses any path that would resolve outside SCAN_ROOT.
- S3Store is a stub behind the same interface (SCAN_STORE=s3), not wired yet.
- With SCAN_ROOT unset there is no store: the Documents tab lists metadata and shows a banner.
"""

from pathlib import Path, PureWindowsPath
from typing import Protocol

from app.config import Settings, get_settings

MAX_FILE_BYTES = 50 * 1024 * 1024


class DocumentUnavailableError(Exception):
    """The page file cannot be read (store not configured, missing file, or refused path)."""


class DocumentStore(Protocol):
    def read(self, location: str) -> bytes: ...


class FileShareStore:
    def __init__(self, root: str | Path, unc_prefix: str) -> None:
        self.root = Path(root).resolve()
        self.prefix = PureWindowsPath(unc_prefix.rstrip("\\/"))

    def resolve(self, location: str) -> Path:
        """Map a stored UNC path to a file under root; refuse anything that escapes root."""
        if not location or "\x00" in location:
            raise DocumentUnavailableError("empty or invalid location")
        stored = PureWindowsPath(location.strip())
        prefix_parts = [p.lower() for p in self.prefix.parts]
        parts = list(stored.parts)
        if [p.lower() for p in parts[: len(prefix_parts)]] != prefix_parts:
            raise DocumentUnavailableError("location is outside the configured scan share")
        relative = parts[len(prefix_parts) :]
        if not relative or any(p in ("..", ".") or ":" in p for p in relative):
            raise DocumentUnavailableError("refused path")
        candidate = self.root.joinpath(*relative).resolve()
        if not candidate.is_relative_to(self.root):
            raise DocumentUnavailableError("refused path")
        return candidate

    def read(self, location: str) -> bytes:
        path = self.resolve(location)
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise DocumentUnavailableError("file too large")
            return path.read_bytes()
        except OSError as exc:
            raise DocumentUnavailableError("file not found") from exc


class S3Store:
    """Placeholder for a future S3 copy of the scan share (SCAN_STORE=s3)."""

    def read(self, location: str) -> bytes:  # pragma: no cover - not wired
        raise DocumentUnavailableError("S3 document store is not configured")


def get_store(settings: Settings | None = None) -> DocumentStore | None:
    settings = settings or get_settings()
    if settings.scan_store == "s3":
        return S3Store()
    if not settings.scan_root:
        return None
    return FileShareStore(settings.scan_root, settings.scan_unc_prefix)


def get_legacy_store(settings: Settings | None = None) -> DocumentStore | None:
    """Pre-2010 (DMZ) scans: LEGACY_SCAN_ROOT is a copy of the old image share."""
    settings = settings or get_settings()
    if not settings.legacy_scan_root:
        return None
    return FileShareStore(settings.legacy_scan_root, settings.legacy_scan_unc_prefix)
