"""Configuration for the kit.

A plain dataclass rather than `pydantic_settings.BaseSettings`, so the kit
imposes neither a settings framework nor an environment-variable prefix on the
apps that use it. An app that already uses pydantic-settings maps its own
settings onto this one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fjkit.vendored import StylePack

if TYPE_CHECKING:
    from fastapi import Request

    from fjkit.messages import Message
    from fjkit.plugins import Plugin

    #: What the user is told when `catch_unexpected_errors` catches something:
    #: one fixed `Message`, or a callable taking the request and the exception
    #: and returning the `Message` for it — so an app can word a `TimeoutError`
    #: differently from a `KeyError`. Use the exception to choose the words;
    #: putting `str(exc)` in them shows a visitor the inside of the app.
    UnexpectedErrorMessage = Message | Callable[[Request, Exception], Message]

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

    The defaults suit development. `for_production()` turns `auto_reload` and
    `strict_undefined` off and `catch_unexpected_errors` on.
    """

    #: Where the app's own templates live. Searched before the kit's, so an app
    #: shadows `ui/button.html` by dropping a file at the same path. That is the
    #: mechanism behind `fjkit eject` (CHARTER.md A5).
    template_dir: Path | None = None

    #: URL prefix the kit's stylesheet and vendored JS are served from. Both
    #: `mount_fjkit()` and the shell template read this, so they cannot disagree.
    static_url: str = "/_fjkit"

    #: Which Basecoat style pack the shell loads. All eight ship in the wheel
    #: already built, so switching is a one-word change and a restart — no
    #: Tailwind, no reinstall, and no template edit, because a pack changes
    #: geometry (control heights, radii, borders, shadows) and never the class
    #: names or tokens a template writes.
    #:
    #: `"auto"` is the default pack, so an app that never heard of style packs
    #: keeps the stylesheet it always had. See `fjkit.styles`.
    #:
    #: Deliberately not a per-request value. Two packs on one page would send
    #: two full stylesheets over the wire and let one silently lose the cascade,
    #: so the app makes the choice once.
    style: StylePack | Literal["auto"] = "auto"

    #: Stats every template file on every render. Cheap per call, but the
    #: syscalls sit on the hot path and buy nothing once the files cannot change.
    auto_reload: bool = True

    #: Compiled templates cached as Python bytecode on disk, so a fresh worker
    #: skips parse+compile. Matters for cold starts and autoscaling.
    bytecode_cache_dir: Path | None = None

    #: In-memory LRU of compiled template objects. Jinja's default, already
    #: larger than most apps' template count — sized so nothing is evicted.
    cache_size: int = 400

    #: Raises on a typo'd variable instead of rendering an empty string. Slower,
    #: and it can 500 a page: on in development, off in production.
    strict_undefined: bool = True

    #: Whether an unhandled exception becomes a toast and an error page rather
    #: than a traceback. Off by default, and that default is the useful one: in
    #: development a traceback in the terminal beats a tidy apology in the
    #: browser, and a handler that swallows one turns a real bug into a mystery.
    #: `for_production()` turns it on. Validation failures (422) are handled
    #: either way — a rejected form is not a bug.
    catch_unexpected_errors: bool = False

    #: The toast a caught exception raises, and the note on the error page's
    #: toaster after a navigation. `None` uses the kit's own wording —
    #: "Something went wrong", with a text saying nothing was saved. A `Message`
    #: changes the words once; a callable `(request, exc) -> Message` picks them
    #: per exception. Read only when `catch_unexpected_errors` is on. The
    #: traceback is logged either way; this decides the sentence, not the
    #: logging.
    unexpected_error: UnexpectedErrorMessage | None = None

    #: Extra values exposed to every template. Prefer this over threading the
    #: same key through every route's context dict.
    globals: dict[str, object] = field(default_factory=dict)

    #: Extensions, applied in this order. A plugin can add middleware, an
    #: exception handler, a template directory, or a value that every template
    #: gets — see `fjkit.plugins`. Order matters twice: template directories are
    #: searched in it, and Starlette runs middleware in reverse of it, so a
    #: plugin listed later wraps the ones before it.
    plugins: tuple[Plugin, ...] = ()

    #: Default representation for every `@render` route; a single decorator
    #: overrides it with `mode=`. `"auto"` gives a page to whoever navigates to
    #: one and the fragment to whoever swaps it, and answers everybody else with
    #: the model — so the htmx endpoints are the app's API without a route
    #: saying so. `"json"` turns every route into JSON, which is how you see
    #: exactly what a template was handed. `"html"` serialises nothing.
    render_mode: RenderMode = "auto"

    def for_production(self) -> FjkitConfig:
        """Return the same config with `auto_reload` and `strict_undefined` off
        and `catch_unexpected_errors` on."""
        from dataclasses import replace

        return replace(self, auto_reload=False, strict_undefined=False, catch_unexpected_errors=True)
