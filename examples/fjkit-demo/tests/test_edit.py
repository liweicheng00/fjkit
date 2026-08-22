"""The edit page — the demo's one form that is not an htmx swap.

Everything else on this board posts through htmx and gets a fragment back, so
this route is what keeps the other half of `ui/form.html` honest: a `form()`
with no `target=` is an ordinary POST, the fields do not know the difference,
and the page works with JavaScript turned off. A test that only ever exercised
the htmx path would let that claim rot.
"""

from __future__ import annotations

import re


def test_the_form_posts_to_itself_without_any_htmx(client):
    html = client.get("/tasks/1/edit").text
    assert '<form class="card" action="/tasks/1/edit" method="post">' in html
    assert "hx-post" not in html
    assert "hx-target" not in html


def test_every_editable_field_is_on_the_page(client):
    html = client.get("/tasks/1/edit").text
    posted = set(re.findall(r'<(?:input|textarea|select)[^>]*name="([^"]+)"', html))
    assert posted == {"title", "priority", "owner", "notes", "blocked", "watching"}


def test_the_form_is_filled_from_the_task(client):
    """Task 4 is seeded blocked and with notes, so the round trip is visible."""
    html = client.get("/tasks/4/edit").text
    assert "bytecode cache warmed" in html  # the textarea's content
    assert re.search(r'name="blocked"[^>]* checked', html)
    assert re.search(r'value="normal"[^>]* checked', html)  # the radio group


def test_saving_redirects_to_the_board_and_sticks(client):
    response = client.post(
        "/tasks/1/edit",
        data={"title": "Renamed", "priority": "high", "owner": "mei", "notes": "n", "blocked": "on"},
        follow_redirects=False,
    )
    # 303, not 302: a refresh after a POST must not re-post the form.
    assert response.status_code == 303
    assert response.headers["location"].endswith("/tasks")

    html = client.get("/tasks/1/edit").text
    assert 'value="Renamed"' in html
    assert re.search(r'value="high"[^>]* checked', html)


def test_an_unticked_box_reads_as_false(client):
    """A checkbox that is off posts nothing at all. The route's default is the
    whole of reading one — no hidden companion field."""
    client.post(
        "/tasks/4/edit",
        data={"title": "Still here", "priority": "normal", "owner": "kai", "notes": ""},
        follow_redirects=False,
    )
    html = client.get("/tasks/4/edit").text
    assert not re.search(r'name="blocked"[^>]* checked', html)
    assert not re.search(r'name="watching"[^>]* checked', html)


def test_editing_does_not_touch_status(client):
    """`TaskUpdate` is the closed list of what an edit may change. Status moves
    through Advance, which is a different decision."""
    before = client.get("/tasks").text
    client.post(
        "/tasks/3/edit",
        data={"title": "Move component includes to macros", "priority": "low", "owner": "mei"},
        follow_redirects=False,
    )
    after = client.get("/tasks").text
    assert before.count("Doing") == after.count("Doing")


def test_a_missing_task_is_a_404_on_both_verbs(client):
    assert client.get("/tasks/999/edit").status_code == 404
    assert client.post("/tasks/999/edit", data={"title": "x"}, follow_redirects=False).status_code == 404


def test_the_board_links_to_the_edit_page(client):
    """The pencil is an <a>, so it adds no htmx wiring to the board."""
    html = client.get("/tasks").text
    assert 'href="/tasks/1/edit"' in html
