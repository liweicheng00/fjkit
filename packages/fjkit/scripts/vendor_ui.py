"""Vendor the front-end assets into the fjkit package.

Everything the browser loads is pinned and committed into the wheel, so an
app that installs fjkit has no Node.js step, no CDN at runtime, and nothing to
vendor itself.

    uv run python packages/fjkit/scripts/vendor_ui.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

# Single source of truth lives in the package, so the footer the shell renders
# cannot drift from the bytes on disk.
from fjkit.vendored import BASECOAT_VERSION, HTMX_JSON_ENC_VERSION, HTMX_VERSION, PLOTLY_VERSION  # noqa: E402

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "fjkit"
ROOT = PACKAGE
VENDOR = PACKAGE / "static" / "vendor"

JSDELIVR = "https://cdn.jsdelivr.net/npm"
DATA_API = "https://data.jsdelivr.com/v1/packages/npm"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read()


def write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    print(f"  {path.relative_to(ROOT)}  ({len(payload):,} bytes)")


def package_files(package: str, version: str) -> list[str]:
    """Flatten the jsDelivr file listing for a package into '/dist/...' paths."""
    listing = json.loads(fetch(f"{DATA_API}/{package}@{version}"))
    paths: list[str] = []

    def walk(nodes: list[dict], prefix: str = "") -> None:
        for node in nodes:
            if node["type"] == "directory":
                walk(node["files"], f"{prefix}/{node['name']}")
            else:
                paths.append(f"{prefix}/{node['name']}")

    walk(listing["files"])
    return paths


def vendor_basecoat() -> None:
    print(f"basecoat-css@{BASECOAT_VERSION}")
    files = package_files("basecoat-css", BASECOAT_VERSION)

    # Tailwind *source* CSS (uses @apply / @layer) so the CLI can tree-shake it
    # against our templates. The prebuilt dist/*.cdn.css is ~220 KB; building
    # from source gets us an order of magnitude less.
    css = [
        p
        for p in files
        if p.startswith("/dist/")
        and p.endswith(".css")
        and ".cdn" not in p
        and "/compat/" not in p
        and not p.startswith("/dist/basecoat-compat")
    ]
    for path in css:
        write(
            VENDOR / "basecoat" / path.removeprefix("/dist/"),
            fetch(f"{JSDELIVR}/basecoat-css@{BASECOAT_VERSION}{path}"),
        )

    # Behaviour for the components that cannot be CSS-only.
    write(
        VENDOR / "basecoat" / "js" / "all.min.js",
        fetch(f"{JSDELIVR}/basecoat-css@{BASECOAT_VERSION}/dist/js/all.min.js"),
    )

    # Upstream also ships Jinja macros under /templates/jinja/. They are
    # deliberately NOT vendored: their assumptions are the ones this kit exists
    # to reject — inline `onclick` handlers, randomly generated ids that htmx
    # cannot target, `| safe` on every caller-supplied string, and a trigger
    # button baked into the component. fjkit writes its own macros against the
    # same CSS instead, so what comes down from upstream is stylesheets and the
    # behaviour bundle, nothing that renders.


def vendor_htmx() -> None:
    print(f"htmx.org@{HTMX_VERSION}")
    write(
        VENDOR / "htmx" / "htmx.min.js",
        fetch(f"{JSDELIVR}/htmx.org@{HTMX_VERSION}/dist/htmx.min.js"),
    )

    # Beside the core, because it is an htmx extension and reads as one on
    # disk. Not minified upstream and not minified here: it is 1 KB of
    # readable source, and a build step to save 300 bytes is the exact trade
    # this project exists to refuse. No page loads it unless it says so —
    # `form_scripts()`, and `HTMX_JSON_ENC_VERSION` says why.
    print(f"htmx-ext-json-enc@{HTMX_JSON_ENC_VERSION}")
    write(
        VENDOR / "htmx" / "json-enc.js",
        fetch(f"{JSDELIVR}/htmx-ext-json-enc@{HTMX_JSON_ENC_VERSION}/json-enc.js"),
    )


def vendor_plotly() -> None:
    # The basic bundle, not the full one — `PLOTLY_VERSION` says why. Served
    # from the kit's static mount like htmx, and loaded by nothing but the page
    # that calls `chart_scripts()`.
    print(f"plotly.js-basic-dist-min@{PLOTLY_VERSION}")
    write(
        VENDOR / "plotly" / "plotly-basic.min.js",
        fetch(f"{JSDELIVR}/plotly.js-basic-dist-min@{PLOTLY_VERSION}/plotly-basic.min.js"),
    )


if __name__ == "__main__":
    vendor_basecoat()
    vendor_htmx()
    vendor_plotly()
    print("\nNow rebuild the stylesheet:  uv run fjkit build-css")
