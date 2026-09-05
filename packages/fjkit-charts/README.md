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

Plotly's basic bundle ships inside this wheel and is served from the plugin's
own static mount. Nothing is fetched at runtime, and a page loads the 1.1 MB
only if it calls `chart_scripts()`.

Chart chrome — axis text, grid lines, tick colour, the hover card — is resolved
from the live theme tokens on every draw, so a theme toggle is a redraw.

## License

MIT. See [LICENSE](LICENSE).
