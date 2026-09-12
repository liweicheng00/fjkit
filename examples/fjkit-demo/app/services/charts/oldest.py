"""The horizontal bar of what has been waiting longest."""

from __future__ import annotations

from datetime import UTC, datetime

import plotly.graph_objects as go

from app.schemas.charts import Chart, figure_of
from app.schemas.tasks import Status, Task
from app.services.charts.utils import clip


def oldest_open(tasks: list[Task], limit: int = 5, now: datetime | None = None) -> Chart:
    """Horizontal bar of the `limit` oldest open tasks, by age in hours."""
    moment = now or datetime.now(UTC)
    open_tasks = [task for task in tasks if task.status is not Status.DONE]
    ranked = sorted(open_tasks, key=lambda task: task.created_at)[:limit]
    # Plotly draws the first entry at the bottom; reversed so the oldest is on top.
    ranked.reverse()

    ages = [round((moment - task.created_at).total_seconds() / 3600, 1) for task in ranked]
    labels = [clip(task.title) for task in ranked]

    fig = go.Figure(go.Bar(x=ages, y=labels, orientation="h", hovertemplate="%{x} h<extra></extra>"))
    fig.update_layout(showlegend=False, bargap=0.35)
    fig.update_xaxes(title_text="Hours open")

    return Chart(
        id="chart-oldest",
        title="Oldest open tasks",
        description="Age in hours. Horizontal, because the labels are sentences.",
        summary=(
            f"{len(open_tasks)} tasks still open; the oldest has been waiting {max(ages, default=0)} hours."
            if open_tasks
            else "Nothing is open."
        ),
        height=240,
        figure=figure_of(fig),
    )
