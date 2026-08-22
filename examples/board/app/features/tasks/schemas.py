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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def created_label(self) -> str:
        """The date as the page prints it. Here rather than in Jinja for the
        same reason the variants are: a template that formats a datetime is a
        template deciding what a date means, and the JSON client would have to
        decide it a second time.

        Date only. The panel sets it beside two other values in a
        `metric_group`, which is sized for one short line, and a time nobody
        reads is not worth the second line it wraps onto."""
        return self.created_at.strftime("%Y-%m-%d")


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


class Facet(BaseModel):
    """One bucket of a result set: a value, how many rows carry it, and the
    badge variant that value already wears everywhere else in the app.

    The variant comes from the same `PRIORITY_VARIANT` map a task row reads, so
    a high-priority facet and a high-priority row cannot end up different
    colours. `label` is already the display string because the counting and the
    labelling are one operation — splitting them would leave the template
    deciding how to spell a domain value, which is exactly what the maps above
    exist to prevent.
    """

    label: str
    count: int
    variant: str = "outline"


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


class SearchResponse(BaseModel):
    """One query, four views of its answer.

    Every field here is derived from the same match list, and the page renders
    each of them in a region of its own. That is what makes the out-of-band
    reply honest rather than clever: the four fragments are not four requests
    stitched together, they are one answer shown four ways.
    """

    query: str
    matches: list[Task]
    #: The size of the whole board, so the page can say "N of M" without a
    #: second call. Not `len(matches)` — the template can count that itself.
    total: int
    stats: BoardStats
    owners: list[Facet]
    priorities: list[Facet]
    #: Always `None` from this route, and that is the point: a new query resets
    #: the detail panel out-of-band, because whatever was open may not be in
    #: the new result set. `_detail.html` reads this field either way, so one
    #: template serves both the empty panel and the chosen task.
    selected: Task | None = None


class SearchDetailResponse(BaseModel):
    """One match, opened. The field is named `selected` rather than `task` so
    that `_detail.html` — which the search reply also renders, with nothing
    selected — reads exactly one name."""

    selected: Task
