"""The routes: index, list, search, sort, page, filter, add, change, delete, actions, permissions."""

from __future__ import annotations

import json
import re

import pytest
from admin_fixture import HX, TITLES, Task, TaskAdmin, make_app
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


def rows_of(html: str) -> list[str]:
    """The first link text of every body row: the title cell, in page order."""
    body = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return re.findall(r'<a class="[^"]*" href="/admin/task/\d+">([^<]+)</a>', body)


def test_index_lists_every_model_with_a_count(client: TestClient):
    page = client.get("/admin")
    assert page.status_code == 200
    assert "12 tasks" in page.text
    assert "2 projects" in page.text
    assert 'href="/admin/task"' in page.text
    assert 'href="/admin/project/new"' in page.text


def test_list_is_a_page_for_a_browser_and_a_fragment_for_htmx(client: TestClient):
    page = client.get("/admin/task")
    assert page.status_code == 200
    assert "<html" in page.text
    assert 'id="admin-main"' in page.text
    assert page.headers["vary"] == "HX-Request"

    fragment = client.get("/admin/task", headers=HX)
    assert "<html" not in fragment.text
    assert fragment.text.lstrip().startswith('<div id="admin-main">')


def test_list_shows_the_first_page_in_the_declared_order(client: TestClient):
    html = client.get("/admin/task").text
    assert rows_of(html) == sorted(TITLES)[:5]
    assert "1–5 of 12" in html
    assert 'aria-sort="ascending"' in html
    # Every row links to its change form; the foreign key shows its label.
    assert 'href="/admin/task/1"' in html
    assert ">Core<" in html


def test_sort_reverses_from_the_header_link(client: TestClient):
    html = client.get("/admin/task").text
    match = re.search(r'href="(/admin/task\?[^"]*o=-title[^"]*)"', html)
    assert match, "the sorted column's header links to the reverse order"
    reversed_html = client.get(match.group(1).replace("&amp;", "&"), headers=HX).text
    assert rows_of(reversed_html) == sorted(TITLES, reverse=True)[:5]
    assert 'aria-sort="descending"' in reversed_html


def test_an_unknown_sort_key_falls_back_rather_than_failing(client: TestClient):
    html = client.get("/admin/task?o=nonsense").text
    assert rows_of(html) == sorted(TITLES)[:5]


def test_pagination_walks_the_rows_and_clamps(client: TestClient):
    second = client.get("/admin/task?page=2", headers=HX).text
    assert rows_of(second) == sorted(TITLES)[5:10]
    assert "6–10 of 12" in second

    clamped = client.get("/admin/task?page=99", headers=HX).text
    assert rows_of(clamped) == sorted(TITLES)[10:]

    sized = client.get("/admin/task?per_page=10", headers=HX).text
    assert len(rows_of(sized)) == 10
    assert "1–10 of 12" in sized


def test_search_matches_the_declared_columns_only(client: TestClient):
    by_title = client.get("/admin/task?q=alpha", headers=HX).text
    assert rows_of(by_title) == ["Alpha brief"]

    by_notes = client.get("/admin/task?q=urgent", headers=HX).text
    assert rows_of(by_notes) == sorted(TITLES[i] for i in range(12) if i % 3 == 0)[:5]

    nothing = client.get("/admin/task?q=zzz", headers=HX).text
    assert "No tasks" in nothing
    assert "Nothing matches this search." in nothing


def test_filters_narrow_by_enum_boolean_and_foreign_key(client: TestClient):
    done = client.get("/admin/task?f_done=1&per_page=10", headers=HX).text
    assert rows_of(done) == sorted(TITLES[i] for i in range(12) if i % 4 == 0)

    status = client.get("/admin/task?f_status=done&per_page=10", headers=HX).text
    assert rows_of(status) == sorted(TITLES[i] for i in range(12) if i % 3 == 2)

    project = client.get("/admin/task?f_project_id=2&per_page=10", headers=HX).text
    assert rows_of(project) == sorted(TITLES[i] for i in range(12) if i % 2 == 1)

    bad = client.get("/admin/task?f_status=bogus", headers=HX).text
    assert len(rows_of(bad)) == 5


def test_the_toolbar_carries_the_view_and_the_filter_selects(client: TestClient):
    html = client.get("/admin/task?q=a&f_status=todo").text
    assert 'name="q"' in html and 'value="a"' in html
    assert 'name="f_status"' in html
    assert '<option value="todo" selected>' in html
    assert '<option value="2">Docs</option>' in html
    assert 'name="o"' in html  # the order rides along as a hidden field


def test_add_form_renders_a_widget_per_column(client: TestClient):
    html = client.get("/admin/task/new").text
    assert 'name="title"' in html and "maxlength" in html
    assert "<textarea" in html and 'name="notes"' in html
    assert '<select class="select" id="f-status" name="status"' in html
    assert '<option value="todo" selected>' in html  # the column default
    assert 'name="project_id"' in html and ">Core</option>" in html
    assert 'type="date"' in html and 'name="due"' in html
    assert 'role="switch"' in html and 'name="done"' in html
    # No row yet, so the read-only column has nothing to show.
    assert 'name="created"' not in html
    assert 'hx-post="/admin/task"' in html and 'hx-ext="json-enc"' in html


def test_a_swap_carries_a_title_and_a_page_has_one(client: TestClient):
    page = client.get("/admin/task").text
    assert page.count("<title>") == 1
    fragment = client.get("/admin/task", headers=HX).text
    assert "<title>Tasks · Admin</title>" in fragment


def test_create_saves_and_answers_with_the_list(client: TestClient, db: sessionmaker):
    response = client.post(
        "/admin/task",
        json={"title": "Mike kickoff", "notes": "", "status": "doing", "due": "", "project_id": "2", "done": "on"},
        headers=HX,
    )
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"] == "/admin/task"
    trigger = json.loads(response.headers["HX-Trigger"])
    assert trigger["fjkit:toast"]["messages"][0]["title"] == "Task added"
    assert "13 tasks" in response.text

    with db() as session:
        task = session.scalar(select(Task).where(Task.title == "Mike kickoff"))
        assert task is not None
        assert task.notes is None and task.due is None
        assert task.done is True and task.project_id == 2
        assert task.status.value == "doing"
        assert task.created is not None  # the column default fired


def test_a_rejected_create_is_fastapis_own_422(client: TestClient):
    response = client.post("/admin/task", json={"title": "", "project_id": "x"}, headers=HX)
    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "title") in locs
    assert ("body", "project_id") in locs


def test_change_form_shows_the_row_and_update_saves_it(client: TestClient, db: sessionmaker):
    html = client.get("/admin/task/1").text
    assert 'value="Alpha brief"' in html
    assert "Change task" in html
    assert 'hx-delete="/admin/task/1"' in html
    # The read-only column is shown disabled, formatted, and not posted.
    assert 'name="created"' in html and 'value="2026-01-01 09:00"' in html and "disabled" in html

    response = client.post(
        "/admin/task/1", json={"title": "Alpha renamed", "status": "done", "project_id": "1"}, headers=HX
    )
    assert response.status_code == 200
    with db() as session:
        task = session.get(Task, 1)
        assert task.title == "Alpha renamed"
        assert task.status.value == "done"
        assert task.done is False  # an unticked switch is absent, and absent means no


def test_missing_rows_are_404(client: TestClient):
    assert client.get("/admin/task/999").status_code == 404
    assert client.get("/admin/task/abc").status_code == 404


def test_delete_removes_the_row_and_pushes_the_list_url(client: TestClient, db: sessionmaker):
    response = client.delete("/admin/task/1?o=-title&per_page=10", headers=HX)
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"].startswith("/admin/task?")
    assert "o=-title" in response.headers["HX-Push-Url"]
    assert "11 tasks" in response.text
    with db() as session:
        assert session.get(Task, 1) is None


def test_bulk_actions_run_over_the_ticked_rows(client: TestClient, db: sessionmaker):
    response = client.post(
        "/admin/task/action/mark_done",
        content="selected=2&selected=3",
        headers={**HX, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert "2 marked done" in response.headers["HX-Trigger"]
    with db() as session:
        assert session.get(Task, 2).done is True and session.get(Task, 3).done is True

    response = client.post(
        "/admin/task/action/delete_selected",
        content="selected=2",
        headers={**HX, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert "Deleted 1 task" in response.headers["HX-Trigger"]
    with db() as session:
        assert session.get(Task, 2) is None


def test_an_empty_selection_is_a_warning_not_an_error(client: TestClient):
    response = client.post(
        "/admin/task/action/mark_done", content="", headers={**HX, "Content-Type": "application/x-www-form-urlencoded"}
    )
    assert response.status_code == 200
    assert "Nothing was selected" in response.headers["HX-Trigger"]


def test_an_unknown_action_is_404(client: TestClient):
    assert client.post("/admin/task/action/explode", content="selected=1", headers=HX).status_code == 404


def test_permissions_gate_both_the_button_and_the_route():
    class ReadOnlyTasks(TaskAdmin):
        key = "task"

        def has_add_permission(self, request: Request) -> bool:
            return False

        def has_delete_permission(self, request: Request, obj=None) -> bool:
            return False

    app, _, _ = make_app(ReadOnlyTasks)
    client = TestClient(app)
    html = client.get("/admin/task").text
    assert "Add task" not in html
    assert "Delete selected" not in html
    assert "Mark done" in html
    assert client.get("/admin/task/new").status_code == 403
    assert client.post("/admin/task", json={"title": "x", "project_id": 1}).status_code == 403
    assert client.delete("/admin/task/1").status_code == 403
    assert 'hx-delete="/admin/task/1"' not in client.get("/admin/task/1").text


def test_dependencies_gate_every_route():
    from fastapi import Depends, HTTPException

    def deny() -> None:
        raise HTTPException(status_code=401)

    app, _, _ = make_app(dependencies=(Depends(deny),))
    client = TestClient(app)
    assert client.get("/admin").status_code == 401
    assert client.get("/admin/task").status_code == 401
    assert client.get("/admin/task/1").status_code == 401


def test_the_sidebar_lists_the_models_and_the_way_home():
    app, _, _ = make_app(home_url="/dashboard", home_label="Back", title="Ops")
    html = TestClient(app).get("/admin/project").text
    assert 'href="/dashboard"' in html and ">Back<" in html or "Back" in html
    assert "Ops" in html
    assert 'href="/admin/task"' in html and 'href="/admin/project"' in html


def test_an_async_sessionmaker_is_refused():
    from sqlalchemy.ext.asyncio import async_sessionmaker

    with pytest.raises(TypeError, match="synchronous sessionmaker"):
        AdminPluginForTest = __import__("fjkit_admin").AdminPlugin
        AdminPluginForTest(async_sessionmaker(), views=())


def test_duplicate_registrations_are_refused():
    from fjkit_admin import AdminPlugin

    class Again(TaskAdmin):
        pass

    with pytest.raises(ValueError, match="share key"):
        AdminPlugin(lambda: None, views=(TaskAdmin, Again))
