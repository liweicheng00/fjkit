from __future__ import annotations

import pytest

#: A page and the markup that proves it is *that* page rather than a shell with
#: an empty body. Paired with the path so adding a page cannot quietly pass by
#: matching another page's marker.
PAGES = [("/", "Overview"), ("/tasks", 'id="board"'), ("/jobs", 'id="job-list"')]


@pytest.mark.parametrize(("path", "marker"), PAGES, ids=[p for p, _ in PAGES])
def test_full_pages_render_the_shell(client, path, marker):
    response = client.get(path)
    assert response.status_code == 200
    assert response.text.startswith("<!doctype html>")
    assert marker in response.text


def test_dashboard_rows_are_read_only(client):
    html = client.get("/").text
    assert "Advance" not in html
    assert "hx-post" not in html
    assert "hx-delete" not in html


def test_every_page_reports_server_timing(client):
    assert client.get("/tasks").headers["Server-Timing"].startswith("app;dur=")


def test_streamed_report_is_streamed_and_complete(client):
    with client.stream("GET", "/tasks/report?rows=500") as response:
        assert response.status_code == 200
        # A streamed response cannot know its length up front. TestClient
        # reassembles the chunks before we see them, so the missing header is
        # the observable proof that nothing was buffered server-side.
        assert "content-length" not in response.headers
        html = response.read().decode()
    assert html.rstrip().endswith("</html>")
    assert html.count("<tr>") == 500 + 1  # rows + the thead row


def test_normal_pages_are_not_streamed(client):
    assert "content-length" in client.get("/tasks").headers


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
