from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class Status(StrEnum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


#: Domain value -> Basecoat badge variant. The mapping lives in Python, not in
#: the template: a page never grows an if/elif chain over domain values, the
#: variant names stay greppable from one place, and the template's job stays
#: "print the variant you were handed".
STATUS_VARIANT: dict[Status, str] = {
    Status.TODO: "outline",
    Status.DOING: "info",
    Status.DONE: "success",
}

PRIORITY_VARIANT: dict[Priority, str] = {
    Priority.LOW: "outline",
    Priority.NORMAL: "secondary",
    Priority.HIGH: "destructive",
}


class Task(BaseModel):
    id: int
    title: str
    status: Status = Status.TODO
    priority: Priority = Priority.NORMAL
    owner: str = "unassigned"
    created_at: datetime
    #: The three fields the edit form adds. They are on `Task` rather than on a
    #: side model because a JSON client asking for a task should get the same
    #: task the page shows — a field that exists only for the form is a second
    #: definition of what a task is.
    notes: str = ""
    blocked: bool = False
    watching: bool = False

    # Computed rather than plain properties so the mapping above reaches both
    # representations: the template reads `task.status_variant`, and a JSON
    # client gets the same answer instead of having to re-derive it and drift.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_variant(self) -> str:
        return STATUS_VARIANT[self.status]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority_variant(self) -> str:
        return PRIORITY_VARIANT[self.priority]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    priority: Priority = Priority.NORMAL
    owner: str = Field(default="unassigned", max_length=40)


class TaskUpdate(BaseModel):
    """What the edit form is allowed to change.

    Not `Task`: `id`, `created_at` and `status` are not the form's to set —
    status moves through the board's Advance button, which is a different
    decision from editing a task. A write model that mirrors the read model is
    how a hidden field ends up changing a primary key.
    """

    title: str = Field(min_length=1, max_length=120)
    priority: Priority = Priority.NORMAL
    owner: str = Field(default="unassigned", max_length=40)
    notes: str = Field(default="", max_length=2000)
    blocked: bool = False
    watching: bool = False


class BoardStats(BaseModel):
    total: int
    todo: int
    doing: int
    done: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def done_pct(self) -> int:
        return round(self.done / self.total * 100) if self.total else 0


# --------------------------------------------------------------------------- #
# Response models
#
# What a route returns, not what the page looks like. Each one is the whole
# answer for a route: `@render` spreads its fields into the template context,
# and FastAPI infers `response_model` from the same annotation — so the OpenAPI
# schema and the template are fed by one definition and cannot describe
# different things.
#
# The filter and option lists belong here because the board's controls are part
# of the board: a client rendering this itself needs the same choices the
# template is handed. They stay `(value, label)` pairs rather than a model
# because that is the shape `ui/form.html`'s `select_field` takes, and changing
# a kit macro's signature is a separate decision from changing this style.
# --------------------------------------------------------------------------- #


class BoardResponse(BaseModel):
    tasks: list[Task]
    stats: BoardStats
    owners: list[str]
    status_filters: list[tuple[Status | None, str]]
    priority_options: list[tuple[Priority, str]]
    active_status: Status | None = None
    filter_query: str = ""


class TaskEditResponse(BaseModel):
    """One task and the choices the form offers for it.

    `owner_options` is built in the router from the owners already on the
    board, so the edit form offers the same names the filter bar does instead
    of a hand-kept list that drifts from the data.
    """

    task: Task
    priority_options: list[tuple[Priority, str]]
    owner_options: list[tuple[str, str]]


class DashboardResponse(BaseModel):
    stats: BoardStats
    recent: list[Task]
    owners: list[str]


class ReportResponse(BaseModel):
    tasks: list[Task]
