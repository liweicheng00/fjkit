"""One call to wire fjkit into a FastAPI app.

Two things have to happen before a route can render: the kit's assets need a
URL, and the Jinja Environment needs building. Both read the same `FjkitConfig`
and neither is useful without the other, so they are one call rather than two
an app has to remember to keep in step.

The Environment is built here, at app construction, rather than in lifespan.
It is per-process either way — every worker constructs the app — and doing it
here means a `TestClient` used without its context manager still has templates,
which is the failure this consolidation removes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fjkit.config import STATIC_DIR, FjkitConfig
from fjkit.plugins import install_plugins
from fjkit.styles import resolve_style
from fjkit.templating import Templates

__all__ = ["mount_fjkit"]


def mount_fjkit(app: FastAPI, config: FjkitConfig | None = None) -> Templates:
    """Mount the kit's static assets and build the Environment. Call once.

    Serves the stylesheet and the vendored htmx/Basecoat JS out of the
    installed package at `config.static_url`, then puts the `Templates` on
    `app.state.templates` where `@render` looks for it.

    Returns the same `Templates` it stored, for a caller that wants to render
    outside a request — a build script, a test.
    """
    config = config or FjkitConfig()

    # The resolved pack, not just any pack: a wheel built before this pack
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

    # Before the Environment: a plugin's `mount` may refuse a configuration
    # outright, and failing there is cheaper and clearer than failing after
    # every template in the app has been compiled.
    install_plugins(app, config)

    templates = Templates.create(config)
    app.state.templates = templates
    return templates
