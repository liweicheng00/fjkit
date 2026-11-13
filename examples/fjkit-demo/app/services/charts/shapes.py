"""The trace types the board itself can answer for: violin, histogram, heatmap, ternary.

The six figures in `build()` are views of the board. These are a gallery: one
figure per trace type `fjkit_charts` admits, so the demo exercises every one of
them rather than the three it happened to need. Each still plots real board
data — a gallery of invented numbers proves the bundle draws and nothing else.

`shapes` for the four whose data the task board already holds; the three that
need a second dimension are in `density.py`, and the raster is in `raster.py`.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import plotly.graph_objects as go

from app.schemas.charts import Chart
from app.schemas.tasks import Priority, Status, Task
from app.services.charts.utils import STATUS_LABEL, sentence

#: Highest first, the order the age charts put their groups in.
_ORDER = [Priority.HIGH, Priority.NORMAL, Priority.LOW]


def _hours(tasks: list[Task], moment: datetime) -> list[float]:
    return [round((moment - task.created_at).total_seconds() / 3600, 1) for task in tasks]


def age_shape(tasks: list[Task], now: datetime | None = None) -> Chart:
    """Violin per priority: the box plot's question, answered with the shape.

    Beside `age_spread`, which draws the same numbers as boxes. A box shows four
    summary statistics; a violin shows where the mass actually is, which is the
    difference between "the middle half sits here" and "there are two clusters".
    """
    moment = now or datetime.now(UTC)
    ages = {priority: _hours([t for t in tasks if t.priority is priority], moment) for priority in _ORDER}
    present = [priority for priority in _ORDER if ages[priority]]

    fig = go.Figure(
        [
            go.Violin(
                name=priority.value,
                y=ages[priority],
                points="all",
                meanline_visible=True,
                width=0.8,
                # Without this the kernel runs past the data and the axis reads
                # down to −20 hours open, which is not a thing.
                spanmode="hard",
            )
            for priority in present
        ]
    )
    fig.update_layout(showlegend=False)
    fig.update_yaxes(title_text="Hours open")

    return Chart(
        id="chart-shape",
        title="Age shape by priority",
        description="The same numbers as the box above, drawn as density. The line inside each is the mean.",
        summary=sentence(len(tasks), [(p.value, len(ages[p])) for p in present], unit="by priority"),
        figure=fig,
    )


def age_histogram(tasks: list[Task], now: datetime | None = None) -> Chart:
    """One histogram over every task's age. Plotly does the binning."""
    moment = now or datetime.now(UTC)
    hours = _hours(tasks, moment)

    fig = go.Figure(go.Histogram(x=hours, nbinsx=8, hovertemplate="%{y} tasks, %{x} h<extra></extra>"))
    fig.update_layout(showlegend=False, bargap=0.05)
    fig.update_xaxes(title_text="Hours open")
    fig.update_yaxes(title_text="Tasks", tickformat=",d", dtick=1)

    return Chart(
        id="chart-histogram",
        title="Age distribution",
        description="Every task by how long it has existed. The bins are Plotly's, computed in the browser.",
        summary=(
            f"{len(hours)} tasks spanning {min(hours):g} to {max(hours):g} hours."
            if hours
            else "Nothing on the board yet."
        ),
        figure=fig,
    )


def owner_status_grid(tasks: list[Task]) -> Chart:
    """Heatmap of owner against status: where the board is dense.

    The colour here is the data, which is the one place this package lets a
    scale decide a hue — and it is still Plotly's scale, not one written on the
    server. `charts.js` themes the bar's frame and leaves the ramp alone.
    """
    counts = Counter((task.owner, task.status) for task in tasks)
    owners = sorted({task.owner for task in tasks})
    statuses = list(Status)

    fig = go.Figure(
        go.Heatmap(
            x=owners,
            y=[STATUS_LABEL[status] for status in statuses],
            z=[[float(counts[owner, status]) for owner in owners] for status in statuses],
            hovertemplate="%{x} · %{y}: %{z} <extra></extra>",
            xgap=2,
            ygap=2,
        )
    )
    fig.update_layout(showlegend=False)

    busiest = max(counts.items(), key=lambda item: item[1], default=((None, None), 0))
    return Chart(
        id="chart-grid",
        title="Owner by status",
        description="One cell per pair. The scale is Plotly's; only the bar's frame follows the theme.",
        summary=(
            f"{len(tasks)} tasks across {len(owners)} owners; the fullest cell is "
            f"{busiest[0][0]} at {STATUS_LABEL[busiest[0][1]].lower()}, with {busiest[1]}."
            if tasks
            else "Nothing on the board yet."
        ),
        figure=fig,
    )


def owner_mix(tasks: list[Task]) -> Chart:
    """Each owner as one point in to-do/doing/done space.

    A ternary plot is the honest shape for three shares that sum to one, which
    is what a per-owner status split is. On a bar chart the same reading takes
    three bars per owner and a legend.
    """
    counts = Counter((task.owner, task.status) for task in tasks)
    owners = sorted({task.owner for task in tasks})

    def share(owner: str, status: Status) -> float:
        total = sum(counts[owner, s] for s in Status)
        return round(counts[owner, status] / total, 4) if total else 0.0

    fig = go.Figure(
        go.Scatterternary(
            mode="markers+text",
            a=[share(owner, Status.TODO) for owner in owners],
            b=[share(owner, Status.DOING) for owner in owners],
            c=[share(owner, Status.DONE) for owner in owners],
            text=owners,
            textposition="top center",
            marker={"size": 12},
            hovertemplate="%{text}<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        ternary={
            "sum": 1,
            "aaxis": {"title": {"text": "To do"}},
            "baxis": {"title": {"text": "Doing"}},
            "caxis": {"title": {"text": "Done"}},
        },
    )

    return Chart(
        id="chart-mix",
        title="Owner mix",
        description="One point per owner, placed by their split of to do, doing and done. A corner is all of one.",
        summary=(
            f"{len(owners)} owners placed by their status split across {len(tasks)} tasks."
            if owners
            else "Nothing on the board yet."
        ),
        height=320,
        figure=fig,
    )
