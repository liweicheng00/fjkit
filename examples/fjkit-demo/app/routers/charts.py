"""The charts page route."""

from __future__ import annotations

from fastapi import APIRouter
from fjkit import render

from app.dependencies import TaskServiceDep
from app.schemas.charts import GROUPING_OPTIONS, ChartsResponse, Grouping
from app.services import charts

router = APIRouter(tags=["charts"])


@router.get("/charts", name="charts_page")
@render("charts/page.html", partial="charts/_charts.html")
def charts_page(service: TaskServiceDep, group: Grouping = Grouping.OWNER) -> ChartsResponse:
    """Render the charts page, or just the chart cards for an htmx request."""
    return ChartsResponse(
        charts=charts.build(service.list(), group),
        grouping_options=GROUPING_OPTIONS,
        active_grouping=group,
    )
