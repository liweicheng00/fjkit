"""Tests for the API console pages and try-it calls."""

from __future__ import annotations

import json

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
LOGIN_OP = f"{DOCS}/op/session_login_session_post"


@pytest.fixture
def console(client):
    """A client that sends the trusted Origin and Referer headers."""
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
    assert "Fjkit Demo API" in page.text
    for tag in ("tasks", "jobs", "session", "dashboard"):
        assert tag in page.text


def test_the_sidebar_link_resolves_to_the_plugin_s_own_route(console):
    assert f'href="{DOCS}"' in console.get("/").text


def test_signing_in_runs_the_app_s_own_token_source(console):
    refused = console.post(f"{DOCS}/auth", data={"username": DEMO_USERNAME, "password": "wrong"})
    assert "BadCredentials" in refused.text
    assert "Not signed in" in refused.text

    sign_in(console)
    assert "DemoSource" in console.get(DOCS).text


def test_a_protected_route_answers_the_console_and_refuses_a_stranger(console):
    anonymous = console.post(SECRET_OP)
    assert "401" in anonymous.text
    assert "authentication required" in anonymous.text

    sign_in(console)

    allowed = console.post(SECRET_OP)
    assert "200" in allowed.text
    assert DEMO_USERNAME in allowed.text


def test_a_fragment_endpoint_answers_the_console_with_its_model(console):
    result = console.post(BOARD_OP)

    assert "200" in result.text
    assert "application/json" in result.text


def test_even_a_page_route_answers_the_console_with_its_model(console):
    result = console.post(TASKS_OP, data={"p.query.status": "todo"})

    assert "200" in result.text
    assert "/tasks?status=todo" in result.text
    assert "application/json" in result.text
    assert "&lt;!doctype" not in result.text.lower()


def test_the_same_route_still_gives_a_browser_the_page(console):
    page = console.get("/tasks?status=todo")

    assert page.headers["content-type"].startswith("text/html")
    assert page.text.lstrip().lower().startswith("<!doctype")


def test_a_form_endpoint_gets_fields_rather_than_a_text_box(console):
    """An operation with Form() parameters renders one input per field."""
    page = console.get(LOGIN_OP)

    assert 'name="p.form.username"' in page.text
    assert 'name="p.form.password"' in page.text
    assert 'name="body"' not in page.text


def test_a_json_body_gets_one_editable_example(console):
    """An operation with a JSON body renders a single body field."""
    page = console.get(f"{DOCS}/op/tasks_create_tasks_post")

    assert 'name="body"' in page.text
    assert 'name="p.form.title"' not in page.text


def test_a_write_from_the_console_reaches_the_service(console):
    sign_in(console)

    created = console.post(
        CREATE_OP,
        data={"body": json.dumps({"title": "from the console", "owner": "ada", "priority": "normal"})},
    )
    assert "403" not in created.text
    assert "from the console" in console.get("/tasks").text


def test_the_console_will_not_call_itself(console):
    """A try-it call for an unknown operation id reports "No operation"."""
    result = console.post(f"{DOCS}/try/does-not-exist")
    assert "No operation" in result.text
