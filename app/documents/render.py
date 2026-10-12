"""Turn stored EMR documents into safe, displayable content.

- Allscripts clinical documents (HTML_DOCUMENT_ORIG / HTML_DOCUMENT_ARCH) are ZIP "packages" with
  parts INFO, HEADER, CONTENT, FOOTER, LAYOUT, CSS (+ optional CUSTOMDATA). The readable note is
  HEADER + CONTENT + FOOTER (HTML). A few rows hold raw HTML instead of a package.
- Every piece of EMR HTML is sanitised with nh3 before rendering: no scripts, styles, event
  handlers, images or external URLs (CLAUDE.md §8).
- Dictations (TRANSCRIPTIONDATA) are RTF; they are converted to plain text.
"""

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


def render_document(data: bytes | None) -> str:
    """Safe HTML for a stored document (raises DocumentFormatError when unusable)."""
    return sanitize_html(package_html(data or b""))


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
