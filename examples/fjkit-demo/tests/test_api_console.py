"""The API console, in the app it is meant to be used in.

`packages/fjkit/tests/test_apidocs.py` proves the plugin's own behaviour against
a fixture API. This file is the acceptance test: the demo registers the plugin
and writes no route, no template and no static file, and the claim that follows
from that has to be true here or it is not true anywhere.

The claim is one endpoint. `/session/secret` is behind `Depends(require_session)`
and is unreachable from FastAPI's own Swagger page — the credential is an
HttpOnly cookie, and Swagger's console is JavaScript. From this one it answers,
because signing in ran the app's own `DemoSource` and the call was replayed
through the app carrying that session.
"""

from __future__ import annotations

import pytest
from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME
from app.main import TRUSTED_ORIGINS
from fastapi.testclient import TestClient

DOCS = "/api-docs"
ORIGIN = TRUSTED_ORIGINS[0]

SECRET_OP = f"{DOCS}/try/session_secret_session_secret_get"
BOARD_OP = f"{DOCS}/try/tasks_board_tasks_board_get"
TASKS_OP = f"{DOCS}/try/tasks_page_tasks_get"
CREATE_OP = f"{DOCS}/try/tasks_create_tasks_post"


@pytest.fixture
def console(client):
    """The console as a browser reaches it.

    `Origin` is not decoration. The demo names its trusted origins, and
    `AuthPlugin` checks every cookie-authenticated write against them — which
    includes the console's own POSTs, because they are ordinary requests to
    ordinary routes. A test that forgot to be a browser gets a 403, and so
    would a console that dropped the header on the way through.
    """
    return TestClient(
        client.app,
        base_url=ORIGIN,
        headers={"Origin": ORIGIN, "Referer": f"{ORIGIN}{DOCS}"},
    )


def sign_in(console) -> None:
    response = console.post(f"{DOCS}/auth", data={"username": DEMO_USERNAME, "password": DEMO_PASSWORD})
    assert "Signed in as" in response.text


def test_the_console_exists_without_the_app_writing_a_route(console):
    page = console.get(DOCS)

    assert page.status_code == 200
    assert "Board API" in page.text
    # Every router in this app, grouped by the tags the routes already carry.
    for tag in ("tasks", "jobs", "session", "dashboard"):
        assert tag in page.text


def test_the_sidebar_link_resolves_to_the_plugin_s_own_route(console):
    # `base.html` links by route name; nothing in the app knows the URL.
    assert f'href="{DOCS}"' in console.get("/").text


def test_signing_in_runs_the_app_s_own_token_source(console):
    refused = console.post(f"{DOCS}/auth", data={"username": DEMO_USERNAME, "password": "wrong"})
    assert "BadCredentials" in refused.text
    assert "Not signed in" in refused.text

    sign_in(console)
    # `describe=` in main.py decides what the panel says about the session.
    assert "DemoSource" in console.get(DOCS).text


def test_a_protected_route_answers_the_console_and_refuses_a_stranger(console):
    anonymous = console.post(SECRET_OP)
    # `AuthPlugin`'s answer to a caller that asked for neither HTML nor a swap:
    # a 401 with a reason, rather than a redirect to a login page.
    assert "401" in anonymous.text
    assert "authentication required" in anonymous.text

    sign_in(console)

    allowed = console.post(SECRET_OP)
    assert "200" in allowed.text
    assert DEMO_USERNAME in allowed.text


def test_a_fragment_endpoint_answers_the_console_with_its_model(console):
    """`render_mode="auto"` gives a fragment route's data to whoever is not
    htmx. The console asks for what the document promises, so a swap endpoint is
    already the app's JSON API without a second route existing."""
    result = console.post(BOARD_OP)

    assert "200" in result.text
    assert "application/json" in result.text


def test_even_a_page_route_answers_the_console_with_its_model(console):
    """`/tasks` is a page route — `@render("tasks/page.html", partial=…)` — so a
    navigation gets the whole page. The console is not a navigation, and showing
    it a full HTML document where the API has a model is answering a question
    nobody asked. `SCOPE_RENDER_MODE` is what tells `@render` which caller this
    is; `serves_a_page` alone cannot, because it describes the route."""
    result = console.post(TASKS_OP, data={"p.query.status": "todo"})

    assert "200" in result.text
    assert "/tasks?status=todo" in result.text
    assert "application/json" in result.text
    assert "&lt;!doctype" not in result.text.lower()


def test_the_same_route_still_gives_a_browser_the_page(console):
    """The regression guard for the line above. The console asks through the
    ASGI scope, which nothing outside the process can write — so this must not
    have become a way for any client to turn the app's pages into JSON."""
    page = console.get("/tasks?status=todo")

    assert page.headers["content-type"].startswith("text/html")
    assert page.text.lstrip().lower().startswith("<!doctype")


def test_a_form_endpoint_gets_fields_rather_than_a_text_box(console):
    """Every htmx form in this app posts `Form()` parameters, so this is the
    shape a fjkit API is mostly made of. A console that answered it with a
    textarea would be asking people to hand-write urlencoding."""
    page = console.get(f"{DOCS}/op/tasks_create_tasks_post")

    assert 'name="p.form.title"' in page.text
    assert 'name="p.form.priority"' in page.text
    assert 'name="body"' not in page.text


def test_a_write_from_the_console_reaches_the_service(console):
    sign_in(console)

    created = console.post(
        CREATE_OP,
        data={"p.form.title": "from the console", "p.form.owner": "ada", "p.form.priority": "normal"},
    )
    assert "403" not in created.text
    # Through the router, through the service, into the store the page reads.
    assert "from the console" in console.get("/tasks").text


def test_the_console_will_not_call_itself(console):
    """Nothing in the page offers it — the plugin's routes are out of the
    schema — so this is reachable only by hand. What it prevents is a handler
    re-entering itself until the stack runs out."""
    result = console.post(f"{DOCS}/try/does-not-exist")
    assert "No operation" in result.text
