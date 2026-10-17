"""The auth plugin: the cookie, the CSRF check, and the refresh race."""

from __future__ import annotations

import asyncio
import logging
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, PluginWarning, mount_fjkit, render
from fjkit.auth import (
    AuthPlugin,
    CookieSpec,
    MemoryStore,
    NoCsrf,
    RefreshFailed,
    RefreshRefused,
    RefreshUnavailable,
    Session,
)
from fjkit.auth.plugin import safe_next
from fjkit.auth.types import decode, encode
from jinja2 import DictLoader

ORIGIN = "http://testserver"
IDP = "https://idp.example/authorize"

#: What a browser navigating to a page sends. `TestClient` sends `Accept: */*`,
#: which is the programmatic caller, so a test about browser behaviour has to
#: say so rather than rely on "not htmx".
BROWSER = {"accept": "text/html,application/xhtml+xml"}

TEMPLATES = {
    "who.html": "{{ session.claims.name if session else 'anonymous' }}",
    "ok.html": "ok",
}


def make_auth(**kwargs) -> AuthPlugin:
    kwargs.setdefault("secret", "test-secret")
    kwargs.setdefault("trusted_origins", [ORIGIN])
    # TestClient talks http://, and a Secure cookie would never be sent back.
    kwargs.setdefault("cookie", CookieSpec(secure=False))
    return AuthPlugin(**kwargs)


def make_app(auth: AuthPlugin, **config_kwargs) -> TestClient:
    router = APIRouter()

    @router.get("/who")
    @render("who.html")
    def who() -> dict[str, str]:
        return {}

    @router.post("/login")
    async def login(request: Request, response: Response, name: str = "ada") -> Response:
        await auth.issue(request, response, {"name": name})
        response.status_code = 204
        return response

    @router.post("/logout")
    async def logout(request: Request, response: Response) -> Response:
        await auth.revoke(request, response)
        response.status_code = 204
        return response

    @router.post("/public")
    def public() -> dict[str, str]:
        return {"ok": "yes"}

    # The OpenID Connect shape: a redirect out to the provider, and a GET back
    # carrying the authorization code. The code is the credential.
    @router.get("/oidc/start")
    def oidc_start(response: Response) -> Response:
        state = auth.start_login(response)
        response.status_code = 303
        response.headers["location"] = f"{IDP}?state={state}"
        return response

    @router.get("/oidc/callback")
    async def oidc_callback(request: Request, response: Response, code: str, state: str) -> Response:
        auth.check_state(request, response, state)
        await auth.issue(request, response, code)
        response.status_code = 204
        return response

    private = APIRouter(prefix="/private", dependencies=[Depends(auth.required)])

    @private.get("/thing")
    @render("ok.html")
    def thing() -> dict[str, str]:
        return {}

    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig(plugins=(auth,), **config_kwargs))
    templates.env.loader = DictLoader(TEMPLATES)
    app.include_router(router)
    app.include_router(private)
    return TestClient(app, base_url=ORIGIN)


# ------------------------------------------------------------------- the cookie


def test_an_anonymous_request_has_no_session():
    client = make_app(make_auth())

    assert client.get("/who").text == "anonymous"


def test_login_sets_an_httponly_cookie_and_the_session_survives():
    client = make_app(make_auth())

    login = client.post("/login", headers={"origin": ORIGIN})
    cookie = login.headers["set-cookie"]

    assert login.status_code == 204
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert client.get("/who").text == "ada"


def test_the_cookie_never_carries_the_claims():
    auth = make_auth()
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN}, params={"name": "top-secret"})

    assert "top-secret" not in client.cookies[auth.cookie.name]


def test_a_tampered_cookie_is_anonymous_not_an_error():
    auth = make_auth()
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN})

    sid, _, signature = client.cookies[auth.cookie.name].partition(".")
    client.cookies.set(auth.cookie.name, f"{sid}x.{signature}")

    assert client.get("/who").text == "anonymous"


@pytest.mark.parametrize(
    "value",
    ["café.x", "abc.café"],
    ids=["non-ascii-body", "non-ascii-signature"],
)
def test_a_non_ascii_cookie_is_anonymous_not_an_error(value):
    """A cookie value a browser sends as UTF-8 reaches the verifier as non-ASCII
    text. Nothing this plugin signed looks like that, so it is a bad cookie:
    anonymous, like a tampered one, not a 500 on every page until the user
    clears their cookies. A sibling subdomain can plant such a cookie, which
    would otherwise lock the browser out of the whole app."""
    auth = make_auth()
    client = make_app(auth)

    response = client.get("/who", headers=[(b"cookie", f"{auth.cookie.name}={value}".encode())])

    assert response.status_code == 200
    assert response.text == "anonymous"


def test_logout_clears_both_sides():
    auth = make_auth(store=MemoryStore())
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN})
    sid = client.cookies[auth.cookie.name].partition(".")[0]

    client.post("/logout", headers={"origin": ORIGIN})

    assert client.get("/who").text == "anonymous"
    assert asyncio.run(auth.store.get(sid)) is None


def test_logging_in_again_replaces_the_session_id():
    """A session id that survives a login is a session-fixation hole."""
    auth = make_auth(store=MemoryStore())
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN})
    first = client.cookies[auth.cookie.name].partition(".")[0]

    client.post("/login", headers={"origin": ORIGIN})
    second = client.cookies[auth.cookie.name].partition(".")[0]

    assert first != second
    assert asyncio.run(auth.store.get(first)) is None


# ------------------------------------------------------------------ refusing


def test_a_navigation_without_a_session_is_redirected():
    """A browser is sent to the login form. A 401 here renders a blank page."""
    client = make_app(make_auth())

    response = client.get("/private/thing", headers=BROWSER, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/private/thing"
    assert response.headers["vary"] == "HX-Request, Accept, Sec-Fetch-Mode"


def test_the_next_parameter_keeps_the_query_string():
    """The login form returns the user to the view they were on, filter and all.
    `request.url.path` alone drops the query, landing them on an unfiltered list
    with no sign of where their search went."""
    client = make_app(make_auth())

    response = client.get("/private/thing?status=doing&page=2", headers=BROWSER, follow_redirects=False)

    assert response.headers["location"] == "/login?next=/private/thing%3Fstatus%3Ddoing%26page%3D2"


def test_a_navigation_is_recognised_by_sec_fetch_mode_too():
    """`Sec-Fetch-Mode` is the purpose-built signal, for callers that send it."""
    client = make_app(make_auth())

    response = client.get(
        "/private/thing",
        headers={"sec-fetch-mode": "navigate", "accept": "*/*"},
        follow_redirects=False,
    )

    assert response.status_code == 303


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/tasks?status=doing", "/tasks?status=doing"),
        ("//evil.example.com", "/"),
        ("/\\evil.example.com", "/"),
        ("/\t/evil.example.com", "/"),
        ("/\n/evil.example.com", "/"),
        ("/\r/evil.example.com", "/"),
        ("/\t\\evil.example.com", "/"),
        ("/tasks?path=a\\b", "/tasks?path=a\\b"),
        ("https://evil.example.com", "/"),
        ("evil.example.com", "/"),
        ("", "/"),
        (None, "/"),
    ],
)
def test_safe_next_only_returns_to_this_site(value, expected):
    """A login page that redirects to whatever it is handed is an open redirect:
    your domain, your login form, then a hop to the attacker's site the moment
    someone has typed their password.

    `//evil.example.com` is the case a naive `startswith("/")` waves through. A
    browser reads it as a protocol-relative URL, so it is a different site.
    `/\\evil.example.com` is the same case in disguise: a browser turns the
    backslash into a slash before it resolves the URL. A backslash later in the
    value is still a path on this site and is kept.

    `/\t/evil.example.com` is the same case again: the WHATWG URL parser strips
    ASCII tab and newline before it looks at the slashes, so the second
    character the check reads is not the one the browser reads.
    """
    assert safe_next(value) == expected


def test_a_caller_with_no_markup_waiting_gets_401():
    """The one caller a 401 is right for.

    Under `render_mode="auto"` a route answers this request in JSON, so refusing
    it with a redirect to an HTML login form answers a question it did not ask.
    """
    client = make_app(make_auth())

    response = client.get("/private/thing", follow_redirects=False)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"
    assert response.json()["login_url"] == "/login"


def test_the_401_carries_no_www_authenticate():
    """RFC 9110 asks for the field, and every registered scheme is wrong here.

    `Basic` would make the browser open its own credential dialog, which is
    precisely the login form this plugin exists to replace.
    """
    client = make_app(make_auth())

    assert "www-authenticate" not in client.get("/private/thing").headers


def test_an_htmx_swap_without_a_session_gets_hx_redirect():
    """401 and a redirect together, which is not a contradiction.

    htmx acts on `HX-Redirect` before it reads the status code, so the status
    stays honest while the browser still moves the whole page. A 303 would be
    followed and the login page swapped into a card; a bare 401 would swap
    nothing, because htmx ignores a 4xx body.
    """
    client = make_app(make_auth())

    response = client.get("/private/thing", headers={"HX-Request": "true"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/login?next=/private/thing"


def test_a_session_gets_through():
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    assert client.get("/private/thing").text == "ok"


# ---------------------------------------------------------------------- csrf


def test_a_write_with_a_session_and_no_origin_is_refused():
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    assert client.post("/logout").status_code == 403


def test_a_write_from_another_origin_is_refused():
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    assert client.post("/logout", headers={"origin": "http://evil.example.com"}).status_code == 403


def test_a_csrf_refusal_is_logged_with_its_reason_and_the_response_stays_blank(caplog):
    """A developer on another port sees an empty 403; the log has to say why."""
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    with caplog.at_level("WARNING", logger="fjkit.auth"):
        response = client.post("/logout", headers={"origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert response.content == b""
    [record] = [r for r in caplog.records if r.name == "fjkit.auth"]
    assert record.levelname == "WARNING"
    assert "POST /logout" in record.getMessage()
    assert "http://evil.example.com" in record.getMessage()


def test_a_public_write_without_a_session_is_not_checked():
    """Nothing ambient is attached, so there is nothing to forge."""
    client = make_app(make_auth())

    assert client.post("/public").json() == {"ok": "yes"}


def test_a_cross_origin_login_is_refused_before_a_session_exists():
    """Login CSRF: Lax sends no cookie on a cross-site POST, so the middleware
    has nothing to check, and the attacker's credentials would log the visitor
    in as the attacker."""
    client = make_app(make_auth())

    response = client.post("/login", headers={"origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert client.get("/who").text == "anonymous"


def test_a_cross_origin_logout_is_refused():
    """Logout CSRF, the mirror of login CSRF. A cross-site POST carries no
    cookie under Lax, so the middleware checks nothing, yet the response would
    carry a clearing Set-Cookie that the browser applies on a top-level
    navigation: a foreign page could sign the visitor out."""
    client = make_app(make_auth())

    response = client.post("/logout", headers={"origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_a_login_without_an_origin_is_a_non_browser_client_and_is_let_through():
    """A browser always sends `Origin` on a POST, so no `Origin` means no
    visitor's browser to plant a session in."""
    client = make_app(make_auth())

    assert client.post("/login").status_code == 204
    assert client.get("/who").text == "ada"


def test_reads_are_never_checked():
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    assert client.get("/who").text == "ada"


class CodeSource:
    """An upstream that trades an authorization code for a session, counting
    how often it is asked."""

    def __init__(self) -> None:
        self.exchanges = 0

    async def exchange(self, code: str) -> Session:
        self.exchanges += 1
        return Session(claims={"name": f"owner-of-{code}"})


def state_of(start) -> str:
    """The `state` the app put in its redirect to the provider."""
    assert start.status_code == 303
    return parse_qs(urlsplit(start.headers["location"]).query)["state"][0]


def login_cookie_header(response) -> tuple[str, str]:
    """The name and raw value of the one cookie `start_login` set."""
    header = response.headers["set-cookie"]
    name, _, value = header.split(";", 1)[0].partition("=")
    return name, value


def test_an_oidc_login_round_trips_through_state():
    source = CodeSource()
    client = make_app(make_auth(source=source))

    start = client.get("/oidc/start", follow_redirects=False)
    state = state_of(start)
    callback = client.get("/oidc/callback", params={"code": "c1", "state": state})

    assert "HttpOnly" in start.headers["set-cookie"]
    assert callback.status_code == 204
    assert client.get("/who").text == "owner-of-c1"
    assert source.exchanges == 1


def test_a_callback_the_browser_never_started_is_refused_before_the_exchange():
    """Login CSRF on a GET. The attacker sends the victim to the callback with
    the attacker's own code and state. The victim's browser never visited
    `/oidc/start`, so it holds no nonce, and the request must die before the
    upstream is asked to turn the code into the attacker's session."""
    source = CodeSource()
    client = make_app(make_auth(source=source))

    response = client.get("/oidc/callback", params={"code": "attacker", "state": "attacker-state"})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert client.get("/who").text == "anonymous"
    assert source.exchanges == 0


def test_a_callback_with_someone_elses_state_is_refused_and_the_victims_own_login_survives():
    """The victim is mid-flow, so their browser holds a nonce, and the forged
    callback carries a different one. Refusing it must not break the login the
    victim is in the middle of."""
    source = CodeSource()
    client = make_app(make_auth(source=source))
    state = state_of(client.get("/oidc/start", follow_redirects=False))

    forged = client.get("/oidc/callback", params={"code": "attacker", "state": "attacker-state"})
    honest = client.get("/oidc/callback", params={"code": "c1", "state": state})

    assert forged.status_code == 403
    assert honest.status_code == 204
    assert client.get("/who").text == "owner-of-c1"
    assert source.exchanges == 1


def test_a_callback_cannot_be_replayed_after_it_succeeded():
    source = CodeSource()
    client = make_app(make_auth(source=source))
    state = state_of(client.get("/oidc/start", follow_redirects=False))
    client.get("/oidc/callback", params={"code": "c1", "state": state})

    replay = client.get("/oidc/callback", params={"code": "c2", "state": state})

    assert replay.status_code == 403
    assert client.get("/who").text == "owner-of-c1", "the replay must not replace the session either"
    assert source.exchanges == 1


def test_a_tampered_login_cookie_is_refused():
    source = CodeSource()
    client = make_app(make_auth(source=source))
    start = client.get("/oidc/start", follow_redirects=False)
    state = state_of(start)
    name, value = login_cookie_header(start)
    client.cookies.set(name, value[:-1] + ("A" if value[-1] != "A" else "B"))

    response = client.get("/oidc/callback", params={"code": "c1", "state": state})

    assert response.status_code == 403
    assert client.get("/who").text == "anonymous"
    assert source.exchanges == 0


def test_a_login_cookie_older_than_its_ttl_is_refused(monkeypatch):
    """The cookie's own `Max-Age` makes a browser drop it, which the client here
    does too, so the expired cookie is put back by hand: the server has to
    refuse it on its own evidence, not the browser's."""
    monkeypatch.setattr("fjkit.auth.plugin._LOGIN_TTL", timedelta(seconds=-1))
    source = CodeSource()
    client = make_app(make_auth(source=source))
    start = client.get("/oidc/start", follow_redirects=False)
    state = state_of(start)
    name, value = login_cookie_header(start)
    client.cookies.set(name, value)

    response = client.get("/oidc/callback", params={"code": "c1", "state": state})

    assert response.status_code == 403
    assert source.exchanges == 0


def test_no_csrf_lets_everything_through_and_says_so():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = make_app(AuthPlugin(secret="s", csrf=NoCsrf(), cookie=CookieSpec(secure=False)))

    client.post("/login")
    assert client.post("/logout").status_code == 204
    assert any("CSRF checking is off" in str(w.message) for w in caught)


# ------------------------------------------------------------------- refresh


class CountingSource:
    """An upstream whose token expires, counting how often it renews."""

    def __init__(self, *, ttl: timedelta = timedelta(hours=1), delay: float = 0.0) -> None:
        self.ttl = ttl
        self.delay = delay
        self.refreshes = 0

    async def exchange(self, credentials) -> Session:
        return Session(claims=dict(credentials), access="access-0", expires_at=datetime.now(UTC) + self.ttl)

    async def refresh(self, session: Session) -> Session:
        if self.delay:
            await asyncio.sleep(self.delay)
        self.refreshes += 1
        return Session(
            claims=session.claims,
            access=f"access-{self.refreshes}",
            expires_at=datetime.now(UTC) + self.ttl,
        )


async def seed(auth: AuthPlugin, session: Session) -> str:
    sid = "seeded-sid"
    await auth.store.put(sid, encode(session), 3600)
    return sid


def test_a_healthy_token_is_left_alone():
    source = CountingSource()
    auth = make_auth(source=source, store=MemoryStore())

    async def run():
        sid = await seed(auth, Session(access="a", expires_at=datetime.now(UTC) + timedelta(hours=1)))
        return await auth._refresh(sid, decode(await auth.store.get(sid)))

    assert auth._expiring(Session(expires_at=datetime.now(UTC) + timedelta(hours=1))) is False
    asyncio.run(run())
    assert source.refreshes == 0


def test_an_expiring_token_is_renewed_and_written_back():
    source = CountingSource()
    auth = make_auth(source=source, store=MemoryStore())

    async def run():
        sid = await seed(auth, Session(access="access-0", expires_at=datetime.now(UTC) + timedelta(seconds=5)))
        fresh = await auth._refresh(sid, decode(await auth.store.get(sid)))
        stored = decode(await auth.store.get(sid))
        return fresh, stored

    fresh, stored = asyncio.run(run())

    assert source.refreshes == 1
    assert fresh.access == "access-1"
    assert stored.access == "access-1", "the renewed token has to reach the store, not just this request"


@pytest.mark.asyncio
async def test_concurrent_requests_refresh_exactly_once():
    """The failure this lock exists for.

    Four htmx swaps fire at once and all see an expiring token. Without the lock
    all four call refresh, and an upstream that rotates refresh tokens revokes
    the family when the second arrives, logging the user out mid-click.
    """
    source = CountingSource(delay=0.1)
    auth = make_auth(source=source, store=MemoryStore())

    stale = Session(access="access-0", expires_at=datetime.now(UTC) + timedelta(seconds=5))
    sid = await seed(auth, stale)

    results = await asyncio.gather(*(auth._refresh(sid, stale) for _ in range(4)))

    assert source.refreshes == 1
    assert {s.access for s in results} == {"access-1"}, "the losers must return the renewed token, not the stale one"


@pytest.mark.asyncio
async def test_a_request_holding_a_spent_token_does_not_spend_it_again():
    """The race the lock alone does not close.

    A refresh finishes and releases the lock. A request that read the store just
    before that write finds the lock free, and would renew again with a refresh
    token the upstream has already retired.
    """
    source = CountingSource()
    auth = make_auth(source=source, store=MemoryStore())

    stale = Session(access="access-0", expires_at=datetime.now(UTC) + timedelta(seconds=5))
    sid = await seed(auth, stale)
    await auth._refresh(sid, stale)

    late = await auth._refresh(sid, stale)  # same stale session, lock now free

    assert source.refreshes == 1
    assert late.access == "access-1"


@pytest.mark.asyncio
async def test_a_refused_refresh_ends_the_session():
    class Broken(CountingSource):
        async def refresh(self, session: Session) -> Session:
            raise RefreshRefused("upstream said no")

    auth = make_auth(source=Broken(), store=MemoryStore())
    stale = Session(access="a", expires_at=datetime.now(UTC) + timedelta(seconds=5))
    sid = await seed(auth, stale)

    with pytest.raises(RefreshFailed):
        await auth._refresh(sid, stale)

    assert await auth.store.get(sid) is None, "a session that cannot be renewed must not linger"


@pytest.mark.asyncio
async def test_the_lock_is_released_even_when_the_upstream_fails():
    class Broken(CountingSource):
        async def refresh(self, session: Session) -> Session:
            raise RuntimeError("upstream said no")

    auth = make_auth(source=Broken(), store=MemoryStore())
    sid = await seed(auth, Session(access="a", expires_at=datetime.now(UTC) + timedelta(seconds=5)))

    with pytest.raises(RefreshUnavailable):
        await auth._refresh(sid, Session(access="a", expires_at=datetime.now(UTC) + timedelta(seconds=5)))

    assert await auth.store.acquire_refresh_lock(sid, 10) is True


@pytest.mark.asyncio
async def test_no_expiry_means_no_refresh():
    """A source that never reports `expires_at` has nothing to trigger on."""
    source = CountingSource()
    auth = make_auth(source=source, store=MemoryStore())
    session = Session(access="a")

    assert auth._expiring(session) is False
    assert await auth._refresh("sid", session) is session
    assert source.refreshes == 0


@pytest.mark.asyncio
async def test_a_source_that_cannot_refresh_keeps_the_session_it_has():
    class NoRefresh:
        async def exchange(self, credentials) -> Session:
            return Session(claims=dict(credentials))

    auth = make_auth(source=NoRefresh(), store=MemoryStore())
    stale = Session(access="a", expires_at=datetime.now(UTC) + timedelta(seconds=5))

    with warnings.catch_warnings():
        # The warning has its own test below.
        warnings.simplefilter("ignore", PluginWarning)
        assert await auth._refresh("sid", stale) is stale


# ------------------------------------------------------- the refresh contract


class FlakySource(CountingSource):
    """An upstream whose `refresh` raises whatever `error` holds, counting every
    attempt, so a test can turn an outage on and off between requests."""

    def __init__(self, error: Exception | None, *, delay: float = 0.0, ttl: timedelta = timedelta(seconds=5)) -> None:
        super().__init__(ttl=ttl, delay=delay)
        self.error = error
        self.attempts = 0

    async def refresh(self, session: Session) -> Session:
        self.attempts += 1
        if self.error is not None:
            if self.delay:
                await asyncio.sleep(self.delay)
            raise self.error
        return await super().refresh(session)


def test_an_upstream_refusal_ends_the_session():
    source = FlakySource(RefreshRefused("the refresh token was revoked"))
    client = make_app(make_auth(source=source))
    client.post("/login", headers={"origin": ORIGIN})

    response = client.get("/who", headers=BROWSER, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/who"
    source.error = None
    assert client.get("/who").text == "anonymous", "a refused session must not come back when the upstream does"


@pytest.mark.parametrize("error", [ConnectionError("no route to host"), TimeoutError("read timed out")])
def test_an_unreachable_upstream_keeps_the_session_and_says_when_to_retry(error):
    """An outage is not a refusal. The user stays signed in, this one request
    is answered 503 with a `Retry-After`, and the next request after the
    upstream is back renews the token as if nothing had happened."""
    source = FlakySource(error)
    client = make_app(make_auth(source=source))
    client.post("/login", headers={"origin": ORIGIN})

    during = client.get("/who", headers=BROWSER, follow_redirects=False)
    source.error = None
    after = client.get("/who")

    assert during.status_code == 503
    assert during.headers["retry-after"].isdigit()
    assert after.text == "ada"
    assert source.refreshes == 1


def test_a_static_asset_never_waits_on_the_upstream():
    """The stylesheet and htmx are served whatever the identity provider is
    doing: a 503 on `/_fjkit/*` would leave a page that did load unstyled."""
    source = FlakySource(ConnectionError("no route to host"))
    client = make_app(make_auth(source=source))
    client.post("/login", headers={"origin": ORIGIN})

    response = client.get("/_fjkit/vendor/htmx/htmx.min.js")

    assert response.status_code == 200
    assert source.attempts == 0


def race_two_requests(source: FlakySource) -> tuple[int, int, float]:
    """Log in, then send two `GET /who` so the second arrives while the first
    holds the refresh lock. Returns the winner's status, the loser's status and
    how long the loser waited."""
    with make_app(make_auth(source=source, refresh_wait=timedelta(seconds=2))) as client:
        client.post("/login", headers={"origin": ORIGIN})

        def timed_get() -> tuple[int, float]:
            started = time.monotonic()
            return client.get("/who", follow_redirects=False).status_code, time.monotonic() - started

        with ThreadPoolExecutor(max_workers=2) as pool:
            winner = pool.submit(timed_get)
            time.sleep(0.1)
            loser = pool.submit(timed_get)
            (winner_status, _), (loser_status, loser_elapsed) = winner.result(), loser.result()
    return winner_status, loser_status, loser_elapsed


def test_a_request_that_lost_the_refresh_race_learns_the_winner_failed_promptly():
    """Two swaps notice the expiring token at once. The first holds the lock
    and finds the upstream unreachable; the second must get the same 503 as
    soon as the first lets go, not wait out `refresh_wait` and then send the
    user to the login page for a session that still exists."""
    source = FlakySource(ConnectionError("no route to host"), delay=0.3)

    winner_status, loser_status, loser_elapsed = race_two_requests(source)

    assert winner_status == 503
    assert loser_status == 503
    assert loser_elapsed < 1.0, "the loser must learn the outcome, not wait out refresh_wait"
    assert source.attempts == 1, "the loser reports the winner's outcome rather than trying the upstream again"


# ------------------------------------------ an outage while the token is good


@pytest.mark.xfail(strict=True, reason="the fix lands in the next commit")
def test_an_outage_inside_the_leeway_serves_the_token_that_is_still_good(caplog):
    """The refresh runs `refresh_leeway` ahead of expiry, while the token is
    still valid. An upstream that cannot be reached in that window costs the
    user nothing: the request is served on the token they have, the attempt is
    logged, and the next request tries again."""
    source = FlakySource(ConnectionError("no route to host"))
    client = make_app(make_auth(source=source))
    client.post("/login", headers={"origin": ORIGIN})

    with caplog.at_level(logging.WARNING, logger="fjkit.auth"):
        first = client.get("/who", follow_redirects=False)
        second = client.get("/who", follow_redirects=False)
    attempts_during = source.attempts
    source.error = None
    after = client.get("/who")

    assert (first.status_code, first.text) == (200, "ada")
    assert (second.status_code, second.text) == (200, "ada")
    assert attempts_during == 2, "every request inside the leeway tries again"
    assert len(caplog.records) == 2, "one warning per attempt, so an operator sees the outage"
    assert after.text == "ada"
    assert source.refreshes == 1


@pytest.mark.parametrize("path", ["/who", "/private/thing"])
def test_an_outage_past_expiry_answers_503_wherever_the_session_is_needed(path):
    """Once the token has expired there is nothing to serve the request on. A
    page that reads the session and a route behind `required` both wait for
    the upstream; the session itself is kept for when it returns."""
    source = FlakySource(ConnectionError("no route to host"), ttl=timedelta(seconds=-1))
    client = make_app(make_auth(source=source))
    client.post("/login", headers={"origin": ORIGIN})

    during = client.get(path, headers=BROWSER, follow_redirects=False)
    source.error = None
    after = client.get("/who")

    assert during.status_code == 503
    assert during.headers["retry-after"].isdigit()
    assert after.text == "ada", "the session survives the outage"
    assert source.refreshes == 1


@pytest.mark.xfail(strict=True, reason="the fix lands in the next commit")
def test_logging_out_needs_no_upstream():
    """Logout deletes a row and clears a cookie, neither of which needs the
    identity provider. A user whose token expired during an outage must still
    be able to leave, and the session must be gone on both sides."""
    source = FlakySource(ConnectionError("no route to host"), ttl=timedelta(seconds=-1))
    auth = make_auth(source=source)
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN})
    cookie = client.cookies[auth.cookie.name]

    response = client.post("/logout", headers={"origin": ORIGIN})

    assert response.status_code == 204
    assert auth.cookie.name not in client.cookies, "the browser's cookie is cleared"
    source.error = None
    client.cookies.set(auth.cookie.name, cookie)
    assert client.get("/who").text == "anonymous", "the store's row is gone, so the old cookie is worthless"


@pytest.mark.xfail(strict=True, reason="the fix lands in the next commit")
def test_a_request_that_lost_the_refresh_race_is_served_when_its_token_is_still_good():
    """The loser's version of the leeway rule: the winner found the upstream
    unreachable, the token is still valid, so the loser proceeds on it as soon
    as the winner lets go."""
    source = FlakySource(ConnectionError("no route to host"), delay=0.3)

    winner_status, loser_status, loser_elapsed = race_two_requests(source)

    assert winner_status == 200
    assert loser_status == 200
    assert loser_elapsed < 1.0, "the loser must learn the outcome, not wait out refresh_wait"
    assert source.attempts == 1


# ----------------------------------------------------------------- wiring


def test_memory_store_under_a_production_config_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        make_app(make_auth(store=MemoryStore()), auto_reload=False)

    assert any(
        issubclass(w.category, PluginWarning) and "MemoryStore under a production config" in str(w.message)
        for w in caught
    )


@pytest.mark.asyncio
async def test_an_expiring_token_with_no_way_to_renew_warns_once():
    """Warned when it becomes true, not at startup.

    A source with neither `refresh()` nor `expires_at` is an ordinary
    configuration — `LocalSource` is exactly that — so warning about the
    combination at startup would fire on apps that have no problem, and teach
    people to ignore the warning that does matter.
    """

    class NoRefresh:
        async def exchange(self, credentials) -> Session:
            return Session()

    auth = make_auth(source=NoRefresh(), store=MemoryStore())
    healthy = Session(access="a")
    stale = Session(access="a", expires_at=datetime.now(UTC) + timedelta(seconds=5))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await auth._refresh("sid", healthy)  # nothing to renew, nothing to say
        assert caught == []

        await auth._refresh("sid", stale)
        await auth._refresh("sid", stale)

    assert len(caught) == 1, "once per plugin, not once per request"
    assert "has no `refresh()`" in str(caught[0].message)


@pytest.mark.asyncio
async def test_memory_store_forgets_sessions_nobody_reads_again():
    """A login whose user never returns (a closed browser, a script) leaves a
    row that only its own `get` would remove. Nothing reads it, so the process
    grows with every login unless the store sweeps on its own. The rows are
    the store's memory, which is what the assertion looks at."""
    store = MemoryStore()
    for i in range(100):
        await store.put(f"gone-{i}", b"x", 0)
    await store.put("live", b"x", 3600)

    assert await store.get("live") == b"x"
    assert set(store._items) == {"live"}


def test_trusted_origins_are_required_unless_csrf_is_chosen():
    with pytest.raises(ValueError, match="needs `trusted_origins"):
        AuthPlugin(secret="s")


def test_csrf_and_trusted_origins_together_are_refused():
    with pytest.raises(ValueError, match="not both"):
        AuthPlugin(secret="s", csrf=NoCsrf(), trusted_origins=[ORIGIN])


def test_a_session_round_trips_through_the_store_encoding():
    when = datetime.now(UTC) + timedelta(hours=1)
    session = Session(claims={"user_id": 7}, access="a", refresh="r", expires_at=when)

    assert decode(encode(session)) == session
