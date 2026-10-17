"""Workspaces this repository does not have, built in a temporary directory:
formatting, encodings and layouts the demos never exercise."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

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


def test_a_form_feed_does_not_shift_the_line_under_the_cursor(tmp_path: Path) -> None:
    """LSP counts lines by `\\n` alone; `str.splitlines()` also breaks on `\\x0c`."""
    text = 'Terms\x0cconditions\n{% extends "base.html" %}\n'
    ws = _workspace(tmp_path, {"app/templates/base.html": "<html></html>\n", "app/templates/page.html": text})
    rs = Resolver(Index([ws]))
    sym = rs.symbol(ws / "app/templates/page.html", text, *_cursor(text, '"base.html"', "base"))
    assert sym.kind == "template"
    assert sym.target is not None and sym.target.path == ws / "app/templates/base.html"


def test_a_file_that_is_not_utf8_does_not_stop_the_index(tmp_path: Path) -> None:
    """A coding cookie is valid Python; a Latin-1 mail template is skipped, not fatal."""
    legacy = '# -*- coding: latin-1 -*-\n@router.get("/caf\xe9")\ndef legacy(): ...\n'
    ws = _workspace(
        tmp_path,
        {
            "app/legacy.py": legacy.encode("latin-1"),
            "app/templates/mail.txt": "Gr\xfc\xdfe\n".encode("latin-1"),
            "app/templates/page.html": "<p></p>\n",
        },
    )
    ix = Index([ws])
    assert ws / "app/templates/page.html" in ix.by_path
    assert [(r.func, r.path) for r in ix.routes if r.module.is_relative_to(ws)] == [("legacy", "/caf\xe9")]


def test_the_index_does_not_read_inside_a_virtualenv(tmp_path: Path) -> None:
    """The server rebuilds on every save, so a 10,000-file `.venv` must cost nothing."""
    ws = _workspace(tmp_path, {"app/templates/page.html": "<p></p>\n", "app/main.py": "x = 1\n"})

    def build_ms() -> float:
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            Index([ws])
            best = min(best, (time.perf_counter() - start) * 1000)
        return best

    without = build_ms()
    for i in range(100):
        package = ws / f".venv/lib/python3.13/site-packages/pkg{i}"
        package.mkdir(parents=True)
        for j in range(100):
            (package / f"m{j}.py").touch()
    assert build_ms() - without < 150


def test_a_checkout_under_a_src_directory_keeps_its_applications_apart(tmp_path: Path) -> None:
    """`~/src/<repo>` is a common place to clone into; it does not make every app a distribution."""
    files = {}
    for app in ("alpha", "beta"):
        files[f"src/repo/{app}/app/templates/base.html"] = f"{app}\n"
        files[f"src/repo/{app}/app/templates/page.html"] = '{% extends "base.html" %}\n'
    repo = _workspace(tmp_path, files) / "src/repo"
    ix = Index([repo])
    page = ix.by_path[repo / "beta/app/templates/page.html"]
    hit = ix.resolve_template("base.html", page)
    assert hit is not None and hit.path == repo / "beta/app/templates/base.html"


SITE = ".venv/lib/python3.13/site-packages"


def test_the_kit_and_a_plugin_installed_in_the_workspace_venv_are_found(tmp_path: Path) -> None:
    """The deployment the editor extension starts: `.venv/bin/fjkit-lsp` in the user's
    project, with fjkit and its plugins in that venv's site-packages."""
    page = (
        '{% from "ui/button.html" import button %}\n'
        '{% include "acme/card.html" %}\n'
        '{% import "fjkit/ui/button.html" as kit %}\n'
    )
    plugin_metadata = "Metadata-Version: 2.1\nName: acme-cards\nVersion: 1.0\nRequires-Dist: fjkit>=0.1\n"
    ws = _workspace(
        tmp_path,
        {
            f"{SITE}/fjkit/__init__.py": "",
            f"{SITE}/fjkit/templates/ui/button.html": "{% macro button() %}{% endmacro %}\n",
            f"{SITE}/acme_cards/__init__.py": "",
            f"{SITE}/acme_cards/templates/acme/card.html": "<div></div>\n",
            f"{SITE}/acme_cards-1.0.dist-info/METADATA": plugin_metadata,
            "app/templates/page.html": page,
        },
    )
    # The server runs on that venv's interpreter; PYTHONPATH puts its site-packages first.
    env = {**os.environ, "PYTHONPATH": str(ws / SITE)}

    def definition(line: int, needle: str) -> str:
        col = page.split("\n")[line - 1].index(needle) + 2
        out = subprocess.run(
            [sys.executable, "-m", "fjkit_lsp", "at", "app/templates/page.html", str(line), str(col)],
            cwd=ws,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return out.split("definition:", 1)[1].split("references:", 1)[0].strip()

    assert definition(1, "ui/button.html") == f"{SITE}/fjkit/templates/ui/button.html:1:1"
    assert definition(2, "acme/card.html") == f"{SITE}/acme_cards/templates/acme/card.html:1:1"
    assert definition(3, "fjkit/ui/button.html") == f"{SITE}/fjkit/templates/ui/button.html:1:1"
