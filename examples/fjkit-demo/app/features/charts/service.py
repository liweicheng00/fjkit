"""Build the charts page's figures from the task list. This module sets no colour."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import plotly.graph_objects as go

from app.features.charts.schemas import Chart, Grouping, figure_of
from app.features.tasks.schemas import Priority, Status, Task

STATUS_LABEL: dict[Status, str] = {
    Status.TODO: "To do",
    Status.DOING: "Doing",
    Status.DONE: "Done",
}

#: Days covered by the trend and intake charts.
TREND_DAYS = 7


def status_mix(tasks: list[Task]) -> Chart:
    """Donut of tasks by status. Labels sit outside the slices."""
    counts = Counter(task.status for task in tasks)
    statuses = [status for status in Status if counts[status]]

    fig = go.Figure(
        go.Pie(
            labels=[STATUS_LABEL[status] for status in statuses],
            values=[float(counts[status]) for status in statuses],
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

    return Chart(
        id="chart-status",
        title="Status mix",
        description="Every task on the board, by column.",
        summary=_sentence(len(tasks), [(STATUS_LABEL[s], counts[s]) for s in statuses]),
        figure=figure_of(fig),
    )


def workload(tasks: list[Task], grouping: Grouping) -> Chart:
    """Stacked bar per owner or priority, one trace per status."""
    if grouping is Grouping.OWNER:
        key, buckets, label = (lambda t: t.owner), sorted({t.owner for t in tasks}), "owner"
    else:
        order = [Priority.HIGH, Priority.NORMAL, Priority.LOW]
        present = {t.priority for t in tasks}
        key, buckets, label = (lambda t: t.priority.value), [p.value for p in order if p in present], "priority"

    counts = Counter((key(task), task.status) for task in tasks)
    totals = [(bucket, sum(counts[bucket, status] for status in Status)) for bucket in buckets]

    fig = go.Figure(
        [
            go.Bar(
                name=STATUS_LABEL[status],
                x=[str(bucket) for bucket in buckets],
                y=[float(counts[bucket, status]) for bucket in buckets],
            )
            for status in Status
        ]
    )
    fig.update_layout(barmode="stack", showlegend=True, bargap=0.35)
    fig.update_yaxes(title_text="Tasks")
    _integer_axis(fig, [float(total) for _, total in totals])

    return Chart(
        id="chart-workload",
        title=f"Workload by {label}",
        description="Stacked by status: the height is what someone is holding, the split is how much is finished.",
        summary=_sentence(len(tasks), totals, unit=f"across {len(buckets)} {label}s"),
        figure=figure_of(fig),
    )


def created_trend(tasks: list[Task], days: int = TREND_DAYS, now: datetime | None = None) -> Chart:
    """Line of tasks created per day over the last `days` days."""
    today = (now or datetime.now(UTC)).date()
    window = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    counts = Counter(task.created_at.date() for task in tasks)
    values = [float(counts[day]) for day in window]
    created = int(sum(values))

    fig = go.Figure(
        go.Scatter(
            name="Created",
            x=[day.isoformat() for day in window],
            y=values,
            mode="lines+markers",
            line={"width": 2, "shape": "spline", "smoothing": 0.4},
            marker={"size": 6},
        )
    )
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title_text="Tasks")
    _integer_axis(fig, values)

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


def owner_share(tasks: list[Task]) -> Chart:
    """Donut of tasks by owner."""
    counts = Counter(task.owner for task in tasks)
    owners = sorted(counts, key=lambda owner: (-counts[owner], owner))

    fig = go.Figure(
        go.Pie(
            labels=owners,
            values=[float(counts[owner]) for owner in owners],
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

    return Chart(
        id="chart-owners",
        title="Share by owner",
        description="Who is carrying the board right now.",
        summary=_sentence(len(tasks), [(owner, counts[owner]) for owner in owners]),
        figure=figure_of(fig),
    )


def intake(tasks: list[Task], days: int = TREND_DAYS, now: datetime | None = None) -> Chart:
    """Two lines over one window: tasks created per day, and how many remain open."""
    today = (now or datetime.now(UTC)).date()
    window = [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
    created = Counter(task.created_at.date() for task in tasks)
    open_now = Counter(task.created_at.date() for task in tasks if task.status is not Status.DONE)

    lines = [
        ("Created", [float(created[day]) for day in window]),
        ("Still open", [float(open_now[day]) for day in window]),
    ]
    fig = go.Figure(
        [
            go.Scatter(
                name=name,
                x=[day.isoformat() for day in window],
                y=values,
                mode="lines+markers",
                line={"width": 2, "shape": "spline", "smoothing": 0.4},
                marker={"size": 6},
            )
            for name, values in lines
        ]
    )
    fig.update_layout(showlegend=True)
    fig.update_yaxes(title_text="Tasks")
    _integer_axis(fig, [value for _, values in lines for value in values])

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


def oldest_open(tasks: list[Task], limit: int = 5, now: datetime | None = None) -> Chart:
    """Horizontal bar of the `limit` oldest open tasks, by age in hours."""
    moment = now or datetime.now(UTC)
    open_tasks = [task for task in tasks if task.status is not Status.DONE]
    ranked = sorted(open_tasks, key=lambda task: task.created_at)[:limit]
    # Plotly draws the first entry at the bottom; reversed so the oldest is on top.
    ranked.reverse()

    ages = [round((moment - task.created_at).total_seconds() / 3600, 1) for task in ranked]
    labels = [_clip(task.title) for task in ranked]

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


def _clip(text: str, width: int = 34) -> str:
    """Shorten `text` to `width` characters with an ellipsis."""
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def _integer_axis(fig: go.Figure, stacked_totals: list[float]) -> None:
    """Use integer y ticks when every value is an integer; `dtick=1` when the peak is at most 10."""
    if not all(float(value).is_integer() for value in stacked_totals):
        return
    peak = max(stacked_totals, default=0)
    fig.update_yaxes(tickformat=",d", **({"dtick": 1} if peak <= 10 else {}))


def _sentence(total: int, parts: list[tuple[str, int]], unit: str | None = None) -> str:
    """Build the chart's text summary from its counts."""
    head = f"{total} tasks" + (f" {unit}" if unit else "")
    if not parts:
        return f"{head}. Nothing to plot yet."
    body = ", ".join(f"{count} {name.lower()}" for name, count in parts)
    return f"{head}: {body}."
