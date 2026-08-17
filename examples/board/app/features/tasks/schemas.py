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


class DashboardResponse(BaseModel):
    stats: BoardStats
    recent: list[Task]
    owners: list[str]


class ReportResponse(BaseModel):
    tasks: list[Task]
