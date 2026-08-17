"""`@render` — the handler returns data, the decorator picks the wire format.

Calling `templates.page()` in the body of a handler commits the route to HTML at
the one place that should still be talking about data, and it costs every route
two parameters (`request`, `templates`) that exist only to be passed straight
back out again. Moving the template name onto a decorator leaves a handler that
reads the request, calls a service and returns a model:

    @router.get("/tasks", name="tasks_page")
    @render("tasks/page.html", partial="tasks/_board.html")
    def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
        return BoardResponse(...)

The return annotation then does double duty. FastAPI already reads it to infer
`response_model`, so it documents the JSON; `@render` spreads the same model
into the template context. One annotation, two representations, and neither is a
reshaping of the other.

The decorator goes **below** the routing decorator. `@router.get(...)` registers
whatever function it is handed, so a `@render` above it would decorate a
function nobody calls.
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, TypeVar, get_type_hints

from fastapi import Request, Response

from fjkit.config import RenderMode

__all__ = ["render"]

F = TypeVar("F", bound=Callable[..., Any])

#: Names for the parameters `@render` appends to a handler that did not ask for
#: them. Deliberately unusable as ordinary argument names: they arrive in the
#: handler's keyword arguments, and a collision with an app's own parameter
#: would be silent.
_REQUEST = "__fjkit_request"
_RESPONSE = "__fjkit_response"


@dataclasses.dataclass(frozen=True, slots=True)
class _Plan:
    """What the decorator was asked to do. Built once, read on every request."""

    template: str
    partial: str | None
    mode: RenderMode | None
    stream: bool
    buffer_size: int
    #: Whether a request that is not from htmx still has markup waiting for it.
    #: Decided once, when the decorator is applied, because it is a property of
    #: the route rather than of the request.
    serves_a_page: bool


def render(
    template: str,
    *,
    partial: str | None = None,
    mode: RenderMode | None = None,
    stream: bool = False,
    buffer_size: int = 64,
) -> Callable[[F], F]:
    """Render `template` with whatever the handler returned.

    :param template: the full page, or the only template when there is one.
    :param partial: rendered instead of `template` for an htmx swap, so the
        page route and its swap endpoint are the same handler (CHARTER A6).
    :param mode: `"html"`, `"json"` or `"auto"` for this route, overriding
        `FjkitConfig.render_mode`. Leave it `None` to follow the app default,
        which is `"auto"`: render whenever this caller has markup waiting —
        htmx gets its fragment, a navigation gets the page — and serialise the
        model when it does not. A fragment endpoint is therefore the app's API
        without a second route, while a page route keeps answering a cold
        navigation in HTML, which is the request it exists for.
    :param stream: render through `templates.stream()` rather than `page()`.
        For output the user sizes — exports, long report tables.
    :param buffer_size: chunk size when `stream=True`. Never 0; unbuffered
        streaming is 65× slower than buffered.

    The handler may return a Pydantic model, a dataclass, a mapping, `None`, or
    a `Response`. A `Response` is passed through untouched, which is the escape
    hatch for redirects and files.
    """
    plan = _Plan(
        template=template,
        partial=partial,
        mode=mode,
        stream=stream,
        buffer_size=buffer_size,
        # `partial=` is definitive: it exists precisely because `template` is
        # the page that a navigation gets. Otherwise the filename answers, on
        # the convention every template in the codebase already follows and
        # `test_conventions.py` enforces — a fragment is `_*.html`.
        serves_a_page=partial is not None or not template.rpartition("/")[2].startswith("_"),
    )

    def decorate(func: F) -> F:
        # The frame applying the decorator. Its locals are the only place a
        # response model defined inside a function — a factory, a test — can be
        # found, and under `from __future__ import annotations` the annotation
        # naming it is a string that nothing else can resolve.
        endpoint = _Endpoint(func, _caller_locals(depth=1))

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(**kwargs: Any) -> Any:
                request, response, call_kwargs = endpoint.unpack(kwargs)
                return _finish(await func(**call_kwargs), request, response, plan)

        else:
            # A sync handler keeps a sync wrapper on purpose. Starlette sends
            # only `def` endpoints to the threadpool, so wrapping one in
            # `async def` would quietly move every template render onto the
            # event loop and stall the worker's other requests.
            @wraps(func)
            def wrapper(**kwargs: Any) -> Any:
                request, response, call_kwargs = endpoint.unpack(kwargs)
                return _finish(func(**call_kwargs), request, response, plan)

        wrapper.__signature__ = endpoint.signature  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


class _Endpoint:
    """The handler's signature, resolved and amended, ready for FastAPI.

    Two things have to happen before FastAPI inspects the wrapper.

    Annotations are resolved here rather than left as strings. FastAPI
    evaluates string annotations — which is all of them under `from __future__
    import annotations` — against `endpoint.__globals__`, and a wrapper's
    globals are *fjkit's* module namespace, where the app's own names do not
    exist. Resolving against the original function's globals first is what
    keeps `ServiceDep` working.

    Then `Request` and `Response` are appended if the handler did not ask for
    them, so routes stop declaring plumbing they never use. Both are needed:
    `Request` to reach the Environment and the htmx headers, `Response` because
    a handler that sets `response.headers["HX-Trigger"]` expects it to arrive.
    """

    __slots__ = ("injected", "request_param", "response_param", "signature")

    def __init__(self, func: Callable[..., Any], localns: Mapping[str, Any] | None = None) -> None:
        hints = _hints(func, localns)
        original = inspect.signature(func)
        params = [p.replace(annotation=hints.get(p.name, p.annotation)) for p in original.parameters.values()]

        self.request_param = _param_named(params, Request)
        self.response_param = _param_named(params, Response)

        added: list[inspect.Parameter] = []
        if self.request_param is None:
            self.request_param = _REQUEST
            added.append(inspect.Parameter(_REQUEST, inspect.Parameter.KEYWORD_ONLY, annotation=Request))
        if self.response_param is None:
            self.response_param = _RESPONSE
            added.append(inspect.Parameter(_RESPONSE, inspect.Parameter.KEYWORD_ONLY, annotation=Response))
        self.injected = frozenset(p.name for p in added)

        # Keyword-only, and ahead of any **kwargs. An appended positional would
        # have to follow the handler's defaulted parameters, and `Signature`
        # rejects that outright.
        var_kw = [p for p in params if p.kind is inspect.Parameter.VAR_KEYWORD]
        fixed = [p for p in params if p.kind is not inspect.Parameter.VAR_KEYWORD]
        self.signature = original.replace(
            parameters=fixed + added + var_kw,
            return_annotation=hints.get("return", original.return_annotation),
        )

    def unpack(self, kwargs: dict[str, Any]) -> tuple[Request, Response | None, dict[str, Any]]:
        """Split FastAPI's solved arguments into ours and the handler's."""
        request = kwargs[self.request_param]
        response = kwargs.get(self.response_param)
        if self.injected:
            kwargs = {k: v for k, v in kwargs.items() if k not in self.injected}
        return request, response, kwargs


def _caller_locals(depth: int) -> Mapping[str, Any]:
    """Locals of the frame `depth` levels up, or nothing if the interpreter
    will not say. `sys._getframe` is CPython-only, and this is an improvement
    on the resolution rules rather than a requirement of them."""
    try:
        return sys._getframe(depth + 1).f_locals
    except (AttributeError, ValueError):  # pragma: no cover — non-CPython
        return {}


def _hints(func: Callable[..., Any], localns: Mapping[str, Any] | None) -> dict[str, Any]:
    try:
        return get_type_hints(func, localns=dict(localns) if localns else None, include_extras=True)
    except Exception as exc:  # noqa: BLE001 — re-raised with the part that matters
        raise TypeError(
            f"@render cannot resolve the annotations on {func.__module__}.{func.__qualname__}: {exc}. "
            "Annotations on a decorated handler are resolved against its own module and the scope it was "
            "defined in, because a wrapper's __globals__ belongs to fjkit — so a name imported inside "
            "`if TYPE_CHECKING:` will not be found here even though the type checker sees it."
        ) from exc


def _param_named(params: list[inspect.Parameter], kind: type) -> str | None:
    for param in params:
        if inspect.isclass(param.annotation) and issubclass(param.annotation, kind):
            return param.name
    return None


def _finish(result: Any, request: Request, response: Response | None, plan: _Plan) -> Any:
    # An explicit Response is the escape hatch — redirects, files, a hand-built
    # StreamingResponse. Nothing here second-guesses one.
    if isinstance(result, Response):
        return result

    requested = _mode(request, plan.mode)
    htmx = _is_htmx(request)

    # Whether the reply depends on the header, and so whether a shared cache is
    # allowed to reuse it. Two ways it can: a route with a `partial` answers one
    # URL with a page or a fragment, and a fragment route in `"auto"` answers it
    # with markup or with JSON. Miss this and a CDN serves the fragment into a
    # navigation — a page with no shell, and no error anywhere.
    if plan.partial is not None or (requested == "auto" and not plan.serves_a_page):
        _vary_on_htmx(response)

    if requested == "auto":
        # `_is_htmx`, not `_is_htmx_swap`: a boosted link is htmx doing an
        # ordinary navigation, so it is excluded from the page-or-fragment
        # decision but not from this one — it is still a browser waiting for
        # markup. The two questions read different headers.
        requested = "html" if htmx or plan.serves_a_page else "json"

    if requested == "json":
        # Handed back untouched: FastAPI validates and serialises it through
        # the route's response_model, so the return annotation stays the single
        # description of the JSON.
        return result

    templates = _templates(request)
    name = plan.partial if plan.partial and _is_htmx_swap(request) else plan.template
    context = _context(result, plan.template)
    status_code, headers = _response_args(request, response)
    if plan.stream:
        return templates.stream(
            request, name, context, buffer_size=plan.buffer_size, status_code=status_code, headers=headers
        )
    return templates.page(request, name, context, status_code=status_code, headers=headers)


def _mode(request: Request, override: RenderMode | None) -> RenderMode:
    """Decorator argument first, then the app-wide default. Two levels only.

    Two levels of *configuration*, that is. `"auto"` then resolves against the
    request, but it is still one of those two levels choosing it — the request
    never overrides a route that said `"html"` or `"json"`.

    Resolved per request rather than at import time, because the decorator runs
    while the router module is being imported — which is before the app has a
    config, and would make the answer depend on import order.
    """
    if override is not None:
        return override
    return _templates(request).config.render_mode


def _templates(request: Request):
    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        raise RuntimeError(
            "@render needs `app.state.templates`. Build it once in lifespan: "
            "`app.state.templates = Templates.create(config)`."
        )
    return templates


def _vary_on_htmx(response: Response | None) -> None:
    """Add `HX-Request` to `Vary`, keeping whatever the handler already set."""
    if response is None:  # pragma: no cover — the decorator always injects one
        return
    existing = response.headers.get("vary")
    if existing is None:
        response.headers["vary"] = "HX-Request"
    elif "hx-request" not in existing.lower():
        response.headers["vary"] = f"{existing}, HX-Request"


def _is_htmx(request: Request) -> bool:
    """True for any request htmx made, boosted navigations included.

    This is the html-or-json question. A boosted link wants HTML as much as a
    swap does, so unlike `_is_htmx_swap` it does not look at `hx-boosted`.
    """
    return request.headers.get("hx-request", "").lower() == "true"


def _is_htmx_swap(request: Request) -> bool:
    """True for an htmx request that is replacing part of the page.

    `hx-boosted` is excluded deliberately: a boosted link is htmx performing an
    ordinary navigation, and it wants the whole page. Swapping a partial into it
    would leave the browser on a document with no shell.
    """
    headers = request.headers
    return headers.get("hx-request", "").lower() == "true" and headers.get("hx-boosted", "").lower() != "true"


def _context(result: Any, template: str) -> Mapping[str, Any]:
    """Template context from whatever the handler returned.

    A model is spread field by field rather than dumped, so the template gets
    the live objects — `stats.done_pct`, `task.status.value` — while the same
    model handed to FastAPI in json mode becomes the wire form. Dumping here
    would flatten every nested model to a dict and break the templates that
    call methods on them.
    """
    if result is None:
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    # Recognised by its fields rather than by `isinstance(result, BaseModel)`,
    # so the kit does not import pydantic. FastAPI cannot exist without it, but
    # fjkit's declared runtime dependencies are two and CHARTER §7 keeps them
    # that way — an import is what turns a transitive package into a third.
    cls = type(result)
    fields = getattr(cls, "model_fields", None)
    if isinstance(fields, Mapping):
        computed = getattr(cls, "model_computed_fields", {})
        return {name: getattr(result, name) for name in (*fields, *computed)}
    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return {f.name: getattr(result, f.name) for f in dataclasses.fields(result)}
    raise TypeError(
        f"@render({template!r}) expected a pydantic model, a dataclass, a mapping, None or a Response — "
        f"got {type(result).__name__}."
    )


def _response_args(request: Request, response: Response | None) -> tuple[int, dict[str, str]]:
    """Status and headers, in precedence order: handler, route, 200.

    FastAPI merges a handler's `Response` parameter into the reply it builds —
    but only when the handler returned data. Here the reply is ours to build, so
    the merge is ours to do, or a `response.headers["HX-Trigger"] = ...` would
    silently vanish. Same for `@router.post(..., status_code=201)`, which
    FastAPI likewise only applies to replies it constructs itself.
    """
    route = request.scope.get("route")
    status_code = getattr(route, "status_code", None) or 200
    headers: dict[str, str] = {}
    if response is not None:
        if response.status_code is not None:
            status_code = response.status_code
        headers.update(response.headers)
    return status_code, headers
