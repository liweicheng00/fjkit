"""`fjkit eject` — take one macro out of the kit's reach, and only one.

A component template is a file of macros: `ui/data.html` holds fifteen. The
loader searches the app's directory first (CHARTER.md A5), so a file the app
writes at `ui/data.html` shadows the kit's and every call site keeps working.
That is the escape hatch. Copying the whole file used to be the only way to walk
it, so changing `badge` silently cost the other fourteen macros' upstream fixes,
permanently.

So the file an eject writes owns only what was asked for, and re-exports the
rest:

    {# fjkit:eject data 0.2.1 macros:badge=1f0c9a2d3456 #}
    {% import "fjkit/ui/data.html" as _fjkit %}
    …
    {% set card = _fjkit.card %}
    {% macro badge(label, variant="default") %}…your version…{% endmacro %}
    {% set stat = _fjkit.stat %}
    …

`{% set card = _fjkit.card %}` binds the kit's macro object under the name the
module exports, so `{% from "ui/data.html" import card %}` at a call site still
reaches the kit's implementation, including through `{% call %}` blocks and
`**kwargs`, because it is the same object rather than a wrapper. When the kit
fixes `card`, the app gets the fix on its next upgrade. Only the macro taken
diverges.

Three details make it work.

**The reserved namespace.** The override is `ui/data.html`, so it cannot import
`ui/data.html` to reach what it shadows. `fjkit/ui/data.html` is a second name
for the package's own copy that nothing can shadow — see
`fjkit.templating._ReservedNamespace`.

**Private macros are copied, not borrowed.** Jinja keeps a name starting with
`_` out of a module's namespace, so `_fjkit._message` does not exist, and a
macro that calls one takes a copy. Across the kit that is one macro,
`form.html`'s `_message`. Dropping the underscore would fix the tooling by
promoting an implementation detail to public API, which is the wrong trade.

**Source order is preserved.** Every kept statement — the imports, the lookup
tables, the macros — appears where it did upstream, with a one-line re-export
standing in for each macro not taken. A diff against the kit's file then shows
only what changed.

Measured on the kit's worst case: `eject text_field` writes 81 lines against
`form.html`'s 327, seventeen of them the header explaining itself, and the app
diverges from upstream on two of twelve macros instead of all twelve.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from jinja2 import Environment, TemplateSyntaxError, nodes

# `ejected` reaches back the other way for `kit_macro_digests`, but only from
# inside a function, so this stays one-directional at module level.
from fjkit.cli.ejected import STAMP, digest, macro_stamp, stamp_line
from fjkit.config import TEMPLATE_DIR

#: Where components live, inside the kit and inside an app's template dir alike.
UI = "ui"


@dataclass(frozen=True, slots=True)
class Macro:
    """One `{% macro %}` in a component file, with the lines it occupies."""

    name: str
    #: `{% macro … %}` … `{% endmacro %}`, verbatim.
    body: str
    #: The `{# … #}` block directly above it — the signature contract. Carried
    #: along on an eject, and kept out of the digest: a reworded paragraph
    #: should not report the copy as behind.
    doc: str
    #: Every name its body reads, locals and parameters included. Those match
    #: nothing the file binds at the top level, so they cost nothing.
    uses: frozenset[str]

    @property
    def is_private(self) -> bool:
        """Jinja keeps `_`-prefixed names out of the module namespace, so this
        macro cannot be re-exported and has to be copied."""
        return self.name.startswith("_")


@dataclass(frozen=True, slots=True)
class Statement:
    """A top-level `{% from %}`, `{% import %}` or `{% set %}` — the imports and
    the closed lookup tables a component's macros read."""

    #: Verbatim, all of its lines. `{% set _ROWS = { … } %}` spans seven, which
    #: is why a tag's end is found by pairing and not by `lineno`.
    text: str
    #: The `{# … #}` block directly above. A lookup table's comment is often the
    #: signature contract of the macro that reads it: `field_row`'s explanation
    #: of why `template` is a key and not a raw grid string sits above `_ROWS`,
    #: not above the macro.
    doc: str
    binds: frozenset[str]
    uses: frozenset[str]


@dataclass(frozen=True, slots=True)
class Component:
    """One `ui/*.html`, taken apart far enough to rebuild a subset of it."""

    name: str
    path: Path
    source: str
    #: Every top-level statement in source order, macros and the rest mixed,
    #: because the override reproduces that order and a diff against the kit's
    #: file then shows only what changed.
    items: tuple[Macro | Statement, ...]
    macros: dict[str, Macro]

    @property
    def template(self) -> str:
        return f"{UI}/{self.name}.html"

    def closure(self, name: str) -> list[str]:
        """List `name` plus every private macro it needs, transitively.

        Public siblings are left out because they are re-exported: an owned
        macro calling one still calls the kit's.
        """
        taken: list[str] = []
        pending = [name]
        while pending:
            current = pending.pop(0)
            if current in taken:
                continue
            taken.append(current)
            macro = self.macros[current]
            pending.extend(n for n in sorted(macro.uses) if n in self.macros and self.macros[n].is_private)
        return taken

    def needed_statements(self, owned: Iterable[Macro]) -> set[int]:
        """Select the imports and lookup tables the owned macros read.

        Copying all of them is simpler, and wrong: `_ROWS` copied beside a
        `text_field` that never reads it falls silently behind the kit's, while
        the macro that does read it — re-exported `field_row` — goes on using
        the kit's. Dead weight that looks live.

        `owned` may include an author's own macro from the override, so that a
        helper they wrote which reads `_WIDTH` gets the kit's table beside it.
        """
        statements = {i: item for i, item in enumerate(self.items) if isinstance(item, Statement)}
        wanted: set[str] = set()
        for macro in owned:
            wanted |= macro.uses
        keep: set[int] = set()
        changed = True
        while changed:
            changed = False
            for index, statement in statements.items():
                if index not in keep and statement.binds & wanted:
                    keep.add(index)
                    wanted |= statement.uses
                    changed = True
        return keep


def _tag_ends(env: Environment, source: str) -> dict[int, int]:
    """Map the first line of each `{% … %}` to the line its `%}` is on.

    A tag is not a line: `{% set _ROWS = { … } %}` spans seven, and slicing on
    `lineno` alone would cut a dict in half. The lexer already knows where every
    tag closes, so pair the tokens rather than guess from the text.
    """
    ends: dict[int, int] = {}
    start: int | None = None
    for lineno, token, _ in env.lex(source):
        if token == "block_begin":
            start = lineno
        elif token == "block_end" and start is not None:
            ends.setdefault(start, lineno)
            start = None
    return ends


def _comment_ends(env: Environment, source: str) -> dict[int, int]:
    """Map the last line of each `{# … #}` to the line it opened on."""
    ends: dict[int, int] = {}
    start: int | None = None
    for lineno, token, _ in env.lex(source):
        if token == "comment_begin":
            start = lineno
        elif token == "comment_end" and start is not None:
            ends[lineno] = start
            start = None
    return ends


def _is_blank(node: nodes.Node) -> bool:
    return isinstance(node, nodes.Output) and all(
        isinstance(child, nodes.TemplateData) and not child.data.strip() for child in node.nodes
    )


def _macro_end(env: Environment, source: str, ends: dict[int, int], start: int) -> int:
    """Find the `{% endmacro %}` closing the macro that opens at `start`.

    Counted rather than searched: Jinja allows a macro inside a macro, so the
    first `{% endmacro %}` after the opening can be the wrong one.
    """
    depth = 0
    opening: int | None = None
    for lineno, token, value in env.lex(source):
        if token == "block_begin":
            opening = lineno
        elif token == "name" and opening is not None and opening >= start:
            if value == "macro":
                depth += 1
            elif value == "endmacro":
                depth -= 1
                if depth == 0:
                    return ends[opening]
            opening = None
    raise ValueError(f"unterminated {{% macro %}} at line {start}")


def parse(path: Path, env: Environment | None = None) -> Component:
    """Split one component file into its statements and macros."""
    env = env or _env()
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tag_ends = _tag_ends(env, source)
    comment_ends = _comment_ends(env, source)

    def slice_lines(first: int, last: int) -> str:
        return "".join(lines[first - 1 : last])

    def doc_above(first: int) -> str:
        """Return the comment block directly above, skipping blank lines only."""
        above = first - 1
        while above >= 1 and not lines[above - 1].strip():
            above -= 1
        if above in comment_ends:
            return slice_lines(comment_ends[above], above)
        return ""

    items: list[Macro | Statement] = []
    macros: dict[str, Macro] = {}

    for node in env.parse(source).body:
        if _is_blank(node):
            continue
        if isinstance(node, nodes.Macro):
            last = _macro_end(env, source, tag_ends, node.lineno)
            macro = Macro(
                name=node.name,
                body=slice_lines(node.lineno, last),
                doc=doc_above(node.lineno),
                uses=frozenset(_reads(node)),
            )
            macros[node.name] = macro
            items.append(macro)
        elif isinstance(node, nodes.FromImport | nodes.Import | nodes.Assign) and node.lineno in tag_ends:
            items.append(
                Statement(
                    text=slice_lines(node.lineno, tag_ends[node.lineno]),
                    doc=doc_above(node.lineno),
                    binds=frozenset(_binds(node)),
                    uses=frozenset(_reads(node)),
                )
            )
        else:
            # Output, {% block %} or {% if %} at the top level: `shell.html` is
            # a page skeleton, not a macro library. There is no macro to take,
            # so `eject shell` stays a whole-file copy and never reaches here.
            raise Unsplittable(path.stem)

    return Component(name=path.stem, path=path, source=source, items=tuple(items), macros=macros)


def _reads(node: nodes.Node) -> set[str]:
    return {n.name for n in node.find_all(nodes.Name) if n.ctx == "load"}


def _binds(node: nodes.Node) -> set[str]:
    """Collect the names a top-level statement puts into the module namespace."""
    if isinstance(node, nodes.FromImport):
        return {n[1] if isinstance(n, tuple) else n for n in node.names}
    if isinstance(node, nodes.Import):
        return {node.target}
    # `find_all` walks descendants, and `{% set _ROWS = … %}`'s target is a bare
    # `Name` with no descendants, so it has to be read directly.
    target = node.target
    if isinstance(target, nodes.Name):
        return {target.name}
    return {n.name for n in target.find_all(nodes.Name)}


class Unsplittable(Exception):
    """A component file that is not purely a macro library."""


@cache
def _env() -> Environment:
    """Build a bare Environment for parsing only.

    Not `build_environment()`: parsing needs the same syntax settings, not the
    loaders, the globals or a plugin's `extend` hook. `eject` runs in a CLI with
    no app.
    """
    return Environment(trim_blocks=True, lstrip_blocks=True, autoescape=True)


@cache
def components() -> dict[str, Path]:
    return {p.stem: p for p in sorted((TEMPLATE_DIR / UI).glob("*.html"))}


def resolve(name: str) -> tuple[str, str | None]:
    """Turn what was typed into `(component, macro)`; macro None means the file.

    `fjkit eject data` still means the whole of `data.html`: a file name wins
    over a macro name, so nothing that worked before changes meaning. `fjkit
    eject badge` means that one macro, found by searching every component. A
    name two components both define is refused rather than guessed at, and
    `data.badge` says which.
    """
    if "." in name:
        component, _, macro = name.partition(".")
        if component not in components() or macro not in parse_or_none(components()[component]):
            raise Unknown(name)
        holders = [component]
    elif name in components():
        return name, None
    else:
        macro = name
        holders = [component for component, path in components().items() if macro in parse_or_none(path)]
        if not holders:
            raise Unknown(name)

    if macro.startswith("_"):
        raise Private(macro, holders)
    if len(holders) > 1:
        raise Ambiguous(name, holders)
    return holders[0], macro


class Unknown(Exception):
    def __init__(self, name: str) -> None:
        self.name = name

    def __str__(self) -> str:
        macros = sorted({m for p in components().values() for m in parse_or_none(p) if not m.startswith("_")})
        return (
            f"fjkit eject: nothing named {self.name!r}.\n"
            f"Components: {', '.join(components())}\n"
            f"Macros: {', '.join(macros)}"
        )


class Private(Exception):
    """A `_`-prefixed macro asked for on its own. A copy of one changes nothing:
    the kit's macros keep calling the kit's copy (see the module docstring), so
    the only way to take it is with a public macro that calls it."""

    def __init__(self, macro: str, holders: list[str]) -> None:
        self.macro = macro
        self.holders = holders

    def __str__(self) -> str:
        callers = [
            f"{component}.{name}"
            for component in self.holders
            for name, held in parse_or_none(components()[component]).items()
            if self.macro in held.uses and not held.is_private
        ]
        return (
            f"fjkit eject: {self.macro!r} is private, so a copy of it on its own changes nothing:\n"
            f"the kit's macros keep calling the kit's copy. It comes along with any public macro\n"
            f"that calls it. Take one of those instead: {', '.join(callers)}"
        )


class Ambiguous(Exception):
    def __init__(self, name: str, holders: list[str]) -> None:
        self.name = name
        self.holders = holders

    def __str__(self) -> str:
        options = ", ".join(f"{c}.{self.name}" for c in self.holders)
        return f"fjkit eject: {self.name!r} is defined by {len(self.holders)} components. Say which: {options}"


def render_override(component: Component, owned: list[str], version: str) -> str:
    """Render the override: the kit's structure, holes filled by re-exports.

    `owned` is every macro this copy takes — what was asked for, plus the
    private helpers Jinja will not let it borrow.
    """
    taken = [n for n in component.macros if n in owned]
    keep = component.needed_statements(component.macros[n] for n in taken)

    parts = [
        macro_stamp(component.name, version, {n: digest_of(component, n) for n in taken}),
        _header(component, owned, version),
        f'{{% import "fjkit/{component.template}" as _fjkit %}}\n',
    ]
    for index, item in enumerate(component.items):
        if isinstance(item, Statement):
            if index in keep:
                parts.append("\n" + item.doc + item.text)
        elif item.name in owned:
            parts.append("\n" + item.doc + item.body)
        elif not item.is_private:
            parts.append(f"\n{{% set {item.name} = _fjkit.{item.name} %}}\n")
        # An unowned private macro is dropped: nothing left in this file calls
        # it, and the kit's own macros keep using the kit's copy.
    return "".join(parts)


class Unmergeable(Exception):
    """An override that a second eject cannot add a macro to without putting
    the author's edits at risk."""


def splice(target: Path, component: Component, macro: str, stamp: re.Match[str]) -> tuple[str, list[str]]:
    """Add one more macro to the override at `target`, which an earlier eject wrote.

    The file has been the author's since that eject, so nothing in it is
    regenerated. The one line fjkit still owns is the re-export it wrote for
    `macro`, `{% set stat = _fjkit.stat %}`, and that is all this replaces:
    with the kit's macro, the private helpers it needs that the file does not
    define yet, and the lookup tables it reads that the file does not bind. A
    helper the author already wrote stays theirs: the new macro calls that
    copy, and the stamp records no digest for a body fjkit did not write. The
    stamp keeps every digest it had and gains one per macro taken, so a kit
    that moved since the first eject still shows up in `fjkit check`. The
    header is rewritten only when it is still word for word what fjkit wrote.

    Returns the new source and the macros it added.

    Raises `Unmergeable` rather than guess when the file cannot be taken apart,
    the re-export line is not there exactly once, or the author already defines
    a macro named `macro`. Jinja would bind the name to whichever definition
    comes last, so one of the two would be dead code with no warning.
    """
    try:
        mine = parse(target)
    except Unsplittable:
        raise Unmergeable("has top-level content that is not a macro, an import or a `{% set %}`") from None
    except TemplateSyntaxError as exc:
        raise Unmergeable(f"does not parse: {exc}") from exc

    seam = f"{{% set {macro} = _fjkit.{macro} %}}\n"
    if mine.source.count(seam) != 1:
        raise Unmergeable(f"has no `{seam.strip()}` line for fjkit to replace")
    if macro in mine.macros:
        raise Unmergeable(
            f"already defines a macro named {macro!r} that fjkit did not write (rename yours to take the kit's)"
        )

    stamped = _stamped_macros(stamp["macros"])
    closure = [n for n in component.closure(macro) if n not in stamped]
    taken = [n for n in closure if n not in mine.macros]
    theirs = [mine.macros[n] for n in closure if n in mine.macros]
    bound = set(mine.macros).union(*(item.binds for item in mine.items if isinstance(item, Statement)))
    keep = component.needed_statements([*(component.macros[n] for n in taken), *theirs])

    parts: list[str] = []
    for index, item in enumerate(component.items):
        if isinstance(item, Statement):
            if index in keep and not item.binds <= bound:
                parts.append(item.doc + item.text)
        elif item.name in taken:
            parts.append(item.doc + item.body)
    body = mine.source.replace(seam, "\n".join(parts))

    old_header = _header(component, list(stamped), stamp["version"])
    if body.count(old_header) == 1:
        body = body.replace(old_header, _header(component, [*stamped, *taken], stamp["version"]))

    digests = {**stamped, **{n: digest_of(component, n) for n in taken}}
    _, rest = body.split("\n", 1)
    return macro_stamp(component.name, stamp["version"], digests) + rest, taken


def _header(component: Component, owned: list[str], version: str) -> str:
    taken = [n for n in component.macros if n in owned]
    asked = [n for n in taken if not n.startswith("_")]
    borrowed = [n for n in component.macros if n not in owned and not component.macros[n].is_private]
    copied = [n for n in taken if n not in asked]
    lines = [
        "{#",
        f"  Ejected from fjkit {version}: your copy of {_and(asked)},",
        f"  shadowing the kit's {component.template}. Edit {'them' if len(asked) > 1 else 'it'} freely.",
        "",
        f"  The other {len(borrowed)} macro(s) below are re-exported from the kit, and still get",
        "  its fixes. Call sites do not know the difference either way —",
        f'  {{% from "{component.template}" import … %}} keeps working.',
        "",
    ]
    if copied:
        lines += [
            f"  {_and(copied)} is here as a copy rather than a re-export because Jinja",
            "  keeps a `_`-prefixed macro out of a module's namespace, so there is no way to",
            "  borrow it. The kit's own macros go on using the kit's copy, not this one.",
            "",
        ]
    lines += [
        "  `fjkit check` names the macro when the kit's version of one you own moves on.",
        "  To take another macro, run `fjkit eject` again. It replaces that macro's re-export",
        "  line below and leaves the rest of this file as you have it. To give one back, put",
        "  `{% set <name> = _fjkit.<name> %}` where your copy was and drop `<name>=…` from the",
        "  stamp on line 1. To give all of them back, delete this file.",
        "#}",
        "",
    ]
    return "\n".join(lines)


def _and(names: list[str]) -> str:
    quoted = [f"`{n}`" for n in names]
    if len(quoted) < 2:
        return "".join(quoted)
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]


def digest_of(component: Component, macro: str) -> str:
    """Fingerprint one of the kit's macros: the `{% macro %}` block, no doc."""
    return digest(component.macros[macro].body)


def kit_macro_digests(name: str, wanted: list[str]) -> dict[str, str]:
    """Hash the installed kit's versions of `wanted`, skipping any it lacks."""
    path = components().get(name)
    if path is None:
        return {}
    macros = parse_or_none(path)
    return {m: digest(macros[m].body) for m in wanted if m in macros}


def main(name: str, into: Path) -> int:
    """Run the `fjkit eject` command."""
    try:
        component_name, macro = resolve(name)
    except (Unknown, Private, Ambiguous) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    component_path = components()[component_name]
    target = into / UI / f"{component_name}.html"
    existing = target.read_text(encoding="utf-8") if target.exists() else None
    stamp = STAMP.match(existing.splitlines()[0].strip()) if existing else None

    if existing is not None and stamp is None:
        print(f"fjkit eject: {target} already exists and fjkit did not write it", file=sys.stderr)
        return 1

    if macro is None:
        if stamp is not None and stamp["macros"]:
            owned = [n for n in _stamped_macros(stamp["macros"]) if not n.startswith("_")]
            print(
                f"fjkit eject: {target} already exists and owns {_and(owned)}; the other macros in\n"
                f"{component_name}.html are re-exported from the kit. Edit your copy there, or run\n"
                f"`fjkit eject <macro>` to take another. To copy the whole file instead, delete it\n"
                f"first and re-run; that discards your copy of {_and(owned)}.",
                file=sys.stderr,
            )
            return 1
        if existing is not None:
            print(
                f"fjkit eject: {target} already exists — it is a copy of the whole component,\n"
                f"so there is nothing left to take. Edit it, or delete it to go back to the kit's.",
                file=sys.stderr,
            )
            return 1
        source = component_path.read_text(encoding="utf-8")
        _write(target, stamp_line(component_name, _version(), source) + source)
        held = parse_or_none(component_path)
        advice = (
            f"All {len(held)} of its macros stop receiving upstream fixes. To take one and\n"
            f"keep the rest on the kit's, delete this and run `fjkit eject <macro>` instead."
            if held
            else f"{component_name}.html is a page skeleton rather than a macro library, so the\n"
            f"whole file is the only thing there is to take."
        )
        print(
            f"copied the whole of {component_name}.html to {target}\n"
            f"It now shadows fjkit's version — no import changes needed.\n" + advice
        )
        return 0

    if stamp is not None and not stamp["macros"]:
        # A copy of the whole file already owns this macro, along with every
        # other one in it, which someone may have spent a week editing.
        # Rewriting it into a one-macro override would delete that unasked.
        print(
            f"fjkit eject: {target} is a copy of the whole component, so it already owns\n"
            f"{macro!r} — and every other macro in the file. Edit it there. To narrow it down\n"
            f"to one macro, delete it first and re-run; that discards every edit in it.",
            file=sys.stderr,
        )
        return 1

    component = parse(component_path)

    already = list(_stamped_macros(stamp["macros"])) if stamp else []
    if macro in already:
        print(f"fjkit eject: {target} already owns {macro!r}", file=sys.stderr)
        return 1

    owned = list(dict.fromkeys([*already, *component.closure(macro)]))
    unknown = [n for n in owned if n not in component.macros]
    if unknown:
        print(
            f"fjkit eject: {target} claims macro(s) {', '.join(unknown)} the kit no longer ships.\n"
            f"Sort that out first — `fjkit check` explains it.",
            file=sys.stderr,
        )
        return 1

    if stamp is None:
        taken = component.closure(macro)
        _write(target, render_override(component, owned, _version()))
    else:
        try:
            text, taken = splice(target, component, macro, stamp)
        except Unmergeable as exc:
            print(
                f"fjkit eject: {target} {exc}, so it was left alone.\n"
                f"To take {macro!r} by hand, put the kit's macro from {component.path} where\n"
                f"`{{% set {macro} = _fjkit.{macro} %}}` goes and add `{macro}={digest_of(component, macro)}`\n"
                f"to the stamp on line 1.",
                file=sys.stderr,
            )
            return 1
        _write(target, text)

    extra = [n for n in taken if n != macro]
    print(
        f"{f'added {macro!r} to' if existing else 'wrote'} {target}\n"
        f"It owns {_and([n for n in owned if not n.startswith('_')])}"
        + (f", and copies {_and(extra)} because a private macro cannot be re-exported" if extra else "")
        + f".\nThe other {len(component.macros) - len(owned)} macro(s) are re-exported from the kit and still"
        f" get upstream fixes.\nNothing at any call site changes."
    )
    return 0


def parse_or_none(path: Path) -> dict[str, Macro]:
    try:
        return parse(path).macros
    except Unsplittable:
        return {}


def _stamped_macros(raw: str) -> dict[str, str]:
    """Read a `macros:` stamp into macro name → the kit's digest when taken."""
    return dict(entry.split("=", 1) for entry in raw.split(","))


def _write(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _version() -> str:
    """Read the installed fjkit version, for the eject stamp.

    Taken from the installed distribution rather than a `__version__` constant,
    because that is the single source hatchling already builds the wheel from.
    Running from a source tree with nothing installed does not fail the eject:
    the digest detects staleness, and the version is a readable note beside it.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("fjkit")
    except PackageNotFoundError:  # pragma: no cover - only outside an install
        return "unknown"
