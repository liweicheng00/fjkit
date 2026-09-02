"""A Plotly figure, typed down to the parts anything here reads.

The figure that reaches the browser **is** a Plotly figure — `data` and
`layout`, the names Plotly's own documentation uses. What it is not is
`dict[str, Any]`: the fields the drawing code branches on are typed, and the
rest arrives through an explicit tail. OpenAPI then says something true and
useful — *these fields are promised, the remainder is Plotly's* — instead of
shrugging.

The one thing deliberately **not** in a figure is colour.

Series run on Plotly's own palette, applied in the browser. Nothing on the
server picks a hue, and nothing needs to. What the server must not do is write
one down: a colour in the figure is a colour that is wrong in one of the two
themes, invisible to `fjkit check` (which reads class attributes, not JSON),
and impossible to restyle without a redeploy.

`extra="allow"` is what makes the Plotly tail reachable, and it is also the
hole in that rule: `#1F77B4` is a perfectly legal `str`, so no schema stops a
colour arriving through it. The type system was never going to be the guard
here — a test that scans the *rendered* figure JSON is, because it does not
care which field the bytes came from. `ChartsPlugin` ships that test as
`fjkit.charts.assert_no_colour_in`, so an app gets it in one line.

**plotly is not a dependency of fjkit.** `figure_of` takes anything with a
`to_plotly_json()`, which is the whole of the surface it needs. An app that
builds figures by hand as dicts never installs plotly at all.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Chart",
    "PlotlyFigure",
    "PlotlyLayout",
    "PlotlyTrace",
    "assert_no_colour_in",
    "figure_of",
]


class PlotlyTrace(BaseModel):
    """One series, in Plotly's vocabulary.

    Typed down to what the drawing code actually reads and no further. `type`
    is a `Literal` rather than `str` because it is the one field the browser
    branches on — a fourth trace kind arriving unannounced would be a silent
    empty chart, which is exactly how `mpl_to_plotly` fails.

    Everything else Plotly accepts — `mode`, `hole`, `textposition`,
    `hovertemplate` — comes through `extra="allow"` untyped. That is the whole
    trade: the tail is what makes the full library reachable, and the reason
    the colour check is not optional.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["bar", "scatter", "pie"]
    name: str | None = None
    #: Cartesian traces. Not "category" and "value" — Plotly's `x` and `y` are
    #: *axes*, and a horizontal bar puts the numbers on `x` and the labels on
    #: `y`. Typing them as `str` and `float` respectively looks right until the
    #: first `orientation="h"` chart, which is the small version of the lesson
    #: this module is about: a typed subset of somebody else's schema is a
    #: guess, and the tail is what stops a wrong guess being fatal.
    x: list[str | float] | None = None
    y: list[str | float] | None = None
    #: Pie traces use different names for the same two ideas.
    labels: list[str] | None = None
    values: list[float] | None = None


class PlotlyLayout(BaseModel):
    """Layout, minus everything the theme owns.

    No font, no grid colour, no background: those are resolved from the live
    tokens at draw time and would be overwritten anyway. What is here is what
    the *route* decides — how bars combine, whether there is a legend, what the
    axes are called, and the tick rules that follow from the data.
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
    id, a sentence describing it, and what its series mean.

    `summary` is not optional and is not decoration. It is the accessible
    alternative and the only thing a reader without JavaScript gets, so it is
    a required field rather than a keyword someone forgets — a chart with no
    text alternative is a chart that is invisible to a screen reader, and the
    macro cannot invent the sentence.
    """

    id: str
    title: str
    description: str = ""
    #: Write it from the same numbers the traces are built from, so it cannot
    #: describe a different chart.
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


def figure_of(fig: Any) -> PlotlyFigure:
    """Validate a `plotly.graph_objects.Figure` into the model above.

    Two things happen on the way through, both of which have to happen exactly
    once and are therefore not left to callers:

    * `template` is dropped. `plotly.py` writes one even when it is set to
      `None`, and the *default* template is 7,621 bytes carrying 111 colour
      literals — every one of which would violate the rule this module exists
      to enforce.
    * the figure is validated, so a trace type the browser cannot draw is an
      error here rather than an empty box in someone's browser.

    Duck-typed on `to_plotly_json()` rather than imported from plotly, which is
    what keeps plotly out of fjkit's dependencies. A plain dict works too.
    """
    payload = fig.to_plotly_json() if hasattr(fig, "to_plotly_json") else dict(fig)
    layout = payload.get("layout")
    if isinstance(layout, dict):
        layout.pop("template", None)
    return PlotlyFigure.model_validate(payload)


#: Hex literals and the CSS colour functions, in figure JSON. Deliberately the
#: same families `fjkit check` looks for in markup — the rule is one rule, and
#: this is the half that reads JSON instead of class attributes.
_COLOUR = re.compile(
    r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
    r"|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\("
    r"|\bvar\(--"
)


def assert_no_colour_in(charts: Any) -> None:
    """Raise if any figure carries a colour. For an app's own test suite.

        from fjkit.charts import assert_no_colour_in

        def test_the_figures_carry_no_colour(client):
            assert_no_colour_in(build_my_charts())

    Scans the *rendered* JSON rather than the model fields, so it catches a
    hue that arrived through `extra="allow"` — which is the only way one can
    arrive, and therefore the only way worth checking.

    `var(--…)` is in the pattern because it is the failure that looks like it
    works: `plotly.py` accepts the string, validates it and serialises it, and
    the browser's parser then discards it silently. A token name on the server
    is not a token, it is a typo with a plausible shape.

    Accepts one `Chart`, an iterable of them, or anything JSON-serialisable.
    """
    items = charts if isinstance(charts, (list, tuple)) else [charts]
    for item in items:
        blob = item.figure_json if isinstance(item, Chart) else json.dumps(item, default=str)
        found = _COLOUR.search(blob)
        if found is not None:
            where = getattr(item, "id", "<figure>")
            raise AssertionError(
                f"chart {where!r} carries the colour literal {found.group(0)!r}. "
                "Series colours are Plotly's and the chrome is resolved from tokens in the "
                "browser — a colour written on the server is wrong in one of the two themes."
            )
