"""Session routes: the login panel, sign-in, sign-out and one protected fragment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fjkit import render
from fjkit.auth import Session

from app.features.auth.schemas import SecretResponse, SessionResponse
from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME, BadCredentials

router = APIRouter(tags=["session"])


async def require_session(request: Request) -> Session:
    """Dependency: require a session via the app's auth plugin."""
    return await request.app.state.auth.required(request)


#: Routes that require a session.
protected = APIRouter(prefix="/session", tags=["session"], dependencies=[Depends(require_session)])


def _panel(request: Request, error: str | None = None) -> SessionResponse:
    """Build the panel's context from the current session."""
    session = getattr(request.state, "auth", None)
    return SessionResponse(
        signed_in=session is not None,
        username=session.claims.get("username") if session else None,
        error=error,
        demo_username=DEMO_USERNAME,
        demo_password=DEMO_PASSWORD,
    )


@router.get("/session", name="session_page")
@render("auth/page.html", partial="auth/_panel.html")
def session_page(request: Request) -> SessionResponse:
    """Render the session page, or just the panel for an htmx request."""
    return _panel(request)


@router.post("/session", name="session_login")
@render("auth/_panel.html")
async def sign_in(
    request: Request,
    response: Response,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> SessionResponse:
    """Sign in with the posted credentials and return the updated panel."""
    try:
        await request.app.state.auth.issue(request, response, {"username": username, "password": password})
    except BadCredentials:
        return _panel(request, error="That is not the demo account.")
    return _panel(request)


@router.delete("/session", name="session_logout")
@render("auth/_panel.html")
async def sign_out(request: Request, response: Response) -> SessionResponse:
    """Sign out and return the updated panel."""
    await request.app.state.auth.revoke(request, response)
    return _panel(request)


@protected.get("/secret", name="session_secret")
@render("auth/_secret.html")
def secret(request: Request) -> SecretResponse:
    """Render the protected fragment for the signed-in user."""
    session = request.state.auth
    return SecretResponse(username=session.claims["username"])
