"""Jinja2 environment shared by all routers."""

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.documents.render import embed_images

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=TEMPLATE_DIR)


def url_with(path: str, params: Mapping[str, Any] | None = None, **overrides: Any) -> str:
    """`path?query` from params + overrides, dropping empty values (keeps URLs short and stable)."""
    merged = {**(params or {}), **overrides}
    query = urlencode(
        {k: v for k, v in merged.items() if v not in (None, "") and not (k == "page" and v == 1)}
    )
    return f"{path}?{query}" if query else path


_static_versions: dict[str, tuple[float, str]] = {}


def static_url(path: str) -> str:
    """'/static/css/app.css' → '/static/css/app.css?v=<content hash>'. A changed file gets a new
    URL, so browsers never keep using an old stylesheet or script after an update."""
    file = STATIC_DIR / path.removeprefix("/static/")
    try:
        mtime = file.stat().st_mtime
    except OSError:
        return path
    cached = _static_versions.get(path)
    if cached is None or cached[0] != mtime:
        cached = (mtime, hashlib.sha256(file.read_bytes()).hexdigest()[:12])
        _static_versions[path] = cached
    return f"{path}?v={cached[1]}"


templates.env.globals["url_with"] = url_with
templates.env.filters["embed_images"] = embed_images
templates.env.globals["static_url"] = static_url
templates.env.globals["clinic_name"] = lambda: get_settings().clinic_name
templates.env.globals["legacy_enabled"] = lambda: (
    get_settings().feature_legacy_dmz or get_settings().use_fake_data
)


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def render(
    request: Request,
    template: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    context = dict(context or {})
    # Signed-in user and CSRF token (set by the current_user dependency) for every template.
    context.setdefault("user", getattr(request.state, "user", None))
    context.setdefault("csrf_token", getattr(request.state, "csrf_token", None))
    return templates.TemplateResponse(
        request, template, context, status_code=status_code, headers=headers
    )
