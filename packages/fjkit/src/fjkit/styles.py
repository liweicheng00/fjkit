"""Which style pack a page loads, and how that gets decided.

All eight packs are built and shipped inside the wheel, so this module never
chooses what exists — only what is selected. There are two ways to say it, and
they answer different questions:

    uv add "fjkit[nova]"          at install time, for a project that picks once
    FjkitConfig(style="nova")     in code, for one that wants it in the config

The first works through a marker distribution — `fjkit-style-nova`, a package
carrying one entry point and no CSS. The indirection is forced: a Python extra
can only pull in another distribution, and cannot change a byte of the wheel it
belongs to. So `fjkit[nova]` leaves a marker behind, and this is where fjkit
finds it.

Config always wins over marker. An explicit value in code is someone saying it
on purpose; a marker is what the environment was installed with.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Literal

from fjkit.vendored import DEFAULT_STYLE, STYLE_PACKS, StylePack

__all__ = ["ENTRY_POINT_GROUP", "installed_packs", "resolve_style"]

#: Where a marker distribution announces itself.
ENTRY_POINT_GROUP = "fjkit.style"


def installed_packs() -> tuple[StylePack, ...]:
    """The packs named by installed marker distributions, in a stable order.

    Only the entry point's name is read — the module it points at is never
    imported, so a marker costs nothing at startup beyond the metadata scan
    importlib already does.

    An unrecognised name is ignored rather than fatal: a stale marker left by an
    uninstall should not stop an app booting, and the pack it names would not be
    in the wheel to serve anyway.
    """
    names = {ep.name for ep in entry_points(group=ENTRY_POINT_GROUP)}
    return tuple(pack for pack in STYLE_PACKS if pack in names)


def resolve_style(style: StylePack | Literal["auto"]) -> StylePack:
    """Turn a configured value into the pack the shell links.

    `"auto"` is the default, and with nothing installed it lands on
    `DEFAULT_STYLE` — so an app that never heard of any of this keeps the
    stylesheet it always had.
    """
    if style != "auto":
        return style

    match installed_packs():
        case ():
            return DEFAULT_STYLE
        case (pack,):
            return pack
        case packs:
            # Picking one silently would make the page's appearance depend on
            # metadata scan order, which is the kind of bug that survives a
            # bisect. Two installed packs is a question only a human can answer.
            listed = ", ".join(packs)
            extra = " ".join(f"fjkit-style-{pack}" for pack in packs[1:])
            raise RuntimeError(
                f"fjkit found {len(packs)} style packs installed ({listed}) and cannot choose between them.\n"
                f"Either remove the ones you do not want:  uv remove {extra}\n"
                f"or say which one in code, which always wins:  FjkitConfig(style={packs[0]!r})"
            )
