"""Both spellings of every page answer directly, so the admin never redirects.

Django's admin redirects `/admin` to `/admin/` with a permanent 301, which a
browser caches per host and port. An admin that answered `/admin/` with a
redirect back to `/admin` would alternate with that cached 301 forever — the
browser reports it as too many redirects, and nothing on the server shows why.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_every_page_answers_with_and_without_a_trailing_slash(client: TestClient):
    for path in ("/admin", "/admin/task", "/admin/task/new", "/admin/task/1"):
        for spelling in (path, path + "/"):
            response = client.get(spelling, follow_redirects=False)
            assert response.status_code == 200, f"{spelling} answered {response.status_code}"
