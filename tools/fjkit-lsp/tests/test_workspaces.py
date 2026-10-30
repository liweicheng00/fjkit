"""Workspaces this repository does not have, built in a temporary directory:
formatting, encodings and layouts the demos never exercise."""

from __future__ import annotations

import os
import subprocess
import sys
import time
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
LSP_SRC = Path(__file__).resolve().parents[1] / "src"
KIT = {
    f"{SITE}/fjkit/__init__.py": "",
    f"{SITE}/fjkit/templates/ui/button.html": "{% macro button() %}{% endmacro %}\n",
}


def _metadata(name: str) -> str:
    return f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\nRequires-Dist: fjkit>=0.1\n"


def _project(name: str, *deps: str) -> str:
    requires = ", ".join(f'"{d}"' for d in ("fjkit", *deps))
    return f'[project]\nname = "{name}"\nversion = "1.0"\ndependencies = [{requires}]\n'


def _cli(ws: Path, *args: str, path: list[Path]) -> subprocess.CompletedProcess[str]:
    """`fjkit-lsp` as the venv's interpreter would run it: `-S` leaves this test's own
    site-packages out, and PYTHONPATH stands in for that venv's `sys.path`."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(p) for p in [*path, LSP_SRC])}
    return subprocess.run(
        [sys.executable, "-S", "-m", "fjkit_lsp", *args], cwd=ws, env=env, capture_output=True, text=True, check=True
    )


def _definition(ws: Path, template: str, line: int, needle: str, path: list[Path]) -> str:
    text = (ws / template).read_text(encoding="utf-8")
    col = text.split("\n")[line - 1].index(needle) + 2
    out = _cli(ws, "at", template, str(line), str(col), path=path).stdout
    return out.split("definition:", 1)[1].split("references:", 1)[0].strip()


def _roots(ws: Path, path: list[Path]) -> tuple[list[str], list[str]]:
    """(app roots, shared roots) as `fjkit-lsp index` lists them."""
    lines = _cli(ws, "index", path=path).stdout.split("\n")
    at = lines.index("shared roots (every app sees these, in this order):")
    return [ln.strip() for ln in lines[1:at]], [ln.strip() for ln in lines[at + 1 :] if ln.startswith("  ")]


def test_the_kit_and_a_plugin_installed_in_the_workspace_venv_are_found(tmp_path: Path) -> None:
    """The deployment the editor extension starts: `.venv/bin/fjkit-lsp` in the user's
    project, with fjkit and its plugins in that venv's site-packages."""
    page = (
        '{% from "ui/button.html" import button %}\n'
        '{% include "acme/card.html" %}\n'
        '{% import "fjkit/ui/button.html" as kit %}\n'
    )
    ws = _workspace(
        tmp_path,
        {
            **KIT,
            f"{SITE}/acme_cards/__init__.py": "",
            f"{SITE}/acme_cards/templates/acme/card.html": "<div></div>\n",
            f"{SITE}/acme_cards-1.0.dist-info/METADATA": _metadata("acme-cards"),
            "app/templates/page.html": page,
        },
    )
    path = [ws / SITE]
    assert _definition(ws, "app/templates/page.html", 1, "ui/button.html", path) == (
        f"{SITE}/fjkit/templates/ui/button.html:1:1"
    )
    assert _definition(ws, "app/templates/page.html", 2, "acme/card.html", path) == (
        f"{SITE}/acme_cards/templates/acme/card.html:1:1"
    )
    assert _definition(ws, "app/templates/page.html", 3, "fjkit/ui/button.html", path) == (
        f"{SITE}/fjkit/templates/ui/button.html:1:1"
    )


def test_an_app_installed_into_its_own_venv_is_not_a_plugin(tmp_path: Path) -> None:
    """`uv sync` installs the project itself, editable, into `.venv`, and it requires
    fjkit like a plugin does. Two such apps and one plugin they share, all developed
    here: the apps keep their own `base.html`, the plugin stays visible to both."""
    files = dict(KIT)
    for name, deps in (("alpha", ("cards",)), ("beta", ("cards",)), ("cards", ())):
        files[f"{name}/pyproject.toml"] = _project(name, *deps)
        files[f"{name}/src/{name}/__init__.py"] = ""
        files[f"{SITE}/{name}-1.0.dist-info/METADATA"] = _metadata(name)
    for app in ("alpha", "beta"):
        files[f"{app}/src/{app}/templates/base.html"] = f"<title>{app}</title>\n"
        files[f"{app}/src/{app}/templates/page.html"] = '{% extends "base.html" %}\n{% include "cards/deck.html" %}\n'
    files["cards/src/cards/templates/cards/deck.html"] = "<ul></ul>\n"
    ws = _workspace(tmp_path, files)
    # An editable install is a `.pth` line: the project's `src` is on `sys.path`.
    path = [ws / SITE, ws / "alpha/src", ws / "beta/src", ws / "cards/src"]

    apps, shared = _roots(ws, path)
    assert apps == ["alpha/src/alpha/templates", "beta/src/beta/templates"]
    assert shared == ["cards/src/cards/templates", f"{SITE}/fjkit/templates"]
    page = "beta/src/beta/templates/page.html"
    assert _definition(ws, page, 1, "base.html", path) == "beta/src/beta/templates/base.html:1:1"
    assert _definition(ws, page, 2, "cards/deck.html", path) == "cards/src/cards/templates/cards/deck.html:1:1"


def test_a_non_editable_copy_of_the_app_in_site_packages_is_not_indexed(tmp_path: Path) -> None:
    """`uv sync --no-editable` copies the app into site-packages. The workspace holds
    the live source; the copy is stale and must appear in no answer."""
    ws = _workspace(
        tmp_path,
        {
            **KIT,
            "pyproject.toml": _project("alpha"),
            "src/alpha/__init__.py": "",
            "src/alpha/templates/base.html": "<title>alpha</title>\n",
            "src/alpha/templates/page.html": '{% extends "base.html" %}\n',
            f"{SITE}/alpha/__init__.py": "",
            f"{SITE}/alpha/templates/base.html": "<title>alpha, yesterday</title>\n",
            f"{SITE}/alpha/templates/page.html": '{% extends "base.html" %}\n',
            f"{SITE}/alpha-1.0.dist-info/METADATA": _metadata("alpha"),
        },
    )
    path = [ws / SITE]
    apps, shared = _roots(ws, path)
    assert apps == ["src/alpha/templates"]
    assert shared == [f"{SITE}/fjkit/templates"]
    out = _cli(ws, "where", "src/alpha/templates/base.html", path=path).stdout
    assert "extends in page.html (src/alpha/templates/page.html:1)" in out
    assert SITE not in out


def test_a_route_in_an_installed_plugin_is_the_definition_of_its_url_for(tmp_path: Path) -> None:
    """Why a plugin's Python is indexed and not only its templates: the app's templates
    name the plugin's routes, and nothing else knows where those are."""
    routes = (
        "from fastapi import APIRouter\n"
        "\n"
        'router = APIRouter(prefix="/acme")\n'
        "\n"
        "\n"
        '@router.get("/cards", name="acme_cards")\n'
        "def cards(): ...\n"
    )
    ws = _workspace(
        tmp_path,
        {
            **KIT,
            f"{SITE}/acme_cards/__init__.py": "",
            f"{SITE}/acme_cards/routes.py": routes,
            f"{SITE}/acme_cards/templates/acme/card.html": "<div></div>\n",
            f"{SITE}/acme_cards-1.0.dist-info/METADATA": _metadata("acme-cards"),
            "app/templates/page.html": '{{ url_for(request, "acme_cards") }}\n',
        },
    )
    assert _definition(ws, "app/templates/page.html", 1, "acme_cards", [ws / SITE]) == (
        f"{SITE}/acme_cards/routes.py:7:1"
    )


def test_an_interpreter_without_fjkit_says_so_and_names_itself(tmp_path: Path) -> None:
    """`uvx fjkit-lsp` or a `fjkit.lsp.command` pointing anywhere but the project's venv:
    the kit's templates cannot be found, and the only remedy is to start the server
    from the right interpreter, so the message has to say which one this was."""
    ws = _workspace(tmp_path, {"app/templates/page.html": '{% from "ui/button.html" import button %}\n'})
    out = _cli(ws, "index", path=[])
    assert "app/templates" in out.stdout
    assert "fjkit" in out.stderr and sys.executable in out.stderr


def test_the_server_warns_once_about_a_missing_kit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The editor shows the warning on start; a rebuild on every save must not repeat it."""
    from fjkit_lsp import server as srv
    from lsprotocol import types as t

    monkeypatch.setattr("fjkit_lsp.index.installed_packages", list)
    shown: list[t.ShowMessageParams] = []
    ls = srv.FjkitServer()
    monkeypatch.setattr(ls, "window_show_message", shown.append)
    ws = _workspace(tmp_path, {"app/templates/page.html": "<p></p>\n"})
    ls.build([ws])
    ls.build([ws])
    assert [m.type for m in shown] == [t.MessageType.Warning]
    assert sys.executable in shown[0].message
