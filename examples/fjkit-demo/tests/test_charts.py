"""Tests for the charts figures, routes and colour-free figure JSON."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import get_args

import pytest
from app.schemas.charts import Grouping
from app.schemas.tasks import Priority, Status, Task
from app.services import charts
from app.services.records.seed import seed_records
from app.services.tasks.seed import seed_tasks
from fjkit_charts import PLOTLY_FILENAME, PlotlyTrace, assert_no_colour_in

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "app" / "templates" / "charts"
CHARTS_JS = ROOT / "app" / "static" / "js" / "charts.js"

#: The same rows the app opens on, so a count here matches a count on the page.
TASKS = seed_tasks(count(1))
RECORDS = seed_records()

#: The board's figures, which the grouping control swaps, and everything the
#: page draws. Two numbers because the swap returns the first group only.
SWAPPED = len(charts.build(TASKS, Grouping.OWNER))
ON_THE_PAGE = SWAPPED + len(charts.gallery(TASKS, RECORDS))


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
    now = datetime.now(UTC)
    only_done = [Task(id=1, title="a", status=Status.DONE, owner="livy", created_at=now)]
    (trace,) = charts.status_mix(only_done).figure.data
    assert trace.labels == ["Done"]


def test_workload_stacks_one_trace_per_status(tasks):
    chart = charts.workload(tasks, Grouping.OWNER)
    assert chart.figure.layout["barmode"] == "stack"
    assert [t.name for t in chart.figure.data] == ["To do", "Doing", "Done"]
    # Every trace spans both owners.
    assert all(t.x == ["livy", "mei"] for t in chart.figure.data)
    assert sum(sum(t.y) for t in chart.figure.data) == len(tasks)


def test_workload_switches_its_x_axis_without_changing_shape(tasks):
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


def test_the_age_spread_is_one_box_per_priority_that_has_a_task(tasks):
    chart = charts.age_spread(tasks, now=datetime.now(UTC))
    assert [trace.type for trace in chart.figure.data] == ["box", "box"]
    # No low-priority task in the fixture, so no third box — an empty box draws
    # an axis label with nothing under it.
    assert [trace.name for trace in chart.figure.data] == ["high", "low"]
    assert sum(len(trace.y) for trace in chart.figure.data) == len(tasks)


def test_the_age_spread_plots_every_point_not_just_the_quartiles(tasks):
    """At this many tasks the box summarises two or three numbers, so the points
    are the honest part of it."""
    for trace in charts.age_spread(tasks).figure.data:
        assert trace.boxpoints == "all"


def test_every_summary_describes_the_data_it_was_built_from(tasks):
    """The summary is the chart's text alternative, so it states the numbers, as a sentence."""
    for chart in charts.build(tasks, Grouping.OWNER):
        assert any(character.isdigit() for character in chart.summary), chart.id
        assert chart.summary.endswith("."), chart.id


# --------------------------------------------------------------------------- #
# The routes
# --------------------------------------------------------------------------- #


def test_the_page_renders_both_groups(client):
    response = client.get("/charts")
    assert response.status_code == 200
    assert response.text.count("data-chart") == ON_THE_PAGE
    assert 'id="charts"' in response.text


def test_the_gallery_covers_every_trace_type_the_contract_admits(client):
    """The gallery exists so the demo draws all twelve, not the four the board
    needed. A type added to `PlotlyTrace` with no figure here is a type nobody
    has looked at in a browser."""
    admitted = set(get_args(PlotlyTrace.model_fields["type"].annotation))
    everything = charts.build(TASKS, Grouping.OWNER) + charts.gallery(TASKS, RECORDS)
    drawn = {trace.type for chart in everything for trace in chart.figure.data}
    assert drawn == admitted, f"never drawn in the demo: {sorted(admitted - drawn)}"


def test_the_page_is_the_only_one_that_loads_plotly(client):
    assert PLOTLY_FILENAME in client.get("/charts").text
    for path in ("/", "/tasks", "/jobs"):
        assert "plotly" not in client.get(path).text


def test_the_vendored_bundle_is_actually_served(client):
    """Through `PLOTLY_FILENAME`, not the literal: the plugin owns which bundle
    it ships, and a demo spelling the name itself breaks on a swap it has no
    opinion about."""
    response = client.get(f"/_fjkit-charts/assets/vendor/plotly/{PLOTLY_FILENAME}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(("text/javascript", "application/javascript"))


def test_an_htmx_swap_returns_the_cards_and_nothing_else(htmx):
    response = htmx.get("/charts?group=priority")
    assert response.status_code == 200
    assert "<html" not in response.text
    # The board's cards only. The gallery sits outside the target, because
    # nothing the control changes reaches a gallery figure.
    assert response.text.count("data-chart") == SWAPPED
    # The grouping control is not part of the swap.
    assert 'name="group"' not in response.text


def test_the_grouping_control_drives_the_swap(client):
    page = client.get("/charts").text
    assert 'hx-get="/charts"' in page
    assert 'hx-target="#charts"' in page
    assert 'name="group"' in page


def test_the_figure_is_typed_with_an_explicit_tail(client):
    """`PlotlyTrace` types only the trace kind and stays open: the rest is Plotly's.

    The enum is read from the model rather than restated, because its contents
    are the plugin's business — `test_the_literal_is_exactly_what_the_bundle_registers`
    in `fjkit-charts` is what pins them to the shipped bundle. What this asserts
    is that the enum survives the trip into the app's OpenAPI schema.
    """
    schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert set(schemas["PlotlyTrace"]["properties"]) == {"type"}
    assert schemas["PlotlyTrace"]["additionalProperties"] is True
    admitted = set(get_args(PlotlyTrace.model_fields["type"].annotation))
    assert set(schemas["PlotlyTrace"]["properties"]["type"]["enum"]) == admitted
    assert {"bar", "scatter", "pie", "box"} <= admitted

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

#: The one figure on the page whose payload is colour. `services/charts/raster.py`
#: is the long version; the short one is that an `image` trace's `z` is an RGB
#: triple per pixel, so it cannot be re-themed and cannot be pattern-matched.
#: Named here rather than skipped silently, so removing it breaks a test.
RASTER = "chart-raster"


def test_no_figure_on_the_page_contains_a_colour(client):
    """Colour lives in the token layer, so a rebrand never has to reach into figure JSON."""
    page = client.get("/charts").text
    figures = re.findall(r'data-figure="([^"]*)"', page)
    assert len(figures) == ON_THE_PAGE
    for figure in figures:
        assert not HUES.search(figure), f"a colour reached the figure JSON: {figure[:120]}"


def test_no_trace_carries_a_colour_field(tasks):
    from html import unescape

    for chart in charts.build(tasks, Grouping.OWNER) + charts.gallery(tasks, RECORDS):
        for trace in chart.figure.model_dump()["data"]:
            marker = trace.get("marker", {})
            assert "color" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
            assert "colors" not in marker, f"{chart.id}: colour belongs to the browser, not the figure"
            # No figure picks a ramp either. A heatmap's scale is Plotly's, the
            # same way a bar's fill is.
            assert "colorscale" not in trace, f"{chart.id}: the scale is Plotly's, not the server's"
        assert not HUES.search(unescape(chart.figure_json))


def test_the_colour_guard_the_plugin_ships_agrees(tasks):
    """`assert_no_colour_in` is what an app is told to call, so the demo calls it.

    Twice, because the raster is the documented exception: the default refuses
    an image trace, and the opt-out is a keyword the caller has to write.
    """
    everything = charts.build(tasks, Grouping.OWNER) + charts.gallery(tasks, RECORDS)
    assert_no_colour_in([c for c in everything if c.id != RASTER])
    assert_no_colour_in(everything, allow_image=True)

    with pytest.raises(AssertionError, match="image trace"):
        assert_no_colour_in(everything)


def test_the_raster_is_the_only_image_on_the_page(tasks):
    """An exception that spreads is not an exception."""
    with_image = [
        chart.id
        for chart in charts.build(tasks, Grouping.OWNER) + charts.gallery(tasks, RECORDS)
        if any(trace.type == "image" for trace in chart.figure.data)
    ]
    assert with_image == [RASTER]


def test_the_default_plotly_template_never_reaches_the_page(client):
    """Plotly's default template carries its own colours and inflates every figure; neither may reach the page.

    The size bound is 6 KB rather than the 2 KB it was while every figure was a
    summary. A binning trace — `histogram2d`, `histogram2dcontour` — is handed
    raw points and bins them in the browser, so its payload is the 137 records
    at about 2.4 KB. The template measures 7,621 bytes, so 6 KB still catches
    the thing this guard is for.
    """
    from html import unescape

    for figure in re.findall(r'data-figure="([^"]*)"', client.get("/charts").text):
        # Checks the parsed layout keys, not the raw text.
        assert "template" not in json.loads(unescape(figure))["layout"]
        assert len(figure) < 6000, "a figure this size means the template came back"


def test_the_charts_page_carries_a_text_alternative(client):
    """The plot area is a canvas no screen reader can read, so the caption has to carry the chart."""
    page = client.get("/charts").text
    expected = ON_THE_PAGE
    assert page.count("<figcaption>") == expected
    assert page.count('aria-hidden="true"') >= expected


def test_the_figure_attribute_is_valid_json(client):
    """An escaping bug in the attribute shows up as a blank chart in the browser and nowhere else."""
    from html import unescape

    page = client.get("/charts").text
    for figure in re.findall(r'data-figure="([^"]*)"', page):
        assert json.loads(unescape(figure))["data"]
    assert "data-roles" not in page
