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

#: idiomorph's htmx extension, which adds the `morph:*` swap styles. A morph
#: patches the DOM it is given instead of replacing it, so the nodes that did
#: not change keep what the browser put on them: focus, scroll position, an
#: open `<details>`, a checkbox the person ticked, the caret's place in an
#: input. Every other swap style throws that away, because it throws the nodes
#: away.
#:
#: **No page loads it unless that page asks for it** — `morph_scripts()` in
#: `ui/swap.html`, the same page-level opt-in `form_scripts()` and
#: `chart_scripts()` use. CHARTER §4.2 budgets what every page downloads and
#: that answer has to stay "htmx and Basecoat", so bytes that only a sorting
#: table or a redrawn form needs are opted into by the page that has one.
#:
#: The pin is the extension package, not idiomorph itself. `idiomorph-ext.js`
#: is the library plus the htmx glue in one file, which is what a page loads;
#: vendoring the bare library as well would ship the same algorithm twice.
IDIOMORPH_VERSION = "0.8.0"


#: The Basecoat style packs vendored alongside each other under
#: `static/vendor/basecoat/styles/`. They share one token vocabulary and one
#: selector set — a pack changes geometry (radii, control heights, borders,
#: shadows), never the names a template writes. That is why fjkit can ship all
#: eight and why swapping one touches no template.
StylePack = Literal["vega", "nova", "maia", "lyra", "mira", "luma", "sera", "rhea"]

#: Upstream's own default, and therefore ours: `basecoat.css` aliases it.
DEFAULT_STYLE: StylePack = "vega"

STYLE_PACKS: tuple[StylePack, ...] = get_args(StylePack)
