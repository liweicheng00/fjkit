"""Charts for a fjkit app — a plugin, so it costs one line to have and none to skip.

    from fjkit import FjkitConfig
    from fjkit.charts import ChartsPlugin

    config = FjkitConfig(
        template_dir=APP_DIR / "templates",
        plugins=(ChartsPlugin(),),
    )

Then in a template:

    {% from "charts/macros.html" import chart, chart_scripts %}
    {% for item in charts %}{{ chart(item) }}{% endfor %}

    {% block scripts %}{{ chart_scripts() }}{% endblock %}

and in the router, a `Chart` per figure:

    from fjkit.charts import Chart, figure_of

    Chart(id="by-owner", title="Workload", summary="Ana has 5 of 12 open tasks.",
          figure=figure_of(go.Figure(...)))

That is the whole of the setup. Plotly's basic bundle ships in the wheel —
one of the scripts CHARTER §7 whitelists, pinned in `fjkit.vendored` beside
htmx and Basecoat — and is served from the kit's static mount. No download,
no npm, no bundler, nothing fetched at runtime; and no page loads the 1.1 MB
unless it calls `chart_scripts()` itself.
"""

from __future__ import annotations

from fjkit.charts.figures import (
    Chart,
    PlotlyFigure,
    PlotlyLayout,
    PlotlyTrace,
    assert_no_colour_in,
    figure_of,
)
from fjkit.charts.plugin import PLOTLY_FILENAME, PLOTLY_URL, PLOTLY_VERSION, ChartsPlugin

__all__ = [
    "PLOTLY_FILENAME",
    "PLOTLY_URL",
    "PLOTLY_VERSION",
    "Chart",
    "ChartsPlugin",
    "PlotlyFigure",
    "PlotlyLayout",
    "PlotlyTrace",
    "assert_no_colour_in",
    "figure_of",
]
