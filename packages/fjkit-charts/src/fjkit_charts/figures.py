"""A Plotly figure, typed down to the one field this package reads.

The figure that reaches the browser is a Plotly figure: `data` and `layout`, the
names Plotly's own documentation uses. Only a trace's `type` is typed, because
the drawing code branches on it; every other attribute is Plotly's, and
`plotly.py` already validates those when it builds a `go.Figure`. A typed copy
of that schema here would be a second, smaller guess at it.

`Chart.figure` takes the figure as Plotly builds it: a `go.Figure`. Not a
plain dict, because a dict skips the validation `plotly.py` does, and that
validation is what lets this module type only `type`.

A figure carries no colour.

Series run on Plotly's own palette, applied in the browser, so nothing on the
server picks a hue. A colour written into the figure is wrong in one of the two
themes, invisible to `fjkit check` (which reads class attributes, not JSON), and
unchangeable without a redeploy.

`extra="allow"` makes the Plotly tail reachable and is also the hole in that
rule: `#1F77B4` is a legal `str`, so no schema stops a colour arriving through
it. The guard is a test that scans the rendered figure JSON, which does not care
which field the bytes came from. `ChartsPlugin` ships that test as
`fjkit_charts.assert_no_colour_in`, so an app gets it in one line.

**plotly is not a dependency of fjkit.** `Chart` accepts anything with a
`to_plotly_json()`, which is its whole required surface, so this package never
imports plotly. The app that builds the figures declares it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "Chart",
    "PlotlyFigure",
    "PlotlyTrace",
    "assert_no_colour_in",
]


class PlotlyTrace(BaseModel):
    """One series, in Plotly's vocabulary.

    `type` is a `Literal` rather than `str` because the browser branches on it:
    a fourth trace kind arriving unannounced renders a silent empty chart, which
    is how `mpl_to_plotly` fails.

    Everything else — `x`, `values`, `orientation`, `hovertemplate` — comes
    through `extra="allow"` untyped. That tail is what makes the full library
    reachable, and why the colour check is not optional.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal["bar", "scatter", "pie"]


class PlotlyFigure(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[PlotlyTrace]
    #: What the route decides — how bars combine, whether there is a legend,
    #: what the axes are called. Font, grid colour and background resolve from
    #: the live tokens at draw time, so a figure need not carry a layout at all.
    layout: dict[str, Any] = Field(default_factory=dict)

    @field_validator("layout", mode="before")
    @classmethod
    def _drop_template(cls, value: Any) -> Any:
        """`plotly.py` writes a template even when it is set to `None`, and the
        default template is 7,621 bytes carrying 111 colour literals, each of
        which violates this module's colour rule. Dropped here, so every path
        into a figure drops it."""
        if isinstance(value, Mapping):
            return {key: item for key, item in value.items() if key != "template"}
        return value


class Chart(BaseModel):
    """A figure, plus the three things a figure cannot supply itself: a stable
    id, a sentence describing it, and what its series mean.

    `summary` is required, not decoration. It is the text alternative, and the
    only content a reader without JavaScript gets. A required field rather than
    a keyword someone forgets: a chart with no text alternative is invisible to
    a screen reader, and the macro cannot invent the sentence.
    """

    id: str
    title: str
    description: str = ""
    #: Write it from the same numbers the traces are built from, so it cannot
    #: describe a different chart.
    summary: str
    height: int = 288
    #: A `go.Figure`. Validated on the way in, so a trace type the browser
    #: cannot draw fails here rather than rendering an empty box.
    figure: PlotlyFigure

    @field_validator("figure", mode="before")
    @classmethod
    def _from_plotly(cls, value: Any) -> Any:
        """Duck-typed on `to_plotly_json()` rather than an `isinstance` check
        against plotly, which keeps plotly out of fjkit's dependencies. A
        `PlotlyFigure` passes through: it is already validated."""
        if hasattr(value, "to_plotly_json"):
            return value.to_plotly_json()
        if isinstance(value, PlotlyFigure):
            return value
        raise ValueError(f"figure must be a plotly Figure, not {type(value).__name__}")

    # A plain property, not a `@computed_field`: a computed field joins the JSON
    # representation, putting the same bytes on the wire twice — `figure` is
    # already there, and this only renders it for an HTML attribute. Jinja reads
    # plain properties.
    @property
    def figure_json(self) -> str:
        """Render the figure for an HTML attribute."""
        return json.dumps(self.figure.model_dump())


#: Hex literals and the CSS colour functions, in figure JSON. The same families
#: `fjkit check` looks for in markup: one rule, of which this is the half that
#: reads JSON instead of class attributes.
_COLOUR = re.compile(
    r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
    r"|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\("
    r"|\bvar\(--"
)


def assert_no_colour_in(charts: Any) -> None:
    """Raise if any figure carries a colour. For an app's own test suite.

        from fjkit_charts import assert_no_colour_in

        def test_the_figures_carry_no_colour(client):
            assert_no_colour_in(build_my_charts())

    Scans the rendered JSON rather than the model fields, so it catches a hue
    that arrived through `extra="allow"` — the only route a hue can take.

    `var(--…)` is in the pattern because that failure looks like it works:
    `plotly.py` accepts the string, validates it and serialises it, and the
    browser's parser then discards it silently. A token name on the server is
    not a token; it is a typo with a plausible shape.

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
