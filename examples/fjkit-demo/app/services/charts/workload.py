"""Stacked bars per owner or priority, one trace per status."""

from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go

from app.schemas.charts import Chart, Grouping, figure_of
from app.schemas.tasks import Priority, Status, Task
from app.services.charts.utils import STATUS_LABEL, integer_axis, sentence


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
    integer_axis(fig, [float(total) for _, total in totals])

    return Chart(
        id="chart-workload",
        title=f"Workload by {label}",
        description="Stacked by status: the height is what someone is holding, the split is how much is finished.",
        summary=sentence(len(tasks), totals, unit=f"across {len(buckets)} {label}s"),
        figure=figure_of(fig),
    )
