"""Tests for the board partial, its htmx endpoints and double-submit guards."""

from __future__ import annotations

import re


def test_board_partial_has_no_shell(htmx):
    response = htmx.get("/tasks/board")
    assert response.status_code == 200
    assert "<!doctype html>" not in response.text.lower()
    assert response.text.lstrip().startswith('<div id="board"')


def test_full_page_embeds_the_same_partial(client, htmx):
    page = client.get("/tasks").text
    partial = htmx.get("/tasks/board").text
    assert page.count('id="board"') == 1
    assert partial.count('id="board"') == 1


def test_filtering_narrows_the_board(htmx):
    everything = htmx.get("/tasks/board")
    todo_only = htmx.get("/tasks/board?status=todo")
    assert todo_only.text.count("<tr>") < everything.text.count("<tr>")
    assert "Advance" in todo_only.text


def test_create_returns_the_updated_board(htmx):
    response = htmx.post("/tasks", json={"title": "A brand new task", "priority": "high", "owner": "livy"})
    assert response.status_code == 200
    assert "A brand new task" in response.text
    assert response.text.lstrip().startswith('<div id="board"')


def test_advance_cycles_status(htmx):
    before = htmx.get("/tasks/board").text
    htmx.post("/tasks/5/advance")
    after = htmx.get("/tasks/board").text
    assert before != after


def test_delete_removes_the_row(htmx):
    assert htmx.delete("/tasks/1").status_code == 200
    assert htmx.delete("/tasks/1").status_code == 404


def test_empty_state_when_nothing_matches(htmx):
    for task_id in range(1, 20):
        htmx.delete(f"/tasks/{task_id}")
    assert "Nothing here" in htmx.get("/tasks/board").text


# Double-submit

FORM = re.compile(r"<form\b[^>]*>.*?</form>", re.S)


def test_every_mutating_control_disables_itself(htmx):
    """Without `hx-disabled-elt` a second click during the request sends the mutation twice."""
    board = htmx.get("/tasks/board").text
    mutating = re.findall(r"<(?:form|button)\b[^>]*hx-(?:post|delete)=[^>]*>", board)
    assert mutating, "the board is where the mutations are"
    for control in mutating:
        assert "hx-disabled-elt=" in control, f"can be double-clicked: {control[:120]}"


def test_a_form_s_disabled_selector_finds_something(client):
    """A selector that matches nothing disables nothing, so the guard is absent and no test says so."""
    for page in ("/tasks", "/jobs", "/session"):
        for form in FORM.findall(client.get(page).text):
            if "hx-disabled-elt=" not in form:
                continue
            assert 'find button[type=submit]' in form, "the only form selector this app uses"
            assert 'type="submit"' in form, f"nothing for the selector to disable on {page}"
