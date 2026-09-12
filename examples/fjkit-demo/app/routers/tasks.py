"""Task board routes. Every mutation returns the board partial."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fjkit import render

from app.dependencies import TaskServiceDep
from app.schemas.tasks import (
    LABEL_OPTIONS,
    PRIORITY_OPTIONS,
    STATUS_FILTERS,
    BoardResponse,
    ReportResponse,
    Status,
    TaskCreate,
    TaskEditResponse,
    TaskUpdate,
)
from app.services import tasks as task_service
from app.services.tasks import TaskService

router = APIRouter(tags=["tasks"])


def _board(service: TaskService, status: Status | None = None, owner: str | None = None) -> BoardResponse:
    # Query string the row actions carry, so a mutation keeps the active filter.
    active = {k: v for k, v in (("status", status), ("owner", owner)) if v}
    return BoardResponse(
        tasks=service.list(status=status, owner=owner),
        # The whole board, not the filtered rows: the counters describe what is
        # on the board, and a filter is a view of it rather than a smaller one.
        stats=task_service.stats(service.list()),
        owners=service.owners(),
        status_filters=STATUS_FILTERS,
        priority_options=PRIORITY_OPTIONS,
        active_status=status,
        filter_query=f"?{urlencode(active)}" if active else "",
    )


@router.get("/tasks", name="tasks_page")
@render("tasks/page.html", partial="tasks/_board.html")
def tasks_page(
    service: TaskServiceDep,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    """Render the tasks page, or just the board for an htmx request."""
    return _board(service, status, owner)


@router.get("/tasks/board", name="tasks_board")
@render("tasks/_board.html")
def tasks_board(
    service: TaskServiceDep,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    """Render the board partial."""
    return _board(service, status, owner)


@router.post("/tasks", name="tasks_create")
@render("tasks/_board.html")
def create_task(service: TaskServiceDep, payload: TaskCreate) -> BoardResponse:
    """Create a task from the JSON body and return the board."""
    service.create(payload)
    return _board(service)


@router.post("/tasks/{task_id}/advance", name="tasks_advance")
@render("tasks/_board.html")
def advance_task(
    service: TaskServiceDep,
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
    service: TaskServiceDep,
    task_id: int,
    status: Status | None = None,
    owner: str | None = None,
) -> BoardResponse:
    if not service.delete(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return _board(service, status, owner)


def _edit_view(service: TaskService, task_id: int) -> TaskEditResponse:
    """Build the edit form's context for one task."""
    task = service.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskEditResponse(
        task=task,
        priority_options=PRIORITY_OPTIONS,
        owner_options=[(o, o.capitalize()) for o in task_service.owners_including(service.owners(), task.owner)],
        label_options=LABEL_OPTIONS,
    )


@router.get("/tasks/{task_id}/edit", name="tasks_edit")
@render("tasks/edit.html", partial="tasks/_edit_form.html")
def edit_task(service: TaskServiceDep, task_id: int) -> TaskEditResponse:
    """Render the edit page, or just the form for an htmx request."""
    return _edit_view(service, task_id)


@router.put("/tasks/{task_id}", name="tasks_update")
def update_task(
    request: Request,
    service: TaskServiceDep,
    task_id: int,
    payload: TaskUpdate,
) -> Response:
    """Update a task from the JSON body, then answer 204 with `HX-Redirect` to the board."""
    if service.update(task_id, payload) is None:
        raise HTTPException(status_code=404, detail="task not found")
    return Response(status_code=204, headers={"HX-Redirect": str(request.url_for("tasks_page"))})


@router.get("/tasks/report", name="tasks_report")
@render("tasks/report.html", stream=True)
def tasks_report(service: TaskServiceDep, rows: int = 5000) -> ReportResponse:
    """Render a report of `rows` rows as a stream."""
    return ReportResponse(tasks=task_service.repeat(service.list(), rows))
