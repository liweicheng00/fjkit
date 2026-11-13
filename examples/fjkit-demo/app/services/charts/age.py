"""The box plot: how long work has been sitting, by priority.

The only chart here that shows a distribution rather than a total. The other six
answer "how much"; this one answers "how spread out", which a bar of means
cannot — two priorities with the same average age look identical on a bar and
nothing like each other here.

Needs `box`, which is why `fjkit-charts` carries Plotly's cartesian bundle
rather than its basic one.
"""

from __future__ import annotations

from datetime import UTC, datetime

import plotly.graph_objects as go

from app.schemas.charts import Chart
from app.schemas.tasks import Priority, Task

#: Highest first, so the box the reader cares about is on the left.
_ORDER = [Priority.HIGH, Priority.NORMAL, Priority.LOW]


def age_spread(tasks: list[Task], now: datetime | None = None) -> Chart:
    """One box per priority, over the age in hours of every task at it."""
    moment = now or datetime.now(UTC)
    ages: dict[Priority, list[float]] = {
        priority: [
            round((moment - task.created_at).total_seconds() / 3600, 1)
            for task in tasks
            if task.priority is priority
        ]
        for priority in _ORDER
    }
    present = [priority for priority in _ORDER if ages[priority]]

    fig = go.Figure(
        [
            go.Box(
                name=priority.value,
                y=ages[priority],
                # Every point drawn beside the box, jittered off the centre line.
                # At eight tasks the quartiles are a summary of three numbers, and
                # hiding the three would overstate what the box knows.
                boxpoints="all",
                jitter=0.4,
                pointpos=-1.6,
                hovertemplate="%{y} h<extra></extra>",
            )
            for priority in present
        ]
    )
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title_text="Hours open")

    spans = [(priority.value, round(max(ages[priority]) - min(ages[priority]), 1)) for priority in present]
    widest = max(spans, key=lambda span: span[1], default=("none", 0.0))

    return Chart(
        id="chart-age",
        title="Age spread by priority",
        description="The box is the middle half; the whiskers are the rest. Every task is a point beside it.",
        summary=(
            f"{len(tasks)} tasks across {len(present)} priorities; "
            f"{widest[0]} is the widest spread at {widest[1]} hours."
            if present
            else "Nothing on the board yet."
        ),
        figure=fig,
    )
