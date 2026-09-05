"""Wire contracts for the charts page. Re-exports `Chart` and `figure_of` from `fjkit_charts`."""

from __future__ import annotations

from enum import StrEnum

from fjkit_charts import Chart, PlotlyFigure, figure_of
from pydantic import BaseModel

__all__ = [
    "GROUPING_OPTIONS",
    "Chart",
    "ChartsResponse",
    "Grouping",
    "PlotlyFigure",
    "figure_of",
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
    charts: list[Chart]
    grouping_options: list[tuple[Grouping, str]]
    active_grouping: Grouping
