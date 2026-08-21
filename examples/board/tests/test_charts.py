"""The charts page: the figures, the swap, and the rule the page exists to prove.

That rule is the last test in this file. Everything a chart library normally
tempts you into — a hex code in a template, a colour in the JSON, a second
figure for dark mode — is a thing this app must not have, and none of them are
caught by looking at the picture.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.features.charts import service as charts
from app.features.charts.schemas import Grouping
from app.features.tasks.schemas import Priority, Status, Task

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "app" / "templates" / "charts"
CHARTS_JS = ROOT / "app" / "static" / "js" / "charts.js"


@pytest.fixture
def tasks() -> list[Task]:
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)
    return [
        Task(id=1, title="a", status=Status.DONE, priority=Priority.HIGH, owner="livy", created_at=now),
        Task(id=2, title="b", status=Status.DOING, priority=Priority.HIGH, owner="livy", created_at=now),
        Task(id=3, title="c", status=Status.TODO, priority=Priority.LOW, owner="mei", created_at=yesterday),
    ]


# --------------------------------------------------------------------------- #
# The figures — plain functions over a list of tasks, so no HTTP is involved.
# --------------------------------------------------------------------------- #


def test_status_mix_counts_every_task_once(tasks):
    chart = charts.status_mix(tasks)
    (trace,) = chart.figure.data
    assert trace.type == "pie"
    assert sum(trace.values) == len(tasks)
    assert trace.labels == ["To do", "Doing", "Done"]


def test_a_status_nobody_is_in_gets_no_slice():
    """An empty slice is a legend entry that means nothing, and a 0% label."""
    now = datetime.now(UTC)
    only_done = [Task(id=1, title="a", status=Status.DONE, owner="livy", created_at=now)]
    (trace,) = charts.status_mix(only_done).figure.data
    assert trace.labels == ["Done"]


def test_workload_stacks_one_trace_per_status(tasks):
    chart = charts.workload(tasks, Grouping.OWNER)
    assert chart.figure.layout.barmode == "stack"
    assert [t.name for t in chart.figure.data] == ["To do", "Doing", "Done"]
    # Two owners, and every trace spans both so the segments line up.
    assert all(t.x == ["livy", "mei"] for t in chart.figure.data)
    assert sum(sum(t.y) for t in chart.figure.data) == len(tasks)


def test_workload_switches_its_x_axis_without_changing_shape(tasks):
    """What the control changes is the buckets, not the figure."""
    by_owner = charts.workload(tasks, Grouping.OWNER)
    by_priority = charts.workload(tasks, Grouping.PRIORITY)
    assert by_priority.id == by_owner.id
    assert by_priority.figure.data[0].x == ["high", "low"]
    assert [t.name for t in by_priority.figure.data] == [t.name for t in by_owner.figure.data]


def test_the_trend_window_is_pinned_by_its_caller(tasks):
    chart = charts.created_trend(tasks, days=3, now=datetime.now(UTC))
    (trace,) = chart.figure.data
    assert trace.type == "scatter"
    assert len(trace.x) == 3
    assert sum(trace.y) == len(tasks)


def test_every_summary_describes_the_data_it_was_built_from(tasks):
    """The accessible name is the only thing a reader without JavaScript gets,
    so it may not be prose someone typed next to the numbers.

    "Contains a number" rather than "contains the task count": not every chart
    is about every task — `oldest_open` counts what is still open — and an
    invariant that only holds because today's charts happen to agree is not an
    invariant.
    """
    for chart in charts.build(tasks, Grouping.OWNER):
        assert any(character.isdigit() for character in chart.summary), chart.id
        assert chart.summary.endswith("."), chart.id


# --------------------------------------------------------------------------- #
# The routes
# --------------------------------------------------------------------------- #


def test_the_page_renders_every_chart(client):
    response = client.get("/charts")
    assert response.status_code == 200
    assert response.text.count("data-chart") == len(charts.build([], Grouping.OWNER))
    assert 'id="charts"' in response.text


def test_the_page_is_the_only_one_that_loads_plotly(client):
    assert "plotly-basic.min.js" in client.get("/charts").text
    for path in ("/", "/tasks", "/jobs"):
        assert "plotly" not in client.get(path).text


def test_the_vendored_bundle_is_actually_served(client):
    response = client.get("/static/vendor/plotly/plotly-basic.min.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(("text/javascript", "application/javascript"))


def test_an_htmx_swap_returns_the_cards_and_nothing_else(htmx):
    """CHARTER A6: the partial the page embedded is the partial the swap gets."""
    response = htmx.get("/charts?group=priority")
    assert response.status_code == 200
    assert "<html" not in response.text
    assert response.text.count("data-chart") == len(charts.build([], Grouping.OWNER))
    # The control is on the page, not in the swap — it keeps its own state.
    assert 'name="group"' not in response.text


def test_the_grouping_control_drives_the_swap(client):
    page = client.get("/charts").text
    assert 'hx-get="/charts"' in page
    assert 'hx-target="#charts"' in page
    assert 'name="group"' in page


def test_the_figure_is_typed_with_an_explicit_tail(client):
    """CHARTER A9: the return annotation is the route's only contract.

    The figure is a Plotly figure, so `dict[str, Any]` was the tempting field
    type and it would have made this schema say nothing. Instead the fields
    this app reads are typed and the rest arrives through `extra="allow"`,
    which OpenAPI reports honestly as `additionalProperties: true`.

    That tail is deliberate — it is what keeps the whole library reachable
    without re-describing it — and it is also why the colour test below is a
    requirement rather than a nicety: no schema can stop a hex code arriving
    through it, because `#1F77B4` is a perfectly legal `str`.
    """
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas["PlotlyTrace"]["properties"]) >= {"type", "name", "x", "y", "labels", "values"}
    assert schemas["PlotlyTrace"]["additionalProperties"] is True
    assert set(schemas["PlotlyTrace"]["properties"]["type"]["enum"]) == {"bar", "scatter", "pie"}

    assert set(schemas["Chart"]["properties"]) == {
        "id",
        "title",
        "description",
        "summary",
        "height",
        "figure",
    }
    # `figure_json` is a plain property, not a `@computed_field`, so the same
    # bytes are not described — or sent — twice.
    assert "figure_json" not in schemas["Chart"]["properties"]


# --------------------------------------------------------------------------- #
# The rule the page exists to prove
# --------------------------------------------------------------------------- #

#: Same families `fjkit check` rejects in markup. Applied here to the *rendered
#: figure JSON*, which no template checker looks inside.
HUES = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b|\b(?:rgba?|hsla?|oklch|oklab)\(")


def test_no_figure_on_the_page_contains_a_colour(client):
    """The point of the whole feature, and the guard the type system cannot be.

    A hex code in a template fails `fjkit check`. A hex code inside a
    `data-figure` attribute is invisible to it — the checker reads class
    attributes, not JSON. `PlotlyTrace` cannot catch it either: it allows extra
    fields on purpose, and `marker={"color": "#1F77B4"}` satisfies every type
    in this app.

    So this is the only thing standing between the `extra="allow"` tail and a
    chart that ignores the theme. It reads the *rendered* JSON, which is why it
    does not care which field the bytes arrived in.
    """
    page = client.get("/charts").text
    figures = re.findall(r'data-figure="([^"]*)"', page)
    assert len(figures) == len(charts.build([], Grouping.OWNER))
    for figure in figures:
        assert not HUES.search(figure), f"a colour reached the figure JSON: {figure[:120]}"


def test_no_trace_carries_a_colour_field(tasks):
    """The structural half of the check above.

    The regex catches a hue that got written down. This catches the field
    existing at all — including a colour Plotly would accept by name (`"red"`),
    which no hex/rgb pattern would ever match.
    """
    from html import unescape

    for chart in charts.build(tasks, Grouping.OWNER):
        for trace in chart.figure.model_dump(exclude_none=True)["data"]:
            marker = trace.get("marker", {})
            assert "color" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
            assert "colors" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
        assert not HUES.search(unescape(chart.figure_json))


def test_the_default_plotly_template_never_reaches_the_page(client):
    """`plotly.py` writes a `template` into every figure, and the default one
    is 7,621 bytes carrying 111 colour literals — colorscales for traces this
    page does not draw. `figure_of()` drops it; this is what notices if that
    ever stops happening, because the symptom is only a bigger page."""
    from html import unescape

    for figure in re.findall(r'data-figure="([^"]*)"', client.get("/charts").text):
        # Parsed, not grepped: `hovertemplate` is a legitimate key and one of
        # the seeded task titles is "Audit templates for hard-coded hues".
        assert "template" not in json.loads(unescape(figure))["layout"]
        assert len(figure) < 2000, "a figure this size means the template came back"


def test_the_charts_page_carries_a_text_alternative(client):
    """Plotly's SVG is a thousand unlabelled paths. The figcaption is the
    chart, as far as a screen reader or a reader without JS is concerned."""
    page = client.get("/charts").text
    expected = len(charts.build([], Grouping.OWNER))
    assert page.count("<figcaption>") == expected
    assert page.count('aria-hidden="true"') >= expected


def test_the_figure_attribute_is_valid_json(client):
    """It is HTML-escaped into an attribute; a quoting slip would be silent
    until the browser tried to parse it."""
    from html import unescape

    page = client.get("/charts").text
    for figure in re.findall(r'data-figure="([^"]*)"', page):
        assert json.loads(unescape(figure))["data"]
    # `data-roles` was how an earlier version carried semantic colour. It is
    # gone, and this is what notices if it comes back by accident.
    assert "data-roles" not in page
