"""`fjkit build-css` — compile the kit's stylesheets, one per style pack.

Runs when fjkit is released, not when an app runs. Consumers get the built files
in the wheel and never install Tailwind. That asymmetry is the point of
CHARTER.md A1, so this command lives in the `build` dependency group.

Eight packs, eight stylesheets, one served. The browser downloads only the one
`FjkitConfig.style` names; the other seven are bytes in the wheel no request
touches. Compressed they are ~24 KB each, so shipping all eight costs the
installer around 190 KB and costs the page nothing, which is what makes the
choice a config value rather than a reinstall.
"""

from __future__ import annotations

import gzip
import re
import shutil
import subprocess
import sys
from pathlib import Path

from fjkit.config import STATIC_DIR
from fjkit.vendored import DEFAULT_STYLE, STYLE_PACKS, StylePack

SRC = STATIC_DIR / "src" / "fjkit.css"
DIST = STATIC_DIR / "dist"

#: The one line in `src/fjkit.css` that names a pack. Anchored on the marker
#: comment rather than the filename, so a reformatted import breaks the build
#: loudly instead of silently compiling eight identical stylesheets.
_PACK_IMPORT = re.compile(r'^@import\s+"[^"]*basecoat-\w+\.css";\s*/\*\s*fjkit:style-pack\s*\*/\s*$', re.MULTILINE)


def output_for(style: str) -> Path:
    """Give the path a pack's stylesheet lands at. `mount_fjkit` and the shell
    read it too, so the URL a page requests and the file the build wrote cannot
    drift apart."""
    return DIST / f"fjkit-{style}.css"


def _entry_for(style: str) -> Path:
    """Write the per-pack Tailwind entry point.

    `src/fjkit.css` is the real source and stays readable and buildable on its
    own; this is that file with one import swapped. It is written next to the
    original because every other path in it — the `@source` globs, the vendor
    imports — is relative to the file's own directory.
    """
    text = SRC.read_text(encoding="utf-8")
    swapped, count = _PACK_IMPORT.subn(
        f'@import "../vendor/basecoat/basecoat-{style}.css"; /* fjkit:style-pack */',
        text,
    )
    if count != 1:
        raise SystemExit(
            f"{SRC} has {count} lines carrying the `fjkit:style-pack` marker, expected exactly 1.\n"
            "The builder rewrites that line to select a pack — restore the marker comment on the "
            "Basecoat import and try again."
        )

    entry = SRC.with_name(f".build-{style}.css")
    entry.write_text(swapped, encoding="utf-8")
    return entry


def _compile(style: str, watch: bool) -> int:
    entry = _entry_for(style)
    cmd = ["tailwindcss", "--input", str(entry), "--output", str(output_for(style))]
    cmd += ["--watch"] if watch else ["--minify"]
    try:
        return subprocess.run(cmd, cwd=STATIC_DIR.parent).returncode
    finally:
        # Kept alive for the whole of `--watch`, which only returns on Ctrl-C.
        entry.unlink(missing_ok=True)


def main(watch: bool = False, style: str | None = None) -> int:
    if shutil.which("tailwindcss") is None:
        print(
            "tailwindcss not found. It is a build-time dependency of fjkit itself:\n    uv sync --group build",
            file=sys.stderr,
        )
        return 2

    if style is not None and style not in STYLE_PACKS:
        print(f"unknown style pack {style!r}. Available: {', '.join(STYLE_PACKS)}", file=sys.stderr)
        return 2

    DIST.mkdir(parents=True, exist_ok=True)

    if watch:
        # One pack at a time: Tailwind's watcher owns the terminal, and a
        # rebuild loop over eight of them would report nothing useful.
        return _compile(style or DEFAULT_STYLE, watch=True)

    targets: tuple[StylePack, ...] = (style,) if style else STYLE_PACKS  # type: ignore[assignment]
    failed = 0
    for pack in targets:
        if _compile(pack, watch=False) != 0:
            return 1
        failed |= report(output_for(pack), default=pack == DEFAULT_STYLE)
    return failed


#: CHARTER.md §7. The budget is written in gzip because that is what a browser
#: downloads, and stdlib gzip measures it with no extra dependency. The raw
#: ceiling only catches a runaway.
#:
#: Per stylesheet, not per wheel: a page loads one pack, so one pack is what the
#: budget covers. Eight in the wheel is an install-size question, and an install
#: is not a page load.
GZIP_BUDGET = 28 * 1024
RAW_BUDGET = 260 * 1024


def report(path: Path, default: bool = False) -> int:
    """Print the size and return 1 if it is over budget. A budget nobody
    measures is a wish."""
    raw = path.stat().st_size
    compressed = len(gzip.compress(path.read_bytes(), 9))

    mark = "  (default)" if default else ""
    print(f"{path.name}  {raw:,} bytes raw  ·  {compressed:,} bytes gzip ({compressed / 1024:.1f} KB){mark}")

    over = []
    if compressed > GZIP_BUDGET:
        over.append(f"gzip over budget by {(compressed - GZIP_BUDGET) / 1024:.1f} KB")
    if raw > RAW_BUDGET:
        over.append(f"raw over budget by {(raw - RAW_BUDGET) / 1024:.1f} KB")

    if over:
        print("  " + "; ".join(over), file=sys.stderr)
        return 1
    return 0
