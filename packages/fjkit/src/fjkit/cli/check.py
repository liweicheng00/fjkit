"""`fjkit check` — fail if an app template steps outside the vocabulary.

An enforced convention outlasts a documented one, so this ships as a CLI and as
a pytest assertion an app can put in its own suite.

Two families of violation:

1. **Colour literals** — a hex code, `oklch()`, a Tailwind palette hue,
   `text-white`. Colours belong to the token layer; a hue in markup breaks a
   later rebrand.
2. **Non-component classes** — anything outside the published component
   vocabulary. Layout is a component too (`stack`, `row`, `grid`), so an app
   template has no reason to say `flex gap-4`.

Two things are not checked.

**Jinja comments.** `{# … #}` never reaches the browser, so a colour named
inside one cannot break a rebrand. Scanning them stopped the rule describing
itself: `nav.html`'s signature comment explains why the brand tile must not say
`text-white`, and that sentence counted as a violation.

**An ejected file's classes.** The kit's rules judge a copy made by `fjkit
eject`, not the app's — see `_ejected_paths`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fjkit.cli.ejected import find_ejected, stale_ejects
from fjkit.cli.vocabulary import component_classes, emitted_classes

#: Every Tailwind utility that takes a colour, with the side or offset some of
#: them put first: bg-, border-t-, ring-offset- …
_COLOUR_UTILITY = (
    r"\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|divide|shadow|accent|caret|decoration|placeholder)"
    r"-(?:(?:[trblxyse]|offset)-)?"
)
#: Tailwind palette hues used as a colour utility: bg-blue-600, text-red-500 …
PALETTE = re.compile(
    _COLOUR_UTILITY + r"(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|"
    r"blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b"
)
#: Not after `&`, so a numeric entity such as `&#160;` is not a colour.
HEX = re.compile(r"(?<![&\w])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
FUNCS = re.compile(r"\b(?:rgb|rgba|hsl|hsla|hwb|oklch|oklab|lab|lch|color)\(")
ABSOLUTES = re.compile(_COLOUR_UTILITY + r"(?:white|black)\b")

COLOUR_CHECKS = [
    (PALETTE, "Tailwind palette hue — name a role instead (primary / muted / destructive / success …)"),
    (HEX, "hex literal — colours live in the token layer, not in markup"),
    (FUNCS, "raw colour function — colours live in the token layer, not in markup"),
    (ABSOLUTES, "absolute white/black — use the matching -foreground token"),
]

#: A CSS named colour is only a colour where a property reads one, so these are
#: looked for in `style="…"` declarations rather than everywhere: `red` in prose
#: is a word.
_STYLE_ATTR = re.compile(r"""(?<![\w-])style\s*=\s*(["'])(.*?)\1""", re.DOTALL)
_DECLARATION = re.compile(r"([\w-]+)\s*:\s*([^;]*)")
_COLOUR_PROPERTY = re.compile(r"colou?r|background|border|outline|fill|stroke|shadow|decoration|column-rule")
_WORD = re.compile(r"(?<![\w-])[A-Za-z]+(?![\w-])")
_CSS_NAMED_COLOURS = """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown
    burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan
    darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
    darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet
    deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro
    ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow
    lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray
    lightslategrey lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine
    mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab
    orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
    pink plum powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
    seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue tan
    teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen
"""
NAMED_COLOURS = frozenset(_CSS_NAMED_COLOURS.split())

#: `class="…"` including the multi-line form, which templates use a lot.
CLASS_ATTR = re.compile(r"""class\s*=\s*"([^"]*)\"""", re.DOTALL)

#: Jinja expressions are removed from a class attribute before it is split into
#: tokens. Splitting first is wrong: `class="card {{ extra }}"` tokenises to
#: `card`, `{{`, `extra`, `}}`, and `extra` then looks like a hand-written class
#: name. The checker cannot evaluate what an expression produces; the "never
#: build a class by interpolation" rule covers that case.
_JINJA_EXPR = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)

#: A Jinja comment, blanked out before either family of check runs.
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
_NOT_NEWLINE = re.compile(r"[^\n]")

#: An attribute or kwarg whose value is a URL or a CSS selector, blanked before
#: the colour checks: `hx-target="#feed"` names an element, not a hex colour.
_SELECTOR_VALUE = re.compile(
    r"""(?<![\w-])(?:href|action|formaction|xlink:href|usemap|"""
    r"""hx[-_](?:target|select|select[-_]oob|include|indicator|disabled[-_]elt|sync))\s*=\s*(["']).*?\1""",
    re.DOTALL,
)


def _blank(pattern: re.Pattern[str], text: str) -> str:
    """Replace every match with spaces of the same shape.

    Blanked rather than removed so every remaining character keeps its line
    number; the violation report is useful only if it points at the right line.
    """
    return pattern.sub(lambda m: _NOT_NEWLINE.sub(" ", m.group(0)), text)


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    token: str
    reason: str

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        return f"  {rel}:{self.line}  {self.token!r}\n      {self.reason}"


def _named_colours(path: Path, text: str) -> list[Violation]:
    found = []
    for attr in _STYLE_ATTR.finditer(text):
        for decl in _DECLARATION.finditer(attr.group(2)):
            if not _COLOUR_PROPERTY.search(decl.group(1)):
                continue
            for word in _WORD.finditer(decl.group(2)):
                if word.group(0).lower() in NAMED_COLOURS:
                    at = attr.start(2) + decl.start(2) + word.start()
                    found.append(
                        Violation(
                            path,
                            text.count("\n", 0, at) + 1,
                            word.group(0),
                            "named colour — colours live in the token layer, not in markup",
                        )
                    )
    return found


def _ejected_paths(template_dir: Path) -> frozenset[Path]:
    """Return the files `fjkit eject` wrote, exempt from the class rule.

    The escape hatch has to be usable. A kit macro writes utility classes — that
    is its job, and why an app never has to — so a copy of one fails the
    closed-vocabulary rule the moment it lands. Judging an ejected file by the
    app's rules would make the supported way to change a component produce a red
    build, which amounts to not supporting it.

    So the kit's rules judge a stamped file instead. Colours still belong to the
    token layer, which survives an eject: a hue in an ejected macro breaks a
    rebrand as it would anywhere else. The closed vocabulary does not apply,
    because it is a promise the kit makes to the app about classes the app did
    not write.

    The whole class family is dropped rather than only the utilities: without a
    built stylesheet `emitted_classes()` is empty and every utility looks like a
    typo, so allowing utilities while still catching typos would report a clean
    eject as broken on any machine that has not run `fjkit build-css`.

    Only at `ui/<name>.html`, the one path `eject` writes for that name. A stamp
    anywhere else marks nothing the kit wrote, so it exempts nothing. An
    orphaned copy at its own path keeps the exemption: the app cannot rewrite a
    kit macro without utilities, so failing it would leave no way back to green.
    """
    return frozenset(e.path for e in find_ejected(template_dir) if e.path == template_dir / "ui" / f"{e.name}.html")


def check_templates(template_dir: Path) -> list[Violation]:
    """Collect every violation in an app's template directory, in file order."""
    allowed = component_classes()
    emitted = emitted_classes()
    ejected = _ejected_paths(template_dir)
    violations: list[Violation] = []

    paths = sorted(template_dir.rglob("*.html")) + sorted(template_dir.rglob("*.jinja"))
    for path in paths:
        text = _blank(_JINJA_COMMENT, path.read_text(encoding="utf-8"))

        for lineno, line in enumerate(_blank(_SELECTOR_VALUE, text).splitlines(), 1):
            for pattern, reason in COLOUR_CHECKS:
                for match in pattern.finditer(line):
                    violations.append(Violation(path, lineno, match.group(0), reason))
        violations.extend(_named_colours(path, text))

        if path in ejected:
            continue

        for match in CLASS_ATTR.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            for token in _JINJA_EXPR.sub(" ", match.group(1)).split():
                if "{" in token or "}" in token:
                    continue  # an unbalanced fragment of an expression
                # Strip Tailwind variant prefixes so `sm:grid-cols-2` is judged
                # on `grid-cols-2` rather than treated as an unknown name.
                bare = token.rsplit(":", 1)[-1]
                if bare in allowed or bare.lstrip("-") in allowed:
                    continue
                if bare in emitted:
                    reason = (
                        "utility class in an app template — use a fjkit layout or component macro "
                        "(stack / row / grid / split / card / table …). Utilities that fjkit happens "
                        "to emit today are not part of its public vocabulary."
                    )
                else:
                    reason = (
                        "not a fjkit class — it is absent from the shipped stylesheet, so it has no "
                        "effect. Check the spelling, or use a component macro."
                    )
                violations.append(Violation(path, lineno, token, reason))

    return violations


def assert_templates_clean(template_dir: Path) -> None:
    """Raise `AssertionError` listing every violation. For an app's own suite.

    from fjkit.cli.check import assert_templates_clean

    def test_templates_stay_in_the_vocabulary():
        assert_templates_clean(Path("app/templates"))
    """
    violations = check_templates(template_dir)
    if violations:
        listing = "\n".join(v.render(template_dir) for v in violations)
        raise AssertionError(f"{len(violations)} fjkit vocabulary violation(s):\n{listing}")


def main(template_dir: Path) -> int:
    if not template_dir.is_dir():
        print(f"fjkit check: {template_dir} is not a directory")
        return 2

    violations = check_templates(template_dir)
    stale = stale_ejects(template_dir)

    if violations:
        print(f"{len(violations)} violation(s) in {template_dir}:\n")
        print("\n".join(v.render(template_dir) for v in violations))
    else:
        count = len(list(template_dir.rglob("*.html")))
        print(f"{count} template(s) clean — every class is part of the fjkit vocabulary")

    # Printed either way, and never changes the exit code. Ejecting is a
    # supported escape hatch, so a diverged copy is the feature working, not a
    # fault. Failing a build on it would push people back to editing the kit in
    # place, which eject exists to avoid.
    if stale:
        print(f"\nnote: {len(stale)} ejected component(s) behind the kit:\n")
        print("\n".join(e.render(template_dir) for e in stale))

    return 1 if violations else 0
