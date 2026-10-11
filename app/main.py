"""FastAPI app factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import LoginRequiredError
from app.middleware import SecurityMiddleware
from app.routers import auth, health, pages, partials
from app.templating import is_htmx, render

log = logging.getLogger("app")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # TODO(Phase 3): load lookups, warm caches.
    yield


def _error_page(request: Request, status_code: int) -> HTMLResponse:
    if is_htmx(request):
        return render(
            request, "partials/error.html", {"status_code": status_code}, status_code=status_code
        )
    template = "pages/errors/404.html" if status_code == 404 else "pages/errors/500.html"
    return render(request, template, {"nav": None}, status_code=status_code)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Legacy Records Viewer",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityMiddleware)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    app.include_router(health.router)
    app.include_router(auth.router)
    # Partials before pages: /patients/rows must win over /patients/{key}.
    app.include_router(partials.router)
    app.include_router(pages.router)

    @app.exception_handler(LoginRequiredError)
    async def login_required(request: Request, _exc: LoginRequiredError) -> Response:
        if is_htmx(request):
            # HTMX follows HX-Redirect with a full page load.
            return Response(status_code=204, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> HTMLResponse:
        if exc.status_code == 404:
            return _error_page(request, 404)
        return render(
            request,
            "partials/error.html",
            {"status_code": exc.status_code},
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError) -> HTMLResponse:
        # Malformed IDs / page numbers: treat as not found rather than echoing input back.
        return _error_page(request, 404)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception) -> HTMLResponse:
        # Never log request data (may contain PHI); type + route only.
        route = getattr(request.scope.get("route"), "path", "?")
        log.error("unhandled %s on %s", type(exc).__name__, route)
        return _error_page(request, 500)

    return app


app = create_app()
