"""The demos are the fixture: every assertion names a real file under examples/.

Cursor positions are searched for rather than written down. The suite that this
one replaces pinned line and column numbers, and every edit to the demo broke it
somewhere unrelated to the navigation being tested.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fjkit_lsp.index import Index
from fjkit_lsp.resolve import Resolver, Symbol

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples/fjkit-demo/app"
ADMIN_DEMO = ROOT / "examples/fjkit-admin-demo/admin_demo"
WORKBENCH = ROOT / "packages/fjkit/docs/workbench"


@pytest.fixture(scope="module")
def rs() -> Resolver:
    return Resolver(Index([ROOT]))


def _cursor(path: Path, needle: str, on: str | None = None) -> tuple[int, int]:
    """0-based line and column of `on` inside the first occurrence of `needle`."""
    text = path.read_text(encoding="utf-8")
    start = text.index(needle) + (needle.index(on) if on else 0)
    line = text.count("\n", 0, start)
    return line, start - (text.rfind("\n", 0, start) + 1)


def _at(rs: Resolver, path: Path, needle: str, on: str | None = None) -> Symbol:
    line, col = _cursor(path, needle, on)
    return rs.symbol(path, path.read_text(encoding="utf-8"), line, col)


def _tpl(rs: Resolver, path: Path):
    return rs.index.template_at(path)


# ---- routes, models and templates ---------------------------------------


def test_template_is_rendered_by_routes_and_included_by_page(rs: Resolver) -> None:
    ix = rs.index
    board = _tpl(rs, DEMO / "templates/tasks/_board.html")
    assert {r.func for r in ix.routes_rendering(board)} >= {"tasks_page", "tasks_board", "create_task"}
    assert [p.name for p in ix.parents(board)] == ["tasks/page.html"]


def test_context_field_resolves_to_the_response_model(rs: Resolver) -> None:
    board = _tpl(rs, DEMO / "templates/tasks/_board.html")
    sym = Symbol("ident", "tasks", template=board, line=len(board.text.splitlines()))
    (loc,) = rs.definition(sym)
    assert loc.path == DEMO / "features/tasks/schemas.py"
    assert "tasks: list[Task]" in loc.path.read_text().splitlines()[loc.line]


def test_for_loop_variable_is_recognised(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/_board.html", "{% for task in tasks %}", "task")
    assert sym.kind == "ident" and sym.name == "task"
    assert "for" in (rs.hover(sym) or "")


def test_macro_parameter_type_comes_from_call_sites(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/macros.html", "cell(task.title", "title")
    assert sym.kind == "attr" and (sym.head, sym.name) == ("task", "title")
    (loc,) = rs.definition(sym)
    assert loc.path == DEMO / "features/tasks/schemas.py"
    assert loc.path.read_text().splitlines()[loc.line].strip().startswith("title:")


def test_imported_macro_goes_to_its_definition(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/_board.html", "import task_row", "task_row")
    (loc,) = rs.definition(sym)
    assert loc.path == DEMO / "templates/tasks/macros.html"
    assert "{% macro task_row(" in loc.path.read_text().splitlines()[loc.line]


def test_python_render_string_opens_the_template(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "features/tasks/router.py", '@render("tasks/page.html"', "tasks/page")
    assert sym.kind == "template"
    (loc,) = rs.definition(sym)
    assert loc.path == DEMO / "templates/tasks/page.html"


def test_route_name_in_url_for_goes_to_the_handler(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/macros.html", '"tasks_advance"', "tasks_advance")
    assert sym.kind == "route" and sym.name == "tasks_advance"
    (loc,) = rs.definition(sym)
    assert "def advance_task" in loc.path.read_text().splitlines()[loc.line]


def test_model_field_references_are_jinja_code_in_the_demo(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "features/tasks/schemas.py", "    tasks: list[Task]", "tasks")
    assert sym.kind == "py_field" and sym.name == "tasks"
    refs = rs.references(sym)
    assert refs
    for loc in refs:
        assert loc.path.is_relative_to(DEMO / "templates")
        line = loc.path.read_text().splitlines()[loc.line]
        assert "{{" in line or "{%" in line


def test_global_resolves_into_the_kit(rs: Resolver) -> None:
    board = _tpl(rs, DEMO / "templates/tasks/_board.html")
    sym = Symbol("ident", "url_for", template=board, line=len(board.text.splitlines()))
    (loc,) = rs.definition(sym)
    assert loc.path == ROOT / "packages/fjkit/src/fjkit/templating.py"


# ---- one repository, several applications --------------------------------


def test_kit_templates_are_reachable_under_the_reserved_name(rs: Resolver) -> None:
    ix = rs.index
    kit = ROOT / "packages/fjkit/src/fjkit/templates/ui/button.html"
    assert ix.resolve_template("fjkit/ui/button.html").path == kit
    assert ix.resolve_template("ui/button.html").path == kit


def test_each_app_resolves_its_own_shell(rs: Resolver) -> None:
    """`base.html` exists in both demos and in the docs workbench. A name is only
    unique inside one app's loader chain, so each has to see its own."""
    ix = rs.index
    for app in (DEMO / "templates", ADMIN_DEMO / "templates", WORKBENCH / "templates"):
        here = ix.by_path[app / "base.html"]
        assert ix.resolve_template("base.html", here) is here
        # And from any other page of the same app — the admin demo has none.
        for page in (t for t in ix.by_path.values() if t.root == app and t is not here):
            assert ix.resolve_template("base.html", page) is here


def test_the_shells_do_not_share_a_parent_graph(rs: Resolver) -> None:
    ix = rs.index
    parents = ix.parents(ix.by_path[DEMO / "templates/base.html"])
    assert parents
    assert all(p.path.is_relative_to(DEMO) for p in parents)


def test_a_plugin_template_is_shared_by_every_app(rs: Resolver) -> None:
    """fjkit-admin ships its templates through `mount_fjkit`, so they sit in the
    shared part of every chain rather than in one application."""
    ix = rs.index
    admin_page = ix.by_path[ROOT / "packages/fjkit-admin/src/fjkit_admin/templates/admin/page.html"]
    assert ix.resolve_template("admin/page.html") is admin_page
    demo_board = ix.by_path[DEMO / "templates/tasks/_board.html"]
    assert ix.resolve_template("admin/page.html", demo_board) is admin_page
    assert admin_page.root in ix.shared_roots


# ---- htmx: events, targets and URLs ---------------------------------------


def test_event_in_a_template_goes_to_the_routes_raising_it(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/panels/page.html", 'on=["task-changed"]', "task-changed")
    assert sym.kind == "event" and sym.name == "task-changed"
    where = {(loc.path.relative_to(DEMO).as_posix(), loc.line + 1) for loc in rs.definition(sym)}
    assert where == {("features/panels/router.py", 120), ("features/search/router.py", 150)}
    text = rs.hover(sym) or ""
    assert "CHANGED_EVENT" in text and "HX-Trigger-After-Swap" in text and "HX-Trigger via" in text


def test_event_constant_in_python_finds_every_listener(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "features/search/router.py", "{CHANGED_EVENT: {SELECTED_KEY", "CHANGED_EVENT")
    assert sym.kind == "event" and sym.name == "task-changed"
    assert rs.definition(sym) == []  # the constant is Pyright's to find
    refs = rs.references(sym)
    files = {loc.path.relative_to(DEMO).as_posix() for loc in refs}
    assert {"templates/panels/page.html", "templates/search/_matches.html", "features/search/router.py"} <= files
    for loc in refs:
        if loc.path.suffix == ".html":
            line = loc.path.read_text().splitlines()[loc.line]
            assert '"' in line[: loc.col] and "task-changed" in line[loc.col :]


def test_hx_target_goes_to_the_element_with_that_id(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/macros.html", 'hx_target="#board"', "#board")
    assert sym.kind == "target" and sym.name == "board"
    (loc,) = rs.definition(sym)
    assert loc.path == DEMO / "templates/tasks/_board.html"
    assert 'id="board"' in loc.path.read_text().splitlines()[loc.line]


def test_an_id_finds_its_hx_targets_but_not_a_comment_quoting_one(rs: Resolver) -> None:
    sym = _at(rs, DEMO / "templates/tasks/_board.html", '<div id="board">', "board")
    assert sym.kind == "id"
    refs = rs.references(sym)
    assert len(refs) == 3
    assert all(loc.path.is_relative_to(DEMO) for loc in refs)  # ui/attrs.html quotes `#board` in a comment


def test_a_literal_url_resolves_to_the_route_with_the_router_prefix(rs: Resolver) -> None:
    here = DEMO / "templates/tasks/_board.html"  # decides which application is asking
    text = '<b hx-post="/tasks/7/advance?x=1">a</b>\n<a hx-get="/session/secret">s</a>'
    sym = rs.symbol(here, text, 0, 14)
    assert sym.kind == "url"
    (loc,) = rs.definition(sym)
    assert "def advance_task" in loc.path.read_text().splitlines()[loc.line]
    assert "POST `/tasks/{task_id}/advance`" in (rs.hover(sym) or "")
    sym = rs.symbol(here, text, 1, 12)
    assert sym.kind == "url" and "`/session/secret`" in (rs.hover(sym) or "")


def test_python_definitions_are_left_to_pyright(rs: Resolver) -> None:
    field = _at(rs, DEMO / "features/tasks/schemas.py", "    tasks: list[Task]", "tasks")
    cls = _at(rs, DEMO / "features/tasks/schemas.py", "class BoardResponse", "BoardResponse")
    assert field.kind == "py_field" and cls.kind == "py_class"
    assert rs.definition(field) == [] and rs.definition(cls) == []
    assert rs.references(field)  # what the kit adds: where the field is used in templates


def test_routes_in_test_files_are_not_indexed(rs: Resolver) -> None:
    assert not [r for r in rs.index.routes if "tests" in r.module.parts]
