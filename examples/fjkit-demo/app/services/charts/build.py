"""The page's figure list, in page order."""

from __future__ import annotations

from app.schemas.charts import Chart, Grouping
from app.schemas.tasks import Task
from app.services.charts.mix import owner_share, status_mix
from app.services.charts.oldest import oldest_open
from app.services.charts.trend import created_trend, intake
from app.services.charts.workload import workload


def build(tasks: list[Task], grouping: Grouping) -> list[Chart]:
    """Build every chart the page shows, in page order."""
    return [
        status_mix(tasks),
        workload(tasks, grouping),
        created_trend(tasks),
        owner_share(tasks),
        intake(tasks),
        oldest_open(tasks),
    ]
