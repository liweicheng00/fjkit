"""One call to wire fjkit into a FastAPI app.

Two things have to happen before a route can render: the kit's assets need a
URL, and the Jinja Environment needs building. Both read the same `FjkitConfig`
and neither is useful without the other, so they are one call rather than two
an app must keep in step.

The Environment is built here, at app construction, rather than in lifespan.
It is per-process either way — every worker constructs the app — and building
it here means a `TestClient` used without its context manager still has
templates, which is the failure this consolidation removes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from fjkit.config import STATIC_DIR, FjkitConfig
from fjkit.errors import install_error_handlers
from fjkit.plugins import install_plugins
from fjkit.styles import resolve_style
from fjkit.templating import Templates

__all__ = ["mount_fjkit"]


def mount_fjkit(app: FastAPI, config: FjkitConfig | None = None) -> Templates:
    """Mount the kit's static assets and build the Environment. Call once.

    Serves the stylesheet and the vendored htmx/Basecoat JS out of the
    installed package at `config.static_url`, then puts the `Templates` on
    `app.state.templates`, where `@render` looks for it.

    Returns the same `Templates` it stored, for a caller that renders outside a
    request — a build script, a test.
    """
    config = config or FjkitConfig()

    # Check the resolved pack, not just any pack: a wheel built before this pack
    # existed would otherwise pass the check and 404 on the page. Resolving here
    # as well as in the Environment is deliberate — an app that mounts but never
    # renders should still fail at startup rather than on its first request.
    style = resolve_style(config.style)
    stylesheet = STATIC_DIR / "dist" / f"fjkit-{style}.css"
    if not stylesheet.exists():
        raise RuntimeError(
            f"fjkit's stylesheet for style={style!r} is missing from the "
            f"installed package ({stylesheet}).\n"
            "A released wheel ships all eight style packs. If you are working on "
            "fjkit itself, build them once with:  uv run fjkit build-css"
        )

    app.mount(
        config.static_url,
        StaticFiles(directory=STATIC_DIR),
        name="fjkit_static",
    )

    # Before the plugins, because Starlette keys exception handlers by class and
    # the last registration wins: going first lets a plugin — or the app —
    # replace the kit's answer to a rejected form rather than be shadowed by it.
    install_error_handlers(app, config)

    # Before the Environment: a plugin's `mount` may refuse a configuration
    # outright, and failing there is cheaper and clearer than failing after
    # every template in the app has been compiled.
    install_plugins(app, config)

    # After the plugins, so the overlap check sees every mount they made.
    if config.static_dir is not None:
        _mount_app_static(app, config)

    templates = Templates.create(config)
    app.state.templates = templates
    return templates


#: Starlette's conventional name for an app's static mount. Kept, so an app's
#: existing `url_for(request, "static", path=…)` calls resolve after it moves to
#: `FjkitConfig.static_dir`.
APP_STATIC_NAME = "static"


def _mount_app_static(app: FastAPI, config: FjkitConfig) -> None:
    """Serve `config.static_dir`, refusing every setup that would 404 later."""
    directory = config.static_dir
    assert directory is not None
    if not directory.is_dir():
        raise RuntimeError(
            f"FjkitConfig.static_dir is {directory}, which is not a directory. "
            "Point it at the folder holding the app's own scripts and images, or leave it None."
        )

    url = config.static_dir_url.rstrip("/")
    if not url.startswith("/"):
        raise ValueError(
            f"FjkitConfig.static_dir_url must be a path below the root such as '/static', "
            f"not {config.static_dir_url!r}."
        )

    for route in app.routes:
        name = getattr(route, "name", None)
        if name == APP_STATIC_NAME or (isinstance(route, Mount) and _nested(url, route.path)):
            raise ValueError(
                f"FjkitConfig.static_dir_url {url!r} overlaps the mount {name!r} at {getattr(route, 'path', '')!r}. "
                "Starlette matches the first mount whose prefix fits, so one of them would 404 for "
                "files it holds. Choose a URL outside it — or, if the app mounts its own static "
                "directory as well, drop that mount: static_dir replaces it."
            )

    app.mount(url, StaticFiles(directory=directory), name=APP_STATIC_NAME)


def _nested(a: str, b: str) -> bool:
    """Whether one URL prefix contains the other, comparing whole segments, so
    `/static-v2` is not inside `/static`."""
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")
