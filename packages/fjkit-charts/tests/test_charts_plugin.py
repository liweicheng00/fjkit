"""`fjkit_charts` — the plugin, the figure models, and the colour rule.

These lock down what an app cannot check for itself: the 1.1 MB bundle is in
the wheel and served, only the page that asks for it loads it, and a colour
written on the server is caught before it reaches a browser, where it is wrong
in exactly one of the two themes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fjkit import FjkitConfig, build_environment, mount_fjkit
from fjkit_charts import (
    PLOTLY_FILENAME,
    PLOTLY_VERSION,
    Chart,
    ChartsPlugin,
    PlotlyFigure,
    assert_no_colour_in,
    figure_of,
)

BAR = {"data": [{"type": "bar", "x": ["a", "b"], "y": [1, 2]}], "layout": {"barmode": "group"}}


def a_chart(**over) -> Chart:
    return Chart(
        id=over.pop("id", "c1"),
        title=over.pop("title", "Workload"),
        summary=over.pop("summary", "Ana has 5 of 12 open tasks."),
        figure=figure_of(over.pop("figure", BAR)),
        **over,
    )


class FakeFigure:
    """What `plotly.graph_objects.Figure` looks like from `figure_of`'s side.

    A stand-in rather than the real class: plotly is not a dependency of fjkit,
    and a test that imported it would quietly make it one.
    """

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def to_plotly_json(self) -> dict:
        return self._payload


class TestFigureOf:
    def test_accepts_anything_with_to_plotly_json(self):
        figure = figure_of(FakeFigure(BAR))
        assert isinstance(figure, PlotlyFigure)
        assert figure.data[0].type == "bar"

    def test_accepts_a_plain_dict_so_plotly_is_never_needed(self):
        assert figure_of(BAR).layout.barmode == "group"

    def test_the_default_template_is_stripped(self):
        """plotly.py writes a template even when it is set to `None`, and the
        default template carries 111 colour literals."""
        payload = {**BAR, "layout": {"barmode": "group", "template": {"layout": {"font": {"color": "#444"}}}}}
        figure = figure_of(FakeFigure(payload))
        assert "template" not in figure.layout.model_dump(exclude_none=True)

    def test_an_undrawable_trace_type_fails_here_not_in_the_browser(self):
        with pytest.raises(ValueError, match="type"):
            figure_of({"data": [{"type": "surface", "z": [[1]]}], "layout": {}})

    def test_the_plotly_tail_survives(self):
        """`extra="allow"` keeps the rest of the library reachable."""
        figure = figure_of({"data": [{"type": "pie", "labels": ["a"], "values": [1], "hole": 0.4}], "layout": {}})
        assert figure.data[0].model_dump(exclude_none=True)["hole"] == 0.4


class TestChart:
    def test_figure_json_drops_the_nulls_of_the_other_trace_kinds(self):
        """A bar has no `labels`, a pie has no `x`. Emitting them as nulls sends
        Plotly keys it has to ignore, on every trace."""
        blob = a_chart().figure_json
        assert "labels" not in blob and "null" not in blob

    def test_a_summary_is_required_because_it_is_the_text_alternative(self):
        with pytest.raises(ValueError, match="summary"):
            Chart(id="c", title="t", figure=figure_of(BAR))


class TestColourRule:
    def test_a_clean_figure_passes(self):
        assert_no_colour_in(a_chart())
        assert_no_colour_in([a_chart(), a_chart(id="c2")])

    @pytest.mark.parametrize(
        "colour",
        ["#1F77B4", "rgb(31, 119, 180)", "oklch(0.72 0.15 275)", "hsl(210 50% 40%)"],
    )
    def test_a_colour_anywhere_in_the_tail_is_caught(self, colour):
        """A colour can only arrive through `extra="allow"`, so scanning the
        rendered JSON is the only check that works."""
        chart = a_chart(figure={"data": [{"type": "bar", "marker": {"color": colour}}], "layout": {}})
        with pytest.raises(AssertionError, match="carries the colour literal"):
            assert_no_colour_in(chart)

    def test_a_token_name_is_caught_too(self):
        """A failure that looks like success: plotly.py accepts the string and
        serialises it, and the browser's parser discards it silently."""
        chart = a_chart(figure={"data": [{"type": "bar", "marker": {"color": "var(--primary)"}}], "layout": {}})
        with pytest.raises(AssertionError, match="carries the colour literal"):
            assert_no_colour_in(chart)

    def test_the_message_names_the_chart(self):
        chart = a_chart(id="by-owner", figure={"data": [{"type": "bar", "line": {"color": "#fff"}}], "layout": {}})
        with pytest.raises(AssertionError, match="by-owner"):
            assert_no_colour_in(chart)


class TestPlugin:
    def test_the_url_must_be_a_path(self):
        with pytest.raises(ValueError, match="absolute path"):
            ChartsPlugin(url="charts")

    def test_the_macro_is_on_the_loader_path(self, tmp_path):
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), auto_reload=False))
        assert env.get_template("charts/macros.html")

    def test_a_chart_renders_its_figure_and_its_caption(self, tmp_path):
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart %}{{ chart(item) }}').render(item=a_chart())
        assert "data-chart" in html and 'id="c1"' in html
        assert "<figcaption>Ana has 5 of 12 open tasks.</figcaption>" in html
        # The SVG is a thousand unlabelled paths; the sentence beside it is the
        # description a screen reader gets.
        assert 'aria-hidden="true"' in html

    def test_the_markup_carries_no_colour_and_no_class(self, tmp_path):
        """fjkit's vocabulary has no chart class, and inventing one is how a
        closed vocabulary stops being closed."""
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart %}{{ chart(item, boxed=false) }}').render(
            item=a_chart()
        )
        assert "class=" not in html
        assert "#" not in html.split("data-figure=")[0]

    def test_boxed_wraps_it_in_the_card_component(self, tmp_path):
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart %}{{ chart(item) }}').render(item=a_chart())
        assert 'class="card"' in html and "Workload" in html

    def test_scripts_load_the_vendored_plotly_from_the_plugins_own_mount(self):
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart_scripts %}{{ chart_scripts() }}').render()
        assert f"/_fjkit-charts/assets/vendor/plotly/{PLOTLY_FILENAME}" in html
        # Both stamped, for the reason every kit asset is: `StaticFiles` sends
        # no `Cache-Control`, so a browser may keep a script whose lifetime it
        # was never told.
        assert html.count("?v=") == 2
        assert html.index(PLOTLY_FILENAME) < html.index("charts.js"), "deferred scripts run in document order"

    def test_plotly_follows_the_kit_static_url(self):
        env = build_environment(FjkitConfig(plugins=(ChartsPlugin(),), static_url="/assets", auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart_scripts %}{{ chart_scripts() }}').render()
        assert f"/assets/vendor/plotly/{PLOTLY_FILENAME}" in html

    def test_plotly_url_overrides_the_vendored_copy(self):
        plugin = ChartsPlugin(plotly_url="https://example.test/plotly.js")
        env = build_environment(FjkitConfig(plugins=(plugin,), auto_reload=False))
        html = env.from_string('{% from "charts/macros.html" import chart_scripts %}{{ chart_scripts() }}').render()
        assert "https://example.test/plotly.js" in html
        assert "vendor/plotly" not in html

    def test_the_vendored_plotly_is_served_by_the_plugins_mount(self):
        """The bundle moved out of the kit's `static/vendor/` when charts became
        their own distribution. One mount now serves both files this plugin
        ships, so an app that never registers it serves neither."""
        from fastapi.testclient import TestClient

        app = FastAPI()
        mount_fjkit(app, FjkitConfig(plugins=(ChartsPlugin(),)))
        body = TestClient(app).get(f"/_fjkit-charts/assets/vendor/plotly/{PLOTLY_FILENAME}")
        assert body.status_code == 200
        assert f"v{PLOTLY_VERSION}" in body.text[:2000]

    def test_the_bridge_is_served(self, tmp_path):
        from fastapi.testclient import TestClient

        app = FastAPI()
        mount_fjkit(app, FjkitConfig(plugins=(ChartsPlugin(plotly_url="/x.js"),)))
        body = TestClient(app).get("/_fjkit-charts/assets/charts.js")
        assert body.status_code == 200
        assert "Plotly.react" in body.text


def test_this_package_ships_exactly_the_whitelisted_plotly():
    """CHARTER §7 whitelists the JavaScript a wheel may carry, and Plotly's
    basic bundle is on it: one copy, at the pinned version, under this package's
    own `static/vendor/` where `scripts/vendor_plotly.py` writes it."""
    import fjkit_charts

    root = Path(fjkit_charts.__file__).parent
    bundles = list(root.rglob("plotly*.js"))
    assert bundles == [root / "static" / "vendor" / "plotly" / PLOTLY_FILENAME]
    assert f"v{PLOTLY_VERSION}" in bundles[0].read_text(encoding="utf-8")[:2000]
    assert (root / "static" / "charts.js").stat().st_size < 20_000


def test_the_kit_no_longer_carries_plotly():
    """The whole point of the split: `pip install fjkit` stops downloading a
    1.1 MB bundle that only a charts page loads."""
    import fjkit

    assert list(Path(fjkit.__file__).parent.rglob("plotly*.js")) == []


def test_this_package_never_imports_the_plotly_library():
    """Plotly's JavaScript ships here; Plotly's Python does not.

    `figure_of` is duck-typed on `to_plotly_json()`, so an app that builds
    figures with `plotly.py` declares it itself and an app that builds them by
    hand installs nothing extra. A single `import plotly` here would make the
    20 MB library a runtime dependency of every install of this package, and
    the only visible symptom would be a slower `uv sync`.
    """
    import ast

    import fjkit_charts

    banned = {"plotly", "pandas", "numpy", "matplotlib"}
    root = Path(fjkit_charts.__file__).parent
    offenders = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in banned:
                    offenders.append(f"{path.relative_to(root)}: {name}")

    assert not offenders, f"a charting library must not be imported: {offenders}"
