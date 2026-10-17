"""Cross-site request forgery (CSRF) defence, in two layers.

A cookie is an ambient credential: the browser attaches it to a cross-site
request unasked. That is the vulnerability, and a `Bearer` header does not have
it.

The two layers cover different gaps. `SameSite=Lax` on the cookie (see
`CookieSpec`) stops the browser sending it on a cross-*site* write, which is
nearly every classic CSRF. It misses same-site cross-origin: `evil.example.com`
and `app.example.com` share a registrable domain, so Lax treats them as one site
and sends the cookie. An `Origin` comparison is exact — scheme, host and port —
so it catches exactly what Lax misses.

Login is the one anonymous write that is checked. A cross-site `POST /login`
carries no cookie, so the middleware has nothing to verify, yet it is the
request that sets one: a foreign page that submits the attacker's credentials
logs the visitor in as the attacker, and whatever they type next is recorded
under that account (login CSRF). `AuthPlugin.issue` therefore runs `verify`
whenever the request carries an `Origin`. A login without one comes from a
non-browser client, which has no visitor to plant a session in, and is let
through. Other anonymous writes stay unchecked, because an endpoint that is
open to anyone has nothing for a forged request to steal.

This version ships no token strategy. A token has to reach every form and every
htmx request, so the form macro and the shell both need request-scoped data;
shipping a token means shipping a templating feature with it. `Csrf.on_issue` is
the plug-in point when that cost is worth paying.

Three cases this cannot cover:

* A GET that changes state. No header check helps; fix it in the routing.
* A login completed on a GET, which is what an OpenID Connect or OAuth
  callback is (`GET /callback?code=…`). A browser sends no `Origin` on a
  navigation and `verify` passes safe methods anyway, so `issue` checks
  nothing there, and a visitor sent to `/callback?code=<attacker's code>` is
  logged in as the attacker. Only the `state` parameter closes it: a nonce
  set in a cookie before the redirect to the provider, and a callback refused
  when its `state` does not match. This plugin has no hook for that yet;
  `TokenSource.exchange` receives the credentials and nothing else, so the
  app has to compare `state` in the callback route before calling `issue`.
* Non-browser clients on cookie-authenticated writes. They send no `Origin` and
  are refused. Those callers should use a bearer token instead, which is the
  same route in `"auto"` mode answering JSON.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import Request, Response

from fjkit.auth.errors import CsrfRejected

__all__ = ["NoCsrf", "OriginCsrf"]

#: Methods that do not change state, so no CSRF risk justifies refusing them.
#: `OPTIONS` is here because refusing a preflight breaks the very requests that
#: would have been checked properly a moment later.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class OriginCsrf:
    """Refuse a cookie-authenticated write whose `Origin` is not ours.

    Pass `trusted_origins` explicitly; never derive it from the `Host` header.
    An attacker controls `Host`, and a check that compares a request against a
    value the request supplied is not a check.
    """

    __slots__ = ("_trusted",)

    def __init__(self, trusted_origins: Sequence[str]) -> None:
        self._trusted = frozenset(o.rstrip("/") for o in trusted_origins)

    async def verify(self, request: Request) -> None:
        if request.method in SAFE_METHODS:
            return

        origin = request.headers.get("origin")
        if origin is None:
            # Every browser sends `Origin` on a write, so a request without one
            # carries no automatically attached cookie. That reasoning rests on
            # clients we do not control, so refuse rather than infer.
            raise CsrfRejected(f"{request.method} {request.url.path} carried a session cookie but no Origin header")

        if origin.rstrip("/") not in self._trusted:
            raise CsrfRejected(f"Origin {origin!r} is not one of this app's trusted origins")

    def on_issue(self, response: Response, sid: str) -> None:
        """Plant nothing: the check reads a header the browser already sends."""


class NoCsrf:
    """Check nothing.

    For an app that needs no protection of its own: an internal tool behind a
    gateway that already checks. Explicit rather than `csrf=None`, so the
    decision appears in the app's wiring and stays findable.
    """

    __slots__ = ()

    async def verify(self, request: Request) -> None:
        return

    def on_issue(self, response: Response, sid: str) -> None:
        return
