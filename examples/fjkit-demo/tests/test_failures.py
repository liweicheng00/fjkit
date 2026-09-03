"""Tests for the failures page and the 400 and 500 responses it triggers."""

from __future__ import annotations

import json

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _toasts(reply) -> list[dict]:
    header = reply.headers.get("HX-Trigger")
    return json.loads(header)["fjkit:toast"]["messages"] if header else []


@pytest.fixture
def quiet():
    """A client that returns a 500 response instead of re-raising the exception."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


def test_the_page_renders_with_both_buttons(client):
    page = client.get("/failures")
    assert page.status_code == 200
    assert 'hx-get="/failures/400"' in page.text
    assert 'hx-get="/failures/500"' in page.text
    assert page.text.count('id="outcome"') == 1


# 400


def test_a_refused_swap_is_empty_and_carries_the_toast(htmx):
    reply = htmx.get("/failures/400")
    assert reply.status_code == 400
    assert reply.text == ""
    [toast] = _toasts(reply)
    assert toast["category"] == "warning"
    assert toast["title"] == "That request was refused"


def test_a_refused_navigation_gets_the_same_status(client):
    reply = client.get("/failures/400", headers=BROWSER)
    assert reply.status_code == 400


# 500


def test_a_crashed_swap_is_empty_and_carries_the_toast(quiet):
    reply = quiet.get("/failures/500", headers={"HX-Request": "true"})
    assert reply.status_code == 500
    assert reply.text == "", "no body: htmx must have nothing it could swap in"
    [toast] = _toasts(reply)
    assert toast["category"] == "error"
    assert toast["title"] == "Something went wrong"
    assert toast["description"] == "RuntimeError: the failures page asked for this", (
        "main.exception_handler composes the text from the exception"
    )


def test_a_crashed_navigation_lands_on_the_error_page(quiet):
    reply = quiet.get("/failures/500", headers=BROWSER)
    assert reply.status_code == 500
    assert "text/html" in reply.headers["content-type"]
    assert "Something went wrong" in reply.text
    assert "Traceback" not in reply.text, "the traceback belongs in the log"


def test_a_crashed_json_call_gets_plain_text(quiet):
    reply = quiet.get("/failures/500", headers={"Accept": "application/json"})
    assert reply.status_code == 500
    assert "text/html" not in reply.headers["content-type"]
