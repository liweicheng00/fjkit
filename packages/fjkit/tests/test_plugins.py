"""The extension seam: what a plugin may contribute, and what it may not."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, PluginWarning, mount_fjkit, render
from fjkit.plugins import AppSetup, EnvSetup
from jinja2 import DictLoader


class Recording:
    """A plugin that records which hooks ran, and contributes nothing."""

    def __init__(self, name: str = "recording") -> None:
        self.name = name
        self.calls: list[str] = []

    def mount(self, setup: AppSetup) -> None:
        self.calls.append("mount")

    def extend(self, setup: EnvSetup) -> None:
        self.calls.append("extend")


class Greeter:
    """A plugin that touches only Jinja, with no `mount` hook."""

    name = "greeter"

    def extend(self, setup: EnvSetup) -> None:
        setup.add_global("greeting", "hello")
        setup.add_filter("shout", lambda s: f"{s}!")
        setup.add_context_processor(lambda r: {"who": r.headers.get("x-who", "world")}, provides=["who"])


def app_with(*plugins, **config_kwargs):
    config = FjkitConfig(plugins=tuple(plugins), **config_kwargs)
    app = FastAPI()
    templates = mount_fjkit(app, config)
    return app, templates


def test_both_hooks_run_and_are_optional():
    both, jinja_only = Recording(), Greeter()
    app_with(both, jinja_only)

    assert both.calls == ["mount", "extend"]
    assert not hasattr(jinja_only, "mount")  # a plugin need not implement both


def test_globals_and_filters_reach_templates():
    _, templates = app_with(Greeter())

    assert templates.env.from_string("{{ greeting|shout }}").render() == "hello!"


def test_context_processor_runs_once_per_render():
    router = APIRouter()

    @router.get("/hi")
    @render("hi.html")
    def hi() -> dict[str, str]:
        return {}

    app, templates = app_with(Greeter())
    templates.env.loader = DictLoader({"hi.html": "{{ greeting }} {{ who }}"})
    app.include_router(router)

    assert TestClient(app).get("/hi", headers={"x-who": "fjkit"}).text == "hello fjkit"


def test_the_route_wins_over_a_processor():
    """A handler knows something the app-wide rule does not, so it wins."""
    router = APIRouter()

    @router.get("/hi")
    @render("hi.html")
    def hi() -> dict[str, str]:
        return {"who": "the handler"}

    app, templates = app_with(Greeter())
    templates.env.loader = DictLoader({"hi.html": "{{ who }}"})
    app.include_router(router)

    assert TestClient(app).get("/hi").text == "the handler"


def test_two_plugins_claiming_one_context_key_fail_at_startup():
    class OtherGreeter:
        name = "other"

        def extend(self, setup: EnvSetup) -> None:
            setup.add_context_processor(lambda r: {"who": "me"}, provides=["who"])

    with pytest.raises(ValueError, match="'greeter' and 'other' both provide context key 'who'"):
        app_with(Greeter(), OtherGreeter())


def test_two_plugins_claiming_one_global_fail_at_startup():
    class OtherGreeter:
        name = "other"

        def extend(self, setup: EnvSetup) -> None:
            setup.add_global("greeting", "hi")

    with pytest.raises(ValueError, match="both provide global 'greeting'"):
        app_with(Greeter(), OtherGreeter())


def test_a_duplicate_plugin_name_is_refused():
    with pytest.raises(ValueError, match="'recording' is registered twice"):
        app_with(Recording(), Recording())


def test_an_undeclared_context_key_is_caught_under_strict_undefined():
    class Sneaky:
        name = "sneaky"

        def extend(self, setup: EnvSetup) -> None:
            setup.add_context_processor(lambda r: {"a": 1, "b": 2}, provides=["a"])

    router = APIRouter()

    @router.get("/x")
    @render("x.html")
    def x() -> dict[str, str]:
        return {}

    app, templates = app_with(Sneaky())
    templates.env.loader = DictLoader({"x.html": "{{ a }}"})
    app.include_router(router)

    with pytest.raises(RuntimeError, match=r"'sneaky' returned context key\(s\) \['b'\]"):
        TestClient(app).get("/x")


def test_plugin_templates_sit_between_the_app_and_the_kit(tmp_path: Path):
    """A plugin may replace a kit macro; it may never shadow the app's own file."""
    app_dir, plugin_dir = tmp_path / "app", tmp_path / "plugin"
    for d in (app_dir, plugin_dir):
        (d / "ui").mkdir(parents=True)
    (app_dir / "ui" / "owned.html").write_text("app", encoding="utf-8")
    (plugin_dir / "ui" / "owned.html").write_text("plugin", encoding="utf-8")
    (plugin_dir / "ui" / "extra.html").write_text("from the plugin", encoding="utf-8")

    class Shipper:
        name = "shipper"

        def extend(self, setup: EnvSetup) -> None:
            setup.add_template_dir(plugin_dir)

    _, templates = app_with(Shipper(), template_dir=app_dir)

    assert templates.env.get_template("ui/owned.html").render() == "app"
    assert templates.env.get_template("ui/extra.html").render() == "from the plugin"


def test_warn_names_the_plugin():
    class Fussy:
        name = "fussy"

        def mount(self, setup: AppSetup) -> None:
            setup.warn("this will not work")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        app_with(Fussy())

    assert len(caught) == 1
    assert issubclass(caught[0].category, PluginWarning)
    assert str(caught[0].message) == "[fjkit:fussy] this will not work"


def test_a_plugin_can_add_middleware_and_a_route():
    from starlette.middleware.base import BaseHTTPMiddleware

    class Stamping:
        name = "stamping"

        def mount(self, setup: AppSetup) -> None:
            async def stamp(request, call_next):
                response = await call_next(request)
                response.headers["x-plugin"] = "stamping"
                return response

            setup.add_middleware(BaseHTTPMiddleware, dispatch=stamp)

            router = APIRouter()

            @router.get("/_plugin/ping")
            def ping() -> dict[str, str]:
                return {"ok": "yes"}

            setup.include_router(router)

    app, _ = app_with(Stamping())
    response = TestClient(app).get("/_plugin/ping")

    assert response.json() == {"ok": "yes"}
    assert response.headers["x-plugin"] == "stamping"
