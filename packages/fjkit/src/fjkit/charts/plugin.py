"""`ChartsPlugin` — charts as a registration, not a page built twice.

    config = FjkitConfig(template_dir=…, plugins=(ChartsPlugin(),))

That gives an app the `chart` macro, the theming bridge, the Plotly bundle and
the two `<script>` lines that load them. Nothing to download, nothing to mount:
Plotly ships in the wheel beside htmx and Basecoat, one of the scripts CHARTER
§7 whitelists, and is served from the kit's own static mount like the rest.

**The division of labour.** Python decides the shape of the figure; the browser
decides its chrome. Axis text, grid lines, tick colour, the gaps between pie
slices and the hover card belong to the card a chart sits in, not to the data,
and Plotly's defaults for them are `#444` on `#eee` — a chart drawn for a white
page, on a page that may be dark. So `charts.js` resolves those from the live
tokens on every draw, and a theme toggle is a redraw. The series colours are
Plotly's own and never change.

**Why the JavaScript is not in the shell.** A plugin cannot inject markup into
`ui/shell.html` (`fjkit.plugins`), and this is why that rule holds: Plotly's
basic bundle is 1.1 MB, so a hook letting this plugin put a `<script>` on every
page would put it on the login screen. Instead the page that draws charts calls
`chart_scripts()` in its own `{% block scripts %}` and no other page pays. Being
in the wheel changes what an install contains, not what a page downloads, and §7
budgets the download.
"""

from __future__ import annotations

from pathlib import Path

from fjkit.config import STATIC_DIR as KIT_STATIC_DIR
from fjkit.plugins import AppSetup, EnvSetup
from fjkit.templating import static_url
from fjkit.vendored import PLOTLY_VERSION

__all__ = ["ChartsPlugin"]

#: This plugin's own templates. Named `templates/charts/` so template names are
#: `charts/…`, matching how `apidocs` does it.
TEMPLATE_DIR = Path(__file__).parent / "templates"

#: `charts.js` — the theming bridge. 3 KB, and the only JavaScript this plugin
#: ships of its own.
STATIC_DIR = Path(__file__).parent / "static"

#: The Plotly build this plugin is written against. The version is pinned in
#: `fjkit.vendored` with the other whitelisted scripts, and
#: `scripts/vendor_ui.py` puts the bytes under the kit's `static/vendor/plotly/`.
PLOTLY_FILENAME = "plotly-basic.min.js"
PLOTLY_PATH = f"vendor/plotly/{PLOTLY_FILENAME}"
PLOTLY_URL = f"https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@{PLOTLY_VERSION}/{PLOTLY_FILENAME}"


class ChartsPlugin:
    """Register in `FjkitConfig.plugins`.

    :param url: where this plugin's own assets (`charts.js`) are served. Keep it
        outside `config.static_url` (`/_fjkit` by default): Starlette matches
        the first mount whose prefix fits, so a path nested inside the kit's own
        static mount is swallowed by it and 404s against a directory that does
        not hold this plugin's files.
    :param plotly_url: serve Plotly from somewhere other than the copy in the
        wheel — a path your app already serves, or a URL. The default is the
        vendored bundle under `config.static_url`, cache-stamped like every
        other kit asset.
    """

    name = "charts"

    def __init__(self, *, url: str = "/_fjkit-charts", plotly_url: str | None = None) -> None:
        if not url.startswith("/") or url == "/":
            raise ValueError(f"ChartsPlugin(url={url!r}) must be an absolute path such as '/_fjkit-charts'.")
        self.url = url.rstrip("/")
        self.plotly_url = plotly_url

    # ---------------------------------------------------------------- plugin

    def mount(self, setup: AppSetup) -> None:
        # Only the bridge. Plotly already sits behind `mount_fjkit`'s own static
        # mount, which serves the whole of the kit's `static/`.
        setup.mount_static(f"{self.url}/assets", STATIC_DIR)

    def extend(self, setup: EnvSetup) -> None:
        """Contribute the templates and the two URLs they need.

        The globals are namespaced `fjkit_charts_*` for the reason `EnvSetup`
        makes collisions a startup error: an app is entitled to want `charts`
        for its own context.
        """
        setup.add_template_dir(TEMPLATE_DIR)

        # Same `?v=<mtime>` stamp the kit's own assets get, for the same reason:
        # StaticFiles sends no Cache-Control, so a browser may keep a script
        # whose lifetime it was never told.
        assets = static_url(f"{self.url}/assets", STATIC_DIR, auto_reload=setup.config.auto_reload)
        setup.add_global("fjkit_charts_script", lambda: assets("charts.js"))

        if self.plotly_url is not None:
            plotly = self.plotly_url
        else:
            kit = static_url(setup.config.static_url, KIT_STATIC_DIR, auto_reload=setup.config.auto_reload)
            plotly = kit(PLOTLY_PATH)
        setup.add_global("fjkit_charts_plotly", lambda: plotly)
