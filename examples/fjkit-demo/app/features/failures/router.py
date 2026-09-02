"""The Failures page: one route that answers 400 with a toast, one that raises."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fjkit import messages, render

router = APIRouter(tags=["failures"])


@router.get("/failures", name="failures_page")
@render("failures/page.html")
def failures_page() -> None:
    """Render the Failures page."""


@router.get("/failures/400", name="failures_bad_request")
def bad_request(request: Request) -> Response:
    """Answer 400 with an empty body and a warning toast in `HX-Trigger`."""
    messages.add(
        request,
        "That request was refused",
        "The server understood it and said no. The board is untouched.",
        category="warning",
    )
    headers = {}
    if (trigger := messages.trigger_header(request)) is not None:
        headers["HX-Trigger"] = trigger
    return Response(status_code=400, headers=headers)


@router.get("/failures/500", name="failures_crash")
def crash() -> Response:
    """Raise an unhandled exception so `fjkit.errors` answers 500."""
    raise RuntimeError("the failures page asked for this")
