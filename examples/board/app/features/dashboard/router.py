from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fjkit import render

from app.features.tasks.schemas import DashboardResponse
from app.features.tasks.service import TaskService

router = APIRouter(tags=["dashboard"])


def get_service(request: Request) -> TaskService:
    return request.app.state.tasks


ServiceDep = Annotated[TaskService, Depends(get_service)]


@router.get("/", name="dashboard")
@render("dashboard/page.html")
def dashboard(service: ServiceDep) -> DashboardResponse:
    tasks = service.list()
    return DashboardResponse(stats=service.stats(), recent=tasks[:5], owners=service.owners())
