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

A chart is drawn when it first comes into view, not when the page loads.
Drawing one costs around 20 ms, so a page of fifteen draws the four that are on
screen; the rest are sized from `Chart.height` and wait. An `overflow-x: auto`
row counts — a chart scrolled off the side of one is off screen. Pass
`chart(item, eager=true)` for a chart that has to be in the first paint.

Each chart dispatches two bubbling DOM events on its `[data-chart]` div.
`fjkit:chart-drawn` follows every draw, theme redraws included, with an empty
`detail`. `fjkit:chart-click` fires once per click on a point, with
`detail = {curve, point, x, y, name, meta, customdata}`. Keyword arguments to
`chart()` land on that div, so a click can drive an htmx request:

```jinja
{{ chart(item, hx_get="/tasks/table", hx_trigger="fjkit:chart-click",
         hx_target="#tasks", hx_vals="js:{...event.detail}") }}
```

With htmx 2, that sends each field as a query parameter: an array as repeated
parameters, an object as JSON, and a field the trace does not set as the string
`undefined`. Name the fields the route reads — `js:{status: event.detail.x}` —
to send only those.

## License

MIT. See [LICENSE](LICENSE).
