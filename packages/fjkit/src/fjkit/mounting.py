"""Serve the kit's stylesheet and vendored JavaScript from inside the package.

This is the half of "no build step" that isn't about CSS: the consumer never
downloads htmx or Basecoat, never runs a vendoring script, and has nothing to
commit. The assets ship in the wheel and are served from wherever pip put them.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from fjkit.config import STATIC_DIR, FjkitConfig
from fjkit.styles import resolve_style

__all__ = ["mount_ui"]


def mount_ui(app: FastAPI, config: FjkitConfig | None = None) -> None:
    """Mount the kit's static assets. Call once, at app construction.

    Reads `static_url` from the same config the Environment was built with, so
    the mount path and the URLs the shell template emits cannot drift apart.
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
