"""The two time series over the same window: what was created, and what is still open."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import plotly.graph_objects as go

from app.schemas.charts import Chart, figure_of
from app.schemas.tasks import Status, Task
from app.services.charts.utils import TREND_DAYS, integer_axis


def _window(days: int, now: datetime | None) -> list:
    """The last `days` dates ending today, oldest first."""
    today = (now or datetime.now(UTC)).date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


def _line(name: str, window: list, values: list[float]) -> go.Scatter:
    """One spline with markers. Both charts draw the same kind of line."""
    return go.Scatter(
        name=name,
        x=[day.isoformat() for day in window],
        y=values,
        mode="lines+markers",
        line={"width": 2, "shape": "spline", "smoothing": 0.4},
        marker={"size": 6},
    )


def created_trend(tasks: list[Task], days: int = TREND_DAYS, now: datetime | None = None) -> Chart:
    """Line of tasks created per day over the last `days` days."""
    window = _window(days, now)
    counts = Counter(task.created_at.date() for task in tasks)
    values = [float(counts[day]) for day in window]
    created = int(sum(values))

    fig = go.Figure(_line("Created", window, values))
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title_text="Tasks")
    integer_axis(fig, values)

    return Chart(
        id="chart-trend",
        title="Created per day",
        description=f"The last {days} days. A demo seeds its board in one sitting, so expect a spike.",
        summary=(
            f"{created} of {len(tasks)} tasks were created in the last {days} days, "
            f"peaking at {int(max(values, default=0))} in a day."
        ),
        figure=figure_of(fig),
    )


def intake(tasks: list[Task], days: int = TREND_DAYS, now: datetime | None = None) -> Chart:
    """Two lines over one window: tasks created per day, and how many remain open."""
    window = _window(days, now)
    created = Counter(task.created_at.date() for task in tasks)
    open_now = Counter(task.created_at.date() for task in tasks if task.status is not Status.DONE)

    lines = [
        ("Created", [float(created[day]) for day in window]),
        ("Still open", [float(open_now[day]) for day in window]),
    ]
    fig = go.Figure([_line(name, window, values) for name, values in lines])
    fig.update_layout(showlegend=True)
    fig.update_yaxes(title_text="Tasks")
    integer_axis(fig, [value for _, values in lines for value in values])

    still_open = int(sum(open_now[day] for day in window))
    return Chart(
        id="chart-intake",
        title="Intake vs backlog",
        description="Everything created in the window, and how much of it is still open.",
        summary=(
            f"{int(sum(created[day] for day in window))} tasks created in the last {days} days, "
            f"{still_open} of them still open."
        ),
        figure=figure_of(fig),
    )
