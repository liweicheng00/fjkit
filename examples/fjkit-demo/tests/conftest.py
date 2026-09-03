from __future__ import annotations

import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    # A fresh app per test: the services hold their rows in memory, and writes
    # from one test would otherwise be visible to the next.
    with TestClient(create_app()) as client:
        yield client


@pytest.fixture
def htmx(client):
    """A client on the same app that sends `HX-Request: true`."""
    return TestClient(client.app, headers={"HX-Request": "true"})
