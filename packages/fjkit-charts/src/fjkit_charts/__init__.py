"""Charts for a fjkit app: a plugin, one line to add and nothing to skip.

    from fjkit import FjkitConfig
    from fjkit_charts import ChartsPlugin

    config = FjkitConfig(
        template_dir=APP_DIR / "templates",
        plugins=(ChartsPlugin(),),
    )

Then in a template:

    {% from "charts/macros.html" import chart, chart_scripts %}
    {% for item in charts %}{{ chart(item) }}{% endfor %}

    {% block scripts %}{{ chart_scripts() }}{% endblock %}

and in the router, a `Chart` per figure:

    from fjkit_charts import Chart, figure_of

    Chart(id="by-owner", title="Workload", summary="Ana has 5 of 12 open tasks.",
          figure=figure_of(go.Figure(...)))

That is the whole setup. Plotly's basic bundle ships in this wheel — one of the
scripts CHARTER §7 whitelists, pinned here rather than in `fjkit.vendored`
because the bytes are here too — and is served from this plugin's own static
mount. No download, no npm, no bundler, nothing fetched at runtime. A page
loads the 1.1 MB only if it calls `chart_scripts()`.
"""

from __future__ import annotations

from fjkit_charts.figures import (
    Chart,
    PlotlyFigure,
    PlotlyLayout,
    PlotlyTrace,
    assert_no_colour_in,
    figure_of,
)
from fjkit_charts.plugin import PLOTLY_FILENAME, PLOTLY_URL, PLOTLY_VERSION, ChartsPlugin

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
