"""Helpers the chart builders share, and nothing outside this feature imports.

None of this sets a colour. Plotly is handed a figure with no palette in it, and
`fjkit_charts` applies the page's tokens when it renders.
"""

from __future__ import annotations

import plotly.graph_objects as go

from app.schemas.tasks import Status

STATUS_LABEL: dict[Status, str] = {
    Status.TODO: "To do",
    Status.DOING: "Doing",
    Status.DONE: "Done",
}

#: Days covered by the trend and intake charts.
TREND_DAYS = 7


def clip(text: str, width: int = 34) -> str:
    """Shorten `text` to `width` characters with an ellipsis."""
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def integer_axis(fig: go.Figure, stacked_totals: list[float]) -> None:
    """Use integer y ticks when every value is an integer; `dtick=1` when the peak is at most 10."""
    if not all(float(value).is_integer() for value in stacked_totals):
        return
    peak = max(stacked_totals, default=0)
    fig.update_yaxes(tickformat=",d", **({"dtick": 1} if peak <= 10 else {}))


def sentence(total: int, parts: list[tuple[str, int]], unit: str | None = None) -> str:
    """Build a chart's text summary from its counts."""
    head = f"{total} tasks" + (f" {unit}" if unit else "")
    if not parts:
        return f"{head}. Nothing to plot yet."
    body = ", ".join(f"{count} {name.lower()}" for name, count in parts)
    return f"{head}: {body}."
