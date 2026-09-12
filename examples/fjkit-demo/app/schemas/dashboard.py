"""Wire contract for the dashboard: the board summarised, and nothing to act on."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.tasks import BoardStats, Task


class DashboardResponse(BaseModel):
    stats: BoardStats
    recent: list[Task]
    owners: list[str]
