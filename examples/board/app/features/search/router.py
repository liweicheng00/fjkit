"""One request, four regions.

Every other swap in this demo replaces a single element: the board's filter bar
and its row actions all point at `#board`, and `_board.html` is one partial
wrapping everything that could change. That works because the board *is* one
thing.

A search result is not. It updates a row of counters, a table, a progress card
and a facet list — four fragments in three different places on the page, and
the only element that contains all four is `<body>`. Swapping the body is a
page reload with extra steps.

So the reply carries the other three as **out-of-band** fragments. htmx swaps
the response body into `hx-target` as usual, then, before it does, lifts out
every top-level element marked `hx-swap-oob` and swaps each into the element
with the same id. One round trip, four regions, and each region still has
exactly one definition — `page.html` and `_results.html` include the same four
partials, and differ only in whether they hand them `oob`.

This router looks like any other. Nothing about the out-of-band reply reaches
Python: the handler returns one model describing one answer, and *where* the
fragments land is a property of the markup.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fjkit import render

from app.features.tasks.schemas import SearchResponse
from app.features.tasks.service import TaskService

router = APIRouter(tags=["search"])


def get_service(request: Request) -> TaskService:
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


@router.get("/search", name="search_page")
@render("search/page.html", partial="search/_results.html")
def search_page(service: ServiceDep, q: str = "") -> SearchResponse:
    """The page, and — for an htmx request — the four fragments on their own.

    One route rather than a page route plus a swap route, because here they
    really are the same resource: `/search?q=cache` is a URL worth bookmarking,
    and the input carries `hx-push-url` so it becomes one. `partial=` is what
    lets the same address answer a navigation with the page and a keystroke
    with the fragments.
    """
    matches = service.search(q)
    return SearchResponse(
        query=q,
        matches=matches,
        total=service.count(),
        stats=service.stats(matches),
        owners=service.owner_facets(matches),
        priorities=service.priority_facets(matches),
    )
