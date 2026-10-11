"""Jinja2 environment shared by all routers."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings

TEMPLATE_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=TEMPLATE_DIR)


def url_with(path: str, params: Mapping[str, Any] | None = None, **overrides: Any) -> str:
    """`path?query` from params + overrides, dropping empty values (keeps URLs short and stable)."""
    merged = {**(params or {}), **overrides}
    query = urlencode(
        {k: v for k, v in merged.items() if v not in (None, "") and not (k == "page" and v == 1)}
    )
    return f"{path}?{query}" if query else path


templates.env.globals["url_with"] = url_with
templates.env.globals["clinic_name"] = lambda: get_settings().clinic_name


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
