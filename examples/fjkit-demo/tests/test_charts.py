"""Tests for the charts figures, routes and colour-free figure JSON."""

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


# The figures


def test_status_mix_counts_every_task_once(tasks):
    chart = charts.status_mix(tasks)
    (trace,) = chart.figure.data
    assert trace.type == "pie"
    assert sum(trace.values) == len(tasks)
    assert trace.labels == ["To do", "Doing", "Done"]


def test_a_status_nobody_is_in_gets_no_slice():
    """status_mix omits statuses with a zero count."""
    now = datetime.now(UTC)
    only_done = [Task(id=1, title="a", status=Status.DONE, owner="livy", created_at=now)]
    (trace,) = charts.status_mix(only_done).figure.data
    assert trace.labels == ["Done"]


def test_workload_stacks_one_trace_per_status(tasks):
    chart = charts.workload(tasks, Grouping.OWNER)
    assert chart.figure.layout.barmode == "stack"
    assert [t.name for t in chart.figure.data] == ["To do", "Doing", "Done"]
    # Every trace spans both owners.
    assert all(t.x == ["livy", "mei"] for t in chart.figure.data)
    assert sum(sum(t.y) for t in chart.figure.data) == len(tasks)


def test_workload_switches_its_x_axis_without_changing_shape(tasks):
    """Grouping by priority keeps the chart id and trace names, changing only x."""
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
    """Every chart summary contains a digit and ends with a full stop."""
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
    """The kit's static mount serves plotly-basic.min.js as JavaScript."""
    response = client.get("/_fjkit/vendor/plotly/plotly-basic.min.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(("text/javascript", "application/javascript"))


def test_an_htmx_swap_returns_the_cards_and_nothing_else(htmx):
    """An htmx GET of /charts returns only the chart cards."""
    response = htmx.get("/charts?group=priority")
    assert response.status_code == 200
    assert "<html" not in response.text
    assert response.text.count("data-chart") == len(charts.build([], Grouping.OWNER))
    # The grouping control is not part of the swap.
    assert 'name="group"' not in response.text


def test_the_grouping_control_drives_the_swap(client):
    page = client.get("/charts").text
    assert 'hx-get="/charts"' in page
    assert 'hx-target="#charts"' in page
    assert 'name="group"' in page


def test_the_figure_is_typed_with_an_explicit_tail(client):
    """The OpenAPI schema types the trace fields and allows additional properties."""
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
    assert "figure_json" not in schemas["Chart"]["properties"]


# Colour literals

#: Hex codes and colour function calls.
HUES = re.compile(r"#(?:[0-9a-fA-F]{3,8})\b|\b(?:rgba?|hsla?|oklch|oklab)\(")


def test_no_figure_on_the_page_contains_a_colour(client):
    """No data-figure attribute on the page contains a colour literal."""
    page = client.get("/charts").text
    figures = re.findall(r'data-figure="([^"]*)"', page)
    assert len(figures) == len(charts.build([], Grouping.OWNER))
    for figure in figures:
        assert not HUES.search(figure), f"a colour reached the figure JSON: {figure[:120]}"


def test_no_trace_carries_a_colour_field(tasks):
    """No trace marker has a color or colors field."""
    from html import unescape

    for chart in charts.build(tasks, Grouping.OWNER):
        for trace in chart.figure.model_dump(exclude_none=True)["data"]:
            marker = trace.get("marker", {})
            assert "color" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
            assert "colors" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
        assert not HUES.search(unescape(chart.figure_json))


def test_the_default_plotly_template_never_reaches_the_page(client):
    """No figure layout carries a template key and every figure is under 2000 bytes."""
    from html import unescape

    for figure in re.findall(r'data-figure="([^"]*)"', client.get("/charts").text):
        # Checks the parsed layout keys, not the raw text.
        assert "template" not in json.loads(unescape(figure))["layout"]
        assert len(figure) < 2000, "a figure this size means the template came back"


def test_the_charts_page_carries_a_text_alternative(client):
    """Every chart has a figcaption and an aria-hidden plot area."""
    page = client.get("/charts").text
    expected = len(charts.build([], Grouping.OWNER))
    assert page.count("<figcaption>") == expected
    assert page.count('aria-hidden="true"') >= expected


def test_the_figure_attribute_is_valid_json(client):
    """Every data-figure attribute unescapes to JSON with a data array."""
    from html import unescape

    page = client.get("/charts").text
    for figure in re.findall(r'data-figure="([^"]*)"', page):
        assert json.loads(unescape(figure))["data"]
    assert "data-roles" not in page
