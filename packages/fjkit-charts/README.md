# fjkit-charts

Server-rendered Plotly charts for [fjkit](https://liweicheng00.github.io/fjkit/).
A plugin, one line to add, no front-end build.

```bash
uv add fjkit-charts
```

```python
from fjkit import FjkitConfig
from fjkit_charts import ChartsPlugin

config = FjkitConfig(template_dir=APP_DIR / "templates", plugins=(ChartsPlugin(),))
```

```jinja
{% from "charts/macros.html" import chart, chart_scripts %}
{% for item in charts %}{{ chart(item) }}{% endfor %}

{% block scripts %}{{ chart_scripts() }}{% endblock %}
```

Plotly's cartesian bundle ships inside this wheel and is served from the
plugin's own static mount. Nothing is fetched at runtime, and a page loads the
1.4 MB only if it calls `chart_scripts()`.

`Chart` accepts exactly the twelve trace types that bundle registers — `bar`,
`box`, `contour`, `heatmap`, `histogram`, `histogram2d`, `histogram2dcontour`,
`image`, `pie`, `scatter`, `scatterternary` and `violin`. Any other type fails
validation in the route rather than drawing an empty box in the browser.

`assert_no_colour_in(charts)` is the test to put in your own suite. It refuses
an `image` trace, whose `z` is a colour per pixel chosen on the server and
cannot follow the theme; pass `allow_image=True` when the pixels are the point.

If the app builds figures with plotly.py, that library targets one plotly.js
release. When its major or minor differs from the bundled one, the plugin emits
a `PluginWarning` at startup. plotly.py is not a dependency of this package.

Chart chrome — axis text, grid lines, tick colour, the hover card — is resolved
from the live theme tokens on every draw, so a theme toggle is a redraw.

## License

MIT. See [LICENSE](LICENSE).
