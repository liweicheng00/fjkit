"""Pinned versions of the front-end assets shipped inside the package.

Single source of truth: the vendoring script reads these to know what to
download, and the shell's footer reads them to report what is loaded. The footer
therefore cannot drift from the bytes on disk.

These pins are also CHARTER §7's whitelist of client-side JavaScript: what is
listed here, and nothing else, may ship inside the wheel. Two of them reach
every page. The others do not, which is why each is a separate pin — see
`HTMX_JSON_ENC_VERSION` and `PLOTLY_VERSION`.
"""

from __future__ import annotations

from typing import Literal, get_args

BASECOAT_VERSION = "1.0.2"
HTMX_VERSION = "2.0.10"

#: htmx's `json-enc` extension, which makes a submit send JSON instead of
#: urlencoded fields. Its own npm package and therefore its own version: htmx 2
#: moved every extension out of the core repository, and this pin tracks the
#: extension rather than the core it plugs into.
#:
#: **No page loads it unless that page asks for it** — `form_scripts()` in
#: `ui/form.html`, the same page-level opt-in `chart_scripts()` uses for Plotly.
#: CHARTER §7 budgets what a page downloads by default, and that answer has to
#: stay "htmx and Basecoat", so 1,012 bytes that only some forms need cannot go
#: in the shell.
HTMX_JSON_ENC_VERSION = "2.0.3"

#: Plotly's basic bundle — scatter, bar and pie — drawn by `fjkit.charts`. The
#: full `plotly.js-dist-min` is 4.85 MB of 3D, maps, financial and statistical
#: traces most dashboards never draw; the basic one is 1.1 MB, and picking the
#: bundle is the only size knob Plotly offers without a build step.
#:
#: **No page loads it unless that page asks for it** — `chart_scripts()`, the
#: same per-page opt-in as `form_scripts()`. It lives in the wheel because
#: CHARTER §7 whitelists it (2026-08-26): an app that draws charts gets the
#: bytes by installing fjkit, with nothing to download, vendor or mount itself.
PLOTLY_VERSION = "3.7.0"


#: The Basecoat style packs vendored alongside each other under
#: `static/vendor/basecoat/styles/`. They share one token vocabulary and one
#: selector set — a pack changes geometry (radii, control heights, borders,
#: shadows), never the names a template writes. That is why fjkit can ship all
#: eight and why swapping one touches no template.
StylePack = Literal["vega", "nova", "maia", "lyra", "mira", "luma", "sera", "rhea"]

#: Upstream's own default, and therefore ours: `basecoat.css` aliases it.
DEFAULT_STYLE: StylePack = "vega"

STYLE_PACKS: tuple[StylePack, ...] = get_args(StylePack)
