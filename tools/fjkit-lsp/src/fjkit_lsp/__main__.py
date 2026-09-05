"""`fjkit-lsp` — stdio language server, or a command-line query.

fjkit-lsp                         start the server (stdio)
fjkit-lsp where tasks/_board.html who renders, includes or imports a template
                                  (a path, when two apps share the name)
fjkit-lsp var tasks/_board.html tasks
                                  where a template identifier comes from
fjkit-lsp at FILE LINE COL        definition + references for a cursor position
fjkit-lsp index                   a summary of what was indexed
"""

from __future__ import annotations

import sys
from pathlib import Path

from fjkit_lsp.index import Index, Loc
from fjkit_lsp.resolve import Resolver, Symbol, _rel


def _fmt(loc: Loc) -> str:
    return f"{_rel(loc.path)}:{loc.line + 1}:{loc.col + 1}"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from fjkit_lsp.server import start

        start()
        return 0
    cmd, *rest = argv
    index = Index([Path.cwd()])
    rs = Resolver(index)
    if cmd == "index":
        print("app roots:")
        for r in index.app_roots:
            print(f"  {_rel(r)}")
        print("shared roots (every app sees these, in this order):")
        for r in index.shared_roots:
            print(f"  {_rel(r)}")
        n_models = sum(len(v) for v in index.models.values())
        print(f"{len(index.by_path)} templates, {len(index.routes)} routes, {n_models} models")
        events = index.events()
        if events:
            print("events: " + ", ".join(f"{k} ({len(v)})" for k, v in sorted(events.items())))
        return 0
    if cmd == "where":
        tpl = _template(index, rest[0])
        if not tpl:
            print(f"unknown template {rest[0]}")
            return 1
        sym = Symbol("template", tpl.name, target=tpl)
        print(rs.hover(sym) or "")
        for loc in rs.references(sym):
            print("  ", _fmt(loc))
        return 0
    if cmd == "var":
        tpl, ident = _template(index, rest[0]), rest[1]
        if not tpl:
            print(f"unknown template {rest[0]}")
            return 1
        sym = Symbol("ident", ident, template=tpl, line=len(tpl.text.splitlines()))
        print(rs.hover(sym))
        for loc in rs.definition(sym):
            print("  ", _fmt(loc))
        return 0
    if cmd == "at":
        path, line, col = Path(rest[0]), int(rest[1]) - 1, int(rest[2]) - 1
        sym = rs.symbol(path, path.read_text(encoding="utf-8"), line, col)
        print(f"{sym.kind} {sym.name}" + (f" (head {sym.head})" if sym.head else ""))
        print(rs.hover(sym) or "")
        print("definition:")
        for loc in rs.definition(sym):
            print("  ", _fmt(loc))
        print("references:")
        for loc in rs.references(sym):
            print("  ", _fmt(loc))
        return 0
    print(__doc__)
    return 2


def _template(index: Index, arg: str):
    """A path names one file; a bare template name is read on the default chain,
    which is why the path form is the one to reach for when two apps share a name."""
    p = Path(arg)
    if p.exists():
        return index.template_at(p) or index.resolve_template(arg)
    return index.resolve_template(arg)


if __name__ == "__main__":
    raise SystemExit(main())
