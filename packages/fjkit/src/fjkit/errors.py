"""Exception handlers `mount_fjkit` installs for every route.

    404  no route matched, or a handler raised `HTTPException(404)`
    422  FastAPI refused the input
    500  anything else that escaped (only with `catch_unexpected_errors`;
         the words are `FjkitConfig.unexpected_error`)

The 404 handler is keyed by status, which Starlette consults before any
handler keyed by class, so every other `HTTPException` keeps whatever handler
the app has: FastAPI's reply, headers included (a 401's `WWW-Authenticate` is
for the client, not for a page), or the app's own. An app that registered its
own `HTTPException` handler, before or after `mount_fjkit`, gets its 404s
there too, and a 404 handler it registered before `mount_fjkit` is kept.

What each caller gets:

    htmx swap        422: FastAPI's reply as it is; `static/js/errors.js` draws
                     it under the fields of the form still on the page.
                     404 and 500: an empty body and a toast in `HX-Trigger`.
                     The page the swap came from still works, and htmx swaps
                     no 4xx or 5xx body, so the toast is the only thing the
                     person sees. FastAPI's 404 JSON would be silent.
    navigation       `errors/page.html`, rendered through the app's shell
    JSON client      FastAPI's own reply, untouched

A route whose `@render` mode resolves to `"json"` answers every caller in JSON,
so its errors do too.

A pydantic `ValidationError` raised inside a handler is not caught: it is the
shape of a bug, not of a rejected form. Declare the model in the signature.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler as _fastapi_http_reply
from fastapi.exception_handlers import (
    request_validation_exception_handler as _fastapi_validation_reply,
)
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from fjkit import htmx, messages
from fjkit.forms import FieldErrors, field_errors
from fjkit.rendering import _mode

if TYPE_CHECKING:
    from fjkit.config import FjkitConfig

__all__ = ["ERROR_TEMPLATE", "install_error_handlers"]

#: The page a failed navigation lands on. An app replaces it with a file at the
#: same path in its own template directory — the shadowing that makes `fjkit
#: eject` work, so there is no separate "custom error page" mechanism to learn.
ERROR_TEMPLATE = "errors/page.html"

_log = logging.getLogger("fjkit.errors")

#: Addressed to the user, not the developer. A 500 means the app is in a state
#: nobody predicted, so the honest thing to show is that something broke and
#: nothing about what. An app changes the words with
#: `FjkitConfig.unexpected_error`.
_UNEXPECTED = messages.Message(
    "Something went wrong", "The action was not completed. Nothing was saved.", category="error"
)

#: What a swap that found nothing says. Usually the row was deleted in another
#: tab, so the advice is to reload.
_NOT_FOUND = messages.Message(
    "That could not be found", "It may have been deleted. Reload the page to see the latest.", category="error"
)


def install_error_handlers(app: FastAPI, config: FjkitConfig) -> None:
    """Install the 404 and 422 handlers, and the 500 handler when
    `catch_unexpected_errors` is on. Called by `mount_fjkit`."""
    if 404 not in app.exception_handlers:

        async def on_not_found(request: Request, exc: Exception) -> Response:
            return await _on_not_found(request, exc, _http_handler(app, exc))

        app.add_exception_handler(404, on_not_found)
    app.add_exception_handler(RequestValidationError, _on_request_validation)
    if config.catch_unexpected_errors:
        choose = config.unexpected_error

        async def on_unexpected(request: Request, exc: Exception) -> Response:
            return await _on_unexpected(request, exc, _message_for(choose, request, exc))

        app.add_exception_handler(Exception, on_unexpected)


def _message_for(choose: Any, request: Request, exc: Exception) -> messages.Message:
    """Choose the words for this failure.

    A `choose` callable that itself raises is logged and falls back to the kit's
    own wording: the handler it runs inside is the last one there is."""
    if choose is None:
        return _UNEXPECTED
    if callable(choose):
        try:
            return choose(request, exc)
        except Exception:  # noqa: BLE001 — see docstring
            _log.exception("FjkitConfig.unexpected_error raised; using the default message")
            return _UNEXPECTED
    return choose


# --------------------------------------------------------------------------- #
# 404 — nothing at this address
# --------------------------------------------------------------------------- #


async def _on_not_found(request: Request, exc: Exception, handler: Any) -> Response:
    """Answer a 404 like the other errors here, unless the app answers its own
    or the caller is not reading a page: `handler` answers those."""
    if handler is not _fastapi_http_reply or not _wants_markup(request, _plan_for(request)):
        if inspect.iscoroutinefunction(handler):
            return await handler(request, exc)
        return await run_in_threadpool(handler, request, exc)
    if htmx.is_swap(request):
        messages.extend(request, (_NOT_FOUND,))
        return _toast_only(request, status_code=404)
    return _error_page(request, status_code=404, errors=None)


# --------------------------------------------------------------------------- #
# 422 — a form was rejected
# --------------------------------------------------------------------------- #


async def _on_request_validation(request: Request, exc: Exception) -> Response:
    """Answer a rejected input: FastAPI's reply unchanged for a swap or a JSON
    client, `ERROR_TEMPLATE` for a navigation."""
    if htmx.is_swap(request) or not _wants_markup(request, _plan_for(request)):
        return await _fastapi_validation_reply(request, exc)
    return _error_page(request, status_code=422, errors=field_errors(exc, request_scoped=True))


# --------------------------------------------------------------------------- #
# 500 — something else entirely
# --------------------------------------------------------------------------- #


async def _on_unexpected(request: Request, exc: Exception, message: messages.Message) -> Response:
    """Log the exception in full and show `message` to the user."""
    _log.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)

    if not _wants_markup(request, _plan_for(request)):
        # This caller was not reading a page, so hand back Starlette's own
        # answer. Not a re-raise: raising inside `ServerErrorMiddleware`'s
        # handler replaces the original traceback with one from this line.
        return Response("Internal Server Error", status_code=500, media_type="text/plain")

    messages.extend(request, (message,))
    if htmx.is_swap(request):
        return _toast_only(request, status_code=500)
    return _error_page(request, status_code=500, errors=None)


# --------------------------------------------------------------------------- #
# shared
# --------------------------------------------------------------------------- #


def _http_handler(app: FastAPI, exc: Exception) -> Any:
    """The handler Starlette would have chosen had there been no 404 handler:
    the nearest class in `exc`'s MRO. Read per request, so a handler the app
    registers after `mount_fjkit` counts."""
    for cls in type(exc).__mro__:
        if cls in app.exception_handlers:
            return app.exception_handlers[cls]
    return _fastapi_http_reply


def _toast_only(request: Request, *, status_code: int) -> Response:
    """An empty reply carrying the queued messages in `HX-Trigger`.

    The reply carries no markup, so htmx must not swap an empty body into the
    target. The toast rides the header instead, which htmx reads before it
    decides on swapping at all."""
    response = Response(status_code=status_code)
    trigger = messages.trigger_header(request, None)
    if trigger is not None:
        response.headers["HX-Trigger"] = trigger
    return response


def _error_page(request: Request, *, status_code: int, errors: FieldErrors | None) -> Response:
    """Render `ERROR_TEMPLATE` through the app's own `Templates`, falling back
    to plain text when that render fails too."""
    templates = getattr(request.app.state, "templates", None)
    if templates is None:  # pragma: no cover — mount_fjkit always sets it
        return Response(_UNEXPECTED.title, status_code=status_code, media_type="text/plain")
    context = {"status_code": status_code, "errors": errors}
    try:
        return templates.page(request, ERROR_TEMPLATE, context, status_code=status_code)
    except Exception:  # noqa: BLE001 — the last line of defence, deliberately broad
        _log.exception("fjkit could not render %s", ERROR_TEMPLATE)
        return Response(_UNEXPECTED.title, status_code=status_code, media_type="text/plain")


def _wants_markup(request: Request, plan: Any) -> bool:
    """False for a route whose `@render` mode resolves to `"json"`. Otherwise
    true for htmx, for a route whose `@render` serves a page, or for an
    `Accept` that names HTML (a route with no `@render` at all)."""
    if plan is not None and _mode(request, plan.mode) == "json":
        return False
    if htmx.is_htmx(request):
        return True
    if plan is not None and plan.serves_a_page:
        return True
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


def _plan_for(request: Request) -> Any:
    """The `@render` plan stamped on the route's endpoint, if any."""
    route = request.scope.get("route")
    return getattr(getattr(route, "endpoint", None), "__fjkit_plan__", None)
