"""Which style pack a page loads.

All eight packs are built and shipped inside the wheel, so this module never
chooses what exists — only what is selected, and there is one way to say it:

    FjkitConfig(style="nova")

Install-time selection (`uv add "fjkit[nova]"`) was removed before 0.1.0. It
took eight marker distributions to express, because a Python extra can only
pull in another distribution and cannot change a byte of the wheel it belongs
to — eight PyPI names and eight version streams to carry one word that the
config already says.
"""

from __future__ import annotations

from typing import Literal

from fjkit.vendored import DEFAULT_STYLE, StylePack

__all__ = ["resolve_style"]


def resolve_style(style: StylePack | Literal["auto"]) -> StylePack:
    """Turn a configured value into the pack the shell links.

    `"auto"` is the default and lands on `DEFAULT_STYLE`, so an app that never
    heard of style packs keeps the stylesheet it always had.
    """
    return DEFAULT_STYLE if style == "auto" else style
