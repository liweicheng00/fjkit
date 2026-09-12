"""What a fragment of the search and panels pages carries, and the events they trade.

Both pages answer one id with several regions, so both answer with the same five
shapes. They live here rather than under either page because neither owns them,
and neither should have to import the other to get at them.

The two event names are here for the same reason: they are the wire between a
route's `hx_trigger` and a fragment's `hx-trigger`, and both pages are on it.
They are separate events because their audiences are. Picking a row concerns the
panels that describe one task; changing its status concerns anything that counts.
A fragment subscribes to whichever it has a reason to hear — the facets hear
neither, because advancing a task changes no owner and no priority.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.tasks import BoardStats, Facet, Task

#: Raised by `search_select` and `panels_select`, heard by the detail and
#: siblings panels.
SELECTED_EVENT = "task-selected"

#: Raised when a task advances, heard by everything that counts or shows a status.
CHANGED_EVENT = "task-changed"

#: The key both details carry the id under, and the query parameter every
#: fragment endpoint reads. `hx-vals` turns one into the other.
SELECTED_KEY = "task_id"


class Fragment(BaseModel):
    """What every fragment carries: the moment it rendered.

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
