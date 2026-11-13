"""The page's two figure lists, each in page order.

`build` is the board: seven views that answer a question about the tasks, and
the only ones the grouping control swaps. `gallery` is the rest of the trace
types `fjkit_charts` admits, drawn once each so the demo exercises all twelve
rather than the four the board happened to need. Separate lists because they
have separate lifetimes — only `build` is behind the htmx endpoint.
"""

from __future__ import annotations

from app.schemas.charts import Chart, Grouping
from app.schemas.records import Record
from app.schemas.tasks import Task
from app.services.charts.age import age_spread
from app.services.charts.density import size_against_age, size_against_age_contour, stage_over_time
from app.services.charts.mix import owner_share, status_mix
from app.services.charts.oldest import oldest_open
from app.services.charts.raster import board_raster
from app.services.charts.shapes import age_histogram, age_shape, owner_mix, owner_status_grid
from app.services.charts.trend import created_trend, intake
from app.services.charts.workload import workload


def build(tasks: list[Task], grouping: Grouping) -> list[Chart]:
    """Build every chart the grouping control swaps, in page order."""
    return [
        status_mix(tasks),
        workload(tasks, grouping),
        created_trend(tasks),
        owner_share(tasks),
        intake(tasks),
        oldest_open(tasks),
        age_spread(tasks),
    ]


def gallery(tasks: list[Task], records: list[Record]) -> list[Chart]:
    """One figure per trace type the board's seven do not already cover.

    `board_raster` is last and is the only one carrying colour; its own module
    says why it is here at all.
    """
    return [
        age_shape(tasks),
        age_histogram(tasks),
        owner_status_grid(tasks),
        owner_mix(tasks),
        size_against_age(records),
        size_against_age_contour(records),
        stage_over_time(records),
        board_raster(tasks),
    ]
