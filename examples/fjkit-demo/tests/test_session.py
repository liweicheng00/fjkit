"""The session feature, as the browser exercises it.

The kit's own suite covers the plugin's mechanics. This file covers the thing
that only shows up once it is wired into a real app: that signing in is an
ordinary htmx swap, that the cookie survives the trip, and that no route or
template outside this feature had to learn about any of it.
"""

from __future__ import annotations

from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME
from app.main import TRUSTED_ORIGINS

ORIGIN = {"origin": TRUSTED_ORIGINS[0]}
GOOD = {"username": DEMO_USERNAME, "password": DEMO_PASSWORD}

#: What a browser navigating to a page sends, which `TestClient` does not.
BROWSER = {"accept": "text/html,application/xhtml+xml"}


def test_the_page_starts_signed_out(client):
    body = client.get("/session").text

    assert 'name="password"' in body
    assert "Sign out" not in body


def test_signing_in_is_a_swap_that_also_sets_the_cookie(htmx):
    """The reply is a fragment. The cookie rides out on the same response."""
    response = htmx.post("/session", data=GOOD)

    assert response.status_code == 200
    assert "<html" not in response.text, "an htmx swap gets the partial, not the page"
    assert "Sign out" in response.text
    assert "HttpOnly" in response.headers["set-cookie"]


def test_the_session_survives_the_next_request(client):
    client.post("/session", data=GOOD, headers=ORIGIN)

    assert "Sign out" in client.get("/session").text


def test_the_cookie_carries_no_claims(client):
    client.post("/session", data=GOOD, headers=ORIGIN)

    assert DEMO_USERNAME not in client.cookies["fjkit_session"]


def test_bad_credentials_come_back_as_a_swappable_panel(htmx):
    """200, not 401: htmx leaves the DOM alone on a 4xx, and an error nobody
    can see is the same as no error at all."""
    response = htmx.post("/session", data={"username": DEMO_USERNAME, "password": "wrong"})

    assert response.status_code == 200
    assert "not the demo account" in response.text
    assert "set-cookie" not in response.headers


def test_signing_out_clears_the_session(htmx):
    """Asked through `htmx`, because `/session` answers a fragment — and under
    `render_mode="auto"` a fragment route without the header answers JSON."""
    htmx.post("/session", data=GOOD, headers=ORIGIN)

    response = htmx.request("DELETE", "/session", headers=ORIGIN)

    assert "Sign in" in response.text
    assert "Sign out" not in htmx.get("/session").text


def test_signing_out_from_another_origin_is_refused(client):
    """The CSRF check, on the one route in this demo that has a session to
    protect. Same request, same cookie, a different site asking."""
    client.post("/session", data=GOOD, headers=ORIGIN)

    response = client.request("DELETE", "/session", headers={"origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert "Sign out" in client.get("/session").text, "and the session survives the attempt"


def test_a_write_with_no_origin_at_all_is_refused(client):
    client.post("/session", data=GOOD, headers=ORIGIN)

    assert client.request("DELETE", "/session").status_code == 403


def test_the_protected_route_answers_a_session(htmx):
    htmx.post("/session", data=GOOD, headers=ORIGIN)

    response = htmx.get("/session/secret")

    assert response.status_code == 200
    assert DEMO_USERNAME in response.text


def test_the_protected_route_sends_an_anonymous_swap_to_the_login_page(htmx):
    """204 + HX-Redirect, not a 303.

    A 303 would be followed by htmx's own fetch and the login page swapped into
    the card that asked — a form inside a panel, on a URL that still claims to
    be somewhere else.
    """
    response = htmx.get("/session/secret", follow_redirects=False)

    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/session?next=/session/secret"


def test_the_protected_route_redirects_an_anonymous_navigation(client):
    """Same refusal, the shape a browser address bar understands."""
    response = client.get("/session/secret", headers=BROWSER, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/session?next=/session/secret"


def test_the_protected_route_answers_401_to_a_script(client):
    """No markup waiting, so no redirect to a login page it cannot render."""
    response = client.get("/session/secret", follow_redirects=False)

    assert response.status_code == 401
    assert response.json()["login_url"] == "/session"


def test_being_bounced_leaves_a_toast_on_the_login_page(client):
    """The message has to cross a full page load, which is why it is a cookie.

    `HX-Trigger` cannot do this: the document it would fire into is replaced by
    the redirect before the header arrives.
    """
    bounced = client.get("/session/secret", headers=BROWSER, follow_redirects=False)

    assert "fjkit_flash" in bounced.headers["set-cookie"]

    landed = client.get("/session").text
    assert 'class="toast"' in landed
    assert "Sign in to continue" in landed


def test_the_toast_is_shown_once_and_not_on_reload(client):
    client.get("/session/secret", headers=BROWSER, follow_redirects=False)
    client.get("/session")

    assert 'class="toast"' not in client.get("/session").text


def test_signing_out_closes_the_protected_route_again(htmx):
    htmx.post("/session", data=GOOD, headers=ORIGIN)
    htmx.request("DELETE", "/session", headers=ORIGIN)

    assert htmx.get("/session/secret", follow_redirects=False).status_code == 401


def test_the_rest_of_the_app_stays_open(client):
    """Nothing here is behind `auth.required`. Adding the plugin did not
    quietly put the demo behind a login."""
    for path in ("/", "/tasks", "/jobs"):
        assert client.get(path).status_code == 200


def test_a_public_write_still_needs_no_origin(client):
    """CSRF is only checked when the browser attached a session cookie, so the
    task board's own POSTs are untouched by any of this."""
    response = client.post("/tasks", data={"title": "no session here"})

    assert response.status_code == 200
