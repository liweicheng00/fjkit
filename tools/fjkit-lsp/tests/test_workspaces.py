"""Workspaces this repository does not have, built in a temporary directory:
formatting, encodings and layouts the demos never exercise."""

from __future__ import annotations

from pathlib import Path

import pytest
from fjkit_lsp.index import Index
from fjkit_lsp.resolve import Resolver


def _workspace(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    root = tmp_path.resolve()
    for name, content in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return root


def _cursor(text: str, needle: str, on: str) -> tuple[int, int]:
    start = text.index(needle) + needle.index(on)
    return text.count("\n", 0, start), start - (text.rfind("\n", 0, start) + 1)


def test_an_hx_target_wrapped_onto_the_next_line_is_still_a_reference(tmp_path: Path) -> None:
    text = '<button hx-post="/go" hx-target=\n  "#board">go</button>\n<div id="board"></div>\n'
    ws = _workspace(tmp_path, {"app/templates/page.html": text})
    page = ws / "app/templates/page.html"
    rs = Resolver(Index([ws]))
    sym = rs.symbol(page, text, *_cursor(text, 'id="board"', "board"))
    assert sym.kind == "id"
    assert [(loc.line, loc.col) for loc in rs.references(sym)] == [(1, 3)]


@pytest.mark.xfail(strict=True, reason="LSP-7")
def test_a_form_feed_does_not_shift_the_line_under_the_cursor(tmp_path: Path) -> None:
    """LSP counts lines by `\\n` alone; `str.splitlines()` also breaks on `\\x0c`."""
    text = 'Terms\x0cconditions\n{% extends "base.html" %}\n'
    ws = _workspace(tmp_path, {"app/templates/base.html": "<html></html>\n", "app/templates/page.html": text})
    rs = Resolver(Index([ws]))
    sym = rs.symbol(ws / "app/templates/page.html", text, *_cursor(text, '"base.html"', "base"))
    assert sym.kind == "template"
    assert sym.target is not None and sym.target.path == ws / "app/templates/base.html"
