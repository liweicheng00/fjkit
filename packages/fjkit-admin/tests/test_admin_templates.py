"""The templates keep fjkit's rules: closed vocabulary, page/partial split, explicit imports."""

from __future__ import annotations

from pathlib import Path

from fjkit import FjkitConfig, build_environment
from fjkit.cli.check import assert_templates_clean
from fjkit_admin import AdminPlugin
from fjkit_admin.plugin import TEMPLATE_DIR
from jinja2 import nodes

ADMIN_TEMPLATES = TEMPLATE_DIR / "admin"


def templates() -> list[Path]:
    return sorted(ADMIN_TEMPLATES.glob("*.html"))


def env():
    return build_environment(FjkitConfig(plugins=(AdminPlugin(lambda: None, views=()),)))


def test_every_template_stays_inside_the_fjkit_vocabulary():
    # The stylesheet is built from fjkit's own templates only. A class this
    # package invented would render as nothing, so it may write none.
    assert_templates_clean(TEMPLATE_DIR)


def test_no_template_writes_a_class_attribute():
    for path in templates():
        assert 'class="' not in path.read_text(), f"{path.name} writes a class; compose a macro instead"


def test_the_page_extends_the_base_and_the_partials_extend_nothing():
    page = (ADMIN_TEMPLATES / "page.html").read_text()
    assert "{% extends base_template %}" in page
    for path in templates():
        if path.name.startswith("_"):
            assert "{% extends" not in path.read_text(), f"{path.name} is a partial"


def test_every_template_compiles():
    environment = env()
    for path in templates():
        environment.get_template(f"admin/{path.name}")


def test_partials_import_every_macro_they_call():
    environment = env()
    for path in templates():
        if path.name == "page.html":
            continue
        source = path.read_text()
        tree = environment.parse(source)
        defined: set[str] = set()
        for node in tree.find_all(nodes.FromImport):
            for name in node.names:
                defined.add(name[1] if isinstance(name, tuple) else name)
        for node in tree.find_all(nodes.Macro):
            defined.add(node.name)
        for node in tree.find_all(nodes.Assign):
            if isinstance(node.target, nodes.Name):
                defined.add(node.target.name)
        known = defined | set(environment.globals) | {"request", "caller"}
        for call in tree.find_all(nodes.Call):
            root = call.node
            while isinstance(root, nodes.Getattr):
                root = root.node
            if isinstance(root, nodes.Name):
                assert root.name in known, f"{path.name} calls {root.name} without importing it"
