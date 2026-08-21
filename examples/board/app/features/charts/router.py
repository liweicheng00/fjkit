"""HTTP surface for the charts page.

One route, two entrances: a navigation gets the page, an htmx swap gets the
cards. `render_mode="auto"` resolves that from the request, so a page route
like this one never answers in JSON — what the return annotation buys here is
the published schema. `ChartsResponse` is what OpenAPI documents, and because
`PlotlyTrace` types the fields this app reads rather than falling back to
`dict[str, Any]`, that schema says something a client can act on instead of
shrugging (CHARTER A9).

The grouping control is a `<select>` with `hx-get`, so switching it costs one
request that returns the three cards and nothing else. The 1.1 MB of Plotly
that drew them is already in memory; a full navigation would re-parse it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fjkit import render

from app.features.charts import service as charts
from app.features.charts.schemas import GROUPING_OPTIONS, ChartsResponse, Grouping
from app.features.tasks.service import TaskService

router = APIRouter(tags=["charts"])


def get_service(request: Request) -> TaskService:
    """The board's service, not one of its own.

    Charts are a second reading of the same data, so a `ChartService` holding
    its own copy would be a second source of truth for how many tasks are
    `done`. What this feature owns is the bucketing, and that lives in
    `service.py` as functions over a list of tasks.
    """
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


@router.get("/charts", name="charts_page")
@render("charts/page.html", partial="charts/_charts.html")
def charts_page(service: ServiceDep, group: Grouping = Grouping.OWNER) -> ChartsResponse:
    """The full page — and, for an htmx swap, just the three cards inside it."""
    return ChartsResponse(
        charts=charts.build(service.list(), group),
        grouping_options=GROUPING_OPTIONS,
        active_grouping=group,
    )
