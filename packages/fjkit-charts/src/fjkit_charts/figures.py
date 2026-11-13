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

One trace type is the exception and is handled by name rather than by pattern:
an `image` trace's `z` is a colour per pixel, and there is no notation for the
pattern to find. `assert_no_colour_in` rejects it unless the caller opts in.

**plotly is not a dependency of fjkit.** `Chart` accepts anything with a
`to_plotly_json()`, which is its whole required surface, so this package never
imports plotly. The app that builds the figures declares it.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from decimal import Decimal
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

    `type` is a `Literal` rather than `str` because an unregistered trace kind
    renders a silent empty chart rather than an error, which is how
    `mpl_to_plotly` fails. The twelve here are exactly the trace modules the
    vendored cartesian bundle registers — not a subset, and never a superset.
    `type="scatter3d"` would otherwise validate here and draw nothing there, and
    catching that in the route is the whole reason this field is typed.

    `test_the_literal_is_exactly_what_the_bundle_registers` holds both halves of
    that equality against the bundle's own bytes, so swapping `PLOTLY_DIST` in
    `plugin.py` fails until this list is brought with it.

    `image` is the one type whose payload *is* colour — see `assert_no_colour_in`,
    which rejects it unless the caller opts in.

    Everything else — `x`, `values`, `orientation`, `hovertemplate` — comes
    through `extra="allow"` untyped. That tail is what makes the full library
    reachable, and why the colour check is not optional.
    """

    model_config = ConfigDict(extra="allow")

    type: Literal[
        "bar",
        "box",
        "contour",
        "heatmap",
        "histogram",
        "histogram2d",
        "histogram2dcontour",
        "image",
        "pie",
        "scatter",
        "scatterternary",
        "violin",
    ]


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
        """Render the figure for an HTML attribute, as Plotly's own
        `fig.to_json()` would. `to_plotly_json()` keeps dates, `Decimal`s and
        arrays as Python values, and leaves `NaN`, which `JSON.parse` rejects."""
        blob = json.dumps(self.figure.model_dump(), default=_plotly_value)
        if "NaN" in blob or "Infinity" in blob:
            blob = json.dumps(json.loads(blob, parse_constant=lambda _: None))
        return blob


def _plotly_value(value: Any) -> Any:
    """`PlotlyJSONEncoder.default`, without importing plotly: the same checks,
    tried in the same order. numpy and pandas are read from `sys.modules`, as
    plotly reads them, so neither becomes a dependency: a value of theirs means
    the app has already imported them.

    The order carries the behaviour. `tolist()` turns a `datetime64[ns]` array
    into integer nanoseconds and `pd.NaT.isoformat()` returns "NaT", so both
    are caught before the generic methods."""
    if hasattr(value, "to_plotly_json"):
        return value.to_plotly_json()
    numpy = sys.modules.get("numpy")
    if numpy is not None:
        if value is numpy.ma.core.masked:
            return float("nan")
        if isinstance(value, numpy.ndarray) and value.dtype.kind == "M":
            return numpy.datetime_as_string(value).tolist()
    pandas = sys.modules.get("pandas")
    if pandas is not None and (value is pandas.NaT or value is getattr(pandas, "NA", None)):
        return None
    for method in ("isoformat", "tolist"):
        if hasattr(value, method):
            return getattr(value, method)()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


#: Hex literals and the CSS colour functions, in figure JSON. The same families
#: `fjkit check` looks for in markup: one rule, of which this is the half that
#: reads JSON instead of class attributes.
_COLOUR = re.compile(
    r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
    r"|\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\("
    r"|\bvar\(--"
)


def assert_no_colour_in(charts: Any, *, allow_image: bool = False) -> None:
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

    **`image` is checked by type, not by pattern.** Every other trace describes
    data and lets the browser colour it; an `image` trace's `z` *is* the colour,
    one RGB triple per pixel, chosen on the server. The pattern cannot see it —
    `[[[31, 119, 180]]]` holds no `#`, no `rgb(`, nothing to match — so a raster
    would sail through the one check this package offers while being the most
    thoroughly hard-coded palette on the page, and wrong in one of the two themes
    by construction.

    `allow_image=True` is the opt-out, and it is deliberately a keyword the
    caller has to write: a raster whose pixels are the point (a thumbnail, a
    captured frame) is legitimate, and saying so in the test is how that stays a
    decision rather than an oversight.

    Accepts one `Chart`, an iterable of them, or anything JSON-serialisable.
    """
    items = charts if isinstance(charts, (list, tuple)) else [charts]
    for item in items:
        where = getattr(item, "id", "<figure>")
        if not allow_image and isinstance(item, Chart):
            for trace in item.figure.data:
                if trace.type == "image":
                    raise AssertionError(
                        f"chart {where!r} holds an image trace, whose z is a colour per pixel "
                        "chosen on the server. Nothing in the browser can re-theme it, and the "
                        "colour pattern cannot see it. Pass allow_image=True if the pixels are "
                        "the point."
                    )
        blob = item.figure_json if isinstance(item, Chart) else json.dumps(item, default=str)
        found = _COLOUR.search(blob)
        if found is not None:
            raise AssertionError(
                f"chart {where!r} carries the colour literal {found.group(0)!r}. "
                "Series colours are Plotly's and the chrome is resolved from tokens in the "
                "browser — a colour written on the server is wrong in one of the two themes."
            )
