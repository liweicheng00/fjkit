"""Vendor Plotly's cartesian bundle into the fjkit-charts package.

Split out of the kit's `scripts/vendor_ui.py` when charts became their own
distribution: the bytes live here now, so the script that fetches them does too.

    uv run python packages/fjkit-charts/scripts/vendor_plotly.py

Writes one file and removes any other bundle beside it, because
`test_this_package_ships_exactly_the_whitelisted_plotly` asserts there is one:
switching bundles otherwise leaves the previous one in the wheel, served by the
same mount, at a filename nothing points at.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

# Single source of truth lives in the package, so the URL the plugin advertises
# cannot drift from the bytes on disk.
from fjkit_charts.plugin import PLOTLY_DIST, PLOTLY_FILENAME, PLOTLY_VERSION

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "fjkit_charts"
VENDOR = PACKAGE / "static" / "vendor" / "plotly"

JSDELIVR = "https://cdn.jsdelivr.net/npm"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def vendor_plotly() -> None:
    # The cartesian bundle, neither the basic one nor the full one —
    # `PLOTLY_DIST` says why. Served from this plugin's own static mount, and
    # loaded by nothing but the page that calls `chart_scripts()`.
    print(f"{PLOTLY_DIST}@{PLOTLY_VERSION}")
    target = VENDOR / PLOTLY_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = fetch(f"{JSDELIVR}/{PLOTLY_DIST}@{PLOTLY_VERSION}/{PLOTLY_FILENAME}")
    target.write_bytes(payload)
    print(f"  {target.relative_to(PACKAGE.parent.parent)}  {len(payload) / 1024:.0f} KB")

    for stale in sorted(VENDOR.glob("plotly*.js")):
        if stale != target:
            stale.unlink()
            print(f"  removed {stale.relative_to(PACKAGE.parent.parent)}")


if __name__ == "__main__":
    vendor_plotly()
