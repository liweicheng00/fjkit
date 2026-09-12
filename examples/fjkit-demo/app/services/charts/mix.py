"""The two donuts: the board split by status, and by owner."""

from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go

from app.schemas.charts import Chart, figure_of
from app.schemas.tasks import Status, Task
from app.services.charts.utils import STATUS_LABEL, sentence


def _donut(labels: list[str], values: list[float]) -> go.Figure:
    """The shape both donuts use: a hole, no legend, labels outside the slices."""
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.58,
            sort=False,
            direction="clockwise",
            textposition="outside",
            textinfo="label+value",
            automargin=True,
            hoverinfo="label+value+percent",
        )
    )
    fig.update_layout(showlegend=False)
    return fig


def status_mix(tasks: list[Task]) -> Chart:
    """Donut of tasks by status. Labels sit outside the slices."""
    counts = Counter(task.status for task in tasks)
    statuses = [status for status in Status if counts[status]]

    return Chart(
        id="chart-status",
        title="Status mix",
        description="Every task on the board, by column.",
        summary=sentence(len(tasks), [(STATUS_LABEL[s], counts[s]) for s in statuses]),
        figure=figure_of(
            _donut([STATUS_LABEL[status] for status in statuses], [float(counts[status]) for status in statuses])
        ),
    )


def owner_share(tasks: list[Task]) -> Chart:
    """Donut of tasks by owner."""
    counts = Counter(task.owner for task in tasks)
    owners = sorted(counts, key=lambda owner: (-counts[owner], owner))

    return Chart(
        id="chart-owners",
        title="Share by owner",
        description="Who is carrying the board right now.",
        summary=sentence(len(tasks), [(owner, counts[owner]) for owner in owners]),
        figure=figure_of(_donut(owners, [float(counts[owner]) for owner in owners])),
    )
