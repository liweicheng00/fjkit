"""The single Jinja entry point.

Everything about *how* templates are compiled and rendered lives here — routers
never touch `Environment`. One place to tune, one place to profile.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import (
    ChainableUndefined,
    ChoiceLoader,
    Environment,
    FileSystemBytecodeCache,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from fjkit.config import TEMPLATE_DIR, FjkitConfig
from fjkit.icons import path as _icon_path
from fjkit.styles import resolve_style

__all__ = ["Templates", "build_environment", "get_templates"]


def build_environment(config: FjkitConfig | None = None) -> Environment:
    """Compile-time settings for every template the app renders."""
    config = config or FjkitConfig()

    # App templates first, kit templates second. A file at the same path in the
    # app wins — that is how `fjkit eject` works, and why shadowing is a
    # supported feature rather than a fork.
    searchpath: list[FileSystemLoader] = []
    if config.template_dir is not None:
        searchpath.append(FileSystemLoader(config.template_dir, encoding="utf-8"))
    searchpath.append(FileSystemLoader(TEMPLATE_DIR, encoding="utf-8"))

    bytecode_cache = None
    if config.bytecode_cache_dir is not None:
        config.bytecode_cache_dir.mkdir(parents=True, exist_ok=True)
        bytecode_cache = FileSystemBytecodeCache(str(config.bytecode_cache_dir), "%s.j2c")

    env = Environment(
        loader=ChoiceLoader(searchpath),
        # Only .html/.jinja are escaped; a template that renders JSON or CSV
        # opts out by extension instead of by sprinkling |safe.
        autoescape=select_autoescape(("html", "jinja")),
        auto_reload=config.auto_reload,
        bytecode_cache=bytecode_cache,
        cache_size=config.cache_size,
        # Drops the newline after a block tag and the indentation before it.
        # Templates stay indented for humans; the bytes on the wire don't pay
        # for it. Typically 10-20% off a nested page.
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined if config.strict_undefined else ChainableUndefined,
        # Async rendering exists for awaiting inside templates. We deliberately
        # do not: templates receive finished data, so sync rendering avoids the
        # coroutine wrapper on every block.
        enable_async=False,
    )

    # Resolved once per Environment. Anything a template needs on every page
    # belongs here rather than in every route's context dict.
    env.globals["url_for"] = _url_for
    env.globals["is_active"] = _is_active
    env.globals["fjkit_static"] = _static_url(config.static_url)
    env.globals["fjkit_icon_path"] = _icon_path
    env.globals["fjkit_version"] = _versions()
    # The shell builds its stylesheet URL from this. Exposed as the pack
    # *name* rather than a finished URL so a custom shell can also report or
    # switch on which pack is live.
    env.globals["fjkit_style"] = resolve_style(config.style)
    env.globals.update(config.globals)
    return env


def _url_for(request: Request, name: str, /, **path_params: Any) -> str:
    """Root-relative URL for a named route.

    Starlette's `url_for` returns an absolute URL. Root-relative is better on
    three counts: it survives proxies and hostname changes, it is correct in
    the htmx partials swapped into an already-loaded page, and it is ~25 bytes
    shorter at every call site — which on a table of links is real output.
    """
    url = request.url_for(name, **path_params)
    return url.path + (f"?{url.query}" if url.query else "")


def _is_active(request: Request, name: str) -> bool:
    route = request.scope.get("route")
    return getattr(route, "name", None) == name


def _static_url(prefix: str):
    """Bind the configured prefix once, so templates just name the file.

    Not `request.url_for` on purpose: the kit's assets are mounted by
    `mount_fjkit()` at a path the config already knows, and going through the
    route table would make a missing mount fail deep inside a template render
    instead of at startup.
    """
    base = prefix.rstrip("/")

    def fjkit_static(path: str) -> str:
        return f"{base}/{path.lstrip('/')}"

    return fjkit_static


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

    Two ways out on purpose:

    * `page()` builds the whole string, then hands it to Starlette. Right for
      anything that fits comfortably in memory — which is nearly everything.
      It is also what returns a *partial*: an htmx endpoint is just a page()
      call naming a `_*.html` file.
    * `stream()` yields the page in chunks. Right when the output is large or
      unbounded (exports, long report tables): peak memory becomes one buffer
      instead of the whole document, and the browser starts painting the
      <head> before the query at the bottom has finished.
    """

    __slots__ = ("config", "env")

    def __init__(self, env: Environment, config: FjkitConfig | None = None) -> None:
        self.env = env
        # Kept alongside the Environment, not just consumed by it: `@render`
        # reaches through `app.state.templates` for `render_mode`, and a config
        # that only survived as compiled-in Environment settings would leave it
        # with nowhere to look.
        self.config = config or FjkitConfig()

    @classmethod
    def create(cls, config: FjkitConfig | None = None) -> Templates:
        """Build the Environment and wrap it. Call once, per process.

        `mount_fjkit()` already does this; reach for it directly only to render
        outside an app — a build script, a benchmark.

        Compiling a template is expensive; looking one up in the Environment's
        LRU afterwards is a dict hit. Anything that builds an Environment per
        request pays the former on every render.
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
        html = template.render(request=request, **(context or {}))
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

        def chunks() -> Iterator[str]:
            stream = template.stream(request=request, **(context or {}))
            # Un-buffered, Jinja yields one string per literal/expression —
            # thousands of tiny writes, each one an ASGI message. Buffering
            # batches them, which is where nearly all of the win is.
            stream.enable_buffering(buffer_size)
            yield from stream

        return StreamingResponse(
            chunks(),
            status_code=status_code,
            media_type="text/html",
            headers=dict(headers or {}),
        )


def get_templates(request: Request) -> Templates:
    """FastAPI dependency. The Environment is built once, by `mount_fjkit()`."""
    return request.app.state.templates
