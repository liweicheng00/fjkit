"""The auth plugin: the cookie, the CSRF check, and the refresh race."""

from __future__ import annotations

import asyncio
import warnings
from datetime import UTC, datetime, timedelta

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
    Session,
)
from fjkit.auth.plugin import safe_next
from fjkit.auth.types import decode, encode
from jinja2 import DictLoader

ORIGIN = "http://testserver"

#: What a browser navigating to a page sends. `TestClient` sends `Accept: */*`,
#: which is the programmatic caller — so a test about browser behaviour has to
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


def test_logout_clears_both_sides():
    auth = make_auth(store=MemoryStore())
    client = make_app(auth)
    client.post("/login", headers={"origin": ORIGIN})
    sid = client.cookies[auth.cookie.name].partition(".")[0]

    client.post("/logout", headers={"origin": ORIGIN})

    assert client.get("/who").text == "anonymous"
    assert asyncio.run(auth.store.get(sid)) is None


def test_logging_in_again_replaces_the_session_id():
    """A session id that survives a login is a fixation hole."""
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
    """A browser gets sent to the login form. A 401 here is a blank page."""
    client = make_app(make_auth())

    response = client.get("/private/thing", headers=BROWSER, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/private/thing"
    assert response.headers["vary"] == "HX-Request, Accept, Sec-Fetch-Mode"


def test_the_next_parameter_keeps_the_query_string():
    """Come back from the login form to the view you were looking at, filter
    and all. `request.url.path` alone drops it, and the user lands on an
    unfiltered list wondering where their search went."""
    client = make_app(make_auth())

    response = client.get("/private/thing?status=doing&page=2", headers=BROWSER, follow_redirects=False)

    assert response.headers["location"] == "/login?next=/private/thing%3Fstatus%3Ddoing%26page%3D2"


def test_a_navigation_is_recognised_by_sec_fetch_mode_too():
    """The purpose-built signal, for the callers that send it."""
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
        ("https://evil.example.com", "/"),
        ("evil.example.com", "/"),
        ("", "/"),
        (None, "/"),
    ],
)
def test_safe_next_only_returns_to_this_site(value, expected):
    """A login page that redirects to whatever it is handed is an open
    redirect — your domain, your login form, and a hop to the attacker's site
    at the moment someone has just typed their password.

    `//evil.example.com` is the case a naive `startswith("/")` waves through:
    a browser reads it as a protocol-relative URL, so it is a different site.
    """
    assert safe_next(value) == expected


def test_a_caller_with_no_markup_waiting_gets_401():
    """The one caller 401 is right for.

    Under `render_mode="auto"` this is the request a route answers in JSON, so
    refusing it with a redirect to an HTML login form would be answering a
    question it did not ask.
    """
    client = make_app(make_auth())

    response = client.get("/private/thing", follow_redirects=False)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication required"
    assert response.json()["login_url"] == "/login"


def test_the_401_carries_no_www_authenticate():
    """RFC 9110 asks for the field; every registered scheme is wrong here.

    `Basic` would make the browser open its own credential dialog — precisely
    the login form this plugin exists to replace.
    """
    client = make_app(make_auth())

    assert "www-authenticate" not in client.get("/private/thing").headers


def test_an_htmx_swap_without_a_session_gets_hx_redirect():
    """401 *and* a redirect, which is not a contradiction.

    htmx acts on `HX-Redirect` before it looks at the status code, so the
    status can be honest while the browser still moves the whole page. A 303
    would be followed and the login page swapped into a card; a bare 401 would
    swap nothing at all, because htmx ignores a 4xx body.
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


def test_a_public_write_without_a_session_is_not_checked():
    """Nothing ambient is attached, so there is nothing to forge."""
    client = make_app(make_auth())

    assert client.post("/public").json() == {"ok": "yes"}


def test_reads_are_never_checked():
    client = make_app(make_auth())
    client.post("/login", headers={"origin": ORIGIN})

    assert client.get("/who").text == "ada"


def test_no_csrf_lets_everything_through_and_says_so():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        client = make_app(AuthPlugin(secret="s", csrf=NoCsrf(), cookie=CookieSpec(secure=False)))

    client.post("/login")
    assert client.post("/logout").status_code == 204
    assert any("CSRF checking is off" in str(w.message) for w in caught)


# ------------------------------------------------------------------- refresh


class CountingSource:
    """An upstream whose token expires, and that counts how often it renews."""

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

    Four htmx swaps fire at once, all see an expiring token. Without the lock
    all four call refresh, and an upstream that rotates refresh tokens revokes
    the family when the second arrives — logging the user out mid-click.
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

    A refresh finishes and releases the lock. A request that read the store
    just before that write now finds the lock free — and would renew again,
    using a refresh token the upstream has already retired.
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
async def test_a_failed_refresh_ends_the_session():
    class Broken(CountingSource):
        async def refresh(self, session: Session) -> Session:
            raise RuntimeError("upstream said no")

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

    with pytest.raises(RefreshFailed):
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
        # The warning itself is the subject of its own test, below.
        warnings.simplefilter("ignore", PluginWarning)
        assert await auth._refresh("sid", stale) is stale


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
    people to ignore the warning that matters.
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
