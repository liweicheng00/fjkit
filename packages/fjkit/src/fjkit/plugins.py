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

A plugin that reads a sibling declares it — `uses = ("flash",)` — and reaches
it only through `setup.plugin("flash")`. The declaration is checked the way
`provides=` is: a lookup the plugin never declared, and a sibling listed after
the plugin that uses it, are both startup errors naming the plugin. The host
never reorders. `FjkitConfig.plugins` is the order middleware wraps in, and that
stays the app's to decide; what the host adds is a check that the order the
app wrote is one the plugins can live with.

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

    `uses` names the siblings this plugin may read through `setup.plugin()`.
    Every entry is optional — a name nobody registered comes back as `None` —
    but a registered one must be listed before its user. Declaring rather than
    scanning is what lets the dependency be read off the class and checked at
    startup, instead of found by reading the body of `mount`.
    """

    name: str
    uses: tuple[str, ...] = ()

    def mount(self, setup: AppSetup) -> None:
        """App construction. Optional."""

    def extend(self, setup: EnvSetup) -> None:
        """Environment build. Optional."""


class AppSetup:
    """What a plugin may do to the app. Handed to `Plugin.mount`.

    A pass-through to FastAPI rather than a wrapper with opinions, except that
    everything it does is attributed to the plugin, so a misbehaving one is
    named in the traceback rather than found by elimination. The app itself is
    not exposed: what a plugin can do is this list, and a plugin that needs
    more asks for a method here rather than reaching around it.
    """

    __slots__ = ("_app", "config", "_name", "_plugins")

    def __init__(self, app: FastAPI, config: FjkitConfig, name: str, plugins: Mapping[str, Plugin]) -> None:
        self._app = app
        self.config = config
        self._name = name
        self._plugins = plugins

    def add_middleware(self, cls: type, /, **options: Any) -> None:
        """Starlette runs middleware in reverse registration order, so a plugin
        listed later in `FjkitConfig.plugins` wraps the earlier ones."""
        self._app.add_middleware(cls, **options)

    def add_exception_handler(self, exc: type[Exception] | int, handler: Callable) -> None:
        self._app.add_exception_handler(exc, handler)

    def include_router(self, router: APIRouter) -> None:
        """Add the plugin's routes, warning first if their prefix is already
        routed.

        Starlette matches the first route that fits, so a plugin mounted under
        a path the app or FastAPI already claimed — `/docs`, say — would never
        render and never say why. Every plugin with a router needs this check
        and none of them should have to remember it.
        """
        prefix = router.prefix
        if prefix:
            taken = next((r for r in self._app.routes if getattr(r, "path", None) == prefix), None)
            if taken is not None:
                self.warn(
                    f"{prefix} is already routed by {getattr(taken, 'name', taken)!r}. Starlette matches "
                    "the first route that fits, so the routes this plugin adds there will never be "
                    "reached. Pass a different `url=`, or remove the route that holds it."
                )
        self._app.include_router(router)

    def mount_static(self, url: str, directory: Path) -> None:
        self._app.mount(url, StaticFiles(directory=directory), name=f"fjkit_{self._name}_static")

    def plugin(self, name: str) -> Plugin | None:
        """A sibling this plugin declared in `uses`, or `None` if the app did
        not register one."""
        return _lookup(self._plugins, self._name, name)

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

    __slots__ = ("config", "_current", "_owners", "_plugins", "contributions")

    def __init__(self, config: FjkitConfig, plugins: Mapping[str, Plugin]) -> None:
        self.config = config
        self.contributions = EnvContributions()
        self._current = ""
        self._plugins = plugins
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

    def plugin(self, name: str) -> Plugin | None:
        """A sibling this plugin declared in `uses`, or `None` if the app did
        not register one."""
        return _lookup(self._plugins, self._current, name)

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
    registry = _ordered(config)
    setup = EnvSetup(config, registry)
    for plugin in registry.values():
        setup._current = plugin.name
        extend = getattr(plugin, "extend", None)
        if extend is not None:
            extend(setup)
    return setup.contributions


def install_plugins(app: FastAPI, config: FjkitConfig) -> None:
    """Run every plugin's `mount`, in `FjkitConfig.plugins` order."""
    registry = _ordered(config)
    for plugin in registry.values():
        mount = getattr(plugin, "mount", None)
        if mount is not None:
            mount(AppSetup(app, config, plugin.name, registry))


def _lookup(plugins: Mapping[str, Plugin], current: str, name: str) -> Plugin | None:
    """`setup.plugin()` for both setups: the declaration is the permission.

    Refusing an undeclared name is what keeps `uses` honest. Without the check
    it would be documentation, and the one plugin that forgot it would be the
    one whose dependency nobody can see.
    """
    declared = getattr(plugins[current], "uses", ())
    if name not in declared:
        raise ValueError(
            f"fjkit plugin {current!r} looked up {name!r} without declaring it. "
            f"Add it to `uses`: uses = {tuple(declared) + (name,)!r}."
        )
    return plugins.get(name)


def _ordered(config: FjkitConfig) -> dict[str, Plugin]:
    """The configured plugins by name, in `FjkitConfig.plugins` order, with
    duplicate names and unusable orders rejected.

    Two plugins under one name would collide on `request.state.<name>` and make
    every later error message ambiguous, so the duplicate is refused at startup
    rather than resolved by last-one-wins.

    A plugin listed before one it `uses` is refused rather than moved: its
    `mount` would run before the sibling's, and reordering silently would
    change which middleware wraps which — an order the app wrote on purpose.
    """
    registry: dict[str, Plugin] = {}
    for plugin in config.plugins:
        name = getattr(plugin, "name", None)
        if not name:
            raise ValueError(f"fjkit plugin {plugin!r} has no `name`.")
        if name in registry:
            raise ValueError(f"fjkit plugin {name!r} is registered twice in FjkitConfig.plugins.")
        registry[name] = plugin

    position = {name: index for index, name in enumerate(registry)}
    for name, plugin in registry.items():
        for used in getattr(plugin, "uses", ()):
            if used in position and position[used] > position[name]:
                raise ValueError(
                    f"fjkit plugin {name!r} uses {used!r}, which is listed after it. "
                    f"List {used!r} before {name!r} in FjkitConfig.plugins."
                )
    return registry
