"""Tests for the task edit form and PUT /tasks/{id}."""

from __future__ import annotations

import re


def test_the_form_is_an_htmx_put_carrying_json(client):
    html = client.get("/tasks/1/edit").text
    assert 'hx-put="/tasks/1"' in html
    assert 'hx-target="#edit-form"' in html
    assert 'hx-ext="json-enc"' in html
    assert "method=" not in html


def test_the_page_loads_both_scripts_the_form_depends_on(client):
    html = client.get("/tasks/1/edit").text
    assert "vendor/htmx/json-enc.js" in html
    assert "js/multiselect.js" in html


def test_every_editable_field_is_on_the_page(client):
    html = client.get("/tasks/1/edit").text
    posted = set(re.findall(r'<(?:input|textarea|select)[^>]*name="([^"]+)"', html))
    assert posted == {"title", "priority", "owner", "notes", "blocked", "watching", "labels"}


def test_the_form_is_filled_from_the_task(client):
    html = client.get("/tasks/4/edit").text
    assert "bytecode cache warmed" in html
    assert re.search(r'name="blocked"[^>]* checked', html)
    assert re.search(r'value="normal"[^>]* checked', html)


def test_the_page_embeds_the_partial_the_route_returns(client, htmx):
    """The page embeds the partial its htmx endpoint returns, so one markup serves both paths."""
    page = client.get("/tasks/1/edit").text
    fragment = htmx.get("/tasks/1/edit").text
    assert not fragment.lstrip().startswith("<!doctype")
    assert fragment.strip() in page


def test_the_form_page_caps_its_own_measure(client, htmx):
    """A page that is one form gets a width cap, and the cap belongs to the page:
    the partial is swapped inside it and must not carry a second one."""
    page = client.get("/tasks/1/edit").text
    fragment = htmx.get("/tasks/1/edit").text

    assert "max-w-xl" in page
    assert "mx-auto" in page
    assert "max-w-xl" not in fragment


def test_saving_answers_hx_redirect_rather_than_a_303(htmx):
    response = htmx.put("/tasks/1", json={"title": "Renamed", "priority": "high", "owner": "mei"})

    assert response.status_code == 204
    assert response.headers["HX-Redirect"].endswith("/tasks")

    html = htmx.get("/tasks/1/edit").text
    assert 'value="Renamed"' in html
    assert re.search(r'value="high"[^>]* checked', html)


def test_an_absent_field_reads_as_false(htmx):
    """An unchecked box sends nothing, so an absent flag means false rather than unchanged."""
    htmx.put("/tasks/4", json={"title": "Still here", "priority": "normal", "owner": "kai"})

    html = htmx.get("/tasks/4/edit").text
    assert not re.search(r'name="blocked"[^>]* checked', html)
    assert not re.search(r'name="watching"[^>]* checked', html)


def test_editing_does_not_touch_status(client, htmx):
    before = client.get("/tasks").text
    htmx.put("/tasks/3", json={"title": "Move component includes to macros", "priority": "low", "owner": "mei"})
    after = client.get("/tasks").text
    assert before.count("Doing") == after.count("Doing")


def test_a_missing_task_is_a_404_on_both_verbs(client, htmx):
    assert client.get("/tasks/999/edit").status_code == 404
    assert htmx.put("/tasks/999", json={"title": "x"}).status_code == 404


def test_the_board_links_to_the_edit_page(client):
    html = client.get("/tasks").text
    assert 'href="/tasks/1/edit"' in html


# The multi-select


def test_the_selection_is_rendered_for_the_script_to_rewrite(client):
    """The labels input for task 4 carries its two labels as a JSON array."""
    html = client.get("/tasks/4/edit").text
    assert "name=\"labels\" data-fjkit-multi value='[\"infra\", \"perf\"]'" in html


def test_a_json_array_is_read_as_a_list(htmx):
    htmx.put("/tasks/1", json={"title": "Tagged", "priority": "high", "owner": "livy", "labels": ["bug", "ui"]})

    assert "value='[\"bug\", \"ui\"]'" in htmx.get("/tasks/1/edit").text


def test_one_label_arrives_as_a_bare_string_and_is_still_a_list(htmx):
    """A bare string in labels is accepted and stored as a one-item list."""
    reply = htmx.put("/tasks/1", json={"title": "One", "priority": "high", "owner": "livy", "labels": "bug"})

    assert reply.status_code == 204
    assert "value='[\"bug\"]'" in htmx.get("/tasks/1/edit").text


def test_an_absent_selection_clears_the_labels(htmx):
    htmx.put("/tasks/1", json={"title": "Untagged", "priority": "high", "owner": "livy"})

    assert "value='[]'" in htmx.get("/tasks/1/edit").text


def test_a_value_the_form_never_offered_is_rejected(htmx):
    """A label outside the Label enum returns 422."""
    reply = htmx.put("/tasks/1", json={"title": "x", "priority": "high", "labels": ["not-a-label"]})
    assert reply.status_code == 422


def test_the_board_shows_what_was_picked(client, htmx):
    htmx.put("/tasks/1", json={"title": "Tagged", "priority": "high", "owner": "livy", "labels": ["bug", "ui"]})

    html = client.get("/tasks").text
    assert ">bug<" in html and ">ui<" in html
