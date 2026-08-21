"""Inline Lucide icons.

A dict lookup and one `<svg>` — no icon font, no sprite request, no runtime JS.
Only the icons a page actually calls end up in the response, so shipping the
whole set costs package size but nothing on the wire.

The set is loaded from JSON on first use rather than imported as a Python
module. Two reasons: `import fjkit` stays fast for an app that renders no icons
on its hot path, and a version bump is a one-line diff in a data file instead
of a 20,000-line one in the source tree.

Regenerate with:  uv run python packages/fjkit/scripts/vendor_icons.py
"""

from __future__ import annotations

import json
from difflib import get_close_matches
from functools import cache

from markupsafe import Markup

from fjkit.config import STATIC_DIR

__all__ = ["path", "names", "version"]

_DATA = STATIC_DIR / "icons" / "lucide.json"


@cache
def _icons() -> dict[str, str]:
    return json.loads(_DATA.read_text(encoding="utf-8"))["icons"]


@cache
def version() -> str:
    """The vendored lucide-static version. Reported in the shell's footer."""
    return json.loads(_DATA.read_text(encoding="utf-8"))["version"]


def path(name: str) -> Markup:
    """The inner SVG markup for one icon.

    Raises on an unknown name rather than rendering an empty box — a silently
    missing icon is the kind of bug that ships. The suggestion matters more
    than it looks: with 1,767 names, `arrow-right` vs `arrow-right-circle` is
    a coin flip from memory.
    """
    icons = _icons()
    try:
        return Markup(icons[name])
    except KeyError:
        suggestion = get_close_matches(name, icons, n=3)
        hint = f" Did you mean: {', '.join(suggestion)}?" if suggestion else ""
        raise KeyError(f"fjkit has no icon named {name!r}.{hint}") from None


def names() -> list[str]:
    """Every available icon name, sorted. Used by the docs page and tests."""
    return sorted(_icons())
