"""Session routes: the login panel, sign-in, sign-out and one protected fragment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fjkit import render
from fjkit.auth import Session

from app.config import settings
from app.dependencies import OptionalSessionDep, SessionDep, require_session
from app.schemas.auth import SecretResponse, SessionResponse
from app.services.auth import BadCredentials

router = APIRouter(tags=["session"])

#: Routes that require a session.
protected = APIRouter(prefix="/session", tags=["session"], dependencies=[Depends(require_session)])


def _panel(session: Session | None, error: str | None = None) -> SessionResponse:
    """Build the panel's context from the session, plus an optional error."""
    return SessionResponse(
        signed_in=session is not None,
        username=session.claims.get("username") if session else None,
        error=error,
        demo_username=settings.username,
        demo_password=settings.password,
    )


@router.get("/session", name="session_page")
@render("auth/page.html", partial="auth/_panel.html")
def session_page(session: OptionalSessionDep) -> SessionResponse:
    """Render the session page, or just the panel for an htmx request."""
    return _panel(session)


@router.post("/session", name="session_login")
@render("auth/_panel.html")
async def sign_in(
    request: Request,
    response: Response,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> SessionResponse:
    """Sign in with the posted credentials and return the updated panel."""
    auth = request.app.state.auth
    try:
        session = await auth.issue(request, response, {"username": username, "password": password})
    except BadCredentials:
        return _panel(auth.session(request), error="That is not the demo account.")
    return _panel(session)


@router.delete("/session", name="session_logout")
@render("auth/_panel.html")
async def sign_out(request: Request, response: Response) -> SessionResponse:
    """Sign out and return the updated panel."""
    await request.app.state.auth.revoke(request, response)
    return _panel(None)


@protected.get("/secret", name="session_secret")
@render("auth/_secret.html")
def secret(session: SessionDep) -> SecretResponse:
    """Render the protected fragment for the signed-in user."""
    return SecretResponse(username=session.claims["username"])
