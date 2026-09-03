"""What classes an app is allowed to write.

There is no hand-maintained whitelist. The component vocabulary is derived from
the CSS that ships, so it cannot drift from reality and nobody has to update it
when a component lands.

Two sets matter:

* **Component classes** — `btn`, `card`, `badge`, `table`, `input`, … the public
  vocabulary, harvested from Basecoat's component stylesheets and fjkit's own
  component layer.
* **Everything else** — utility classes (`flex`, `gap-4`, `text-muted-
  foreground`) and classes that do not exist at all.

App templates are refused utilities even though they work today. An app leaning
on `gap-4` because fjkit's shell emits it breaks silently the day the shell
stops emitting it. A class you did not put in the stylesheet is not yours to
depend on.
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

#: Classes fjkit's own shell and layout macros emit that an app needs to write
#: itself. Kept tiny: every entry is a hole in the closed vocabulary, so adding
#: one should feel expensive.
EXTRA_ALLOWED: frozenset[str] = frozenset(
    {
        # Set by the shell's flash-guard script and read by Basecoat's dark
        # variant. An app that renders its own <html> needs it.
        "dark",
    }
)


@cache
def component_classes() -> frozenset[str]:
    """Collect every class name Basecoat and fjkit define as a component."""
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
    """Collect every class present in the built stylesheet.

    Used only to tell two failures apart: a utility that exists, where the
    message says to use a macro, from a name that exists nowhere, a typo. Before
    the stylesheet is built, everything unknown is reported as a typo, which is
    still actionable.
    """
    # Any pack will do: the packs differ in declarations, not in which utilities
    # Tailwind emitted, and this set only separates a utility from a typo. The
    # default comes first, so the answer is stable when several are built.
    built = next(
        (p for p in (STATIC_DIR / "dist" / f"fjkit-{s}.css" for s in (DEFAULT_STYLE, *STYLE_PACKS)) if p.exists()),
        None,
    )
    if built is None:
        return frozenset()
    # Escaped selectors in built Tailwind look like `.sm\:grid-cols-2`; the
    # backslashes carry nothing this function needs.
    text = built.read_text(encoding="utf-8").replace("\\", "")
    return frozenset(_CLASS_SELECTOR.findall(text))
