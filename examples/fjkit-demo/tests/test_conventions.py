"""Enforces the template rules in CLAUDE.md, "Layer boundaries in the demo".

The demo is the kit's acceptance test, so a convention broken here has to fail
in this suite rather than in an app built on the kit.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fjkit import FjkitConfig, build_environment
from fjkit.cli.check import assert_templates_clean

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "app" / "templates"

FEATURE_TEMPLATES = [p for p in TEMPLATE_DIR.rglob("*.html") if p.parent != TEMPLATE_DIR]


@pytest.mark.parametrize("path", [p for p in FEATURE_TEMPLATES if p.name == "page.html"], ids=lambda p: p.parent.name)
def test_pages_extend_the_shell(path):
    """A `page.html` answers a full GET, and only the shell carries the `<head>` and the nav."""
    assert '{% extends "base.html" %}' in path.read_text(), f"{path.name} is a page, so it must extend base.html"


@pytest.mark.parametrize(
    "path", [p for p in FEATURE_TEMPLATES if p.name.startswith("_")], ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_partials_never_extend_the_shell(path):
    """A partial is swapped into a page that already has a shell; extending one nests a second document."""
    assert "{% extends" not in path.read_text(), f"{path.name} starts with _, so it must render standalone"


def test_base_extends_the_kit_shell():
    """`ui/shell.html` owns the `<head>` and every asset link, so the app's shell has to inherit it."""
    assert '{% extends "ui/shell.html" %}' in (TEMPLATE_DIR / "base.html").read_text()


def test_every_template_compiles():
    """A template no test renders still has to compile; otherwise its syntax error is a 500 in production."""
    env = build_environment(FjkitConfig(template_dir=TEMPLATE_DIR, auto_reload=False))
    for name in env.list_templates(extensions=("html", "jinja")):
        env.get_template(name)


def test_templates_stay_inside_the_fjkit_vocabulary():
    """No colour literal and no class outside the component vocabulary: both survive a rebrand, hues do not."""
    assert_templates_clean(TEMPLATE_DIR)


def test_the_app_ships_no_static_assets_of_its_own():
    """No front-end build step in the app: the kit serves every asset, so an app owns none of them."""
    assert not (ROOT / "app" / "static").exists(), "the kit serves every asset; the demo mounts none"
    assert not list((ROOT / "app").rglob("*.css")), "the kit's stylesheet is the app's stylesheet"
    assert not list(ROOT.rglob("package.json")), "no npm in the demo, not even a manifest"
    assert not (ROOT / "node_modules").exists()


@pytest.mark.parametrize(
    "path", [p for p in FEATURE_TEMPLATES if p.name.startswith("_")], ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_partials_import_every_macro_they_call(path):
    """A partial renders standalone, so every name it calls is imported, local, or an environment global."""
    from jinja2 import nodes

    env = build_environment(FjkitConfig(template_dir=TEMPLATE_DIR, auto_reload=False))
    tree = env.parse(path.read_text(), name=path.relative_to(TEMPLATE_DIR).as_posix())

    defined: set[str] = set()
    for node in tree.find_all((nodes.Import, nodes.FromImport, nodes.Macro, nodes.Assign, nodes.For, nodes.CallBlock)):
        if isinstance(node, nodes.Import):
            defined.add(node.target)
        elif isinstance(node, nodes.FromImport):
            defined.update(n if isinstance(n, str) else n[1] for n in node.names)
        elif isinstance(node, nodes.Macro):
            defined.add(node.name)
            defined.update(a.name for a in node.args)
        elif isinstance(node, nodes.CallBlock):
            defined.update(a.name for a in node.args)
        elif isinstance(node, (nodes.Assign, nodes.For)):
            defined.update(n.name for n in node.target.find_all(nodes.Name))

    called = set()
    for call in tree.find_all(nodes.Call):
        root = call.node
        while isinstance(root, (nodes.Getattr, nodes.Getitem)):
            root = root.node
        if isinstance(root, nodes.Name):
            called.add(root.name)

    known = defined | set(env.globals) | {"request", "errors", "caller"}
    missing = sorted(called - known)
    assert not missing, f"{path.name} calls {missing} without importing or defining it; the swap would 500"
