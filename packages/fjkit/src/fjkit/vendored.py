"""Pinned versions of the two front-end assets shipped inside the package.

Single source of truth: the vendoring script reads these to know what to
download, and the shell's footer reads them to report what is actually loaded.
The footer therefore cannot drift from the bytes on disk.
"""

from __future__ import annotations

from typing import Literal, get_args

BASECOAT_VERSION = "1.0.2"
HTMX_VERSION = "2.0.10"


#: The Basecoat style packs vendored alongside each other under
#: `static/vendor/basecoat/styles/`. They share one token vocabulary and one
#: selector set — a pack changes geometry (radii, control heights, borders,
#: shadows), never the names a template writes. That is why fjkit can ship all
#: eight and why swapping one does not touch a single template.
StylePack = Literal["vega", "nova", "maia", "lyra", "mira", "luma", "sera", "rhea"]

#: Upstream's own default, and therefore ours: `basecoat.css` aliases it.
DEFAULT_STYLE: StylePack = "vega"

STYLE_PACKS: tuple[StylePack, ...] = get_args(StylePack)
