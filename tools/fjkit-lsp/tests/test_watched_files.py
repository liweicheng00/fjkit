"""`workspace/didChangeWatchedFiles`: an edit on disk updates the files it names,
and only a change that can reshape the index rebuilds it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fjkit_lsp import server as srv
from lsprotocol import types as t
from pygls.uris import from_fs_path

ROUTES = 'from fastapi import APIRouter\n\nrouter = APIRouter()\n\n\n@router.get("/old")\ndef page(): ...\n'


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path.resolve()
    files = {
        "app/templates/page.html": '{% include "card.html" %}\n',
        "app/templates/card.html": "<div></div>\n",
        "app/routes.py": ROUTES,
    }
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def ls(monkeypatch: pytest.MonkeyPatch, ws: Path) -> srv.FjkitServer:
    monkeypatch.setattr("fjkit_lsp.index.installed_packages", list)
    server = srv.FjkitServer()
    monkeypatch.setattr(server, "window_show_message", lambda _m: None)
    monkeypatch.setattr(server, "roots", lambda: [ws])
    server.build([ws])
    return server


def _notify(ls: srv.FjkitServer, *events: tuple[Path, t.FileChangeType]) -> None:
    changes = [t.FileEvent(uri=from_fs_path(str(p)) or "", type=kind) for p, kind in events]
    srv.on_files_changed(ls, t.DidChangeWatchedFilesParams(changes=changes))


def test_an_edited_template_is_reread_without_a_rebuild(ls: srv.FjkitServer, ws: Path) -> None:
    before = ls.index
    page = ws / "app/templates/page.html"
    page.write_text('{% include "card.html" %}\n{% include "other.html" %}\n', encoding="utf-8")
    _notify(ls, (page, t.FileChangeType.Changed))
    assert ls.index is before
    assert [r.name for r in ls.index.by_path[page].refs] == ["card.html", "other.html"]
    assert ls.index.templates["page.html"] is ls.index.by_path[page]


def test_an_edited_module_replaces_its_own_routes_only(ls: srv.FjkitServer, ws: Path) -> None:
    before = ls.index
    module = ws / "app/routes.py"
    module.write_text(ROUTES.replace("/old", "/new"), encoding="utf-8")
    _notify(ls, (module, t.FileChangeType.Changed))
    assert ls.index is before
    assert [r.path for r in ls.index.routes] == ["/new"]


def test_a_created_or_deleted_file_rebuilds(ls: srv.FjkitServer, ws: Path) -> None:
    other = ws / "app/templates/other.html"
    other.write_text("<p></p>\n", encoding="utf-8")
    before = ls.index
    _notify(ls, (other, t.FileChangeType.Created))
    assert ls.index is not before and other in ls.index.by_path
    other.unlink()
    before = ls.index
    _notify(ls, (other, t.FileChangeType.Deleted))
    assert ls.index is not before and other not in ls.index.by_path


def test_a_changed_pyproject_rebuilds(ls: srv.FjkitServer, ws: Path) -> None:
    """It decides which installed distributions are plugins and which the app."""
    pyproject = ws / "pyproject.toml"
    pyproject.write_text('[project]\nname = "app"\n', encoding="utf-8")
    before = ls.index
    _notify(ls, (pyproject, t.FileChangeType.Changed))
    assert ls.index is not before


def test_a_uv_sync_inside_the_virtualenv_changes_nothing(ls: srv.FjkitServer, ws: Path) -> None:
    site = ws / ".venv/lib/python3.13/site-packages"
    events = []
    for i in range(50):
        module = site / f"pkg{i}/__init__.py"
        module.parent.mkdir(parents=True)
        module.touch()
        events += [(module, t.FileChangeType.Created), (module.parent, t.FileChangeType.Created)]
    before = ls.index
    _notify(ls, *events, (ws / "app/tests/test_x.py", t.FileChangeType.Created))
    assert ls.index is before


def test_a_text_file_outside_any_templates_directory_is_ignored(ls: srv.FjkitServer, ws: Path) -> None:
    notes = ws / "notes.txt"
    notes.write_text("todo\n", encoding="utf-8")
    before = ls.index
    _notify(ls, (notes, t.FileChangeType.Changed))
    assert ls.index is before


def test_a_deleted_directory_drops_the_files_under_it(ls: srv.FjkitServer, ws: Path) -> None:
    """A folder removed in the explorer arrives as one event for the folder."""
    templates = ws / "app/templates"
    for f in templates.iterdir():
        f.unlink()
    templates.rmdir()
    _notify(ls, (templates, t.FileChangeType.Deleted))
    assert not ls.index.by_path
