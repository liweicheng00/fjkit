"""Exception handlers `mount_fjkit` installs for every route.

    422  FastAPI refused the input
    500  anything else that escaped (only with `catch_unexpected_errors`;
         the words are `FjkitConfig.unexpected_error`)

What each caller gets:

    htmx swap        FastAPI's 422 as it is; `static/js/errors.js` draws it
                     under the fields of the form still on the page
    navigation       `errors/page.html`, rendered through the app's shell
    JSON client      FastAPI's own reply, untouched

A pydantic `ValidationError` raised inside a handler is not caught: it is the
shape of a bug, not of a rejected form. Declare the model in the signature.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import (
    request_validation_exception_handler as _fastapi_validation_reply,
)
from fastapi.exceptions import RequestValidationError

from fjkit import htmx, messages
from fjkit.forms import FieldErrors, field_errors

if TYPE_CHECKING:
    from fjkit.config import FjkitConfig

__all__ = ["ERROR_TEMPLATE", "install_error_handlers"]

#: The page a failed navigation lands on. An app replaces it by putting a file
#: at the same path in its own template directory — the same shadowing that
#: makes `fjkit eject` work, so there is no separate "custom error page"
#: mechanism to learn.
ERROR_TEMPLATE = "errors/page.html"

_log = logging.getLogger("fjkit.errors")

#: Said to the person, not to the developer. A 500 means the app is in a state
#: nobody predicted, so the honest thing to show is that something broke and
#: nothing about what. An app changes the words with
#: `FjkitConfig.unexpected_error`.
_UNEXPECTED = messages.Message(
    "Something went wrong", "The action was not completed. Nothing was saved.", category="error"
)


def install_error_handlers(app: FastAPI, config: FjkitConfig) -> None:
    """Wire both handlers. Called by `mount_fjkit`. The 500 handler is
    installed only when `catch_unexpected_errors` is on."""
    app.add_exception_handler(RequestValidationError, _on_request_validation)
    if config.catch_unexpected_errors:
        choose = config.unexpected_error

        async def on_unexpected(request: Request, exc: Exception) -> Response:
            return await _on_unexpected(request, exc, _message_for(choose, request, exc))

        app.add_exception_handler(Exception, on_unexpected)


def _message_for(choose: Any, request: Request, exc: Exception) -> messages.Message:
    """The words for this failure. A callable that itself raises is treated as
    the bug it is — logged, and the kit's own wording used — because the
    handler it runs inside is the last one there is."""
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
# 422 — a form was rejected
# --------------------------------------------------------------------------- #


async def _on_request_validation(request: Request, exc: Exception) -> Response:
    """A swap and a JSON client get FastAPI's reply unchanged; a navigation
    gets the error page."""
    if htmx.is_swap(request) or not _wants_markup(request, _plan_for(request)):
        return await _fastapi_validation_reply(request, exc)
    return _error_page(request, status_code=422, errors=field_errors(exc, request_scoped=True))


# --------------------------------------------------------------------------- #
# 500 — something else entirely
# --------------------------------------------------------------------------- #


async def _on_unexpected(request: Request, exc: Exception, message: messages.Message) -> Response:
    """Logged in full; `message` to the user."""
    _log.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)

    if not _wants_markup(request, _plan_for(request)):
        # Whatever this caller was reading, it was not a page. Starlette's own
        # answer, not ours — and not a re-raise, because raising from inside
        # `ServerErrorMiddleware`'s handler replaces the original traceback
        # with a second one from this line.
        return Response("Internal Server Error", status_code=500, media_type="text/plain")

    messages.extend(request, (message,))
    if htmx.is_swap(request):
        # No markup in this reply, so htmx must not swap the empty body into
        # the target. The toast rides the header, which htmx reads before it
        # decides about swapping at all.
        response = Response(status_code=500)
        trigger = messages.trigger_header(request, None)
        if trigger is not None:
            response.headers["HX-Trigger"] = trigger
        return response
    return _error_page(request, status_code=500, errors=None)


# --------------------------------------------------------------------------- #
# shared
# --------------------------------------------------------------------------- #


def _error_page(request: Request, *, status_code: int, errors: FieldErrors | None) -> Response:
    """`errors/page.html` through the app's own `Templates`; plain text if
    that render fails too."""
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
    """True for htmx, for a route whose `@render` serves a page, or for an
    `Accept` that names HTML (a route with no `@render` at all)."""
    if htmx.is_htmx(request):
        return True
    if plan is not None and getattr(plan, "serves_a_page", False):
        return True
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "application/xhtml+xml" in accept


def _plan_for(request: Request) -> Any:
    """The `@render` plan stamped on the route's endpoint, if any."""
    route = request.scope.get("route")
    return getattr(getattr(route, "endpoint", None), "__fjkit_plan__", None)
