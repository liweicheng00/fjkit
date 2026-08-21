"""CSRF, in the two layers a cookie-authenticated server-rendered app needs.

A cookie is an ambient credential: the browser attaches it to a cross-site
request without being asked. That is the whole vulnerability, and it is the one
thing a `Bearer` header does not have.

`SameSite=Lax` on the cookie (see `CookieSpec`) stops the browser sending it on
a cross-*site* write at all, which is nearly every classic CSRF. What it misses
is same-site cross-origin: `evil.example.com` and `app.example.com` share a
registrable domain, so Lax considers them one site and sends the cookie. An
`Origin` comparison is exact — scheme, host and port — so it catches precisely
the case Lax does not. The two are worth having together because they fail in
different directions, not because either is weak.

There is deliberately no token strategy in this first version. A token has to
reach every form and every htmx request, which means the form macro and the
shell both need request-scoped data — so shipping one means shipping a whole
templating feature alongside it. `Csrf.on_issue` is where that strategy will
plug in when it is worth the cost.

Two things this does not cover, and cannot:

* A GET that changes state. No header check helps; that is a routing decision.
* Non-browser clients on cookie-authenticated writes. They send no `Origin`,
  and are refused. Those callers should use a bearer token instead — which is
  the same route in `"auto"` mode answering JSON.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import Request, Response

from fjkit.auth.errors import CsrfRejected

__all__ = ["NoCsrf", "OriginCsrf"]

#: Methods that do not change state, and so carry no CSRF risk worth refusing
#: a request over. `OPTIONS` is here because refusing a preflight breaks the
#: very requests that would have been checked properly a moment later.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class OriginCsrf:
    """Refuse a cookie-authenticated write whose `Origin` is not ours.

    `trusted_origins` is given explicitly and never derived from the `Host`
    header. `Host` is attacker-controlled; a check that compares a request
    against a value the request supplied is not a check.
    """

    __slots__ = ("_trusted",)

    def __init__(self, trusted_origins: Sequence[str]) -> None:
        self._trusted = frozenset(o.rstrip("/") for o in trusted_origins)

    async def verify(self, request: Request) -> None:
        if request.method in SAFE_METHODS:
            return

        origin = request.headers.get("origin")
        if origin is None:
            # Every browser sends `Origin` on a write, and a request without
            # one has no cookie the browser attached automatically — but that
            # reasoning depends on details of clients we do not control, so the
            # default is to refuse rather than to reason.
            raise CsrfRejected(f"{request.method} {request.url.path} carried a session cookie but no Origin header")

        if origin.rstrip("/") not in self._trusted:
            raise CsrfRejected(f"Origin {origin!r} is not one of this app's trusted origins")

    def on_issue(self, response: Response, sid: str) -> None:
        """Nothing to plant. The check reads a header the browser already sends."""


class NoCsrf:
    """Check nothing.

    For an app that is certain it needs no protection — an internal tool behind
    a gateway that already does this. Explicit rather than `csrf=None`, so the
    decision appears in the app's wiring and can be found later.
    """

    __slots__ = ()

    async def verify(self, request: Request) -> None:
        return

    def on_issue(self, response: Response, sid: str) -> None:
        return
