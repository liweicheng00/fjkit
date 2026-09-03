"""The extension seam — one object that contributes to the app and to Jinja.

A plugin exists because some features need more than a macro: a middleware, an
exception handler, a value in every template's context. Wiring that by hand
means an app keeps four things in the right order and in step, which is the
failure `mount_fjkit()` removes one level down.

Two contribution points, because the kit has two moments:

* `mount(AppSetup)` runs when the app is constructed — middleware, exception
  handlers, routes, static files.
* `extend(EnvSetup)` runs when the Environment is built — template directories,
  globals, filters, and the per-request context.

Both are optional. A plugin that only puts a value in every template writes
only `extend`. Hiding the split would be friendlier right up until someone's
`mount` silently never ran.

A plugin deliberately **cannot** inject markup into the shell. Such a hook
would let any plugin put a `<script>` on every page, and both "no build step in
the app" and the closed vocabulary would leave through it.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from fastapi import APIRouter, FastAPI, Request
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fjkit.config import FjkitConfig

__all__ = [
    "AppSetup",
    "ContextProcessor",
    "EnvSetup",
    "Plugin",
    "PluginWarning",
    "collect_env",
    "install_plugins",
]

#: Called once per render with the live request, returning values to merge into
#: the template context. **Synchronous**: it runs inside `Templates.page()`,
#: which a `def` handler reaches from the threadpool. A plugin that needs I/O
#: does it in middleware and leaves the result on `request.state` for the
#: processor to read, which is what the auth plugin does.
ContextProcessor = Callable[[Request], Mapping[str, object]]


class PluginWarning(UserWarning):
    """A plugin's install-time check found a configuration that fails later.

    Its own category, so an app can turn it into an error:
    `warnings.simplefilter("error", PluginWarning)`.
    """


@runtime_checkable
class Plugin(Protocol):
    """What `FjkitConfig.plugins` accepts.

    `name` identifies the plugin rather than labelling it: it detects duplicate
    registration, names the `request.state` field the plugin owns, and appears
    in the error when two plugins claim one global or context key.
    """

    name: str

    def mount(self, setup: AppSetup) -> None:
        """App construction. Optional."""

    def extend(self, setup: EnvSetup) -> None:
        """Environment build. Optional."""


class AppSetup:
    """What a plugin may do to the app. Handed to `Plugin.mount`.

    A pass-through to FastAPI rather than a wrapper with opinions, except that
    everything it does is attributed to the plugin, so a misbehaving one is
    named in the traceback rather than found by elimination.
    """

    __slots__ = ("app", "config", "_name")

    def __init__(self, app: FastAPI, config: FjkitConfig, name: str) -> None:
        self.app = app
        self.config = config
        self._name = name

    def add_middleware(self, cls: type, /, **options: Any) -> None:
        """Starlette runs middleware in reverse registration order, so a plugin
        listed later in `FjkitConfig.plugins` wraps the earlier ones."""
        self.app.add_middleware(cls, **options)

    def add_exception_handler(self, exc: type[Exception] | int, handler: Callable) -> None:
        self.app.add_exception_handler(exc, handler)

    def include_router(self, router: APIRouter) -> None:
        self.app.include_router(router)

    def mount_static(self, url: str, directory: Path) -> None:
        self.app.mount(url, StaticFiles(directory=directory), name=f"fjkit_{self._name}_static")

    def warn(self, message: str) -> None:
        """Report at startup a configuration that misbehaves later.

        For the combinations only the plugin recognises — an in-memory store
        under a production config, a token source that cannot refresh. Each
        surfaces days later on another machine.
        """
        warnings.warn(f"[fjkit:{self._name}] {message}", PluginWarning, stacklevel=2)


class EnvSetup:
    """What a plugin may contribute to Jinja. Handed to `Plugin.extend`.

    Collects rather than mutates: the Environment does not exist yet, because
    template directories have to be in the search path before it is built.
    """

    __slots__ = ("config", "_current", "_owners", "contributions")

    def __init__(self, config: FjkitConfig) -> None:
        self.config = config
        self.contributions = EnvContributions()
        self._current = ""
        #: key -> the plugin that claimed it, for the collision message.
        self._owners: dict[str, str] = {}

    def add_template_dir(self, directory: Path) -> None:
        """Add a template directory, searched after the app's and before the
        kit's.

        After the app's, so a plugin can never shadow a file the app wrote —
        that would break `fjkit eject` (CHARTER A5) from a direction the app
        cannot see. Before the kit's, so a plugin can replace a kit macro.
        """
        self.contributions.template_dirs.append(directory)

    def add_global(self, name: str, value: object) -> None:
        self._claim(f"global {name!r}", name)
        self.contributions.globals[name] = value

    def add_filter(self, name: str, fn: Callable[..., Any]) -> None:
        self._claim(f"filter {name!r}", f"filter:{name}")
        self.contributions.filters[name] = fn

    def add_context_processor(self, fn: ContextProcessor, *, provides: Sequence[str]) -> None:
        """Merge values into every template's context, once per render.

        `provides` lists the keys the processor returns. Required rather than
        inferred: without it, two plugins fighting over `user` show up only by
        rendering a page and noticing. With it, the clash is a startup error
        naming both plugins.
        """
        for key in provides:
            self._claim(f"context key {key!r}", key)
        self.contributions.processors.append((self._current, tuple(provides), fn))

    def _claim(self, what: str, key: str) -> None:
        owner = self._owners.get(key)
        if owner is not None:
            raise ValueError(
                f"fjkit plugins {owner!r} and {self._current!r} both provide {what}. "
                "Rename one, or drop one from FjkitConfig.plugins."
            )
        self._owners[key] = self._current


@dataclass(slots=True)
class EnvContributions:
    """Everything the plugins added, ready for `build_environment` to apply."""

    template_dirs: list[Path] = field(default_factory=list)
    globals: dict[str, object] = field(default_factory=dict)
    filters: dict[str, Callable[..., Any]] = field(default_factory=dict)
    #: (plugin name, declared keys, callable) — the first two exist only to name
    #: a processor that returns a key it never declared.
    processors: list[tuple[str, tuple[str, ...], ContextProcessor]] = field(default_factory=list)


def collect_env(config: FjkitConfig) -> EnvContributions:
    """Run every plugin's `extend`, in `FjkitConfig.plugins` order."""
    setup = EnvSetup(config)
    for plugin in _ordered(config):
        setup._current = plugin.name
        extend = getattr(plugin, "extend", None)
        if extend is not None:
            extend(setup)
    return setup.contributions


def install_plugins(app: FastAPI, config: FjkitConfig) -> None:
    """Run every plugin's `mount`, in `FjkitConfig.plugins` order."""
    for plugin in _ordered(config):
        mount = getattr(plugin, "mount", None)
        if mount is not None:
            mount(AppSetup(app, config, plugin.name))


def _ordered(config: FjkitConfig) -> tuple[Plugin, ...]:
    """The configured plugins, with duplicate names rejected.

    Two plugins under one name would collide on `request.state.<name>` and make
    every later error message ambiguous, so the duplicate is refused at startup
    rather than resolved by last-one-wins.
    """
    seen: set[str] = set()
    for plugin in config.plugins:
        name = getattr(plugin, "name", None)
        if not name:
            raise ValueError(f"fjkit plugin {plugin!r} has no `name`.")
        if name in seen:
            raise ValueError(f"fjkit plugin {name!r} is registered twice in FjkitConfig.plugins.")
        seen.add(name)
    return tuple(config.plugins)
