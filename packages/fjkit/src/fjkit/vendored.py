"""Pinned versions of the front-end assets shipped inside the package.

Single source of truth: the vendoring script reads these to know what to
download, and the shell's footer reads them to report what is loaded. The footer
therefore cannot drift from the bytes on disk.

These pins are also CHARTER §7's whitelist of client-side JavaScript: what is
listed here, and nothing else, may ship inside this wheel. Two of them reach
every page; `HTMX_JSON_ENC_VERSION` does not, which is why it is a separate pin.

Plotly is whitelisted by §7 too, but pinned in `fjkit_charts` rather than here:
the bundle ships in that distribution, and a kit that cannot serve the bytes
should not claim to know their version.
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


#: The Basecoat style packs vendored alongside each other under
#: `static/vendor/basecoat/styles/`. They share one token vocabulary and one
#: selector set — a pack changes geometry (radii, control heights, borders,
#: shadows), never the names a template writes. That is why fjkit can ship all
#: eight and why swapping one touches no template.
StylePack = Literal["vega", "nova", "maia", "lyra", "mira", "luma", "sera", "rhea"]

#: Upstream's own default, and therefore ours: `basecoat.css` aliases it.
DEFAULT_STYLE: StylePack = "vega"

STYLE_PACKS: tuple[StylePack, ...] = get_args(StylePack)
