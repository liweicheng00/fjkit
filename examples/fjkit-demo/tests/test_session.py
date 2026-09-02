"""Tests for the session routes: sign-in, sign-out, CSRF and the protected route."""

from __future__ import annotations

from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME
from app.main import TRUSTED_ORIGINS

ORIGIN = {"origin": TRUSTED_ORIGINS[0]}
GOOD = {"username": DEMO_USERNAME, "password": DEMO_PASSWORD}

#: The `Accept` header a browser sends on a navigation.
BROWSER = {"accept": "text/html,application/xhtml+xml"}


def test_the_page_starts_signed_out(client):
    body = client.get("/session").text

    assert 'name="password"' in body
    assert "Sign out" not in body


def test_signing_in_is_a_swap_that_also_sets_the_cookie(htmx):
    """POST /session answers a fragment and sets an HttpOnly cookie."""
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
    """Bad credentials answer 200 with the error panel and no cookie."""
    response = htmx.post("/session", data={"username": DEMO_USERNAME, "password": "wrong"})

    assert response.status_code == 200
    assert "not the demo account" in response.text
    assert "set-cookie" not in response.headers


def test_the_password_field_carries_a_reveal_and_the_page_loads_its_script(client):
    """`revealable=true` writes the button; the page opts into the script."""
    body = client.get("/session").text

    assert "data-fjkit-reveal" in body
    assert 'aria-controls="f-password"' in body
    assert 'aria-pressed="false"' in body
    assert "js/reveal.js" in body


def test_the_reveal_survives_a_rejected_sign_in(htmx):
    """The panel a rejected sign-in swaps in carries its own button. The
    listener is on `document`, so this one works too — which is the whole
    reason `js/reveal.js` is not bound per button."""
    panel = htmx.post("/session", data={"username": DEMO_USERNAME, "password": "wrong"}).text

    assert "data-fjkit-reveal" in panel
    assert 'aria-controls="f-password"' in panel
    assert "js/reveal.js" not in panel, "the script is on the page, not in the fragment"


def test_signing_out_clears_the_session(htmx):
    """DELETE /session over htmx answers the sign-in panel and clears the session."""
    htmx.post("/session", data=GOOD, headers=ORIGIN)

    response = htmx.request("DELETE", "/session", headers=ORIGIN)

    assert "Sign in" in response.text
    assert "Sign out" not in htmx.get("/session").text


def test_signing_out_from_another_origin_is_refused(client):
    """Sign-out with an untrusted Origin header returns 403 and keeps the session."""
    client.post("/session", data=GOOD, headers=ORIGIN)

    response = client.request("DELETE", "/session", headers={"origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert "Sign out" in client.get("/session").text, "and the session survives the attempt"


def test_a_write_with_no_origin_at_all_is_refused(client):
    """Sign-out without an Origin header returns 403."""
    client.post("/session", data=GOOD, headers=ORIGIN)

    assert client.request("DELETE", "/session").status_code == 403


def test_the_protected_route_answers_a_session(htmx):
    htmx.post("/session", data=GOOD, headers=ORIGIN)

    response = htmx.get("/session/secret")

    assert response.status_code == 200
    assert DEMO_USERNAME in response.text


def test_the_protected_route_sends_an_anonymous_swap_to_the_login_page(htmx):
    """An anonymous htmx request to the protected route gets 401 with `HX-Redirect`."""
    response = htmx.get("/session/secret", follow_redirects=False)

    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/session?next=/session/secret"


def test_the_protected_route_redirects_an_anonymous_navigation(client):
    """An anonymous browser navigation to the protected route gets a 303 to the login page."""
    response = client.get("/session/secret", headers=BROWSER, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/session?next=/session/secret"


def test_the_protected_route_answers_401_to_a_script(client):
    """An anonymous non-browser request to the protected route gets a JSON 401."""
    response = client.get("/session/secret", follow_redirects=False)

    assert response.status_code == 401
    assert response.json()["login_url"] == "/session"


def test_being_bounced_leaves_a_toast_on_the_login_page(client):
    """The redirect sets a `fjkit_flash` cookie and the login page renders it as a toast."""
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
    """The overview, board and jobs pages answer 200 without a session."""
    for path in ("/", "/tasks", "/jobs"):
        assert client.get(path).status_code == 200


def test_a_public_write_still_needs_no_origin(client):
    """POST /tasks without a session cookie needs no Origin header."""
    response = client.post("/tasks", json={"title": "no session here"})

    assert response.status_code == 200
