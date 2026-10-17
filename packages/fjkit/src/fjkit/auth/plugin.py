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
import hmac
import logging
import secrets
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from fjkit.auth.csrf import NoCsrf, OriginCsrf
from fjkit.auth.errors import (
    AuthError,
    CsrfRejected,
    NotAuthenticated,
    RefreshFailed,
    RefreshRefused,
    RefreshUnavailable,
)
from fjkit.auth.sources import LocalSource
from fjkit.auth.stores import MemoryStore
from fjkit.auth.types import Csrf, Session, SessionStore, TokenSource, decode, encode
from fjkit.flash import FlashPlugin
from fjkit.htmx import is_htmx
from fjkit.plugins import AppSetup, EnvSetup, PluginWarning
from fjkit.signing import sign_text, unsign_text

__all__ = ["AuthPlugin", "CookieSpec", "safe_next"]

_log = logging.getLogger("fjkit.auth")

#: How often a request that lost the refresh race looks for the winner's work.
_POLL_SECONDS = 0.05

#: What a 503 for an unreachable upstream tells the caller. Advisory: a browser
#: ignores it and a person reloads when they like. Short, because the next
#: request retries the refresh anyway and an outage that is over should not
#: keep a script waiting.
_RETRY_AFTER_SECONDS = 5

#: How long a browser has to come back from the identity provider after
#: `start_login`. Long enough for a password and a second factor; short enough
#: that a nonce left in a browser does not outlive the authorization code it
#: was issued for.
_LOGIN_TTL = timedelta(minutes=10)

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
    uses = ("flash",)

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
        #: Derived from the session cookie's name, so two fjkit apps on one
        #: host that renamed their session cookies to coexist keep their login
        #: cookies apart as well.
        self._login_cookie = f"{self.cookie.name}_login"
        #: Optional. Filled at `mount` from the sibling registered as "flash"
        #: unless the app passed one: an explicit argument outranks the lookup,
        #: so an app can hand auth a flash configured differently from the one
        #: its routes use. Auth works without one, and flash stays useful to
        #: routes unrelated to auth.
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
        if self.flash is None:
            found = setup.plugin("flash")
            if isinstance(found, FlashPlugin):
                self.flash = found

        setup.add_middleware(_SessionMiddleware, plugin=self, static_url=setup.config.static_url)
        setup.add_exception_handler(NotAuthenticated, self._handle)
        setup.add_exception_handler(CsrfRejected, self._handle)
        setup.add_exception_handler(RefreshUnavailable, self._handle)

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
        setup.add_context_processor(lambda request: {"session": self._session(request)}, provides=["session"])

    # ------------------------------------------------------------- app-facing

    def start_login(self, response: Response) -> str:
        """Begin a login that completes on a GET, and bind this browser to it.

        An OpenID Connect or OAuth login ends with the provider sending the
        browser to `GET /callback?code=…&state=…`. A navigation carries no
        `Origin`, so nothing in `issue` can tell the visitor's own callback
        from one an attacker sent them to with the attacker's code (login
        CSRF; see `fjkit.auth.csrf`). The `state` parameter closes it: a nonce
        this browser holds in a signed, HttpOnly cookie and the provider echoes
        back, which `check_state` compares in the callback.

            @router.get("/login/oidc")
            def start(response: Response) -> Response:
                state = auth.start_login(response)
                response.status_code = 303
                response.headers["location"] = f"{AUTHORIZE_URL}?client_id=…&state={state}"
                return response

        Returns the value to put in the authorization URL's `state=`. The nonce
        is the whole secret: nothing is kept server-side, and the cookie's
        signature is what stops a browser presenting a nonce it was not given.

        The cookie is `SameSite=Lax` even when the session cookie is `Strict`,
        because the callback is a top-level navigation from the provider's
        site, which `Strict` would strip the cookie from. `None` is kept as
        `None`: an app embedded in another site's iframe cannot set a `Lax`
        cookie from there at all.
        """
        nonce = secrets.token_urlsafe(32)
        expires = int(time.time() + _LOGIN_TTL.total_seconds())
        response.set_cookie(
            self._login_cookie,
            sign_text(self.secret, f"{nonce}:{expires}"),
            max_age=int(_LOGIN_TTL.total_seconds()),
            path=self.cookie.path,
            domain=self.cookie.domain,
            secure=self.cookie.secure,
            httponly=True,
            samesite="none" if self.cookie.same_site == "none" else "lax",
        )
        return nonce

    def check_state(self, request: Request, response: Response, state: str) -> None:
        """Finish what `start_login` began. Call it in the callback, before `issue`.

            @router.get("/callback")
            async def callback(request: Request, response: Response, code: str, state: str) -> Response:
                auth.check_state(request, response, state)
                await auth.issue(request, response, code)
                response.status_code = 303
                response.headers["location"] = "/"
                return response

        Raises `CsrfRejected`, answered 403 like any other refused request,
        unless the browser holds the cookie `start_login` set, it is intact and
        younger than its TTL, and its nonce equals `state`. The comparison is
        constant-time; the rest is a signature check and a clock.

        Takes `response` because a passed check consumes the cookie, so the
        callback cannot be replayed with the same `state`. A refused check
        leaves the cookie alone: the browser may be in the middle of its own
        honest login, and a forged callback must not break it. The clearing
        lives here rather than in `issue` so a password login, which never
        set the cookie, does not emit a header deleting it.
        """
        raw = request.cookies.get(self._login_cookie)
        if not raw:
            raise CsrfRejected(f"GET {request.url.path} completes a login this browser never started")
        body = unsign_text(self.secret, raw)
        if body is None:
            raise CsrfRejected("the login cookie is not one this app signed")
        nonce, _, expires = body.partition(":")
        if not expires.isdigit() or int(expires) <= time.time():
            raise CsrfRejected("the login cookie is older than its TTL")
        if not hmac.compare_digest(nonce.encode("utf-8"), state.encode("utf-8")):
            raise CsrfRejected("`state` is not the one this browser's login started with")
        response.delete_cookie(
            self._login_cookie,
            path=self.cookie.path,
            domain=self.cookie.domain,
        )

    async def issue(self, request: Request, response: Response, credentials: Any) -> Session:
        """Log in: exchange `credentials`, store the session, set the cookie.

        Takes `request` so it can drop the caller's previous session; an id that
        survives a login is a session-fixation hole. This is the only point the
        id changes — a refresh keeps it (see `_refresh`).

        The login route is therefore `async def`, which is correct because it
        does network I/O. Every rendering route stays `def`.
        """
        # Checked before `exchange`, so a refused request never reaches the
        # upstream.
        await self._verify_if_browser(request)

        session = await self.source.exchange(credentials)

        previous = self._read_cookie(request)
        if previous is not None:
            await self.store.delete(previous)

        sid = secrets.token_urlsafe(32)
        await self._write(sid, session)
        self._set_cookie(response, sid)
        self.csrf.on_issue(response, sid)
        # So a login that renders rather than redirects sees the session it
        # just created, and not an outage the previous session hit.
        request.state.auth = session
        request.state.auth_unavailable = None
        return session

    async def revoke(self, request: Request, response: Response) -> None:
        """Log out: forget the session server-side and clear the cookie.

        Needs nothing from the upstream, and runs during an outage that has
        every other page answering 503 (see `_SessionMiddleware`).
        """
        await self._verify_if_browser(request)
        sid = self._read_cookie(request)
        if sid is not None:
            await self.store.delete(sid)
        response.delete_cookie(
            self.cookie.name,
            path=self.cookie.path,
            domain=self.cookie.domain,
        )
        request.state.auth = None
        request.state.auth_unavailable = None

    async def required(self, request: Request) -> Session:
        """Dependency. Refuse an anonymous request.

            router = APIRouter(dependencies=[Depends(auth.required)])

        Returns the session as well as raising, so a handler can take it as a
        parameter instead of reading `request.state`.
        """
        session = self._session(request)
        if session is None:
            raise NotAuthenticated(f"{request.url.path} needs a session")
        return session

    async def optional(self, request: Request) -> Session | None:
        """Dependency. The session, or `None`."""
        return self._session(request)

    # -------------------------------------------------------------- internals

    def _session(self, request: Request) -> Session | None:
        """What the middleware found, for everything that asks about the session.

        Raises the `RefreshUnavailable` the middleware deferred (see
        `_SessionMiddleware`), so asking is what turns an outage into a 503.
        """
        unavailable = getattr(request.state, "auth_unavailable", None)
        if unavailable is not None:
            raise unavailable
        return getattr(request.state, "auth", None)

    async def _verify_if_browser(self, request: Request) -> None:
        """Login and logout CSRF, the two anonymous writes that touch the cookie.

        `SameSite=Lax` keeps the cookie off a cross-site POST, so the middleware
        sees an anonymous request and checks nothing, yet these are the
        requests that create and clear the cookie: a foreign page could log the
        visitor in as the attacker, or sign them out. No `Origin` means no
        browser, hence no visitor to act on.
        """
        if request.headers.get("origin") is not None:
            await self.csrf.verify(request)

    async def load(self, request: Request) -> Session | None:
        """Return the session for this request, refreshed if it is near expiry.

        Called by the middleware. Raises `NotAuthenticated` only for a session
        that existed and the upstream refused to renew, and `RefreshUnavailable`
        only for one whose token has expired while the upstream cannot be
        reached; an absent or unreadable cookie is an anonymous request, not an
        error.
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

        Renewal starts `refresh_leeway` ahead of expiry, so an upstream that
        cannot be reached inside that window has cost nothing yet: the request
        is served on the token it has, which is still good, and the next one
        tries again. `RefreshUnavailable` is for the request that has no good
        token to be served on.

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

            # Only the upstream refusing ends a session. Anything else the
            # source raises is an outage: the session stays and the next
            # request tries again. The store's own failures are outside this
            # block on purpose, so a store that failed a moment ago does not
            # log every user out over a blip.
            try:
                fresh = await self.source.refresh(current)  # type: ignore[attr-defined]
            except RefreshRefused as exc:
                await self.store.delete(sid)
                raise RefreshFailed(f"the upstream refused to renew the session: {exc}") from exc
            except Exception as exc:
                if self._expired(current):
                    raise RefreshUnavailable(f"could not reach the upstream to renew the session: {exc}") from exc
                _log.warning("could not reach the upstream to renew a session ahead of expiry: %s", exc)
                return current

            await self._write(sid, fresh)
            return fresh
        finally:
            await self.store.release_refresh_lock(sid)

    async def _await_refresh(self, sid: str, stale: Session) -> Session:
        """Wait for whoever won the lock, then read what they wrote.

        The store is the only channel to the winner, which may be in another
        process, so the outcome is read off it: a renewed row means success, a
        missing row means the upstream refused, and a lock released with the
        row still expiring means the winner reached nobody. That last case is
        found by taking the lock, which only succeeds once the winner let go.

        The winner's failure is read the same way the winner read it: a token
        that is still good is served, one that has expired is not.
        """
        ttl = int(self.refresh_lock_ttl.total_seconds())
        deadline = asyncio.get_running_loop().time() + self.refresh_wait.total_seconds()
        current = stale
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(_POLL_SECONDS)
            payload = await self.store.get(sid)
            if payload is None:
                raise RefreshFailed("the session was dropped while its token was being renewed")
            current = decode(payload)
            if not self._expiring(current):
                return current
            if await self.store.acquire_refresh_lock(sid, ttl):
                # Not a second attempt: the upstream was unreachable a moment
                # ago, and a retry here would make the user wait out a second
                # timeout. The next request retries.
                await self.store.release_refresh_lock(sid)
                if self._expired(current):
                    raise RefreshUnavailable("another request could not reach the upstream to renew the session")
                return current
        if self._expired(current):
            raise RefreshUnavailable(
                "timed out waiting for another request to renew this session; "
                "raise `refresh_wait` if the upstream is slower than that"
            )
        return current

    def _expiring(self, session: Session) -> bool:
        """Report whether the token is inside the leeway, or already past it.

        `expires_at is None` means the source reported no expiry, so there is
        nothing to act on and the session is left alone.
        """
        if session.expires_at is None:
            return False
        return session.expires_at - datetime.now(UTC) <= self.refresh_leeway

    def _expired(self, session: Session) -> bool:
        """Report whether the token is past expiry, so nothing can be served on it."""
        return session.expires_at is not None and session.expires_at <= datetime.now(UTC)

    async def _write(self, sid: str, session: Session) -> None:
        await self.store.put(sid, encode(session), int(self.cookie.max_age.total_seconds()))

    # ------------------------------------------------------------- the cookie

    def _sign(self, sid: str) -> str:
        return sign_text(self.secret, sid)

    def _read_cookie(self, request: Request) -> str | None:
        raw = request.cookies.get(self.cookie.name)
        if not raw:
            return None
        return unsign_text(self.secret, raw) or None

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
            # and the request is what is wrong. The reason goes to the log, not
            # the wire — an app started on an unlisted port otherwise answers
            # every write with a blank 403 and nothing to say why.
            _log.warning("CSRF check refused %s %s: %s", request.method, request.url.path, exc)
            return Response(status_code=403)

        if isinstance(exc, RefreshUnavailable):
            # The session is intact and the request was fine; the identity
            # provider was not. One answer for every caller, because none of
            # them should move: a login page would need the same upstream.
            _log.warning("session not renewed for %s %s: %s", request.method, request.url.path, exc)
            return Response(
                "Your session could not be renewed because the sign-in service did not answer. "
                "Try again in a moment.",
                status_code=503,
                media_type="text/plain",
                headers={"retry-after": str(_RETRY_AFTER_SECONDS)},
            )

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
    """Verify, load and renew — before the handler, so routes see a plain session.

    One outcome is not settled here. A session whose token has expired while
    the upstream is unreachable leaves `request.state.auth` empty and the
    `RefreshUnavailable` on `request.state.auth_unavailable`, and the handler
    runs. `required`, `optional` and the template context raise it, so a page
    that needs the session still answers 503; a handler that needs none,
    which is what a logout is, gets through.
    """

    def __init__(self, app: Any, *, plugin: AuthPlugin, static_url: str) -> None:
        super().__init__(app)
        self.plugin = plugin
        self.static_prefix = static_url.rstrip("/") + "/"

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        plugin = self.plugin
        request.state.auth = None
        request.state.auth_unavailable = None
        if request.url.path.startswith(self.static_prefix):
            # The kit's own assets need no session, and must not wait on the
            # upstream: a page that loaded would otherwise arrive unstyled
            # during an outage, or cost a store read per stylesheet without one.
            return await call_next(request)
        try:
            if plugin._read_cookie(request) is not None:
                # Only when the browser attached a credential. A public POST
                # carrying no session has nothing for CSRF to steal, and
                # refusing it would break endpoints meant to be open.
                await plugin.csrf.verify(request)
                request.state.auth = await plugin.load(request)
        except RefreshUnavailable as exc:
            # Deferred, not answered. The handler may be a logout, which needs
            # the cookie and the store and nothing from the upstream; the
            # refusal is raised by whatever asks for the session instead.
            request.state.auth_unavailable = exc
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

    A backslash counts as the second slash. Browsers parse `\\` as `/` in the
    path of an `http(s)` URL (the WHATWG URL parser does this for every special
    scheme), so `Location: /\\evil.example.com` lands on `//evil.example.com`.
    The check reads the second character rather than scanning the whole value:
    a backslash anywhere later is still inside a path on this site.

    A control character anywhere refuses the value. The same parser strips tab,
    newline and carriage return before it reads the slashes, so the second
    character of `/\t/evil.example.com` is not the one the browser sees. A
    legitimate `next` has no raw control character in it: a URL carries one
    percent-encoded.
    """
    if not value or value[:1] != "/" or value[1:2] in ("/", "\\"):
        return fallback
    if any(ord(char) < 0x20 or char == "\x7f" for char in value):
        return fallback
    return value
