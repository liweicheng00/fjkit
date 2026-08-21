"""Configuration for the kit.

Deliberately a plain dataclass and not `pydantic_settings.BaseSettings`: a
library has no business conscripting its consumers into a settings framework or
an environment-variable prefix. Apps that use pydantic-settings map their own
settings onto this; apps that don't, don't have to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fjkit.vendored import StylePack

if TYPE_CHECKING:
    from fjkit.plugins import Plugin

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"

#: What an `@render` route puts on the wire. `"html"` renders the template;
#: `"json"` hands the handler's return value back to FastAPI, which serialises
#: it through the route's `response_model`; `"auto"` renders whenever there is
#: markup to render for this caller and falls back to JSON when there is not.
RenderMode = Literal["html", "json", "auto"]


@dataclass(frozen=True, slots=True)
class FjkitConfig:
    """Everything tunable, in one object.

    The defaults are the dev-friendly side. Production flips `auto_reload` and
    `strict_undefined` off — see `for_production()`.
    """

    #: Where the app's own templates live. Searched *before* the kit's, so an
    #: app can shadow `ui/button.html` by dropping a file at the same path.
    #: That is the mechanism behind `fjkit eject` (CHARTER.md A5).
    template_dir: Path | None = None

    #: URL prefix the kit's stylesheet and vendored JS are served from. Both
    #: `mount_fjkit()` and the shell template read this, so they cannot disagree.
    static_url: str = "/_fjkit"

    #: Which Basecoat style pack the shell loads. All eight ship in the wheel
    #: already built, so this is a one-word change and a restart — no Tailwind,
    #: no reinstall, and not one template edit, because a pack changes geometry
    #: (control heights, radii, borders, shadows) and never the class names or
    #: tokens a template writes.
    #:
    #: `"auto"` defers to whatever `uv add "fjkit[nova]"` installed, and falls
    #: back to the default pack when that is nothing — so an app that never
    #: heard of style packs keeps the stylesheet it always had. Naming a pack
    #: here always wins over what is installed. See `fjkit.styles`.
    #:
    #: It is deliberately not a per-request value. Two packs on one page would
    #: mean two full stylesheets over the wire and one silently losing the
    #: cascade, so the choice belongs to the app, once.
    style: StylePack | Literal["auto"] = "auto"

    #: Stats every template file on every render. Cheap per call, but it is
    #: syscalls on the hot path and pure waste once the files cannot change.
    auto_reload: bool = True

    #: Compiled templates cached as Python bytecode on disk, so a fresh worker
    #: skips parse+compile. Matters for cold starts and autoscaling.
    bytecode_cache_dir: Path | None = None

    #: In-memory LRU of compiled template objects. Jinja's default, already
    #: larger than most apps' template count — sized so nothing is evicted.
    cache_size: int = 400

    #: Turns a typo'd variable into an error instead of an empty string.
    #: Slightly slower and it can 500 a page, so: on in dev, off in prod.
    strict_undefined: bool = True

    #: Extra values exposed to every template. Prefer this over threading the
    #: same key through every route's context dict.
    globals: dict[str, object] = field(default_factory=dict)

    #: Extensions, applied in this order. A plugin can add middleware, an
    #: exception handler, a template directory, or a value that every template
    #: gets — see `fjkit.plugins`. Order matters twice: template directories
    #: are searched in it, and Starlette runs middleware in reverse of it, so a
    #: plugin listed later wraps the ones before it.
    plugins: tuple[Plugin, ...] = ()

    #: Default representation for every `@render` route. A single decorator can
    #: override it with `mode=`, so this is the app-wide default rather than a
    #: rule. `"auto"` gives a page to whoever navigates to one and the fragment
    #: to whoever swaps it, and answers everybody else with the model — so the
    #: htmx endpoints are the app's API without a route saying so. `"json"`
    #: turns *every* route into JSON, which is how you see exactly what a
    #: template was handed. `"html"` never serialises anything.
    render_mode: RenderMode = "auto"

    def for_production(self) -> FjkitConfig:
        """The same config with the two dev-only knobs turned off."""
        from dataclasses import replace

        return replace(self, auto_reload=False, strict_undefined=False)
