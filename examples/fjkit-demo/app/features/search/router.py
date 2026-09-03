"""Search routes — the page where both htmx mechanisms are in use at once.

One reply, many regions: a query is one question the server answers completely,
so `search_page` renders five fragments and four of them travel `hx-swap-oob`.

One id, many fragments: a pick has a different shape. The click produces an id,
and the panels that care each need a different query. So `search_select` answers
with its own region and broadcasts, and the panels fetch themselves.

Both halves obey one rule: **the fragment a route answers with must not
subscribe to the event that route raises.** It is already being replaced in band;
hearing the event as well fetches it a second time for the same click, and a
fragment that is its own target never stops. So the matches table is the reply to
`search_select` and hears only `task-changed`, and the detail panel is the reply
to `search_advance` and hears only `task-selected`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fjkit import render

from app.features.search.schemas import CHANGED_EVENT, SELECTED_EVENT, SELECTED_KEY
from app.features.tasks.schemas import (
    DetailResponse,
    FacetsResponse,
    MatchesResponse,
    RelatedResponse,
    SearchResponse,
    StatsResponse,
    Task,
)
from app.features.tasks.service import TaskService

router = APIRouter(tags=["search"])


def get_service(request: Request) -> TaskService:
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


def _selected(service: TaskService, task_id: int | None) -> Task | None:
    """Return the picked task, or `None` when nothing is picked. 404 for a gone id."""
    if task_id is None:
        return None
    task = service.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


def _matches(service: TaskService, q: str, task_id: int | None) -> MatchesResponse:
    return MatchesResponse(
        query=q,
        matches=service.search(q),
        total=service.count(),
        selected_id=task_id,
    )


def _siblings(service: TaskService, selected: Task | None) -> list[Task]:
    """Return everything else assigned to the picked task's owner."""
    if selected is None:
        return []
    return [t for t in service.list(owner=selected.owner) if t.id != selected.id]


# --------------------------------------------------------------------------- #
# one reply, many regions
# --------------------------------------------------------------------------- #


@router.get("/search", name="search_page")
@render("search/page.html", partial="search/_results.html")
def search_page(service: ServiceDep, q: str = "") -> SearchResponse:
    """Render the search page, or the five result fragments for an htmx request.

    Every region on this page depends on the query, so one handler answers for
    all of them and `_results.html` addresses four of the five. That is the case
    `hx-swap-oob` exists for: one question the server can answer completely.

    A new query clears the selection. `selected` is unset, so the detail and
    siblings panels come back empty with the rest.
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


# --------------------------------------------------------------------------- #
# one id, many fragments
# --------------------------------------------------------------------------- #


@router.get("/search/select/{task_id}", name="search_select")
@render("search/_matches.html", hx_trigger=lambda task_id: {SELECTED_EVENT: {SELECTED_KEY: task_id}})
def select_task(service: ServiceDep, task_id: int, q: str = "") -> MatchesResponse:
    """Mark the picked row, answer with the table, and tell the panels which id.

    One round trip does both halves. The table is this button's `hx-target`, so
    the reply swaps it in band — that is how the row gets its badge — and the
    header is what the detail and siblings panels hear.

    A GET, because picking changes nothing on the server: this handler stores no
    selection, and two people picking at once do not contend. The id lands in the
    browser, the only place it is state.

    The event is declared on the decorator, and `@render` resolves `task_id` from
    this handler's own parameters. The detail must be an object: htmx passes an
    object through as `event.detail` and wraps anything else — an array included
    — as `{value: …}`, so a subscriber reading `event.detail.task_id` would find
    nothing.
    """
    return _matches(service, q, _selected(service, task_id).id)


@router.post("/search/advance/{task_id}", name="search_advance")
@render("search/_detail.html", hx_trigger=lambda task_id: {CHANGED_EVENT: {SELECTED_KEY: task_id}})
def advance_task(service: ServiceDep, task_id: int) -> DetailResponse:
    """Advance the picked task, answer with the detail panel, and say what changed.

    Raises `task-changed`, and the panel it answers with hears only
    `task-selected`. Never the same name in both places.
    """
    if service.advance(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return DetailResponse(selected=service.get(task_id))


# --------------------------------------------------------------------------- #
# the fragments, each answering for itself
# --------------------------------------------------------------------------- #


@router.get("/search/matches", name="search_matches")
@render("search/_matches.html")
def matches_fragment(service: ServiceDep, q: str = "", task_id: int | None = None) -> MatchesResponse:
    """Re-render the table. Takes the query as well, because a row shows a status."""
    return _matches(service, q, task_id)


@router.get("/search/stats", name="search_stats")
@render("search/_stats.html")
def stats_fragment(service: ServiceDep, q: str = "") -> StatsResponse:
    """Re-render the counters over the current matches."""
    return StatsResponse(query=q, stats=service.stats(service.search(q)), total=service.count())


@router.get("/search/progress", name="search_progress")
@render("search/_progress.html")
def progress_fragment(service: ServiceDep, q: str = "") -> StatsResponse:
    """Re-render the progress card over the current matches."""
    return StatsResponse(query=q, stats=service.stats(service.search(q)), total=service.count())


@router.get("/search/facets", name="search_facets")
@render("search/_facets.html")
def facets_fragment(service: ServiceDep, q: str = "") -> FacetsResponse:
    """Re-render the facets.

    Nothing subscribes to this. It has a URL because it is a real fragment, and
    it stays still because advancing a task changes neither an owner nor a
    priority — the clearest sign on the page that subscription is each fragment's
    own decision.
    """
    matches = service.search(q)
    return FacetsResponse(owners=service.owner_facets(matches), priorities=service.priority_facets(matches))


@router.get("/search/detail", name="search_detail")
@render("search/_detail.html")
def detail_fragment(service: ServiceDep, task_id: int | None = None) -> DetailResponse:
    """Re-render the detail panel for the picked task."""
    return DetailResponse(selected=_selected(service, task_id))


@router.get("/search/related", name="search_related")
@render("search/_related.html")
def related_fragment(service: ServiceDep, task_id: int | None = None) -> RelatedResponse:
    """Re-render the panel of the picked task's siblings — same owner, other rows."""
    selected = _selected(service, task_id)
    return RelatedResponse(selected=selected, related=_siblings(service, selected))
