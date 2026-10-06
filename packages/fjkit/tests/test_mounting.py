"""Contracts of `mount_fjkit()`, the single call that wires the kit into an app."""

from __future__ import annotations

import os
import re

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Templates, mount_fjkit, render
from fjkit.config import STATIC_DIR
from fjkit.templating import build_environment
from jinja2 import ChoiceLoader, DictLoader


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
    """Regression: building the `Environment` in lifespan broke `TestClient`.

    A `TestClient` used without its context manager never runs startup, so an
    app that built its `Environment` there had no templates and returned 500.
    The `Environment` is now built at construction time.
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


def test_a_rebuilt_asset_gets_a_new_url_so_a_browser_cannot_keep_the_old_one():
    """`StaticFiles` sends `ETag` and `Last-Modified` but no `Cache-Control`, so
    a browser may cache a stylesheet whose lifetime it was never told.

    That failure is silent: the page renders, the markup is current, half the
    rules are missing, and nothing reports why. `fjkit_static` stamps every URL
    with the file's mtime, which moves when `fjkit build-css` rewrites the file
    and when a wheel is upgraded, and does not move otherwise.
    """
    static = build_environment(FjkitConfig(auto_reload=True)).globals["fjkit_static"]
    asset = "dist/fjkit-vega.css"

    before = static(asset)
    assert before.startswith("/_fjkit/dist/fjkit-vega.css?v=")

    path = STATIC_DIR / asset
    was = path.stat().st_mtime
    try:
        os.utime(path, (was + 60, was + 60))
        assert static(asset) != before
    finally:
        os.utime(path, (was, was))

    # Stable while the file does not move: a stamp that changed on every render
    # would defeat caching rather than fix it.
    assert static(asset) == before


def test_the_stamp_is_read_once_when_the_app_is_not_reloading():
    """A `stat` per asset per render is the price of catching a rebuild, and
    production has no rebuild to catch."""
    static = build_environment(FjkitConfig(auto_reload=False)).globals["fjkit_static"]
    asset = "dist/fjkit-vega.css"

    before = static(asset)
    path = STATIC_DIR / asset
    was = path.stat().st_mtime
    try:
        os.utime(path, (was + 60, was + 60))
        assert static(asset) == before  # remembered, not re-stat'd
    finally:
        os.utime(path, (was, was))


def test_an_asset_that_is_not_there_still_renders_a_url():
    """A missing file must 404 visibly, not raise inside a template render."""
    static = build_environment(FjkitConfig()).globals["fjkit_static"]
    assert static("dist/nope.css").startswith("/_fjkit/dist/nope.css?v=")


ASSETS_PAGE = (
    '{% from "ui/form.html" import form_scripts %}'
    '<link href="{{ fjkit_static("dist/fjkit-vega.css") }}">'
    "{{ form_scripts() }}"
)


def _asset_urls(html: str) -> list[str]:
    return re.findall(r'(?:href|src)="([^"?]+)\?v=', html)


def _sub_app(*, stream: bool = False) -> FastAPI:
    router = APIRouter()

    @router.get("/assets-page")
    @render("assets.html", stream=stream)
    def assets_page() -> dict[str, str]:
        return {}

    sub = FastAPI()
    templates = mount_fjkit(sub, FjkitConfig())
    templates.env.loader = ChoiceLoader([DictLoader({"assets.html": ASSETS_PAGE}), templates.env.loader])
    sub.include_router(router)
    return sub


@pytest.mark.parametrize("stream", [False, True], ids=["page", "stream"])
def test_a_sub_app_links_its_assets_under_its_mount_prefix(stream):
    """`mount_fjkit()` mounts the assets on the app it is given, so mounted at
    `/ui` they are served at `/ui/_fjkit`. The URLs must say so — including the
    ones written inside an imported macro, whose context holds no `request`."""
    parent = FastAPI()
    parent.mount("/ui", _sub_app(stream=stream))
    client = TestClient(parent)

    urls = _asset_urls(client.get("/ui/assets-page").text)

    assert urls == ["/ui/_fjkit/dist/fjkit-vega.css", "/ui/_fjkit/vendor/htmx/json-enc.js"]
    assert all(client.get(url).status_code == 200 for url in urls)


def test_a_root_path_behind_a_proxy_prefixes_the_assets():
    client = TestClient(_sub_app(), root_path="/proxy")

    urls = _asset_urls(client.get("/assets-page").text)

    assert urls == ["/proxy/_fjkit/dist/fjkit-vega.css", "/proxy/_fjkit/vendor/htmx/json-enc.js"]


def test_a_render_outside_a_request_keeps_the_bare_prefix():
    """The docs builder and the benchmark render with no request at all."""
    TestClient(_sub_app(), root_path="/proxy").get("/assets-page")
    static = build_environment(FjkitConfig()).globals["fjkit_static"]

    assert static("dist/fjkit-vega.css").startswith("/_fjkit/")
