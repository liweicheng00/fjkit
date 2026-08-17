from __future__ import annotations

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # A fresh app per test: lifespan builds a new Environment and a new
    # in-memory TaskService, so mutating tests cannot leak into each other.
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def htmx(client):
    """The same app, asked the way htmx asks.

    Every request htmx makes carries `HX-Request: true`, and under
    `render_mode="auto"` that header is what a swap endpoint answers in markup
    rather than JSON. A bare `client` call to one of those routes models a
    caller the app does not have, so the tests that assert on a fragment ask
    through here instead.

    It wraps the app the `client` fixture already started — depending on that
    fixture is what guarantees lifespan has run, and reusing the same app
    object is what keeps `app.state` (the services these tests mutate) shared
    between the two.
    """
    return TestClient(client.app, headers={"HX-Request": "true"})
