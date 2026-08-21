"""What classes an app is allowed to write.

The key idea: there is no hand-maintained whitelist. The component vocabulary is
*derived* from the CSS that actually ships, so it cannot drift from reality and
nobody has to remember to update it when a component lands.

Two sets matter:

* **Component classes** — `btn`, `card`, `badge`, `table`, `input`, … These are
  the public vocabulary. Harvested from Basecoat's component stylesheets and
  fjkit's own component layer.
* **Everything else** — utility classes (`flex`, `gap-4`, `text-muted-
  foreground`) and classes that do not exist at all.

Utilities are rejected in app templates *even though they work today*. That is
the whole point: if an app leans on `gap-4` because fjkit's shell happens to
emit it, the app breaks silently the day fjkit's shell stops emitting it. A
class you did not put in the stylesheet is not yours to depend on.
"""

from __future__ import annotations

import re
from functools import cache

from fjkit.config import STATIC_DIR
from fjkit.vendored import DEFAULT_STYLE, STYLE_PACKS

#: `@apply flex gap-4;` inside a component definition names utilities, not
#: component classes. Strip those lines before harvesting.
_APPLY = re.compile(r"@apply[^;]*;")
_CLASS_SELECTOR = re.compile(r"\.(-?[A-Za-z_][\w-]*)")

#: Classes fjkit's own shell and layout macros emit that an app legitimately
#: needs to write itself. Kept tiny on purpose — every entry here is a hole in
#: the closed vocabulary, so adding one should feel expensive.
EXTRA_ALLOWED: frozenset[str] = frozenset(
    {
        # Set by the shell's flash-guard script and read by Basecoat's dark
        # variant. An app that renders its own <html> needs it.
        "dark",
    }
)


@cache
def component_classes() -> frozenset[str]:
    """Every class name Basecoat and fjkit define as a component."""
    names: set[str] = set(EXTRA_ALLOWED)

    sources = [
        *(STATIC_DIR / "vendor" / "basecoat" / "components").glob("*.css"),
        *(STATIC_DIR / "vendor" / "basecoat" / "base").glob("*.css"),
        STATIC_DIR / "src" / "fjkit.css",
    ]
    for path in sources:
        if not path.exists():
            continue
        names.update(_CLASS_SELECTOR.findall(_APPLY.sub("", path.read_text(encoding="utf-8"))))

    return frozenset(names)


@cache
def emitted_classes() -> frozenset[str]:
    """Every class present in the built stylesheet.

    Used only to tell two failures apart: a utility that exists (so the message
    should say "use a macro") from a name that exists nowhere (a typo). If the
    stylesheet has not been built yet, everything unknown is reported as a typo,
    which is still actionable.
    """
    # Any pack will do: the packs differ in declarations, not in which
    # utilities Tailwind emitted, and this set only exists to tell "that class
    # is a utility" apart from "that class is a typo". The default first, so
    # the answer is stable when several are built.
    built = next(
        (p for p in (STATIC_DIR / "dist" / f"fjkit-{s}.css" for s in (DEFAULT_STYLE, *STYLE_PACKS)) if p.exists()),
        None,
    )
    if built is None:
        return frozenset()
    # Escaped selectors in built Tailwind look like `.sm\:grid-cols-2`; the
    # backslashes are noise for our purposes.
    text = built.read_text(encoding="utf-8").replace("\\", "")
    return frozenset(_CLASS_SELECTOR.findall(text))
