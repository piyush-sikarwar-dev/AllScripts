"""Scanned page files (TIFF / JPEG / extension-less) → PNG for the browser, with a small cache."""

import io
from collections import OrderedDict
from collections.abc import Hashable

from PIL import Image, UnidentifiedImageError

from app.documents.render import DocumentFormatError

CACHE_MAX_ITEMS = 64
MAX_PIXELS = 60_000_000  # refuse absurd images (decompression bombs)

_cache: OrderedDict[Hashable, bytes] = OrderedDict()


def to_png(data: bytes, frame: int = 0) -> bytes:
    """One frame (page) of any Pillow-readable image as PNG (format detected from the bytes)."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.seek(frame)
            frame = img.convert("L") if img.mode in ("1", "L", "P", "I;16") else img.convert("RGB")
            out = io.BytesIO()
            frame.save(out, format="PNG", optimize=True)
            return out.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        EOFError,
        ValueError,
    ) as exc:
        raise DocumentFormatError("not a readable image") from exc


def frame_count(data: bytes) -> int:
    """Number of pages (frames) in an image file, e.g. a multi-page TIFF."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as img:
            return max(1, int(getattr(img, "n_frames", 1)))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, EOFError) as exc:
        raise DocumentFormatError("not a readable image") from exc


def cached_png(page_id: Hashable, loader, frame: int = 0) -> bytes:
    """PNG for a page, converted once and kept in a small in-memory LRU cache."""
    if page_id in _cache:
        _cache.move_to_end(page_id)
        return _cache[page_id]
    png = to_png(loader(), frame)
    _cache[page_id] = png
    while len(_cache) > CACHE_MAX_ITEMS:
        _cache.popitem(last=False)
    return png


def clear_cache() -> None:
    _cache.clear()
