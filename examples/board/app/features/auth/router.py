"""HTTP surface for the session — the auth plugin, demonstrated end to end.

Three routes over one partial, and nothing in them touches a cookie. `issue`
and `revoke` are the only two calls an app makes; everything else — signing,
storing, reading it back on the next request, the CSRF check — happens in the
plugin's middleware before any handler runs.

These two handlers are `async def`, unlike every other rendering route in this
app. That is the documented exception rather than a slip: they await the
session store, and a real `TokenSource` would await an identity provider over
the network. Handlers that only render stay `def` so Starlette keeps them in
the threadpool.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response
from fjkit import render
from fjkit.auth import Session

from app.features.auth.schemas import SecretResponse, SessionResponse
from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME, BadCredentials

router = APIRouter(tags=["session"])


async def require_session(request: Request) -> Session:
    """`auth.required`, reached through the app rather than imported.

    The plugin is built per app — the demo's store is in memory, and two apps
    sharing one would share their sessions — so there is no module-level
    instance for `Depends(auth.required)` to name at import time. Going through
    `request.app.state` is what lets a module-level router still be protected.

    A single-app deployment builds the plugin once at module scope and writes
    `Depends(auth.required)` directly.
    """
    return await request.app.state.auth.required(request)


#: Everything under here needs a session. The dependency's return value is
#: discarded — it is here to refuse, not to supply — so the handlers below keep
#: the signatures they would have had without it.
protected = APIRouter(prefix="/session", tags=["session"], dependencies=[Depends(require_session)])


def _panel(request: Request, error: str | None = None) -> SessionResponse:
    """The panel's state, read from wherever the middleware left the session."""
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
    """The full page — and, for an htmx swap, just the panel inside it."""
    return _panel(request)


@router.post("/session", name="session_login")
@render("auth/_panel.html")
async def sign_in(
    request: Request,
    response: Response,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> SessionResponse:
    """Exchange the credentials for a session, and set the cookie.

    The cookie rides out on the `Response` parameter: `@render` merges a
    handler's response headers into the reply it builds, so a swap that returns
    a fragment can still be the thing that logs you in. No redirect, no page
    load — the panel is simply replaced by its signed-in half.
    """
    try:
        await request.app.state.auth.issue(request, response, {"username": username, "password": password})
    except BadCredentials:
        return _panel(request, error="That is not the demo account.")
    return _panel(request)


@router.delete("/session", name="session_logout")
@render("auth/_panel.html")
async def sign_out(request: Request, response: Response) -> SessionResponse:
    """Drop the session server-side and clear the cookie.

    A DELETE, so the plugin's CSRF check applies to it — which is the half of
    the demo worth seeing: the same request without an `Origin` header gets a
    403 before this function is reached.
    """
    await request.app.state.auth.revoke(request, response)
    return _panel(request)


@protected.get("/secret", name="session_secret")
@render("auth/_secret.html")
def secret(request: Request) -> SecretResponse:
    """A fragment only a session can fetch — the demo's one protected route.

    Note what is *not* here. No cookie is read, no header is checked, no branch
    asks whether anyone is signed in. The router's dependency refused the
    request long before this function, which is the whole claim: protecting a
    route costs one line, in one place, and the handler stays about its own job.

    Signed out, an htmx click on this gets `204` with `HX-Redirect` instead —
    so the browser moves the whole page to the login screen rather than swapping
    a login form into a card. Try it: sign out, then press the button.
    """
    session = request.state.auth
    return SecretResponse(username=session.claims["username"])
