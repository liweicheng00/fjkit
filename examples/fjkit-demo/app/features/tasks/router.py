"""HTTP surface for the task board.

Routers do three things and nothing else: read the request, call the service,
name a template. The template name lives on `@render`, so the body of a handler
only ever builds and returns its response model — and that model's annotation is
what FastAPI turns into `response_model`, so one declaration describes both the
page and the JSON.

Every mutating endpoint answers with the *same* board partial the full page
embeds, so there is only ever one definition of what a board looks like.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fjkit import render

from app.features.tasks.schemas import (
    BoardResponse,
    Priority,
    ReportResponse,
    Status,
    TaskCreate,
    TaskEditResponse,
    TaskUpdate,
)
from app.features.tasks.service import TaskService

router = APIRouter(tags=["tasks"])


def get_service(request: Request) -> TaskService:
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


#: Option lists are built here, not in the template. Templates that reshape
#: data grow map/select/zip filter chains that are slower than the equivalent
#: Python and much harder to read; the rule is that a template prints what it
#: is handed. These are module constants because they never change.
STATUS_FILTERS: list[tuple[Status | None, str]] = [(None, "All")] + [(s, s.value.capitalize()) for s in Status]
PRIORITY_OPTIONS: list[tuple[Priority, str]] = [(p, p.value.capitalize()) for p in Priority]


def _board(service: TaskService, status: Status | None = None, owner: str | None = None) -> BoardResponse:
    # The mutating endpoints have to preserve the active filter, so every row
    # action carries it as a query string. Built here rather than concatenated
    # in the template: urlencode gets the "?" and the "&" right, and an empty
    # filter produces an empty string instead of a bare "?".
    active = {k: v for k, v in (("status", status), ("owner", owner)) if v}
    return BoardResponse(
        tasks=service.list(status=status, owner=owner),
        stats=service.stats(),
        owners=service.owners(),
        status_filters=STATUS_FILTERS,
        priority_options=PRIORITY_OPTIONS,
        active_status=status,
        filter_query=f"?{urlencode(active)}" if active else "",
    )


@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(
    service: ServiceDep,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    """The full page — and, for an htmx swap, just the board inside it."""
    return _board(service, status, owner)


@router.get("/tasks/board", name="tasks_board")
@render("tasks/_board.html")
def tasks_board(
    service: ServiceDep,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    """The htmx target, addressable on its own.

    Same handler body as the page above, and `@render` there would already
    serve the partial to an htmx request. This route stays because the board is
    a resource with its own URL: `hx-get` names it explicitly rather than
    relying on a header to change what `/tasks` means.
    """
    return _board(service, status, owner)


@router.post("/tasks", name="tasks_create")
@render("tasks/_board.html")
def create_task(
    service: ServiceDep,
    title: Annotated[str, Form()],
    priority: Annotated[Priority, Form()] = Priority.NORMAL,
    owner: Annotated[str, Form()] = "unassigned",
) -> BoardResponse:
    service.create(TaskCreate(title=title, priority=priority, owner=owner))
    return _board(service)


@router.post("/tasks/{task_id}/advance", name="tasks_advance")
@render("tasks/_board.html")
def advance_task(
    service: ServiceDep,
    task_id: int,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    if service.advance(task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return _board(service, status, owner)


@router.delete("/tasks/{task_id}", name="tasks_delete")
@render("tasks/_board.html")
def delete_task(
    service: ServiceDep,
    task_id: int,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    if not service.delete(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return _board(service, status, owner)


@router.get("/tasks/{task_id}/edit", name="tasks_edit")
@render("tasks/edit.html")
def edit_task(service: ServiceDep, task_id: int) -> TaskEditResponse:
    """The edit form, on a page of its own.

    Deliberately not an htmx swap. Everything else on this board is one, so
    without this route the demo would only ever show half of what `ui/form.html`
    does — `form()` with no `target=` emits an ordinary POST, and the fields do
    not know the difference. This page needs no JavaScript at all.
    """
    task = service.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    owners = service.owners()
    if task.owner not in owners:
        owners.append(task.owner)
    return TaskEditResponse(
        task=task,
        priority_options=PRIORITY_OPTIONS,
        owner_options=[(o, o.capitalize()) for o in owners],
    )


@router.post("/tasks/{task_id}/edit", name="tasks_update")
def update_task(
    request: Request,
    service: ServiceDep,
    task_id: int,
    title: Annotated[str, Form()],
    priority: Annotated[Priority, Form()] = Priority.NORMAL,
    owner: Annotated[str, Form()] = "unassigned",
    notes: Annotated[str, Form()] = "",
    # An unticked box posts nothing at all, so "absent" is what off looks like
    # on the wire. A default of False is the whole of reading a checkbox — no
    # hidden companion field, because this form posts every field it owns.
    blocked: Annotated[bool, Form()] = False,
    watching: Annotated[bool, Form()] = False,
) -> RedirectResponse:
    """Save, then redirect. No `@render` here — the answer is a Location, not
    markup, and 303 is what stops a refresh from re-posting the form."""
    payload = TaskUpdate(title=title, priority=priority, owner=owner, notes=notes, blocked=blocked, watching=watching)
    if service.update(task_id, payload) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return RedirectResponse(url=str(request.url_for("tasks_page")), status_code=303)


@router.get("/tasks/report", name="tasks_report")
@render("tasks/report.html", stream=True)
def tasks_report(service: ServiceDep, rows: int = 5000) -> ReportResponse:
    """A deliberately oversized page, rendered as a stream.

    Buffering the same table into one string costs peak memory proportional to
    the whole document; streaming it costs one chunk. `stream=True` is the only
    difference from any other route here — streaming is a property of how the
    template is rendered, not of the template or of the model.
    """
    tasks = service.list()
    repeated = [tasks[i % len(tasks)] for i in range(max(rows, 1))]
    return ReportResponse(tasks=repeated)
