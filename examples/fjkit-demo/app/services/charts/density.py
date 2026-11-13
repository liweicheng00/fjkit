"""The three two-dimensional types: histogram2d, histogram2dcontour, contour.

These need a second numeric dimension, and the board has one numeric field. So
they plot the Records dataset instead — 137 rows with a size and a last-touched
date, which is a real cloud of points rather than eight tasks stretched into a
shape they do not have.

That is why `charts_page` takes `RecordServiceDep` as well. The layer rule is
unchanged: the router injects both stores, this module takes the rows it plots.

**These figures are larger than the others.** A binning trace is handed raw
points and bins them in the browser, so the payload is the dataset, not a
summary — about 2 KB each against 300–500 bytes for a bar chart. `contour` is
the counter-example and is binned here, which is why it is the small one.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime

import plotly.graph_objects as go

from app.schemas.charts import Chart
from app.schemas.records import Record

#: Both axes are log-ish in nature — row counts run from thousands to millions —
#: so the size axis is binned by order of magnitude rather than linearly.
_SIZE_BINS = 12


def _points(records: list[Record], today: date) -> tuple[list[float], list[int]]:
    """Row count and days since last update, one pair per record."""
    sizes = [float(record.rows) for record in records]
    ages = [(today - record.updated).days for record in records]
    return sizes, ages


def size_against_age(records: list[Record], today: date | None = None) -> Chart:
    """2D histogram: which (size, staleness) corner the datasets fall into.

    Plotly does the binning, so the trace carries the 137 raw pairs.
    """
    day = today or datetime.now(UTC).date()
    sizes, ages = _points(records, day)

    fig = go.Figure(
        go.Histogram2d(
            x=ages,
            y=sizes,
            nbinsx=10,
            nbinsy=_SIZE_BINS,
            hovertemplate="%{z} datasets<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Days since update")
    fig.update_yaxes(title_text="Rows")

    return Chart(
        id="chart-density",
        title="Size against staleness",
        description="137 datasets binned in two dimensions. The bins are Plotly's, from the raw pairs.",
        summary=(
            f"{len(records)} datasets, last updated between {min(ages)} and {max(ages)} days ago."
            if records
            else "No datasets."
        ),
        figure=fig,
    )


def size_against_age_contour(records: list[Record], today: date | None = None) -> Chart:
    """The same pairs as `size_against_age`, drawn as a smoothed density."""
    day = today or datetime.now(UTC).date()
    sizes, ages = _points(records, day)

    fig = go.Figure(
        go.Histogram2dContour(
            x=ages,
            y=sizes,
            nbinsx=10,
            nbinsy=_SIZE_BINS,
            # Lines, not a filled surface. `coloring="heatmap"` fills the whole
            # plot area with the scale's low end, which in Plotly's default
            # scale is near-white — an opaque light panel on a dark card, where
            # every other figure lets the card through.
            contours={"coloring": "lines", "showlabels": True},
            hovertemplate="%{z} datasets<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Days since update")
    fig.update_yaxes(title_text="Rows")

    return Chart(
        id="chart-density-contour",
        title="Size against staleness, smoothed",
        description=(
            "The same 137 pairs as a contour. Where the cloud has a peak is easier to see "
            "than where it has cells."
        ),
        summary=(
            f"{len(records)} datasets, the same pairs as the panel beside this one."
            if records
            else "No datasets."
        ),
        figure=fig,
    )


def stage_over_time(records: list[Record], today: date | None = None) -> Chart:
    """Contour over a grid this module bins itself: stage against staleness.

    The counter-example to the two above. `contour` takes a `z` matrix rather
    than raw points, so the binning happens here and the figure that goes out is
    a 3×8 grid — a few hundred bytes, not the dataset.
    """
    day = today or datetime.now(UTC).date()
    columns = 8
    stages = sorted({record.stage for record in records}, key=lambda stage: stage.value)

    # Bucketed across the range the data actually occupies, not in fixed weeks
    # back from today. The seed is months old, so fixed weeks put every record
    # in the last bucket and the contour is one flat block.
    ages = [(day - record.updated).days for record in records]
    oldest, newest = (max(ages), min(ages)) if ages else (1, 0)
    width = max((oldest - newest) / columns, 1)

    counts: Counter[tuple[int, str]] = Counter()
    for record, age in zip(records, ages, strict=True):
        counts[min(int((age - newest) / width), columns - 1), record.stage.value] += 1

    fig = go.Figure(
        go.Contour(
            x=[round(newest + column * width) for column in range(columns)],
            y=[stage.value for stage in stages],
            z=[[float(counts[column, stage.value]) for column in range(columns)] for stage in stages],
            line_smoothing=0.85,
            hovertemplate="%{y}, %{x} days: %{z}<extra></extra>",
        )
    )
    fig.update_layout(showlegend=False)
    fig.update_xaxes(title_text="Days since update")

    return Chart(
        id="chart-contour",
        title="Stage against staleness",
        description=(
            "Binned on the server into a 3×8 grid, so this figure is a few hundred bytes "
            "rather than the dataset."
        ),
        summary=(
            f"{len(records)} datasets across {len(stages)} stages, binned into {columns} columns."
            if records
            else "No datasets."
        ),
        figure=fig,
    )
