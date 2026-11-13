"""The one figure on this page that carries colour, and the one that explains why.

`image` is the twelfth trace type, and the only one whose payload *is* the
colour: `z` is an RGB triple per pixel, chosen here, on the server. Every other
trace sends numbers and lets the browser decide what they look like, which is
the rule the rest of this feature is built on.

So this card is not a counter-example to that rule — it is the rule's edge,
drawn once so the demo shows where it is. Two things follow, and the tests
assert both:

* `assert_no_colour_in` rejects an image trace unless the caller writes
  `allow_image=True`. The colour pattern cannot see a raster — `[[[90, 90, 90]]]`
  holds no `#` and no `rgb(` — so the guard checks the type instead.
* The pixels here are grey, and grey is still a decision. On a dark card this
  raster does not invert; it is the same grey it was on a white one. That is
  exactly the failure the colour rule exists to prevent, and an app shipping an
  image trace is accepting it.

A raster whose pixels are the point — a thumbnail, a captured frame, a scan —
is the legitimate use, and the demo has none of those to show.
"""

from __future__ import annotations

from collections import Counter

import plotly.graph_objects as go

from app.schemas.charts import Chart
from app.schemas.tasks import Status, Task
from app.services.charts.utils import STATUS_LABEL

#: Darkest for the fullest cell. Mid-greys rather than the full range, so the
#: raster reads as a block on a white card and on a near-black one.
_DARKEST, _LIGHTEST = 70, 220


def board_raster(tasks: list[Task]) -> Chart:
    """The board as a raster: one pixel per owner and status, grey by count."""
    counts = Counter((task.owner, task.status) for task in tasks)
    owners = sorted({task.owner for task in tasks})
    statuses = list(Status)
    peak = max(counts.values(), default=0)

    def level(owner: str, status: Status) -> list[int]:
        share = counts[owner, status] / peak if peak else 0.0
        grey = round(_LIGHTEST - (_LIGHTEST - _DARKEST) * share)
        return [grey, grey, grey]

    fig = go.Figure(
        go.Image(
            z=[[level(owner, status) for owner in owners] for status in statuses],
            hovertemplate="%{x}, %{y}<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(tickmode="array", tickvals=list(range(len(owners))), ticktext=owners)
    fig.update_yaxes(
        tickmode="array",
        tickvals=list(range(len(statuses))),
        ticktext=[STATUS_LABEL[status] for status in statuses],
    )

    return Chart(
        id="chart-raster",
        title="The board as pixels",
        description=(
            "The only figure here that carries colour. Its greys are chosen on the server and "
            "do not follow the theme — which is why assert_no_colour_in refuses an image trace "
            "unless you say so."
        ),
        summary=(
            f"{len(owners)} owners by {len(statuses)} statuses, {len(tasks)} tasks, "
            f"darkest cell holding {peak}."
            if tasks
            else "Nothing on the board yet."
        ),
        height=240,
        figure=fig,
    )
