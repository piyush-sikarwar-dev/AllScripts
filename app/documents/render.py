"""Turn stored EMR documents into safe, displayable content.

- Allscripts clinical documents (HTML_DOCUMENT_ORIG / HTML_DOCUMENT_ARCH) are ZIP "packages" with
  parts INFO, HEADER, CONTENT, FOOTER, LAYOUT, CSS (+ optional CUSTOMDATA). The readable note is
  HEADER + CONTENT + FOOTER (HTML). A few rows hold raw HTML instead of a package.
- Every piece of EMR HTML is sanitised with nh3 before rendering: no scripts, styles, event
  handlers, images or external URLs (CLAUDE.md §8).
- Dictations (TRANSCRIPTIONDATA) are RTF; they are converted to plain text.
"""

import base64
import binascii
import io
import re
import zipfile

import nh3

PACKAGE_PARTS = ("HEADER", "CONTENT", "FOOTER")

# nh3 defaults minus images (would load external or relative URLs); no URL schemes at all, so
# links lose their href. Style attributes are not in nh3's defaults; <style>/<script> content
# is dropped entirely.
_TAGS = set(nh3.ALLOWED_TAGS) - {"img"}


class DocumentFormatError(ValueError):
    """The stored bytes are not a recognisable document."""


def decode_text(data: bytes) -> str:
    """Bytes → text: honour BOMs, prefer UTF-8, fall back to Windows-1252."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def sanitize_html(html: str) -> str:
    return nh3.clean(html, tags=_TAGS, url_schemes=set(), link_rel=None).strip()


def package_html(data: bytes) -> str:
    """Raw (unsanitised) HTML of a stored document."""
    if not data:
        raise DocumentFormatError("empty document")
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = {info.filename.upper(): info for info in z.infolist()}
                parts = [
                    decode_text(z.read(names[part])) for part in PACKAGE_PARTS if part in names
                ]
        except (zipfile.BadZipFile, KeyError) as exc:
            raise DocumentFormatError("unreadable document package") from exc
        html = "\n".join(p for p in parts if p.strip())
        if not html:
            raise DocumentFormatError("document package has no content")
        return html
    text = decode_text(data)
    if "<" not in text[:500]:
        raise DocumentFormatError("not an HTML document")
    return text


# Some packages embed a picture (e.g. a scanned report) as base64 text right after an <img> tag
# whose src is an internal name ("SCANDOC_261"). The tag is removed by the sanitiser, which would
# leave the base64 text on screen. Such runs are cut out, checked to be a real JPEG / PNG / GIF,
# and replaced by an <img> that points at a patient-checked URL (see embed_images below).
_BASE64_RUN = re.compile(r"[A-Za-z0-9+/][A-Za-z0-9+/\r\n]{398,}={0,2}")
_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
_TOKEN = "\u27e6embedded-image-{n}\u27e7"
_TOKEN_RE = re.compile("\u27e6embedded-image-(\\d+)\u27e7")


def _decode_image(run: str) -> tuple[str, bytes] | None:
    try:
        data = base64.b64decode(re.sub(r"\s+", "", run), validate=True)
    except (binascii.Error, ValueError):
        return None
    for magic, mime in _IMAGE_MAGIC:
        if data.startswith(magic):
            return mime, data
    return None


def _split_images(html: str) -> tuple[str, list[tuple[str, bytes]]]:
    """Replace embedded base64 pictures by tokens; returns (html, [(mime, bytes), ...])."""
    images: list[tuple[str, bytes]] = []

    def cut(m: re.Match) -> str:
        image = _decode_image(m.group(0))
        if image is None:
            return m.group(0)
        images.append(image)
        return f"<p>{_TOKEN.format(n=len(images) - 1)}</p>"

    return _BASE64_RUN.sub(cut, html), images


def embedded_images(data: bytes | None) -> list[tuple[str, bytes]]:
    """The pictures embedded in a stored document, in order (index = URL number)."""
    return _split_images(package_html(data or b""))[1]


def render_document(data: bytes | None, doc_id: int | None = None) -> str:
    """Safe HTML for a stored document (raises DocumentFormatError when unusable).

    Embedded pictures become <img src="embedded:<doc_id>/<n>"> placeholders (never data from the
    document itself); templates turn them into real URLs with the embed_images filter. Without a
    doc_id they are left out."""
    html, images = _split_images(package_html(data or b""))
    safe = sanitize_html(html)

    def image_tag(m: re.Match) -> str:
        n = int(m.group(1))
        if doc_id is None or n >= len(images):
            return "[embedded image]"
        return (f'<img class="doc-embedded-img" src="embedded:{doc_id}/{n}" '
                f'alt="Embedded image {n + 1} of the document">')  # fmt: skip

    return _TOKEN_RE.sub(image_tag, safe)


_EMBED_SRC = re.compile(r'src="embedded:(\d+)/(\d+)"')


def embed_images(html: str | None, patient_key: str) -> str:
    """Point embedded-image placeholders at the app (or at the PDF renderer with "__pdf__")."""
    if not html:
        return html or ""
    if patient_key == "__pdf__":
        return _EMBED_SRC.sub(r'src="docimage:\1/\2"', html)
    key = re.sub(r"[^A-Za-z0-9:]", "", patient_key)
    return _EMBED_SRC.sub(rf'src="/patients/{key}/documents/document/\1/images/\2"', html)


# --- RTF → plain text ---------------------------------------------------------------------------

_RTF_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer",
    "headerl", "headerr", "footerl", "footerr", "listtable", "listoverridetable", "rsidtbl",
    "generator", "themedata", "colorschememapping", "latentstyles", "datastore", "xmlnstbl",
    "fldinst", "*",
}  # fmt: skip
_RTF_TOKEN = re.compile(
    r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}]+)", re.S
)


def rtf_to_text(rtf: str) -> str:
    """Minimal, safe RTF → text: keeps paragraphs and tabs; drops formatting and objects."""
    out: list[str] = []
    stack: list[bool] = []
    skip = False
    for word, arg, hexcode, symbol, brace, text in _RTF_TOKEN.findall(rtf or ""):
        if brace == "{":
            stack.append(skip)
        elif brace == "}":
            skip = stack.pop() if stack else False
        elif skip:
            continue
        elif word:
            if word in _RTF_DESTINATIONS:
                skip = True
            elif word in ("par", "line", "sect", "page", "row"):
                out.append("\n")
            elif word in ("tab", "cell"):
                out.append("\t")
            elif word == "u" and arg:
                code = int(arg)
                out.append(chr(code + 65536 if code < 0 else code))
        elif hexcode:
            out.append(bytes([int(hexcode, 16)]).decode("cp1252", errors="replace"))
        elif symbol:
            if symbol == "*":
                skip = True
            elif symbol in "\\{}":
                out.append(symbol)
            elif symbol == "~":
                out.append(" ")
            elif symbol in "\n\r":
                out.append("\n")
        elif text:
            out.append(text.replace("\r", "").replace("\n", ""))
    lines = "".join(out).split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()
