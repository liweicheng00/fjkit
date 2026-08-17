"""`fjkit check` — fail if an app template steps outside the vocabulary.

A convention nobody can violate accidentally is worth more than one written
down in a doc, so this ships as a CLI *and* as a pytest assertion an app can
put in its own suite.

Two families of violation:

1. **Colour literals** — a hex code, `oklch()`, a Tailwind palette hue,
   `text-white`. Colours belong to the token layer; a hue in markup is a
   rebrand waiting to fail.
2. **Non-component classes** — anything that is not part of the published
   component vocabulary. Layout is a component too (`stack`, `row`, `grid`),
   so there is no legitimate reason for an app template to say `flex gap-4`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
#: name. The checker cannot evaluate what an expression produces, and the
#: "never build a class by interpolation" rule is what covers that case.
_JINJA_EXPR = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Violation:
    path: Path
    line: int
    token: str
    reason: str

    def render(self, root: Path) -> str:
        rel = self.path.relative_to(root).as_posix()
        return f"  {rel}:{self.line}  {self.token!r}\n      {self.reason}"


def check_templates(template_dir: Path) -> list[Violation]:
    """Every violation in an app's template directory, in file order."""
    allowed = component_classes()
    emitted = emitted_classes()
    violations: list[Violation] = []

    paths = sorted(template_dir.rglob("*.html")) + sorted(template_dir.rglob("*.jinja"))
    for path in paths:
        text = path.read_text(encoding="utf-8")

        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, reason in COLOUR_CHECKS:
                for match in pattern.finditer(line):
                    violations.append(Violation(path, lineno, match.group(0), reason))

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
    """Raise `AssertionError` listing every violation. For an app's test suite.

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
    if violations:
        print(f"{len(violations)} violation(s) in {template_dir}:\n")
        print("\n".join(v.render(template_dir) for v in violations))
        return 1

    count = len(list(template_dir.rglob("*.html")))
    print(f"{count} template(s) clean — every class is part of the fjkit vocabulary")
    return 0
