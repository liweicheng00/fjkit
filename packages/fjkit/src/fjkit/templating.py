"""Builds and owns the Jinja `Environment`.

Routers never touch `Environment` directly, so compilation settings and
profiling have one location.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import (
    BaseLoader,
    ChainableUndefined,
    ChoiceLoader,
    Environment,
    FileSystemBytecodeCache,
    FileSystemLoader,
    PrefixLoader,
    StrictUndefined,
    pass_context,
    select_autoescape,
)

from fjkit.config import STATIC_DIR, TEMPLATE_DIR, FjkitConfig
from fjkit.icons import path as _icon_path
from fjkit.messages import TOAST_EVENT
from fjkit.messages import queue as _message_queue
from fjkit.plugins import collect_env
from fjkit.styles import resolve_style

__all__ = ["FJKIT_NAMESPACE", "Templates", "build_environment", "get_templates", "static_url"]

#: The reserved prefix under which the kit's own templates are always reachable,
#: whatever an app has shadowed. See `_ReservedNamespace`.
FJKIT_NAMESPACE = "fjkit"


class _ReservedNamespace(PrefixLoader):
    """`fjkit/ui/form.html` — the kit's own copy, even when `ui/form.html` is not.

    An ejected override lives at `ui/form.html` and shadows the kit's file of
    that name. To re-export the macros it did not take, it has to name the very
    file it shadows — and by then `ui/form.html` means itself, an import loop.
    This loader gives that file a second, unshadowable name.

    It sits first in the chain on purpose: an app cannot take the prefix back by
    creating `templates/fjkit/ui/form.html`, so an override can never be tricked
    into re-exporting from something other than the package.

    It lists nothing. The loader at the end of the chain already lists the same
    files under their bare names, and a second entry for each would double every
    "compile every template" sweep — including the cold-start benchmark that
    guards §7 of the charter.
    """

    def list_templates(self) -> list[str]:
        return []


def build_environment(config: FjkitConfig | None = None) -> Environment:
    """Build the Environment holding the compile-time settings for every
    template the app renders.

    Also the one place plugins' `extend` hooks run, so their context processors
    end up on the returned Environment as `fjkit_context_processors`. They ride
    there because `Templates` is built from an Environment and nothing else;
    collecting them by running the hooks again would call plugin code twice for
    one app.
    """
    config = config or FjkitConfig()
    contributions = collect_env(config)

    # The reserved `fjkit/…` namespace first — nothing may shadow it, because an
    # ejected override reaches back through it for the macros it did not take.
    # Then the app's templates, then any a plugin shipped, then the kit's. A file
    # at the same path in the app wins: that is how `fjkit eject` works, and why
    # shadowing is a supported feature rather than a fork. Plugins sit in the
    # middle so one can replace a kit macro but never a file the app wrote.
    searchpath: list[BaseLoader] = [
        _ReservedNamespace({FJKIT_NAMESPACE: FileSystemLoader(TEMPLATE_DIR, encoding="utf-8")})
    ]
    if config.template_dir is not None:
        searchpath.append(FileSystemLoader(config.template_dir, encoding="utf-8"))
    searchpath.extend(FileSystemLoader(d, encoding="utf-8") for d in contributions.template_dirs)
    searchpath.append(FileSystemLoader(TEMPLATE_DIR, encoding="utf-8"))

    bytecode_cache = None
    if config.bytecode_cache_dir is not None:
        config.bytecode_cache_dir.mkdir(parents=True, exist_ok=True)
        bytecode_cache = FileSystemBytecodeCache(str(config.bytecode_cache_dir), "%s.j2c")

    env = Environment(
        loader=ChoiceLoader(searchpath),
        # Only `.html`/`.jinja` are escaped; a template that renders JSON or CSV
        # opts out by extension instead of by sprinkling `|safe`.
        autoescape=select_autoescape(("html", "jinja")),
        auto_reload=config.auto_reload,
        bytecode_cache=bytecode_cache,
        cache_size=config.cache_size,
        # Drop the newline after a block tag and the indentation before it.
        # Templates stay indented for humans; the bytes on the wire do not pay
        # for it. Typically 10-20% off a nested page.
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined if config.strict_undefined else ChainableUndefined,
        # Async rendering exists for awaiting inside templates. fjkit hands
        # templates finished data instead, so sync rendering avoids the
        # coroutine wrapper on every block.
        enable_async=False,
    )

    # Resolved once per Environment. Anything a template needs on every page
    # belongs here rather than in every route's context dict.
    env.globals["url_for"] = _url_for
    env.globals["is_active"] = _is_active
    env.globals["fjkit_static"] = static_url(config.static_url, auto_reload=config.auto_reload)
    env.globals["fjkit_icon_path"] = _icon_path
    env.globals["fjkit_version"] = _versions()
    # A global rather than a context key: the shell reads it on every page, and
    # a context key would have to be merged into every render — including the
    # ones with nothing to say. It finds the request in the context itself, so
    # the shell need not name it, and a render driven without one (the docs
    # builder, the benchmark) has no messages rather than an undefined name.
    env.globals["fjkit_messages"] = _messages_in_context
    #: The event name the shell's listener binds. Exposed rather than written
    #: twice, so `HX-Trigger` and the listener cannot drift apart.
    env.globals["fjkit_toast_event"] = TOAST_EVENT
    # The shell builds its stylesheet URL from this. Exposed as the pack name
    # rather than a finished URL, so a custom shell can also report or switch on
    # which pack is live.
    env.globals["fjkit_style"] = resolve_style(config.style)

    # Plugins before the app's own globals: an app can always override what a
    # plugin exposed, and never the other way round.
    env.globals.update(contributions.globals)
    env.filters.update(contributions.filters)
    env.globals.update(config.globals)

    #: Read by `Templates.page()` and `.stream()`. A tuple, so the hot path
    #: tests it with one truthiness check and skips the merge entirely when no
    #: plugin asked for a per-request context — the common case.
    env.fjkit_context_processors = tuple(contributions.processors)  # type: ignore[attr-defined]
    return env


@pass_context
def _messages_in_context(context: Any) -> Any:
    """Return the queue for the request this render is for, or an empty queue.

    `context.get("request")` rather than a parameter: every render through
    `Templates` passes `request`, but a bare `Environment.from_string(...)` in a
    test or a build script does not, and under `strict_undefined` naming it in
    the shell would raise on a page that has nothing to do with messages. A
    missing request and an `Undefined` one mean the same thing here.
    """
    request = context.get("request")
    return _message_queue(request if isinstance(request, Request) else None)


def _url_for(request: Request, name: str, /, **path_params: Any) -> str:
    """Root-relative URL for a named route.

    Starlette's `url_for` returns an absolute URL. Root-relative wins on three
    counts: it survives proxies and hostname changes, it is correct in the htmx
    partials swapped into an already-loaded page, and it is ~25 bytes shorter at
    every call site, which on a table of links is real output.
    """
    url = request.url_for(name, **path_params)
    return url.path + (f"?{url.query}" if url.query else "")


def _is_active(request: Request, name: str) -> bool:
    route = request.scope.get("route")
    return getattr(route, "name", None) == name


def static_url(prefix: str, root: Path | None = None, *, auto_reload: bool = False):
    """Bind the configured prefix once, so a template only names the file.

    Not `request.url_for`: `mount_fjkit()` mounts the kit's assets at a path the
    config already knows, and going through the route table would make a missing
    mount fail deep inside a template render instead of at startup.

    **Every URL carries `?v=<mtime>`.** `StaticFiles` sends `ETag` and
    `Last-Modified` but no `Cache-Control`, so a browser may apply heuristic
    caching and keep a stylesheet it was never told the lifetime of. That
    failure is the worst kind: the page renders, the markup is current, and the
    rules for half of it are missing, so a layout degrades with nothing anywhere
    to say why. It costs a day the first time and ten minutes every time after.

    The mtime is the right key in both places this runs. While developing fjkit
    the version never changes but `fjkit build-css` rewrites the file, so a
    version stamp would pin the very asset being iterated on. In an installed
    wheel the mtime is fixed at install time and moves on upgrade, exactly the
    boundary a cache should break at.

    Stat'd once per path and remembered, except under `auto_reload` — the trade
    Jinja makes for templates, for the same reason: a `stat` per render is
    unwanted in production and unavoidable in development.

    `root` is where the files are. It is public so that a plugin mounting its
    own assets gets the same stamping rather than a second answer to the caching
    question above. Defaults to the kit's own static directory.
    """
    base = prefix.rstrip("/")
    directory = STATIC_DIR if root is None else root
    stamps: dict[str, str] = {}

    def fjkit_static(path: str) -> str:
        clean = path.lstrip("/")
        stamp = stamps.get(clean)
        if stamp is None or auto_reload:
            stamp = stamps[clean] = _stamp(clean, directory)
        return f"{base}/{clean}?v={stamp}"

    return fjkit_static


def _stamp(path: str, root: Path = STATIC_DIR) -> str:
    """Build a cache key for one asset: its mtime, or the kit's version when the
    file is gone.

    Reporting a missing file is not this function's job. `mount_fjkit` already
    refuses to start without the stylesheet, and a template naming an absent
    asset should 404 visibly rather than raise inside a render.
    """
    try:
        return str(int((root / path).stat().st_mtime))
    except OSError:
        return _versions()["fjkit"]


def _versions() -> dict[str, str]:
    from importlib.metadata import version

    from fjkit.vendored import BASECOAT_VERSION, HTMX_VERSION

    return {
        "fjkit": version("fjkit"),
        "jinja2": version("jinja2"),
        "fastapi": version("fastapi"),
        "basecoat": BASECOAT_VERSION,
        "htmx": HTMX_VERSION,
    }


class Templates:
    """Render helpers bound to one Environment.

    Two ways out, on purpose:

    * `page()` builds the whole string, then hands it to Starlette. Right for
      anything that fits in memory, which is nearly everything. It also returns
      a partial: an htmx endpoint is a `page()` call naming a `_*.html` file.
    * `stream()` yields the page in chunks. Right when the output is large or
      unbounded (exports, long report tables): peak memory becomes one buffer
      instead of the whole document, and the browser starts painting the
      `<head>` before the query at the bottom has finished.
    """

    __slots__ = ("config", "env")

    def __init__(self, env: Environment, config: FjkitConfig | None = None) -> None:
        self.env = env
        # Kept alongside the Environment, not only consumed by it: `@render`
        # reaches through `app.state.templates` for `render_mode`, and a config
        # that survived only as compiled-in Environment settings would leave it
        # with nowhere to look.
        self.config = config or FjkitConfig()

    @classmethod
    def create(cls, config: FjkitConfig | None = None) -> Templates:
        """Build the Environment and wrap it. Call once, per process.

        `mount_fjkit()` already does this; call it directly only to render
        outside an app — a build script, a benchmark.

        Compiling a template is expensive; looking one up in the Environment's
        LRU afterwards is a dict hit. Building an Environment per request pays
        the former on every render.
        """
        config = config or FjkitConfig()
        return cls(build_environment(config), config)

    def page(
        self,
        request: Request,
        name: str,
        context: Mapping[str, Any] | None = None,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HTMLResponse:
        template = self.env.get_template(name)
        html = template.render(request=request, **self._context(request, context))
        return HTMLResponse(html, status_code=status_code, headers=dict(headers or {}))

    def stream(
        self,
        request: Request,
        name: str,
        context: Mapping[str, Any] | None = None,
        *,
        buffer_size: int = 64,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> StreamingResponse:
        template = self.env.get_template(name)

        merged = self._context(request, context)

        def chunks() -> Iterator[str]:
            stream = template.stream(request=request, **merged)
            # Unbuffered, Jinja yields one string per literal or expression,
            # and every fragment costs an ASGI message plus an HTTP chunk frame.
            # Buffering batches them. The win scales with the fragment count, so
            # it is large on a page that yields thousands and small on one whose
            # body is a `{% call %}` block. See `docs/jinja-performance.md`.
            stream.enable_buffering(buffer_size)
            yield from stream

        return StreamingResponse(
            chunks(),
            status_code=status_code,
            media_type="text/html",
            headers=dict(headers or {}),
        )

    def _context(self, request: Request, context: Mapping[str, Any] | None) -> dict[str, Any]:
        """Merge the route's context over every plugin's per-request values.

        The route wins: a handler that returns `user` overrides the plugin that
        provides one, because the specific caller knows something the app-wide
        rule does not.
        """
        processors = getattr(self.env, "fjkit_context_processors", ())
        if not processors:
            # The common case, and the hot path: no copy, no merge, no loop.
            return dict(context or {})

        merged: dict[str, Any] = {}
        for plugin, provides, processor in processors:
            values = processor(request)
            if self.config.strict_undefined:
                # Same dev/prod switch as undefined names, for the same reason:
                # a key a plugin never declared stays invisible until two
                # plugins collide over it, and by then the page is wrong.
                undeclared = set(values) - set(provides)
                if undeclared:
                    raise RuntimeError(
                        f"fjkit plugin {plugin!r} returned context key(s) "
                        f"{sorted(undeclared)} it did not declare in `provides=`."
                    )
            merged.update(values)
        merged.update(context or {})
        return merged


def get_templates(request: Request) -> Templates:
    """FastAPI dependency. The Environment is built once, by `mount_fjkit()`."""
    return request.app.state.templates
