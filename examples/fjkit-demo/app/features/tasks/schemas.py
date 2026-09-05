from __future__ import annotations

from datetime import UTC, datetime
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


class DashboardResponse(BaseModel):
    stats: BoardStats
    recent: list[Task]
    owners: list[str]


class ReportResponse(BaseModel):
    tasks: list[Task]


class Fragment(BaseModel):
    """What every fragment of the search page carries: the moment it rendered.

    The stamp is what makes the page readable. Two mechanisms move regions there:
    one reply carrying four out of band, and an event each region answers for
    itself. Without a timestamp per region there is no way to see which regions a
    click reached.
    """

    rendered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rendered_label(self) -> str:
        """`rendered_at` as HH:MM:SS.mmm — two clicks a second apart must differ."""
        return f"{self.rendered_at:%H:%M:%S}.{self.rendered_at.microsecond // 1000:03d}"


class OptionsResponse(BaseModel):
    """The combobox's listbox: option rows and nothing else.

    Not a `Fragment`. Every other partial on the search page carries a render
    stamp because the page's whole point is showing which regions an action
    reached; a listbox is inside one region and reached by its own request, so
    there is nothing to disambiguate.
    """

    #: `(value, label)` — the same shape `combobox(options=…)` takes, so the
    #: first paint and the swapped reply are built by the same macro call.
    options: list[tuple[str, str]]


class MatchesResponse(Fragment):
    """The results table: the in-band reply to both a query and a pick."""

    query: str
    matches: list[Task]
    #: Size of the whole board, for "N of M".
    total: int
    selected_id: int | None = None


class StatsResponse(Fragment):
    query: str
    #: Counts over the matches, not over the board.
    stats: BoardStats
    total: int


class FacetsResponse(Fragment):
    owners: list[Facet]
    priorities: list[Facet]


class DetailResponse(Fragment):
    """The detail panel. `None` is the cold state, not an error."""

    selected: Task | None = None


class RelatedResponse(Fragment):
    selected: Task | None = None
    related: list[Task] = Field(default_factory=list)


class SearchResponse(MatchesResponse, StatsResponse, FacetsResponse, RelatedResponse):
    """One query's answer: the matches in band, and four regions out of band.

    The fields are the union of what the five partials read, because one handler
    renders all five. That is what `hx-swap-oob` is for, and what the
    event-driven half of this page is not.
    """
