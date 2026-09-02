"""Panels routes — lesson 07's fragments, moved into tabs.

`/search` fans one id out to five regions that are all on screen at once. Put
those regions in tabs and one thing changes: four of the five are `hidden`, and
`hidden` is `display:none`. A subscriber does not care — the event is raised on
`<body>` and a hidden panel hears it exactly as well as the open one — so every
broadcast fetches five fragments and shows one. That is the "N panels, N
requests" cost of the broadcast pattern, paid for markup nobody is looking at.

So this page inverts the trade. The panels do not subscribe to a broadcast in
order to fetch; they fetch when they are *shown*, and they listen only while
they are showing. `ui/tabs.html` holds the three attributes that says, and the
signature comment there explains why each is the way it is.

The one consequence that reaches this file: an `intersect` has no event, so a
panel opened after the pick has only the page to read the id off. The pick
therefore broadcasts with `hx_trigger_after_swap`, which fires once the table —
carrying the hidden input the panels' `hx-include` selects — is in the document.
`HX-Trigger` would fire before that swap, and every panel would read the
previous id.
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
    """The picked task, or `None` when nothing is picked. 404 for an id that is gone."""
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

    `task_id` is read back so that a reload with a panel open still knows what
    the page is about: the selection lives in the browser, and this is the whole
    of the server's involvement in it.
    """
    return _matches(service, _selected(service, task_id).id if task_id else None)


@router.get("/panels/select/{task_id}", name="panels_select")
@render("panels/_matches.html", hx_trigger_after_swap=SELECTED_EVENT)
def select_task(service: ServiceDep, task_id: int) -> MatchesResponse:
    """Mark the row, answer with the table, and *then* say a pick happened.

    The event carries no detail, which is the point. The id it would carry is
    already in the table this reply swaps in, and a panel that was hidden at the
    time never heard the event anyway — so every panel reads the same one place
    instead, and the two paths into a panel cannot disagree.

    `hx_trigger_after_swap`, not `hx_trigger`, for that same reason: `HX-Trigger`
    fires before this table replaces the old one, and the open panel would read
    the id it is about to stop being about.
    """
    return _matches(service, _selected(service, task_id).id)


@router.post("/panels/advance/{task_id}", name="panels_advance")
@render("panels/_matches.html", hx_trigger_after_swap=CHANGED_EVENT)
def advance_task(service: ServiceDep, task_id: int) -> MatchesResponse:
    """Advance the picked task and answer with the table, which shows its status.

    It answers with the table rather than with the detail panel because on this
    page the detail panel is not addressable: it is the body of a tab, replaced
    whole every time that tab is shown. A page built out of lazy panels has one
    in-band region, and the panels follow it.
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
    """The open task. `task_id` arrives as a query parameter, from the page."""
    return DetailResponse(selected=_selected(service, task_id))


@router.get("/panels/related", name="panels_related")
@render("panels/_related.html")
def related_panel(service: ServiceDep, task_id: int | None = None) -> RelatedResponse:
    """Everything else assigned to the open task's owner."""
    selected = _selected(service, task_id)
    related = [t for t in service.list(owner=selected.owner) if t.id != selected.id] if selected else []
    return RelatedResponse(selected=selected, related=related)


@router.get("/panels/counters", name="panels_counters")
@render("panels/_counters.html")
def counters_panel(service: ServiceDep) -> StatsResponse:
    """Counts over the whole board.

    It takes no id at all, and it is on the page to show that `include` is per
    panel: a panel that needs nothing sends nothing.
    """
    tasks = service.list()
    return StatsResponse(query="", stats=service.stats(tasks), total=service.count())
