"""Panels routes — lesson 07's fragments, moved into tabs.

`/search` fans one id out to five regions that are all on screen. In tabs, four
of the five are `hidden`, which is `display:none`, and a subscriber does not
care: the event is raised on `<body>`, so a hidden panel hears it as well as the
open one. Every broadcast then fetches five fragments and shows one — the
"N panels, N requests" cost of the broadcast pattern, paid for markup nobody is
looking at.

This page inverts that trade. A panel fetches when it is shown, and listens for
a broadcast only while it is showing. `ui/tabs.html` holds the three attributes
that say so, and its signature comment explains each one.

One consequence reaches this file: an `intersect` carries no event, so a panel
opened after the pick reads the id off the page. The pick therefore broadcasts
with `hx_trigger_after_swap`, which fires once the table — carrying the hidden
input the panels' `hx-include` selects — is in the document. `HX-Trigger` fires
before that swap, so every panel would read the previous id.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fjkit import render

from app.features.search.schemas import CHANGED_EVENT, SELECTED_EVENT
from app.features.tasks.schemas import (
    DetailResponse,
    MatchesResponse,
    RelatedResponse,
    StatsResponse,
    Task,
)
from app.features.tasks.service import TaskService

router = APIRouter(tags=["panels"])


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


def _matches(service: TaskService, task_id: int | None) -> MatchesResponse:
    return MatchesResponse(query="", matches=service.list(), total=service.count(), selected_id=task_id)


# --------------------------------------------------------------------------- #
# the page, and the two actions that move the table
# --------------------------------------------------------------------------- #


@router.get("/panels", name="panels_page")
@render("panels/page.html", partial="panels/_matches.html")
def panels_page(service: ServiceDep, task_id: int | None = None) -> MatchesResponse:
    """Render the page, or just the table for an htmx request.

    `task_id` is read back so a reload with a panel open still knows what the
    page is about. The selection lives in the browser; this is the server's only
    involvement in it.
    """
    return _matches(service, _selected(service, task_id).id if task_id else None)


@router.get("/panels/select/{task_id}", name="panels_select")
@render("panels/_matches.html", hx_trigger_after_swap=SELECTED_EVENT)
def select_task(service: ServiceDep, task_id: int) -> MatchesResponse:
    """Mark the row, answer with the table, then announce the pick.

    The event carries no detail. The id it would carry is already in the table
    this reply swaps in, and a panel that was hidden at the time never heard the
    event anyway. So every panel reads that one place instead, and the two paths
    into a panel cannot disagree.

    `hx_trigger_after_swap`, not `hx_trigger`, for the same reason: `HX-Trigger`
    fires before this table replaces the old one, so the open panel would read
    the id it is about to stop being about.
    """
    return _matches(service, _selected(service, task_id).id)


@router.post("/panels/advance/{task_id}", name="panels_advance")
@render("panels/_matches.html", hx_trigger_after_swap=CHANGED_EVENT)
def advance_task(service: ServiceDep, task_id: int) -> MatchesResponse:
    """Advance the picked task and answer with the table, which shows its status.

    The reply is the table rather than the detail panel because the detail panel
    is not addressable here: it is a tab body, replaced whole every time that tab
    is shown. A page built out of lazy panels has one in-band region, and the
    panels follow it.
    """
    if service.advance(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _matches(service, task_id)


# --------------------------------------------------------------------------- #
# the panel bodies — one route each, and none of them knows it is in a tab
# --------------------------------------------------------------------------- #


@router.get("/panels/detail", name="panels_detail")
@render("panels/_detail.html")
def detail_panel(service: ServiceDep, task_id: int | None = None) -> DetailResponse:
    """Render the open task. `task_id` arrives from the page as a query parameter."""
    return DetailResponse(selected=_selected(service, task_id))


@router.get("/panels/related", name="panels_related")
@render("panels/_related.html")
def related_panel(service: ServiceDep, task_id: int | None = None) -> RelatedResponse:
    """Render everything else assigned to the open task's owner."""
    selected = _selected(service, task_id)
    related = [t for t in service.list(owner=selected.owner) if t.id != selected.id] if selected else []
    return RelatedResponse(selected=selected, related=related)


@router.get("/panels/counters", name="panels_counters")
@render("panels/_counters.html")
def counters_panel(service: ServiceDep) -> StatsResponse:
    """Count the whole board.

    It takes no id. It is on the page to show that `include` is per panel: a
    panel that needs nothing sends nothing.
    """
    tasks = service.list()
    return StatsResponse(query="", stats=service.stats(tasks), total=service.count())
