"""Tests for the shape of the board's 422 replies."""

from __future__ import annotations

import json

#: The `Accept` header a browser sends on a form submit.
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def _messages(reply) -> list[str]:
    """Return the toast titles carried in the reply's `HX-Trigger` header."""
    header = reply.headers.get("HX-Trigger")
    if not header:
        return []
    return [m["title"] for m in json.loads(header)["fjkit:toast"]["messages"]]


def _fields(reply) -> dict[str, str]:
    """Return `{field path under body: msg}` from the reply's `detail` list."""
    return {".".join(map(str, d["loc"][1:])): d["msg"] for d in reply.json()["detail"] if d["loc"][0] == "body"}


# the create form


def test_a_rejected_create_is_fastapis_list_and_nothing_else(htmx):
    """A rejected create is a JSON 422 with no `HX-Retarget` and no `HX-Trigger`."""
    reply = htmx.post("/tasks", json={"title": "", "priority": "high", "owner": "kai"})

    assert reply.status_code == 422
    assert reply.headers["content-type"].startswith("application/json")
    assert "HX-Retarget" not in reply.headers
    assert "HX-Trigger" not in reply.headers


def test_the_message_names_the_field_the_form_posted(htmx):
    """The error's `loc` under `body` is the posted field name."""
    reply = htmx.post("/tasks", json={"title": "", "priority": "high"})

    assert _fields(reply) == {"title": "String should have at least 1 character"}


def test_a_rejected_submit_does_not_clear_the_form(htmx):
    """The create form's after-request handler resets only on success."""
    html = htmx.get("/tasks/board").text

    assert "if (event.detail.successful) this.reset()" in html


def test_nothing_was_created(client, htmx):
    before = len(client.get("/tasks/board").json()["tasks"])

    htmx.post("/tasks", json={"title": "", "priority": "high"})

    assert len(client.get("/tasks/board").json()["tasks"]) == before


def test_a_limit_declared_on_the_model_is_a_field_error_too(htmx):
    """A title over 120 characters is a field error under `body`."""
    reply = htmx.post("/tasks", json={"title": "x" * 200, "priority": "high"})

    assert reply.status_code == 422
    assert _fields(reply) == {"title": "String should have at most 120 characters"}


def test_a_navigation_gets_a_page(client):
    """A rejected submit with a browser `Accept` header gets an HTML error page."""
    reply = client.post("/tasks", json={"title": ""}, headers=BROWSER)

    assert reply.status_code == 422
    assert reply.text.lstrip().lower().startswith("<!doctype html>")
    assert "String should have at least 1 character" in reply.text
    # The kit's error page is a standalone page, so it caps its own width
    # rather than running to the shell's full measure.
    assert "max-w-lg" in reply.text


# the edit form


def test_a_rejected_save_is_the_same_list(htmx):
    """A rejected edit is a JSON 422 whose `loc` is under `body`."""
    reply = htmx.put("/tasks/1", json={"priority": "normal", "owner": "kai", "notes": "waiting on legal"})

    assert reply.status_code == 422
    assert reply.headers["content-type"].startswith("application/json")
    assert _fields(reply) == {"title": "Field required"}


def test_a_value_the_form_never_offered_names_the_item(htmx):
    """A bad list item is reported under its indexed path, `labels.0`."""
    reply = htmx.put("/tasks/1", json={"title": "x", "priority": "high", "labels": ["not-a-label"]})

    assert reply.status_code == 422
    assert list(_fields(reply)) == ["labels.0"]


def test_a_rejected_save_changes_nothing(client, htmx):
    before = client.get("/tasks/1/edit").text

    htmx.put("/tasks/1", json={"priority": "normal"})

    assert client.get("/tasks/1/edit").text == before


# non-browser callers


def test_a_json_client_still_gets_the_error_contract_it_always_had(client):
    """A client accepting JSON gets FastAPI's `detail` list."""
    reply = client.post("/tasks", json={"title": ""}, headers={"Accept": "application/json"})

    assert reply.status_code == 422
    assert reply.json()["detail"][0]["loc"] == ["body", "title"]


def test_the_successful_paths_are_untouched(client, htmx):
    """A valid create answers the board; a valid edit answers 204 with `HX-Redirect`."""
    created = htmx.post("/tasks", json={"title": "a real task", "priority": "high"})
    assert created.status_code == 200
    assert 'id="board"' in created.text
    assert "a real task" in created.text

    saved = htmx.put("/tasks/1", json={"title": "renamed", "priority": "low", "owner": "kai"})
    assert saved.status_code == 204
    assert saved.headers["HX-Redirect"].endswith("/tasks")


# errors outside the body


def test_a_failure_outside_the_body_is_not_a_field(htmx):
    """A bad path segment has a `loc` under `path` and yields no field errors."""
    reply = htmx.post("/tasks/not-a-number/advance")

    assert reply.status_code == 422
    assert reply.json()["detail"][0]["loc"][0] == "path"
    assert _fields(reply) == {}
