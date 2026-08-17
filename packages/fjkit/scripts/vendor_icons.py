"""Vendor the Lucide icon set into the package.

    uv run python packages/fjkit/scripts/vendor_icons.py

Fetches `icon-nodes.json` — one request for the whole set, rather than 2000
requests for individual SVG files — and flattens each icon to the inner markup
of its <svg>. The wrapper (size, stroke width, `currentColor`) stays in
templates/ui/icon.html so every icon inherits its context's colour.

Output is a compact JSON data file, not a Python module: 2000 entries of path
data is data, and keeping it out of the source tree means a version bump is a
one-line diff instead of a 20,000-line one.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from xml.sax.saxutils import quoteattr

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "fjkit"
OUT = PACKAGE / "static" / "icons" / "lucide.json"

DATA_API = "https://data.jsdelivr.com/v1/packages/npm/lucide-static"
JSDELIVR = "https://cdn.jsdelivr.net/npm/lucide-static"


def fetch(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def latest_version() -> str:
    return json.loads(fetch(f"{DATA_API}"))["tags"]["latest"]


def render(node: list) -> str:
    """One `[tag, attrs, children?]` node as markup."""
    tag, attrs = node[0], node[1] if len(node) > 1 else {}
    parts = "".join(f" {key}={quoteattr(str(value))}" for key, value in attrs.items())
    children = "".join(render(child) for child in (node[2] if len(node) > 2 else []))
    return f"<{tag}{parts}>{children}</{tag}>" if children else f"<{tag}{parts}/>"


def main() -> int:
    version = latest_version()
    print(f"lucide-static@{version}")

    nodes = json.loads(fetch(f"{JSDELIVR}@{version}/icon-nodes.json"))
    icons = {name: "".join(render(node) for node in node_list) for name, node_list in sorted(nodes.items())}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": version, "icons": icons}
    OUT.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    size = OUT.stat().st_size
    print(f"  {OUT.relative_to(PACKAGE.parent.parent.parent)}")
    print(f"  {len(icons):,} icons, {size:,} bytes ({size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
