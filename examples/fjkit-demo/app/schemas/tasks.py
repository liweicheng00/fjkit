"""Wire contracts for the task board, and the maps that turn a domain value into a badge.

The fragment envelopes the search and panels pages answer with live in
`schemas/fragments.py`. Those are those pages' contracts, not the board's, and a
task's shape is not the place four other pages should have to meet.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field, field_validator


class Status(StrEnum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Label(StrEnum):
    """Labels a task can carry."""

    BUG = "bug"
    DOCS = "docs"
    INFRA = "infra"
    PERF = "perf"
    UI = "ui"


#: Domain value -> badge variant. Labels have no variant; they render as "secondary".
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

#: Option lists for the board's controls. Here rather than in the router for the
#: reason the variant maps are: how a domain value is spelled to a person is part
#: of the contract, and two pages offering different words for one status is drift.
STATUS_FILTERS: list[tuple[Status | None, str]] = [(None, "All")] + [(s, s.value.capitalize()) for s in Status]

PRIORITY_OPTIONS: list[tuple[Priority, str]] = [(p, p.value.capitalize()) for p in Priority]

LABEL_OPTIONS: list[tuple[Label, str]] = [
    (label, label.value.upper() if len(label.value) <= 2 else label.value.capitalize()) for label in Label
]


class Task(BaseModel):
    id: int
    title: str
    status: Status = Status.TODO
    priority: Priority = Priority.NORMAL
    owner: str = "unassigned"
    created_at: datetime
    notes: str = ""
    blocked: bool = False
    watching: bool = False
    labels: list[Label] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status_variant(self) -> str:
        return STATUS_VARIANT[self.status]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority_variant(self) -> str:
        return PRIORITY_VARIANT[self.priority]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def created_label(self) -> str:
        """`created_at` as YYYY-MM-DD."""
        return self.created_at.strftime("%Y-%m-%d")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    priority: Priority = Priority.NORMAL
    owner: str = Field(default="unassigned", max_length=40)


class TaskUpdate(BaseModel):
    """Fields the edit form can change. Status changes only through Advance."""

    title: str = Field(min_length=1, max_length=120)
    priority: Priority = Priority.NORMAL
    owner: str = Field(default="unassigned", max_length=40)
    notes: str = Field(default="", max_length=2000)
    blocked: bool = False
    watching: bool = False
    labels: list[Label] = Field(default_factory=list)

    @field_validator("labels", mode="before")
    @classmethod
    def _one_is_still_a_list(cls, value: object) -> object:
        """Wrap a single string in a list; json-enc posts one selected label as a bare string."""
        return [value] if isinstance(value, str) else value


class BoardStats(BaseModel):
    total: int
    todo: int
    doing: int
    done: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def done_pct(self) -> int:
        return round(self.done / self.total * 100) if self.total else 0


class Facet(BaseModel):
    """One bucket of a result set: display label, count and badge variant."""

    label: str
    count: int
    variant: str = "outline"


# Response models. `@render` spreads each one's fields into the template context.


class BoardResponse(BaseModel):
    tasks: list[Task]
    stats: BoardStats
    owners: list[str]
    status_filters: list[tuple[Status | None, str]]
    priority_options: list[tuple[Priority, str]]
    active_status: Status | None = None
    filter_query: str = ""


class TaskEditResponse(BaseModel):
    """Context for the edit form."""

    task: Task
    priority_options: list[tuple[Priority, str]]
    owner_options: list[tuple[str, str]]
    label_options: list[tuple[Label, str]]


class ReportResponse(BaseModel):
    tasks: list[Task]
