"""Contracts of `mount_fjkit()`, the single call that wires the kit into an app."""

from __future__ import annotations

import os
import re

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.staticfiles import StaticFiles
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


# ------------------------------------------------------- the app's own assets


class _Mounts:
    """A plugin that mounts one static directory, for the collision tests."""

    name = "mounts"

    def __init__(self, url: str, directory) -> None:
        self.url = url
        self.directory = directory

    def mount(self, setup) -> None:
        setup.mount_static(self.url, self.directory)


@pytest.fixture
def app_static_dir(tmp_path):
    root = tmp_path / "static"
    (root / "laboratory").mkdir(parents=True)
    (root / "laboratory" / "marking.js").write_text("// marking\n", encoding="utf-8")
    return root


ASSET = "laboratory/marking.js"
STAMPED = re.compile(r"/static/laboratory/marking\.js\?v=\d+")


def _app_with_static(directory, **config) -> FastAPI:
    router = APIRouter()

    @router.get("/linked")
    @render("linked.html")
    def linked() -> dict[str, str]:
        return {}

    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig(static_dir=directory, **config))
    templates.env.loader = DictLoader(
        {"linked.html": '<script src="{{ app_static("laboratory/marking.js") }}"></script>'}
    )
    app.include_router(router)
    return app


def _linked(client: TestClient, url: str = "/linked") -> str:
    return re.search(r'src="([^"]+)"', client.get(url).text).group(1)


def test_an_app_links_its_own_asset_with_a_stamp(app_static_dir):
    """The stamp `fjkit_static` puts on the kit's assets, on the app's: a deploy
    that ships a new `marking.js` must reach a browser that already cached the
    old one, or the page runs today's markup against yesterday's script."""
    url = _linked(TestClient(_app_with_static(app_static_dir)))

    assert STAMPED.fullmatch(url)


def test_the_asset_is_served_at_the_unstamped_path(app_static_dir):
    client = TestClient(_app_with_static(app_static_dir))
    stamped = _linked(client)

    for url in (stamped, stamped.split("?")[0], f"/static/{ASSET}?v=0"):
        response = client.get(url)
        assert response.status_code == 200, url
        assert response.text == "// marking\n"


def test_url_for_static_keeps_resolving(app_static_dir):
    """The mount keeps Starlette's conventional name, so an app's existing
    `url_for(request, "static", path=…)` calls still find it."""
    app = _app_with_static(app_static_dir)
    router = APIRouter()

    @router.get("/where")
    def where(request: Request) -> dict[str, str]:
        return {"url": request.url_for("static", path=ASSET).path}

    app.include_router(router)

    assert TestClient(app).get("/where").json() == {"url": f"/static/{ASSET}"}


def test_the_url_prefix_is_configurable(app_static_dir):
    client = TestClient(_app_with_static(app_static_dir, static_dir_url="/assets/"))
    url = _linked(client)

    assert re.fullmatch(r"/assets/laboratory/marking\.js\?v=\d+", url)
    assert client.get(url).status_code == 200


def test_a_sub_app_links_its_own_asset_under_its_mount_prefix(app_static_dir):
    parent = FastAPI()
    parent.mount("/ui", _app_with_static(app_static_dir))
    client = TestClient(parent)

    url = _linked(client, "/ui/linked")

    assert re.fullmatch(r"/ui" + STAMPED.pattern, url)
    assert client.get(url).status_code == 200


def test_a_root_path_behind_a_proxy_prefixes_the_app_s_asset(app_static_dir):
    url = _linked(TestClient(_app_with_static(app_static_dir), root_path="/proxy"))

    assert re.fullmatch(r"/proxy" + STAMPED.pattern, url)


def test_the_app_s_stamp_follows_the_file_while_reloading(app_static_dir):
    static = build_environment(FjkitConfig(static_dir=app_static_dir, auto_reload=True)).globals["app_static"]
    before = static(ASSET)

    path = app_static_dir / ASSET
    was = path.stat().st_mtime
    os.utime(path, (was + 60, was + 60))

    assert static(ASSET) != before
    assert static(ASSET) == static(ASSET)


def test_the_app_s_stamp_is_read_once_when_not_reloading(app_static_dir):
    static = build_environment(FjkitConfig(static_dir=app_static_dir, auto_reload=False)).globals["app_static"]
    before = static(ASSET)

    path = app_static_dir / ASSET
    was = path.stat().st_mtime
    os.utime(path, (was + 60, was + 60))

    assert static(ASSET) == before


def test_without_a_static_dir_nothing_is_mounted_or_exposed():
    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig())

    assert "app_static" not in templates.env.globals
    assert all(getattr(route, "name", None) != "static" for route in app.routes)


def test_a_missing_static_dir_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="static_dir"):
        mount_fjkit(FastAPI(), FjkitConfig(static_dir=tmp_path / "nope"))


def test_a_static_dir_that_is_a_file_fails_at_startup(tmp_path):
    file = tmp_path / "static"
    file.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="static_dir"):
        mount_fjkit(FastAPI(), FjkitConfig(static_dir=file))


@pytest.mark.parametrize("url", ["", "/", "static"])
def test_a_static_dir_url_that_is_not_a_path_below_the_root_fails(app_static_dir, url):
    with pytest.raises(ValueError, match="static_dir_url"):
        mount_fjkit(FastAPI(), FjkitConfig(static_dir=app_static_dir, static_dir_url=url))


@pytest.mark.parametrize(
    ("kit", "app_url"),
    [("/static", "/static"), ("/_fjkit", "/_fjkit/app"), ("/assets/kit", "/assets")],
    ids=["same", "inside-the-kit", "around-the-kit"],
)
def test_a_static_dir_url_overlapping_the_kit_s_fails_at_startup(app_static_dir, kit, app_url):
    """Starlette matches the first mount whose prefix fits, so two nested
    mounts mean one of them 404s for files it holds."""
    config = FjkitConfig(static_dir=app_static_dir, static_dir_url=app_url, static_url=kit)
    with pytest.raises(ValueError, match="fjkit_static"):
        mount_fjkit(FastAPI(), config)


def test_a_static_dir_url_overlapping_a_plugin_mount_fails_at_startup(app_static_dir, tmp_path):
    plugin = _Mounts("/static/charts", tmp_path)
    with pytest.raises(ValueError, match="fjkit_mounts_static"):
        mount_fjkit(FastAPI(), FjkitConfig(static_dir=app_static_dir, plugins=(plugin,)))


def test_an_app_that_already_mounted_static_is_told_to_drop_it(app_static_dir):
    """The workaround this field replaces: an app mounting `/static` itself."""
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=app_static_dir), name="static")
    with pytest.raises(ValueError, match="static"):
        mount_fjkit(app, FjkitConfig(static_dir=app_static_dir))


def test_a_sibling_prefix_is_not_an_overlap(app_static_dir):
    """`/static-v2` is not inside `/static`: prefixes compare by segment."""
    mount_fjkit(FastAPI(), FjkitConfig(static_dir=app_static_dir, static_url="/static-kit"))
