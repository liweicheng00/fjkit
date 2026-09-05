"""What is under the cursor, and where it leads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fjkit_lsp.index import _STRING, Index, Loc, Model, Template, _split_top, scan_template

_WORD = re.compile(r"[A-Za-z_]\w*")
#: An htmx event name: `task-changed` is one token, so hyphens belong to it.
_EVENT_TOKEN = re.compile(r"[A-Za-z_][\w-]*")
_BUILTINS = {
    "loop",
    "caller",
    "self",
    "super",
    "varargs",
    "kwargs",
    "request",
    "range",
    "dict",
    "lipsum",
    "cycler",
    "joiner",
    "namespace",
}


@dataclass
class Symbol:
    kind: str  # template | route | ident | attr | macro | py_field | py_class | file | event | url | target | id | none
    name: str = ""
    head: str = ""  # attr: the identifier chain head
    template: Template | None = None  # the template the cursor is in
    target: Template | None = None  # kind == template: the file the name resolved to
    model: Model | None = None  # py_field / py_class
    line: int = 0
    path: Path | None = None  # the file the cursor is in, for app-scoped lookups

    @property
    def near(self) -> Template | Path | None:
        return self.template or self.path


def _string_at(line_text: str, col: int) -> str | None:
    span = _string_span_at(line_text, col)
    return span[0] if span else None


def _string_span_at(line_text: str, col: int) -> tuple[str, int, int] | None:
    """(content, start, end) of the quoted string the cursor is inside."""
    for m in _STRING.finditer(line_text):
        if m.start() < col < m.end():
            return (m.group(1) or m.group(2) or ""), m.start(), m.end()
    return None


def _event_token_at(line_text: str, col: int) -> str | None:
    """The hyphenated token under the cursor: `task-changed` in `"click, task-changed from:body"`."""
    for m in _EVENT_TOKEN.finditer(line_text):
        if m.start() <= col <= m.end():
            return m.group(0)
    return None


def _word_at(line_text: str, col: int) -> tuple[str, int] | None:
    for m in _WORD.finditer(line_text):
        if m.start() <= col <= m.end():
            return m.group(0), m.start()
    return None


def _chain_head(line_text: str, start: int) -> str | None:
    """`a.b.c` with the cursor on `c` -> `a`; None when the word is not an attribute."""
    if start == 0 or line_text[start - 1] != ".":
        return None
    m = re.search(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.$", line_text[:start])
    return m.group(1).split(".")[0] if m else None


class Resolver:
    def __init__(self, index: Index) -> None:
        self.index = index

    # ---- what is here ---------------------------------------------------

    def symbol(self, path: Path, text: str, line: int, col: int) -> Symbol:
        lines = text.splitlines()
        line_text = lines[line] if line < len(lines) else ""
        span = _string_span_at(line_text, col)
        if span is not None:
            s, start, _end = span
            hit = self.index.resolve_template(s, path)
            if hit is not None:
                return Symbol("template", s, target=hit, line=line, path=path)
            if self.index.route_by_name(s):
                return Symbol("route", s, line=line, path=path)
            token = _event_token_at(line_text, col)
            if token and token in self.index.events(path):
                return Symbol("event", token, line=line, path=path)
            if s.startswith("/") and self.index.routes_for_url(s, path):
                return Symbol("url", s, line=line, path=path)
            if s.startswith("#") and len(s) > 1:
                return Symbol("target", s[1:], line=line, path=path)
            if re.search(r"\bid\s*=\s*$", line_text[:start]):
                return Symbol("id", s, line=line, path=path)
        if path.suffix == ".py":
            return self._python_symbol(path, line_text, line, col)
        known = self.index.template_at(path)
        name = known.name if known else self._logical_name(path)
        tpl = scan_template(path.resolve(), name, text)
        tpl.root = known.root if known else self.index.root_of(path)
        w = _word_at(line_text, col)
        if not w:
            return Symbol("file", name, template=tpl, line=line, path=path)
        word, start = w
        if word in tpl.macros and tpl.macros[word].loc.line == line:
            return Symbol("macro", word, template=tpl, line=line, path=path)
        head = _chain_head(line_text, start)
        if head:
            return Symbol("attr", word, head=head, template=tpl, line=line, path=path)
        return Symbol("ident", word, template=tpl, line=line, path=path)

    def _logical_name(self, path: Path) -> str:
        p = path.resolve()
        root = self.index.root_of(p)
        return p.relative_to(root).as_posix() if root else path.name

    def _target(self, sym: Symbol) -> Template | None:
        """The template a `template` symbol names, resolved from where it was named."""
        return sym.target or self.index.resolve_template(sym.name, sym.template)

    def _python_symbol(self, path: Path, line_text: str, line: int, col: int) -> Symbol:
        w = _word_at(line_text, col)
        if not w:
            return Symbol("none")
        word, _ = w
        p = path.resolve()
        const = self.index.constant(word, p)
        if const and const[0] in self.index.events(p):
            return Symbol("event", const[0], line=line, path=p)
        for models in self.index.models.values():
            for m in models:
                if m.module != p:
                    continue
                if m.name == word and m.loc.line == line:
                    return Symbol("py_class", word, model=m, line=line)
                f = m.fields.get(word)
                if f and f.line == line:
                    return Symbol("py_field", word, model=m, line=line)
        if word in self.index.models:
            return Symbol("py_class", word, model=self.index.resolve_model(word, p), line=line)
        return Symbol("none")

    # ---- where an identifier comes from ---------------------------------

    def _local(self, tpl: Template, name: str, line: int):
        params = [
            lo
            for lo in tpl.locals
            if lo.name == name
            and lo.kind == "param"
            and lo.loc.line <= line <= (lo.end_line if lo.end_line is not None else 10**9)
        ]
        if params:
            return params[-1]
        before = [lo for lo in tpl.locals if lo.name == name and lo.kind != "param" and lo.loc.line <= line]
        if before:
            return before[-1]
        after = [lo for lo in tpl.locals if lo.name == name and lo.kind != "param"]
        return after[0] if after else None

    def _field(self, tpl: Template, name: str) -> list[tuple[Model, Loc, str]]:
        """(owning model, location, route function) for every context model that has `name`."""
        out = []
        for route, model in self.index.context_models(tpl):
            hit = self.index.model_fields(model).get(name)
            if hit:
                out.append((hit[0], hit[1], route.func))
        return out

    def _types_of(self, tpl: Template, name: str, line: int, depth: int = 0) -> list[Model]:
        """Models an identifier may be an instance of (or a collection of)."""
        if depth > 4:
            return []
        lo = self._local(tpl, name, line)
        if lo and lo.kind == "for" and lo.source:
            return self._types_of(tpl, lo.source, lo.loc.line, depth + 1)
        if lo and lo.kind == "param":
            return self._param_types(tpl, lo, depth)
        out: list[Model] = []
        for owner, _loc, _route in self._field(tpl, name):
            ann = owner.annotations.get(name, "")
            for cand in re.findall(r"\b[A-Z]\w*\b", ann):
                m = self.index.resolve_model(cand, owner.module)
                if m and m not in out:
                    out.append(m)
        return out

    def _param_types(self, tpl: Template, lo, depth: int) -> list[Model]:
        """A macro parameter's type, inferred from what the call sites pass."""
        macro = next(
            (
                m
                for m in tpl.macros.values()
                if lo.name in m.params and m.loc.line <= lo.loc.line <= max(m.end_line, m.loc.line)
            ),
            None,
        )
        if macro is None:
            return []
        position = macro.params.index(lo.name)
        out: list[Model] = []
        for call in self.index.macro_references(tpl, macro.name):
            caller = self.index.by_path.get(call.path)
            if caller is None or call is macro.loc or (call.path == tpl.path and call.line == macro.loc.line):
                continue
            arg = _call_argument(caller.text, call, lo.name, position)
            if not arg:
                continue
            for m in self._types_of(caller, arg, call.line, depth + 1):
                if m not in out:
                    out.append(m)
        return out

    def definition(self, sym: Symbol) -> list[Loc]:
        ix = self.index
        if sym.kind == "template":
            t = self._target(sym)
            return [Loc(t.path, 0)] if t else []
        if sym.kind == "route":
            r = ix.route_by_name(sym.name)
            return [r.loc] if r else []
        # py_class / py_field answer nothing here on purpose: the cursor is on the
        # definition already, and Pyright answers the same location — a second
        # copy in the editor's list is noise. Their value is in `references`.
        if sym.kind == "event":
            # From a template: the routes that raise it. From Python, Pyright
            # already walks to the constant; only the listeners are new there.
            if sym.path and sym.path.suffix == ".py":
                return []
            return _dedupe([e.loc for _r, e in ix.events(sym.near).get(sym.name, [])])
        if sym.kind == "url":
            return [r.loc for r in ix.routes_for_url(sym.name, sym.near)]
        if sym.kind == "target":
            return ix.ids_named(sym.name, sym.near)
        tpl = sym.template
        if not tpl:
            return []
        if sym.kind == "macro":
            return [tpl.macros[sym.name].loc]
        if sym.kind == "attr":
            out = []
            for m in self._types_of(tpl, sym.head, sym.line):
                hit = ix.model_fields(m).get(sym.name)
                if hit:
                    out.append(hit[1])
            return out
        if sym.kind == "ident":
            lo = self._local(tpl, sym.name, sym.line)
            if lo and lo.kind == "import":
                tname, mname = tpl.imports.get(sym.name, ("", ""))
                target = ix.resolve_template(tname, tpl)
                if target and mname and mname in target.macros:
                    return [target.macros[mname].loc]
                if target:
                    return [Loc(target.path, 0)]
                return [lo.loc]
            if lo:
                return [lo.loc]
            if sym.name in tpl.macros:
                return [tpl.macros[sym.name].loc]
            fields = self._field(tpl, sym.name)
            if fields:
                return _dedupe([loc for _m, loc, _r in fields])
            if sym.name in ix.globals:
                return [ix.globals[sym.name]]
        return []

    # ---- who uses it ----------------------------------------------------

    def references(self, sym: Symbol) -> list[Loc]:
        ix = self.index
        if sym.kind == "event":
            emitters = [e.loc for _r, e in ix.events(sym.near).get(sym.name, [])]
            return _dedupe(ix.listeners(sym.name, sym.near) + emitters)
        if sym.kind == "url":
            return [r.loc for r in ix.routes_for_url(sym.name, sym.near)]
        if sym.kind in ("target", "id"):
            return ix.target_references(sym.name, sym.near)
        if sym.kind in ("template", "file"):
            t = sym.template if sym.kind == "file" else self._target(sym)
            if t is None:
                return []
            out = [loc for _label, loc in ix.references_to_template(t)]
            out.extend(r.loc for r in ix.routes_rendering(t))
            return _dedupe(out)
        if sym.kind == "route":
            pats = [rf"[\"']{re.escape(sym.name)}[\"']"]
            out = [loc for t in ix.by_path.values() for loc in ix.word_occurrences(t, pats, code_only=False)]
            r = ix.route_by_name(sym.name)
            return _dedupe(out + ([r.loc] if r else []))
        if sym.kind == "py_class" and sym.model:
            return _dedupe([r.loc for r in ix.routes if r.model == sym.model.name])
        if sym.kind == "py_field" and sym.model:
            return self._field_usages(sym.model, sym.name)
        tpl = sym.template
        if not tpl:
            return []
        if sym.kind == "macro":
            return ix.macro_references(tpl, sym.name)
        if sym.kind == "ident":
            lo = self._local(tpl, sym.name, sym.line)
            if lo and lo.kind == "import":
                tname, mname = tpl.imports.get(sym.name, ("", ""))
                target = ix.resolve_template(tname, tpl)
                return ix.macro_references(target, mname) if target and mname else []
            if lo:
                return ix.word_occurrences(tpl, [rf"\b{re.escape(sym.name)}\b"])
            if sym.name in tpl.macros:
                return ix.macro_references(tpl, sym.name)
            out: list[Loc] = []
            for owner, _loc, _route in self._field(tpl, sym.name):
                out.extend(self._field_usages(owner, sym.name))
            return _dedupe(out)
        if sym.kind == "attr":
            types = self._types_of(tpl, sym.head, sym.line)
            out = []
            for m in types:
                for loc in self._field_usages(m, sym.name, rf"\.{re.escape(sym.name)}\b"):
                    # Keep only occurrences whose own chain head is one of these models.
                    t = ix.by_path.get(loc.path)
                    if t is None:
                        continue
                    line_text = t.text.splitlines()[loc.line]
                    head = _chain_head(line_text, loc.col + 1)
                    if head and any(x in types for x in self._types_of(t, head, loc.line)):
                        out.append(Loc(loc.path, loc.line, loc.col + 1, loc.end_col))
            return _dedupe(out)
        return []

    def _field_usages(self, model: Model, name: str, pattern: str | None = None) -> list[Loc]:
        """Occurrences of a model field's name in every template that model reaches.

        A top-level field is matched as a bare identifier; `pattern` overrides
        that for an attribute (`.title`), which is searched in every template the
        *owning* model is rendered into — including through `for` loops, which
        is why the search is by name and not by chain.
        """
        ix = self.index
        seen: set[Path] = set()
        out: list[Loc] = []
        pat = pattern or rf"(?<![.\w]){re.escape(name)}\b"
        for r in ix.routes:
            rm = ix.resolve_model(r.model, r.module)
            if rm is None or (rm.name != model.name and model.name not in self._reachable(rm)):
                continue
            for tname in r.templates:
                start = ix.resolve_template(tname, r.module)
                if start is None:
                    continue
                for t in ix.descendants(start):
                    if t.path in seen:
                        continue
                    seen.add(t.path)
                    out.extend(ix.word_occurrences(t, [pat]))
        # A model used only through macros: search the macro files those templates import.
        for t in list(seen):
            tpl = ix.by_path[t]
            for tname, _m in set(tpl.imports.values()):
                target = ix.resolve_template(tname, tpl)
                if target and target.path not in seen:
                    seen.add(target.path)
                    out.extend(ix.word_occurrences(target, [pat]))
        return out

    def _reachable(self, model: Model, depth: int = 0) -> set[str]:
        """Names of models nested in this one's field annotations, transitively."""
        if depth > 3:
            return set()
        names: set[str] = set()
        for ann in model.annotations.values():
            for cand in re.findall(r"\b[A-Z]\w*\b", ann):
                m = self.index.resolve_model(cand, model.module)
                if m and m.name not in names:
                    names.add(m.name)
                    names |= self._reachable(m, depth + 1)
        return names

    # ---- hover ----------------------------------------------------------

    def hover(self, sym: Symbol) -> str | None:
        ix = self.index
        if sym.kind == "event":
            raised = ix.events(sym.near).get(sym.name, [])
            lines = [f"event **{sym.name}**"]
            for r, e in raised:
                header = "HX-Trigger-After-Swap" if e.after_swap else "HX-Trigger"
                via = f" via `{e.name}`" if e.is_const else ""
                lines.append(f"- raised by `{r.func}` ({_rel(r.loc.path)}:{r.loc.line + 1}) as {header}{via}")
            n = len(ix.listeners(sym.name, sym.near))
            lines.append(f"- {n} listener(s) in the templates" if n else "- no template listens for it")
            return "\n".join(lines)
        if sym.kind == "url":
            rs = ix.routes_for_url(sym.name, sym.near)
            return "\n".join(
                f"{r.method or '?'} `{r.path}` → `{r.func}` ({_rel(r.loc.path)}:{r.loc.line + 1})" for r in rs
            )
        if sym.kind == "target":
            hits = ix.ids_named(sym.name, sym.near)
            if not hits:
                return f"`#{sym.name}` — no element with that id in this application's templates"
            return "\n".join([f"`#{sym.name}`"] + [f"- `id` in {_rel(h.path)}:{h.line + 1}" for h in hits])
        if sym.kind == "id":
            n = len(ix.target_references(sym.name, sym.near))
            return f"`id=\"{sym.name}\"` — {n} `hx-*` reference(s)"
        if sym.kind == "template":
            t = self._target(sym)
            if not t:
                return None
            lines = [f"**{sym.name}** — `{_rel(t.path)}`"]
            for r in ix.routes_rendering(t):
                lines.append(f"- rendered by `{r.func}` ({_rel(r.loc.path)}:{r.loc.line + 1}) → `{r.model or '?'}`")
            for label, loc in ix.references_to_template(t):
                if label != "python":
                    lines.append(f"- {label} ({_rel(loc.path)}:{loc.line + 1})")
            return "\n".join(lines)
        if sym.kind == "route":
            r = ix.route_by_name(sym.name)
            return f"route **{sym.name}** → `{r.func}` ({_rel(r.loc.path)}:{r.loc.line + 1})" if r else None
        tpl = sym.template
        if sym.kind == "file" and tpl:
            return self.hover(Symbol("template", tpl.name, target=tpl))
        if sym.kind == "ident" and tpl:
            lo = self._local(tpl, sym.name, sym.line)
            if lo and lo.kind == "import":
                tname, mname = tpl.imports.get(sym.name, ("", ""))
                return f"`{sym.name}` — imported from **{tname}**" + (f" (macro `{mname}`)" if mname else "")
            if lo:
                extra = f" over `{lo.source}`" if lo.source else ""
                return f"`{sym.name}` — {lo.kind} at line {lo.loc.line + 1}{extra}"
            if sym.name in tpl.macros:
                return f"macro `{sym.name}` defined in this file"
            fields = self._field(tpl, sym.name)
            if fields:
                lines = [f"`{sym.name}` — context field"]
                by_model: dict[str, list[str]] = {}
                for owner, loc, route in fields:
                    ann = owner.annotations.get(sym.name, "")
                    by_model.setdefault(
                        f"- `{owner.name}.{sym.name}: {ann}` ({_rel(loc.path)}:{loc.line + 1})", []
                    ).append(route)
                for head, routes in by_model.items():
                    lines.append(f"{head} via " + ", ".join(f"`{r}`" for r in _uniq(routes)))
                return "\n".join(lines)
            if sym.name in ix.globals:
                g = ix.globals[sym.name]
                return f"`{sym.name}` — Jinja global ({_rel(g.path)}:{g.line + 1})"
            if sym.name in _BUILTINS:
                return f"`{sym.name}` — Jinja / fjkit builtin"
            routes = ix.context_routes(tpl)
            if routes:
                return f"`{sym.name}` — not found in {', '.join(sorted({r.model or '?' for r in routes}))}"
            return f"`{sym.name}` — no route renders **{tpl.name}**; only macro parameters are known here"
        if sym.kind == "attr" and tpl:
            types = self._types_of(tpl, sym.head, sym.line)
            hits = []
            for m in types:
                f = ix.model_fields(m).get(sym.name)
                if f:
                    owner, floc = f
                    ann = owner.annotations.get(sym.name, "")
                    hits.append(f"- `{owner.name}.{sym.name}: {ann}` ({_rel(floc.path)}:{floc.line + 1})")
            if hits:
                return "\n".join([f"`{sym.head}.{sym.name}`"] + hits)
            if types:
                return f"`{sym.head}` is `{' | '.join(m.name for m in types)}`; `{sym.name}` not found on it"
            return None
        if sym.kind == "py_field" and sym.model:
            n = len(self._field_usages(sym.model, sym.name))
            return f"`{sym.model.name}.{sym.name}` — {n} template occurrence(s)"
        if sym.kind == "py_class" and sym.model:
            rs = [r for r in ix.routes if r.model == sym.model.name]
            if not rs:
                return None
            return "\n".join(
                [f"`{sym.model.name}` is the context of:"] + [f"- `{r.func}` → {', '.join(r.templates)}" for r in rs]
            )
        return None


def _call_argument(text: str, call: Loc, param: str, position: int) -> str | None:
    """The head identifier of the argument a call passes for `param` (by keyword, else by position)."""
    lines = text.splitlines()
    if call.line >= len(lines):
        return None
    src = "\n".join(lines[call.line :])
    open_paren = src.find("(", call.col)
    if open_paren < 0:
        return None
    depth, i = 0, open_paren
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    args = _split_top(src[open_paren + 1 : i])
    for a in args:
        m = re.match(rf"\s*{re.escape(param)}\s*=\s*(.*)$", a, re.DOTALL)
        if m:
            return _head(m.group(1))
    positional = [a for a in args if not re.match(r"\s*\w+\s*=", a)]
    return _head(positional[position]) if position < len(positional) else None


def _head(expr: str) -> str | None:
    m = _WORD.match(expr.strip())
    return m.group(0) if m else None


def _rel(p: Path) -> str:
    try:
        return p.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return p.as_posix()


def _dedupe(locs: list[Loc]) -> list[Loc]:
    seen: set[tuple[Path, int, int]] = set()
    out = []
    for loc in locs:
        k = (loc.path, loc.line, loc.col)
        if k not in seen:
            seen.add(k)
            out.append(loc)
    return out


def _uniq(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
