from __future__ import annotations

from fastapi import APIRouter
from fjkit import render

from app.dependencies import TaskServiceDep
from app.schemas.dashboard import DashboardResponse
from app.services import tasks as task_service

router = APIRouter(tags=["dashboard"])


@router.get("/", name="dashboard")
@render("dashboard/page.html")
def dashboard(service: TaskServiceDep) -> DashboardResponse:
    board = service.list()
    return DashboardResponse(stats=task_service.stats(board), recent=board[:5], owners=service.owners())
