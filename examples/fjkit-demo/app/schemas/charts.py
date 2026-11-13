"""Wire contracts for the charts page. Re-exports `Chart` and `PlotlyFigure` from `fjkit_charts`."""

from __future__ import annotations

from enum import StrEnum

from fjkit_charts import Chart, PlotlyFigure
from pydantic import BaseModel

__all__ = [
    "GROUPING_OPTIONS",
    "Chart",
    "ChartsResponse",
    "Grouping",
    "PlotlyFigure",
]


class Grouping(StrEnum):
    """What the workload chart puts on its x axis."""

    OWNER = "owner"
    PRIORITY = "priority"


GROUPING_OPTIONS: list[tuple[Grouping, str]] = [
    (Grouping.OWNER, "By owner"),
    (Grouping.PRIORITY, "By priority"),
]


class ChartsResponse(BaseModel):
    #: The board's figures — the group the grouping control swaps.
    charts: list[Chart]
    #: One figure per remaining trace type, outside the swap target because
    #: nothing on the page changes them.
    gallery: list[Chart]
    grouping_options: list[tuple[Grouping, str]]
    active_grouping: Grouping
