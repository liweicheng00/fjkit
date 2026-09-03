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

#: Tailwind palette hues used as a colour utility: bg-blue-600, text-red-500 …
PALETTE = re.compile(
    r"\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|divide|shadow|accent|caret|decoration)"
    r"-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|"
    r"blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3}\b"
)
HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
FUNCS = re.compile(r"\b(?:rgb|rgba|hsl|hsla|oklch|oklab|lab|lch)\(")
ABSOLUTES = re.compile(r"\b(?:bg|text|border|ring|fill|stroke)-(?:white|black)\b")

COLOUR_CHECKS = [
    (PALETTE, "Tailwind palette hue — name a role instead (primary / muted / destructive / success …)"),
    (HEX, "hex literal — colours live in the token layer, not in markup"),
    (FUNCS, "raw colour function — colours live in the token layer, not in markup"),
    (ABSOLUTES, "absolute white/black — use the matching -foreground token"),
]

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


def _without_comments(text: str) -> str:
    """Replace every `{# … #}` with spaces of the same shape.

    Blanked rather than removed so every remaining character keeps its line
    number; the violation report is useful only if it points at the right line.
    """
    return _JINJA_COMMENT.sub(lambda m: _NOT_NEWLINE.sub(" ", m.group(0)), text)


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    token: str
    reason: str

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        return f"  {rel}:{self.line}  {self.token!r}\n      {self.reason}"


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
    """
    return frozenset(e.path for e in find_ejected(template_dir))


def check_templates(template_dir: Path) -> list[Violation]:
    """Collect every violation in an app's template directory, in file order."""
    allowed = component_classes()
    emitted = emitted_classes()
    ejected = _ejected_paths(template_dir)
    violations: list[Violation] = []

    paths = sorted(template_dir.rglob("*.html")) + sorted(template_dir.rglob("*.jinja"))
    for path in paths:
        text = _without_comments(path.read_text(encoding="utf-8"))

        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, reason in COLOUR_CHECKS:
                for match in pattern.finditer(line):
                    violations.append(Violation(path, lineno, match.group(0), reason))

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
