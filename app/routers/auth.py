"""Sign-in / sign-out."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.templating import render

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return render(request, "pages/login.html", {"error": None, "email": ""})


@router.post("/login")
async def login(
    request: Request,
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> RedirectResponse:
    # TODO(Phase 2): verify credentials (argon2), lockout, session rotation, CSRF, audit.
    # Phase 0 fake mode accepts any credentials.
    return RedirectResponse("/patients", status_code=303)


@router.post("/logout")
async def logout() -> RedirectResponse:
    # TODO(Phase 2): delete the server-side session and audit the logout.
    return RedirectResponse("/login", status_code=303)
