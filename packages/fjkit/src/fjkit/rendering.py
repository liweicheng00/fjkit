"""`@render` — the handler returns data, the decorator picks the wire format.

    @router.get("/tasks", name="tasks_page")
    @render("tasks/page.html", partial="tasks/_board.html")
    def tasks_page(service: ServiceDep, status: Status | None = None) -> BoardResponse:
        return BoardResponse(...)

The return annotation is both FastAPI's `response_model` and the template
context. `@render` goes below the routing decorator.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import sys
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, TypeVar, get_type_hints

from fastapi import Request, Response

from fjkit import htmx, messages
from fjkit.config import RenderMode
from fjkit.forms import NO_ERRORS

__all__ = ["SCOPE_RENDER_MODE", "Trigger", "TriggerValue", "render"]

F = TypeVar("F", bound=Callable[..., Any])

#: ASGI scope key: the representation an in-process caller wants back, as one of
#: `RenderMode`. Read by `_mode`, between the decorator's own argument and the
#: app-wide default.
#:
#: A scope key rather than a header, because of who can set each. A header
#: travels from outside and would let any client turn every page in the app
#: into JSON; only code already running in this process can write a scope key,
#: which is the guarantee that makes honouring it safe.
SCOPE_RENDER_MODE = "fjkit_render_mode"

#: Names for the parameters `@render` appends to a handler that did not ask for
#: them. Deliberately unusable as ordinary argument names: they arrive in the
#: handler's keyword arguments, and a collision with an app's own parameter
#: would be silent.
_REQUEST = "__fjkit_request"
_RESPONSE = "__fjkit_response"


#: What a route broadcasts alongside its markup: a mapping of event name to
#: detail, a bare event name, or `None` for "not this time".
TriggerValue = Mapping[str, Any] | str | None

#: `hx_trigger`, as written on the decorator. A callable is resolved per request
#: — see `_TriggerSpec` for what it is handed.
Trigger = TriggerValue | Callable[..., TriggerValue]


@dataclasses.dataclass(frozen=True, slots=True)
class _TriggerSpec:
    """A `hx_trigger` callable, and the names it asked for.

    The names are read once, when the decorator is applied: a signature does not
    change between requests, and `inspect` is not cheap.

    A callable takes its arguments by name from the handler's own resolved
    parameters plus `result`, what the handler returned. So the event is written
    where the route is declared while still reading a path parameter the route
    only has at request time:

        @render(None, hx_trigger=lambda task_id: {"task-selected": {"id": task_id}})
        def select_task(service: ServiceDep, task_id: int) -> None: ...

    Declaring `**kwargs` asks for all of them.
    """

    call: Callable[..., TriggerValue]
    #: The parameter names, or `None` for a callable that declared `**kwargs`.
    wants: frozenset[str] | None

    @classmethod
    def of(cls, trigger: Trigger) -> _TriggerSpec | None:
        if not callable(trigger):
            return None
        params = inspect.signature(trigger).parameters.values()
        if any(p.kind is p.VAR_KEYWORD for p in params):
            return cls(trigger, None)
        return cls(trigger, frozenset(p.name for p in params))

    def resolve(self, result: Any, call_kwargs: Mapping[str, Any]) -> TriggerValue:
        available = {**call_kwargs, "result": result}
        if self.wants is None:
            return self.call(**available)
        return self.call(**{name: available[name] for name in self.wants if name in available})


@dataclasses.dataclass(frozen=True, slots=True)
class _Plan:
    """What the decorator was asked to do. Built once, read on every request."""

    template: str | None
    partial: str | None
    mode: RenderMode | None
    stream: bool
    buffer_size: int
    #: What to put in `HX-Trigger`. A literal value, or a spec resolved per
    #: request. See `render`.
    hx_trigger: TriggerValue
    trigger_spec: _TriggerSpec | None
    #: The same, for `HX-Trigger-After-Swap`. A separate field rather than a
    #: header name on the first, because a route may raise both and they are
    #: not interchangeable: the two differ in what a listener may read.
    hx_trigger_after_swap: TriggerValue
    trigger_after_swap_spec: _TriggerSpec | None
    #: Whether a request that is not from htmx still has markup waiting for it.
    #: Decided once, when the decorator is applied, because it is a property of
    #: the route rather than of the request.
    serves_a_page: bool


def render(
    template: str | None,
    *,
    partial: str | None = None,
    mode: RenderMode | None = None,
    stream: bool = False,
    buffer_size: int = 64,
    hx_trigger: Trigger = None,
    hx_trigger_after_swap: Trigger = None,
) -> Callable[[F], F]:
    """Render `template` with whatever the handler returned.

    :param template: the full page, or the only template when there is one.
    `None` for a route that answers with no body at all — the status code and
    the headers still apply, so it is how a route broadcasts and renders
    nothing.
    :param partial: rendered instead of `template` for an htmx swap.
    :param mode: `"html"`, `"json"` or `"auto"` for this route, overriding
    `FjkitConfig.render_mode`. `"auto"` renders for htmx and for a page
    route's navigation, and serialises the model otherwise.
    :param stream: render through `templates.stream()` rather than `page()`.
    :param buffer_size: chunk size when `stream=True`. Never 0.
    :param hx_trigger: an event to raise in the browser on this response, as
    `HX-Trigger`. Usually a callable, which receives the handler's own
    parameters and `result` **by name**:

        @render("selection/_list.html",
                hx_trigger=lambda task_id: {"task-selected": {"task_id": task_id}})

    so one route answers with its own partial and tells the rest of the page
    what happened — swap and broadcast declared in one place, on a route that is
    otherwise an ordinary partial route.

    A `str` names an event with no detail. `None` — as the argument, or returned
    by the callable — raises nothing, which is how a route broadcasts only
    sometimes. Merged with any `HX-Trigger` the handler set on its `Response`
    and with a queued toast, so none of the three silently drops another.

    Sent on the HTML representation only, exactly like a toast. `HX-Trigger` is
    htmx's protocol, and a caller that asked this route for JSON has no htmx in
    it to read the header — see `mode`.

    Send an **object** as the detail. htmx passes an object through as
    `event.detail` and wraps anything else — an array included — as
    `{value: ...}`, so a listener reading `event.detail.task_id` finds nothing.

    :param hx_trigger_after_swap: the same event, in `HX-Trigger-After-Swap`.
    It takes every form `hx_trigger` does and differs only in **when** htmx
    raises it, which decides what a subscriber may read.

    `HX-Trigger` fires **before** this response is swapped in. A subscriber that
    reads `event.detail` is unaffected; one that reads the page is not, because
    the markup it reads is what this reply is about to replace. A route that
    answers with the table and raises `task-selected` in `HX-Trigger` therefore
    cannot be heard by a fragment whose `hx-include` points at a value that
    table carries: it would read the previous id.

    `HX-Trigger-After-Swap` fires once the swap is in the document, which lets
    the event carry no detail at all and every subscriber pick up what it needs
    off the page with `hx-include`. A lazy tab panel needs that shape, because a
    panel hidden when the pick happened never saw the event and has only the
    page to read — see `ui/tabs.html`.

    Both may be set on one route; they are separate headers and neither
    merges into the other. Reach for `hx_trigger` when the listeners read
    `event.detail`, and for this when they read the DOM.

    The handler may return a Pydantic model, a dataclass, a mapping, `None`, or
    a `Response`; a `Response` is passed through untouched.
    """
    plan = _Plan(
        template=template,
        partial=partial,
        mode=mode,
        stream=stream,
        buffer_size=buffer_size,
        hx_trigger=None if callable(hx_trigger) else hx_trigger,
        trigger_spec=_TriggerSpec.of(hx_trigger),
        hx_trigger_after_swap=None if callable(hx_trigger_after_swap) else hx_trigger_after_swap,
        trigger_after_swap_spec=_TriggerSpec.of(hx_trigger_after_swap),
        # `partial=` is definitive: it exists because `template` is the page a
        # navigation gets. Otherwise the filename answers, on the convention
        # every template in the codebase already follows and
        # `test_conventions.py` enforces — a fragment is `_*.html`.
        serves_a_page=template is not None
        and (partial is not None or not template.rpartition("/")[2].startswith("_")),
    )

    def decorate(func: F) -> F:
        # The frame applying the decorator. Its locals are the only place to
        # find a response model defined inside a function — a factory, a test —
        # and under `from __future__ import annotations` the annotation naming
        # it is a string nothing else can resolve.
        endpoint = _Endpoint(func, _caller_locals(depth=1))

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def wrapper(**kwargs: Any) -> Any:
                request, response, call_kwargs = endpoint.unpack(kwargs)
                return _finish(await func(**call_kwargs), request, response, plan, call_kwargs)

        else:
            # A sync handler keeps a sync wrapper on purpose. Starlette sends
            # only `def` endpoints to the threadpool, so wrapping one in
            # `async def` would move every template render onto the event loop
            # and stall the worker's other requests.
            @wraps(func)
            def wrapper(**kwargs: Any) -> Any:
                request, response, call_kwargs = endpoint.unpack(kwargs)
                return _finish(func(**call_kwargs), request, response, plan, call_kwargs)

        wrapper.__signature__ = endpoint.signature  # type: ignore[attr-defined]
        # Stamped on the function FastAPI registers, so `fjkit.errors` finds it
        # from `request.scope["route"].endpoint` with nothing to keep in step:
        # the route table already knows which function serves the request, and
        # this rides on that instead of a second registry beside it.
        wrapper.__fjkit_plan__ = plan  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


class _Endpoint:
    """The handler's signature, resolved and amended, ready for FastAPI.

    String annotations resolve against the original function's globals, because
    a wrapper's globals are fjkit's. `Request` and `Response` are appended when
    the handler did not declare them.
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
        # `get_type_hints` resolves `-> None` to `NoneType`, and FastAPI reads
        # the return annotation to infer `response_model`. `None` is falsy and
        # means "no model"; the class is not, so a handler annotated `-> None`
        # would acquire a response model it never had — and on a 204 route
        # FastAPI refuses outright, because no body is allowed there. Hand back
        # what the source said.
        returns = hints.get("return", original.return_annotation)
        self.signature = original.replace(
            parameters=fixed + added + var_kw,
            return_annotation=None if returns is type(None) else returns,
        )

    def unpack(self, kwargs: dict[str, Any]) -> tuple[Request, Response | None, dict[str, Any]]:
        """Split FastAPI's solved arguments into ours and the handler's."""
        request = kwargs[self.request_param]
        response = kwargs.get(self.response_param)
        if self.injected:
            kwargs = {k: v for k, v in kwargs.items() if k not in self.injected}
        return request, response, kwargs


def _caller_locals(depth: int) -> Mapping[str, Any]:
    """Locals of the frame `depth` levels up, or nothing when the interpreter
    will not say. `sys._getframe` is CPython-only, so this improves the
    resolution rules rather than being required by them."""
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


def _finish(
    result: Any,
    request: Request,
    response: Response | None,
    plan: _Plan,
    call_kwargs: Mapping[str, Any],
) -> Any:
    # An explicit `Response` is the escape hatch — redirects, files, a
    # hand-built `StreamingResponse`. Nothing here second-guesses one.
    if isinstance(result, Response):
        return result

    # A route with no template answers with headers alone. Nothing below applies
    # to it: there is no representation to negotiate, so no `Vary`, and no shell
    # that could carry a toast instead of the header.
    if plan.template is None:
        status_code, headers = _response_args(request, response)
        _deliver_trigger(plan, result, call_kwargs, headers)
        _deliver_messages(request, headers, renders_shell=False)
        return Response(status_code=status_code, headers=headers)

    requested = _mode(request, plan.mode)
    from_htmx = htmx.is_htmx(request)

    # Whether the reply depends on the header, and so whether a shared cache may
    # reuse it. Two ways it can: a route with a `partial` answers one URL with a
    # page or a fragment, and a fragment route in `"auto"` answers it with
    # markup or with JSON. Miss this and a CDN serves the fragment into a
    # navigation — a page with no shell, and no error anywhere.
    if plan.partial is not None or (requested == "auto" and not plan.serves_a_page):
        _vary_on_htmx(response)

    if requested == "auto":
        # `is_htmx`, not `is_swap`: a boosted link is htmx doing an ordinary
        # navigation, so it is excluded from the page-or-fragment decision but
        # not from this one — it is still a browser waiting for markup. The two
        # questions read different headers.
        requested = "html" if from_htmx or plan.serves_a_page else "json"

    if requested == "json":
        # Handed back untouched: FastAPI validates and serialises it through the
        # route's `response_model`, so the return annotation stays the one
        # description of the JSON.
        return result

    templates = _templates(request)
    name = plan.partial if plan.partial and htmx.is_swap(request) else plan.template
    context = _context(result, plan.template)
    # Every render can ask `errors.<name>`, including the ones with nothing to
    # report, so a template passing `error=errors.title` never has to guard the
    # key — see `fjkit.forms.NO_ERRORS`.
    context.setdefault("errors", NO_ERRORS)
    status_code, headers = _response_args(request, response)
    _deliver_trigger(plan, result, call_kwargs, headers)
    _deliver_messages(request, headers, renders_shell=name == plan.template and plan.serves_a_page)
    if plan.stream:
        return templates.stream(
            request, name, context, buffer_size=plan.buffer_size, status_code=status_code, headers=headers
        )
    return templates.page(request, name, context, status_code=status_code, headers=headers)


def _deliver_trigger(plan: _Plan, result: Any, call_kwargs: Mapping[str, Any], headers: dict[str, str]) -> None:
    """Write the route's own events into their headers, merging with what is
    already there.

    Runs before `_deliver_messages`, so a toast queued on the same response is
    added to `HX-Trigger` rather than replacing it: the merge lives in one
    place, `messages.trigger_header`.

    The two headers are written independently and never merge into each other.
    They are different moments, so an event in one is not the same event in the
    other, and folding them together would change when a subscriber hears it.
    """
    _write_trigger(headers, "HX-Trigger", plan.hx_trigger, plan.trigger_spec, result, call_kwargs)
    _write_trigger(
        headers,
        "HX-Trigger-After-Swap",
        plan.hx_trigger_after_swap,
        plan.trigger_after_swap_spec,
        result,
        call_kwargs,
    )


def _write_trigger(
    headers: dict[str, str],
    name: str,
    literal: TriggerValue,
    spec: _TriggerSpec | None,
    result: Any,
    call_kwargs: Mapping[str, Any],
) -> None:
    """Write one event into one header. `None` — literal or resolved — writes
    nothing."""
    value = spec.resolve(result, call_kwargs) if spec is not None else literal
    if value is None:
        return
    # Case-insensitively, because `_response_args` copies out of a Starlette
    # `MutableHeaders`, which lowercases every name it was given.
    existing = next((key for key in headers if key.lower() == name.lower()), None)
    headers[existing or name] = _merge_trigger(headers.get(existing) if existing else None, value)


def _merge_trigger(existing: str | None, value: Mapping[str, Any] | str) -> str:
    """Add `value` to whatever the handler's own `Response` already carried.

    A bare name stays a bare name when nothing else is in play: htmx accepts
    `HX-Trigger: task-selected`, and a route with one detail-free event should
    not pay for JSON to say so.
    """
    if existing is None and isinstance(value, str):
        return value
    events = _as_events(existing)
    events.update({value: None} if isinstance(value, str) else value)
    return json.dumps(events, separators=(",", ":"))


def _as_events(header: str | None) -> dict[str, Any]:
    """Read an `HX-Trigger` value as the mapping htmx reads it as.

    The same promotion `messages.trigger_header` does, for the same reason: htmx
    accepts a bare event name or a comma-separated list as well as JSON, and
    neither may be discarded because something else wants to be in the header
    too.
    """
    if not header:
        return {}
    text = header.strip()
    if text.startswith("{"):
        try:
            return dict(json.loads(text))
        except ValueError:
            return {text: None}
    return {name.strip(): None for name in text.split(",") if name.strip()}


def _deliver_messages(request: Request, headers: dict[str, str], *, renders_shell: bool) -> None:
    """Pick the channel a queued message goes out on. See `fjkit.messages`.

    A render of the shell carries the toaster, so the message goes in the
    document; anything else sends it as `HX-Trigger`. Never both.
    """
    if renders_shell:
        return
    # Case-insensitively, because `_response_args` copies out of a Starlette
    # `MutableHeaders`, which lowercases every name it was given. A handler
    # writes `HX-Trigger`; what arrives here is `hx-trigger`.
    existing = next((key for key in headers if key.lower() == "hx-trigger"), None)
    trigger = messages.trigger_header(request, headers.get(existing) if existing else None)
    if trigger is not None:
        headers[existing or "HX-Trigger"] = trigger


def _mode(request: Request, override: RenderMode | None) -> RenderMode:
    """Pick the mode: decorator argument, then `SCOPE_RENDER_MODE`, then the app
    default.

    Only in-process code can set the scope key (`fjkit_apidocs.console` does).
    Resolved per request, because the decorator runs before the app has a
    config.
    """
    if override is not None:
        return override
    asked = request.scope.get(SCOPE_RENDER_MODE)
    if asked is not None:
        return asked
    return _templates(request).config.render_mode


def _templates(request: Request):
    templates = getattr(request.app.state, "templates", None)
    if templates is None:
        raise RuntimeError(
            "@render needs `app.state.templates`. Wire it once, at app "
            "construction: `mount_fjkit(app, config)`."
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


def _context(result: Any, template: str) -> dict[str, Any]:
    """Build the template context from whatever the handler returned. A model is
    spread field by field, not dumped, so the template gets the live objects.
    """
    if result is None:
        return {}
    if isinstance(result, Mapping):
        return dict(result)
    # Recognised by its fields rather than by `isinstance(result, BaseModel)`,
    # so the kit does not import pydantic. FastAPI cannot exist without it, but
    # fjkit declares two runtime dependencies and CHARTER §7 keeps it at two —
    # an import is what turns a transitive package into a third.
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
    """Resolve status and headers in precedence order: the handler's
    `Response`, the route's `status_code`, 200. FastAPI merges these only into
    replies it builds itself.
    """
    route = request.scope.get("route")
    status_code = getattr(route, "status_code", None) or 200
    headers: dict[str, str] = {}
    if response is not None:
        if response.status_code is not None:
            status_code = response.status_code
        headers.update(response.headers)
    return status_code, headers
