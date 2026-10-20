"""Request id + security headers (CLAUDE.md §8)."""

import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'"
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
HSTS = "max-age=31536000; includeSubDomains"
log = logging.getLogger("app.request")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request.state.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        if get_settings().cookie_secure:  # served over HTTPS: browsers must never fall back to HTTP
            response.headers["Strict-Transport-Security"] = HSTS
        response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith("/static/"):
            # Everything except static assets may contain PHI: never cache it.
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        elif request.url.query.startswith("v="):
            # Versioned asset (templating.static_url): the URL changes whenever the file does.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # Unversioned asset (fonts, images): always check with the server before reuse.
            response.headers["Cache-Control"] = "no-cache"
        if not request.url.path.startswith("/static/"):
            # One line per request: id, route TEMPLATE (never the path or query: they can hold
            # names), status, duration, user id. CLAUDE.md section 8.
            route = getattr(request.scope.get("route"), "path", "-")
            user = getattr(getattr(request.state, "user", None), "id", "-")
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.info(
                "request id=%s method=%s route=%s status=%s ms=%d user=%s",
                request.state.request_id,
                request.method,
                route,
                response.status_code,
                elapsed_ms,
                user,
            )
        return response
