"""Vendor Plotly into the demo, the same way the kit vendors htmx.

fjkit ships htmx and Basecoat and nothing else — §7 of CHARTER.md caps the
kit's client-side JavaScript at those two. Plotly is an order of magnitude
larger than both together, so it does not belong in the wheel. It belongs
here: an *app* is free to load whatever it needs, and this file is what makes
that choice legible instead of a stray file someone dropped in `static/`.

The pinned bytes are committed, not fetched at runtime. That is the same rule
`packages/fjkit/scripts/vendor_ui.py` follows and for the same three reasons:
the demo runs offline, the demo runs with no Node.js, and what the browser
loads is reviewable in a diff.

    uv run python examples/fjkit-demo/scripts/vendor_plotly.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

#: The *basic* bundle: scatter, bar and pie, which is every chart on the page.
#: The full `plotly.js-dist-min` is 4.85 MB — 3D, maps, financial and
#: statistical traces this demo never draws. Picking the bundle is the only
#: size knob Plotly gives you without a build step, so it is worth spending
#: the one line on.
PLOTLY_VERSION = "3.7.0"
PLOTLY_URL = f"https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@{PLOTLY_VERSION}/plotly-basic.min.js"

TARGET = Path(__file__).resolve().parent.parent / "app" / "static" / "vendor" / "plotly" / "plotly-basic.min.js"


def main() -> None:
    print(f"plotly.js-basic-dist-min@{PLOTLY_VERSION}")
    with urllib.request.urlopen(PLOTLY_URL, timeout=60) as response:
        payload = response.read()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(payload)
    print(f"  {TARGET.name}  ({len(payload):,} bytes)")


if __name__ == "__main__":
    main()
