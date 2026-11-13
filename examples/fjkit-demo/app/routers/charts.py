"""The charts page route."""

from __future__ import annotations

from fastapi import APIRouter
from fjkit import render

from app.dependencies import RecordServiceDep, TaskServiceDep
from app.schemas.charts import GROUPING_OPTIONS, ChartsResponse, Grouping
from app.services import charts

router = APIRouter(tags=["charts"])


@router.get("/charts", name="charts_page")
@render("charts/page.html", partial="charts/_charts.html")
def charts_page(tasks: TaskServiceDep, records: RecordServiceDep, group: Grouping = Grouping.OWNER) -> ChartsResponse:
    """Render the charts page, or just the board's chart cards for an htmx request.

    Two stores, because the page has two groups of figures: the board's seven
    come from the tasks, and three of the gallery's eight need a second numeric
    dimension the board does not have. The partial is the board group only, so
    the gallery is built and discarded on a swap — eight figures over data
    already in memory, against the alternative of a second endpoint and a second
    target for a group that never changes.
    """
    return ChartsResponse(
        charts=charts.build(tasks.list(), group),
        gallery=charts.gallery(tasks.list(), records.all()),
        grouping_options=GROUPING_OPTIONS,
        active_grouping=group,
    )
