"""The charts page route."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fjkit import render

from app.features.charts import service as charts
from app.features.charts.schemas import GROUPING_OPTIONS, ChartsResponse, Grouping
from app.features.tasks.service import TaskService

router = APIRouter(tags=["charts"])


def get_service(request: Request) -> TaskService:
    """Dependency: the app's `TaskService`."""
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


@router.get("/charts", name="charts_page")
@render("charts/page.html", partial="charts/_charts.html")
def charts_page(service: ServiceDep, group: Grouping = Grouping.OWNER) -> ChartsResponse:
    """Render the charts page, or just the chart cards for an htmx request."""
    return ChartsResponse(
        charts=charts.build(service.list(), group),
        grouping_options=GROUPING_OPTIONS,
        active_grouping=group,
    )
