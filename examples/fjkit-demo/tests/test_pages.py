from __future__ import annotations

import pytest

#: Each page path with a marker unique to that page's body.
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


def test_streamed_report_is_streamed_and_complete(client):
    with client.stream("GET", "/tasks/report?rows=500") as response:
        assert response.status_code == 200
        # A streamed response has no content-length header.
        assert "content-length" not in response.headers
        html = response.read().decode()
    assert html.rstrip().endswith("</html>")
    assert html.count("<tr>") == 500 + 1  # 500 rows plus the thead row


def test_normal_pages_are_not_streamed(client):
    assert "content-length" in client.get("/tasks").headers


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
