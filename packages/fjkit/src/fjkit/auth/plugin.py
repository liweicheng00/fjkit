"""`AuthPlugin` — the cookie the browser holds, the token the server keeps.

The browser gets one opaque, signed, HttpOnly cookie. The access token, the
refresh token and the app's claims stay in a `SessionStore` on the server. This
is the token-handler shape, also called a backend for frontend (BFF): a page
carries a session without JavaScript reading, storing or attaching a credential,
so an htmx app needs no `htmx:configRequest` hook, no refresh-and-retry glue and
no token in `<body>`.

The cookie carries a random 32-byte id and a hash-based message authentication
code (HMAC) of it. Signing an already-unguessable id is not about secrecy: it
rejects a forged or corrupted cookie without a round trip to the store.

The trade: a cookie is an ambient credential, so cross-site request forgery
(CSRF) comes back. `fjkit.auth.csrf` explains why this plugin handles it rather
than leaving it to the app.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from fjkit.auth.csrf import NoCsrf, OriginCsrf
from fjkit.auth.errors import AuthError, CsrfRejected, NotAuthenticated, RefreshFailed
from fjkit.auth.sources import LocalSource
from fjkit.auth.stores import MemoryStore
from fjkit.auth.types import Csrf, Session, SessionStore, TokenSource, decode, encode
from fjkit.htmx import is_htmx
from fjkit.plugins import AppSetup, EnvSetup, PluginWarning

if TYPE_CHECKING:
    from fjkit.flash import FlashPlugin

__all__ = ["AuthPlugin", "CookieSpec", "safe_next"]

#: How often a request that lost the refresh race looks for the winner's work.
_POLL_SECONDS = 0.05

#: What the user is told, per reason. Two entries, because they are different
#: events: never signed in here, versus signed in and the session ran out. Only
#: the second is worth interrupting someone about.
_FLASH_TEXT = {
    "required": ("Sign in to continue", "That page needs a session."),
    "expired": ("You were signed out", "Your session expired. Sign in again to carry on."),
}


def _full_path(request) -> str:
    """Join the path and its query string, so a filtered view survives the trip.

    `request.url.path` alone drops the query, and the user returns from the
    login form to an unfiltered list with their search gone.
    """
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def _is_navigation(request) -> bool:
    """Report whether a person is looking at this, rather than a program.

    Two signals, either one sufficient. `Sec-Fetch-Mode: navigate` is the
    purpose-built one: every current browser sends it when the address bar
    moves, and nothing else sends it. `Accept` is the fallback for browsers
    predating it — a navigation asks for `text/html`, while curl, `fetch()` and
    HTTP clients send `*/*`, which states no preference and counts as none.
    """
    if request.headers.get("sec-fetch-mode") == "navigate":
        return True
    return "text/html" in request.headers.get("accept", "")


@dataclass(frozen=True, slots=True)
class CookieSpec:
    """The one cookie this plugin sets.

    `httponly` is not a field. This plugin exists so no script can read the
    credential, and a setting to turn that off would only ever be turned off by
    mistake.
    """

    name: str = "fjkit_session"
    max_age: timedelta = timedelta(hours=8)
    path: str = "/"
    domain: str | None = None
    secure: bool = True
    #: `"lax"` still sends the cookie on a top-level navigation from another
    #: site, so a link into the app keeps the user logged in while a cross-site
    #: write gets nothing. `"none"` drops that protection and leaves the
    #: `Origin` check alone; use it only for an app embedded in another site's
    #: iframe.
    same_site: Literal["lax", "strict", "none"] = "lax"


class AuthPlugin:
    """Sessions for a fjkit app. Register it in `FjkitConfig.plugins`.

        auth = AuthPlugin(
            secret=os.environ["FJKIT_SECRET"],
            store=RedisStore(redis.from_url(REDIS_URL)),
            source=MyOIDCSource(),
            trusted_origins=["https://app.example.com"],
        )
        config = FjkitConfig(template_dir=..., plugins=(auth,))
        mount_fjkit(app, config)

    Every request costs one store read. That buys revoking a session by deleting
    a row, and keeping refresh tokens off the wire; a self-contained encrypted
    cookie gives neither.

    Routes see none of it. Put `Depends(auth.required)` on a router and its
    handlers keep their signatures; the session is on `request.state.auth`, and
    in every template as `session`.
    """

    name = "auth"

    def __init__(
        self,
        *,
        secret: str | bytes,
        store: SessionStore | None = None,
        source: TokenSource | None = None,
        cookie: CookieSpec | None = None,
        csrf: Csrf | None = None,
        trusted_origins: tuple[str, ...] | list[str] = (),
        flash: FlashPlugin | None = None,
        login_url: str = "/login",
        refresh_leeway: timedelta = timedelta(seconds=60),
        refresh_lock_ttl: timedelta = timedelta(seconds=10),
        refresh_wait: timedelta = timedelta(seconds=10),
    ) -> None:
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.store: SessionStore = store if store is not None else MemoryStore()
        self.source: TokenSource = source if source is not None else LocalSource()
        self.cookie = cookie or CookieSpec()
        #: Optional, and injected rather than imported: this kit has no rule
        #: letting one plugin depend on another. The app registers both and
        #: hands one to the other, so auth works without flash and flash stays
        #: useful to routes unrelated to auth.
        self.flash = flash
        self.login_url = login_url
        self.refresh_leeway = refresh_leeway
        self.refresh_lock_ttl = refresh_lock_ttl
        self.refresh_wait = refresh_wait
        self._warned_no_refresh = False

        if csrf is None:
            if not trusted_origins:
                raise ValueError(
                    "AuthPlugin needs `trusted_origins=[...]` for its Origin check. "
                    "They are named explicitly rather than read from the Host header, "
                    "which a request controls. Pass `csrf=NoCsrf()` to opt out on purpose."
                )
            csrf = OriginCsrf(trusted_origins)
        elif trusted_origins:
            raise ValueError("Pass either `csrf=` or `trusted_origins=`, not both.")
        self.csrf = csrf

    # ---------------------------------------------------------------- plugin

    def mount(self, setup: AppSetup) -> None:
        setup.add_middleware(_SessionMiddleware, plugin=self)
        setup.add_exception_handler(NotAuthenticated, self._handle)
        setup.add_exception_handler(CsrfRejected, self._handle)

        if isinstance(self.store, MemoryStore) and not setup.config.auto_reload:
            setup.warn(
                "MemoryStore under a production config: with more than one worker a "
                "request can land on a process that has never seen the session, and "
                "users are logged out at random. Use RedisStore, or a store of your own."
            )
        if self.cookie.same_site == "none" and not self.cookie.secure:
            setup.warn("SameSite=None requires Secure; browsers will drop this cookie.")
        if isinstance(self.csrf, NoCsrf):
            setup.warn("CSRF checking is off. Every cookie-authenticated write is unprotected.")

    def extend(self, setup: EnvSetup) -> None:
        setup.add_context_processor(
            lambda request: {"session": getattr(request.state, "auth", None)},
            provides=["session"],
        )

    # ------------------------------------------------------------- app-facing

    async def issue(self, request: Request, response: Response, credentials: Any) -> Session:
        """Log in: exchange `credentials`, store the session, set the cookie.

        Takes `request` so it can drop the caller's previous session; an id that
        survives a login is a session-fixation hole. This is the only point the
        id changes — a refresh keeps it (see `_refresh`).

        The login route is therefore `async def`, which is correct because it
        does network I/O. Every rendering route stays `def`.
        """
        session = await self.source.exchange(credentials)

        previous = self._read_cookie(request)
        if previous is not None:
            await self.store.delete(previous)

        sid = secrets.token_urlsafe(32)
        await self._write(sid, session)
        self._set_cookie(response, sid)
        self.csrf.on_issue(response, sid)
        # So a login that renders rather than redirects sees the session it
        # just created.
        request.state.auth = session
        return session

    async def revoke(self, request: Request, response: Response) -> None:
        """Log out: forget the session server-side and clear the cookie."""
        sid = self._read_cookie(request)
        if sid is not None:
            await self.store.delete(sid)
        response.delete_cookie(
            self.cookie.name,
            path=self.cookie.path,
            domain=self.cookie.domain,
        )
        request.state.auth = None

    async def required(self, request: Request) -> Session:
        """Dependency. Refuse an anonymous request.

            router = APIRouter(dependencies=[Depends(auth.required)])

        Returns the session as well as raising, so a handler can take it as a
        parameter instead of reading `request.state`.
        """
        session = getattr(request.state, "auth", None)
        if session is None:
            raise NotAuthenticated(f"{request.url.path} needs a session")
        return session

    async def optional(self, request: Request) -> Session | None:
        """Dependency. The session, or `None`."""
        return getattr(request.state, "auth", None)

    # -------------------------------------------------------------- internals

    async def load(self, request: Request) -> Session | None:
        """Return the session for this request, refreshed if it is near expiry.

        Called by the middleware. Raises `NotAuthenticated` only for a session
        that existed and could not be renewed; an absent or unreadable cookie is
        an anonymous request, not an error.
        """
        sid = self._read_cookie(request)
        if sid is None:
            return None

        payload = await self.store.get(sid)
        if payload is None:
            return None
        try:
            session = decode(payload)
        except (ValueError, TypeError):
            # A payload this process cannot read is not a session. Drop it,
            # rather than answer 500 to every request until the user clears
            # their cookies.
            await self.store.delete(sid)
            return None

        return await self._refresh(sid, session)

    async def _refresh(self, sid: str, session: Session) -> Session:
        """Renew the token once, however many requests notice at the same time.

        Self-guarding: a session that is not near expiry, or a source that
        cannot renew, is returned unchanged, so callers need not know which case
        they are in.

        The session id does not change here. Rotating it would give several
        concurrent swaps a different `Set-Cookie` each; the last wins, the rest
        become orphans, and the mechanism meant to keep the user signed in logs
        them out.
        """
        if not self._expiring(session):
            return session

        if not hasattr(self.source, "refresh"):
            # Reported here rather than at startup, where it is not yet true: a
            # source with no `refresh` and no `expires_at` is an ordinary
            # configuration, and warning about it would train people to ignore
            # the warning that matters. Warned once, so a busy app does not
            # write this line on every request.
            if not self._warned_no_refresh:
                self._warned_no_refresh = True
                warnings.warn(
                    f"[fjkit:{self.name}] {type(self.source).__name__} hands out tokens with an "
                    "`expires_at` but has no `refresh()`, so sessions end when the token does.",
                    PluginWarning,
                    stacklevel=2,
                )
            return session

        if not await self.store.acquire_refresh_lock(sid, int(self.refresh_lock_ttl.total_seconds())):
            return await self._await_refresh(sid, session)

        try:
            # Read again now that the lock is held. Another request may have
            # finished renewing since this one's first read, and the token held
            # here is single-use: spending it twice makes an upstream with
            # rotation revoke the whole family.
            payload = await self.store.get(sid)
            current = decode(payload) if payload is not None else session
            if not self._expiring(current):
                return current

            try:
                fresh = await self.source.refresh(current)  # type: ignore[attr-defined]
            except Exception as exc:
                # Only the upstream refusing ends a session. Otherwise a store
                # that failed a moment ago logs every user out over a blip,
                # which is worse than one retried request.
                await self.store.delete(sid)
                raise RefreshFailed(f"could not renew the session: {exc}") from exc

            await self._write(sid, fresh)
            return fresh
        finally:
            await self.store.release_refresh_lock(sid)

    async def _await_refresh(self, sid: str, stale: Session) -> Session:
        """Wait for whoever won the lock, then read what they wrote."""
        deadline = asyncio.get_running_loop().time() + self.refresh_wait.total_seconds()
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_POLL_SECONDS)
            payload = await self.store.get(sid)
            if payload is None:
                raise RefreshFailed("the session was dropped while its token was being renewed")
            session = decode(payload)
            if not self._expiring(session):
                return session
        raise RefreshFailed(
            "timed out waiting for another request to renew this session; "
            "raise `refresh_wait` if the upstream is slower than that"
        )

    def _expiring(self, session: Session) -> bool:
        """Report whether the token is inside the leeway, or already past it.

        `expires_at is None` means the source reported no expiry, so there is
        nothing to act on and the session is left alone.
        """
        if session.expires_at is None:
            return False
        return session.expires_at - datetime.now(UTC) <= self.refresh_leeway

    async def _write(self, sid: str, session: Session) -> None:
        await self.store.put(sid, encode(session), int(self.cookie.max_age.total_seconds()))

    # ------------------------------------------------------------- the cookie

    def _sign(self, sid: str) -> str:
        mac = hmac.new(self.secret, sid.encode("ascii"), hashlib.sha256).digest()
        return f"{sid}.{base64.urlsafe_b64encode(mac).decode('ascii').rstrip('=')}"

    def _read_cookie(self, request: Request) -> str | None:
        raw = request.cookies.get(self.cookie.name)
        if not raw:
            return None
        sid, _, _ = raw.partition(".")
        if not sid or not hmac.compare_digest(raw, self._sign(sid)):
            return None
        return sid

    def _set_cookie(self, response: Response, sid: str) -> None:
        response.set_cookie(
            self.cookie.name,
            self._sign(sid),
            max_age=int(self.cookie.max_age.total_seconds()),
            path=self.cookie.path,
            domain=self.cookie.domain,
            secure=self.cookie.secure,
            httponly=True,
            samesite=self.cookie.same_site,
        )

    # ------------------------------------------------------------- responses

    def _handle(self, request: Request, exc: Exception) -> Response:
        """Build the refusal for both entry points.

        Registered as an exception handler and called from the middleware,
        because Starlette's `ExceptionMiddleware` sits inside the user
        middleware stack, so an error raised in middleware never reaches a
        registered handler. Sharing this function stops the two paths drifting
        into different answers.
        """
        if isinstance(exc, CsrfRejected):
            # No redirect to the login page: the browser is where it belongs,
            # and the request is what is wrong.
            return Response(status_code=403)

        # Three kinds of caller, three answers — the same question `@render`
        # asks about what to put on the wire, asked about how to refuse.
        #
        # 401 everywhere reads the spec tidily and is wrong for one of the
        # three: a plain navigation cannot act on it and lands on a blank page.
        # The other two get 401, and the htmx one still moves — see below.
        vary = {"vary": "HX-Request, Accept, Sec-Fetch-Mode"}
        # `safe="/"` and nothing else. Leaving `?`, `=` or `&` raw lets the
        # value's own query string break out into extra parameters of the login
        # URL, so `next` arrives truncated at the first `?`.
        target = f"{self.login_url}?next={quote(_full_path(request), safe='/')}"
        reason = "expired" if isinstance(exc, RefreshFailed) else "required"

        if is_htmx(request):
            # 401 and a redirect together: htmx acts on `HX-Redirect` before it
            # reads the status code, so the status stays accurate while the
            # browser still moves the whole page.
            #
            # It has to move the whole page. htmx's own fetch would follow a
            # 303 and swap the login form into whatever element the click
            # targeted; a bare 401 would swap nothing, because htmx ignores a
            # 4xx body, and the click would appear to do nothing.
            response: Response = Response(status_code=401, headers={"HX-Redirect": target, **vary})
        elif _is_navigation(request):
            response = Response(status_code=303, headers={"location": target, **vary})
        else:
            # A script, curl, another service. Under `render_mode="auto"` a
            # route answers this caller in JSON, so refusing with a redirect to
            # an HTML login form answers a question it did not ask, and
            # following that redirect hands it a login page with a 200, which
            # reads as success.
            #
            # No `WWW-Authenticate`: RFC 9110 requires the field, and every
            # registered scheme is wrong here. `Basic` makes the browser open
            # its own credential dialog, which is the login form this plugin
            # replaces.
            return JSONResponse(
                {"detail": "authentication required", "reason": reason, "login_url": self.login_url},
                status_code=401,
                headers=vary,
            )

        # Both branches above end in a new page load, which `HX-Trigger` cannot
        # survive: the document it would fire into is gone. A cookie crosses
        # that gap.
        if self.flash is not None:
            self.flash.add(response, *_FLASH_TEXT[reason], category="warning")
        return response


class _SessionMiddleware(BaseHTTPMiddleware):
    """Verify, load and renew — before the handler, so routes see a plain session."""

    def __init__(self, app: Any, *, plugin: AuthPlugin) -> None:
        super().__init__(app)
        self.plugin = plugin

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        plugin = self.plugin
        request.state.auth = None
        try:
            if plugin._read_cookie(request) is not None:
                # Only when the browser attached a credential. A public POST
                # carrying no session has nothing for CSRF to steal, and
                # refusing it would break endpoints meant to be open.
                await plugin.csrf.verify(request)
                request.state.auth = await plugin.load(request)
        except AuthError as exc:
            return plugin._handle(request, exc)
        return await call_next(request)


def safe_next(value: str | None, fallback: str = "/") -> str:
    """Return the `next=` value, or `fallback` when it points off this site.

    The plugin only ever writes a path here, so nothing it produced points
    off-site. What arrives back is a query string, which anyone can type, and a
    login page that redirects to whatever it is handed is an open redirect: a
    link to your own domain, your own login form, then a hop to the attacker's
    site at the moment someone has typed their password.

    The rule is positional rather than a blocklist. One leading slash, not two:
    `//evil.example.com` is a protocol-relative URL that a browser reads as a
    different site, and a naive `startswith("/")` lets it through.
    """
    if not value or not value.startswith("/") or value.startswith("//"):
        return fallback
    return value
