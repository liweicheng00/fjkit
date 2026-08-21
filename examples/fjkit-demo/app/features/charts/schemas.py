"""Wire contracts for the charts page.

The figure this page sends **is** a Plotly figure — `data` and `layout`, the
names Plotly's own documentation uses. What it is not is `dict[str, Any]`: the
parts this app depends on are typed, and the rest arrives through an explicit
tail. OpenAPI then says something true and useful — *these fields I promise,
the remainder is Plotly's* — instead of shrugging.

The one thing that is deliberately **not** in the figure is colour.

The series run on Plotly's own palette, applied in the browser — nothing here
picks a hue, and nothing here needs to. What the server must not do is write
one down: a colour in the figure is a colour that is wrong in one of the two
themes, invisible to `fjkit check` (which reads class attributes, not JSON),
and impossible to restyle without a redeploy.

`extra="allow"` is what makes the Plotly tail reachable, and it is also the
hole in that rule: `#1F77B4` is a perfectly legal `str`, so no amount of schema
stops a colour arriving through it. The type system was never going to be the
guard here. `tests/test_charts.py::test_no_figure_on_the_page_contains_a_colour`
is — it scans the *rendered* figure JSON, so it does not care which field the
bytes came from.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class Grouping(StrEnum):
    """The second chart's x axis. What the page's one control switches."""

    OWNER = "owner"
    PRIORITY = "priority"


GROUPING_OPTIONS: list[tuple[Grouping, str]] = [
    (Grouping.OWNER, "By owner"),
    (Grouping.PRIORITY, "By priority"),
]


class PlotlyTrace(BaseModel):
    """One series, in Plotly's vocabulary.

    Typed down to what this app actually reads and no further. `type` is a
    `Literal` rather than `str` because it is the one field the drawing code
    branches on — a fourth trace kind arriving unannounced would be a silent
    empty chart, which is exactly how `mpl_to_plotly` fails.

    Everything else Plotly accepts — `mode`, `hole`, `textposition`,
    `hovertemplate` — comes through `extra="allow"` untyped. That is the whole
    trade: the tail is what makes the full library reachable, and the reason
    the colour test is not optional.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["bar", "scatter", "pie"]
    name: str | None = None
    #: Cartesian traces. Not "category" and "value" — Plotly's `x` and `y` are
    #: *axes*, and a horizontal bar puts the numbers on `x` and the labels on
    #: `y`. Typing them as `str` and `float` respectively looked right until
    #: the first `orientation="h"` chart, which is the smaller version of the
    #: lesson this whole module is about: a typed subset of somebody else's
    #: schema is a guess, and the tail is what stops a wrong guess being fatal.
    x: list[str | float] | None = None
    y: list[str | float] | None = None
    #: Pie traces use different names for the same two ideas.
    labels: list[str] | None = None
    values: list[float] | None = None


class PlotlyLayout(BaseModel):
    """Layout, minus everything the theme owns.

    No font, no grid colour, no background: those come from the tokens at draw
    time and would be overwritten anyway. What is here is what the *route*
    decides — how bars combine, whether there is a legend, what the axes are
    called, and the tick rules that follow from the data.
    """

    model_config = ConfigDict(extra="allow")

    barmode: Literal["stack", "group"] | None = None
    showlegend: bool | None = None


class PlotlyFigure(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[PlotlyTrace]
    layout: PlotlyLayout


class Chart(BaseModel):
    """A figure, plus the three things a figure cannot supply itself: a stable
    id, a sentence describing it, and what its series mean."""

    id: str
    title: str
    description: str
    #: The accessible alternative, and the only thing a reader without
    #: JavaScript gets. Written by the service from the same numbers the
    #: traces are built from, so it cannot describe a different chart.
    summary: str
    height: int = 288
    figure: PlotlyFigure

    # A plain property, not a `@computed_field`: a computed field joins the
    # JSON representation, and this would put the same bytes on the wire twice
    # — `figure` is already there, and this is only a *rendering* of it for an
    # HTML attribute. Jinja reads plain properties happily.
    @property
    def figure_json(self) -> str:
        """`exclude_none` because the typed fields are a superset of any one
        trace: a bar has no `labels`, a pie has no `x`. Emitting them as nulls
        would send Plotly keys it has to ignore, on every trace."""
        return json.dumps(self.figure.model_dump(exclude_none=True))


class ChartsResponse(BaseModel):
    charts: list[Chart]
    grouping_options: list[tuple[Grouping, str]]
    active_grouping: Grouping


def figure_of(fig: Any) -> PlotlyFigure:
    """Validate a `plotly.graph_objects.Figure` into the typed model above.

    Two things happen on the way through, both of which have to happen exactly
    once and are therefore not left to callers:

    * `template` is dropped. `plotly.py` writes one even when it is set to
      `None`, and the *default* template is 7,621 bytes carrying 111 colour
      literals — every one of which would be a violation of the rule this
      module exists to enforce.
    * the figure is validated, so a trace type this app cannot draw is an
      error here rather than an empty box in someone's browser.
    """
    payload = fig.to_plotly_json()
    payload.get("layout", {}).pop("template", None)
    return PlotlyFigure.model_validate(payload)
