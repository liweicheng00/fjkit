"""`mount_fjkit()` — the one call that wires the kit into an app."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Templates, mount_fjkit, render
from jinja2 import DictLoader


def test_mount_returns_the_templates_it_stored():
    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig())

    assert isinstance(templates, Templates)
    assert app.state.templates is templates


def test_mount_serves_the_stylesheet_at_the_configured_url():
    app = FastAPI()
    mount_fjkit(app, FjkitConfig(static_url="/assets"))

    with TestClient(app) as client:
        response = client.get("/assets/dist/fjkit-vega.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_render_works_without_running_lifespan():
    """The reason the Environment moved out of lifespan.

    A `TestClient` used without its context manager never runs startup, so an
    app that built its Environment there had no templates and 500'd. Building
    at construction removes that failure entirely.
    """
    router = APIRouter()

    @router.get("/ping")
    @render("ping.html")
    def ping() -> dict[str, str]:
        return {}

    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig())
    templates.env.loader = DictLoader({"ping.html": "<p>pong</p>"})
    app.include_router(router)

    response = TestClient(app).get("/ping")  # no `with` — lifespan never runs

    assert response.status_code == 200
    assert "pong" in response.text
