"""Executable version of the template conventions in CLAUDE.md.

A convention nobody can violate accidentally is worth more than one written
down in a doc, so the naming rules are tests.

The colour and vocabulary rules used to live in `scripts/check_styles.py`; they
now ship with the kit as `fjkit check`, and this file just points at it. That is
the intended shape: an app gets the enforcement, not a copy of the enforcer.
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
    assert '{% extends "base.html" %}' in path.read_text(), f"{path.name} is a page, so it must extend base.html"


@pytest.mark.parametrize(
    "path", [p for p in FEATURE_TEMPLATES if p.name.startswith("_")], ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_partials_never_extend_the_shell(path):
    assert "{% extends" not in path.read_text(), f"{path.name} starts with _, so it must render standalone"


def test_base_extends_the_kit_shell():
    """The app owns its brand and nav; the kit owns the <head> and the
    skeleton. An app that stops extending the shell has quietly taken on the
    theme flash-guard and the asset links."""
    assert '{% extends "ui/shell.html" %}' in (TEMPLATE_DIR / "base.html").read_text()


def test_every_template_compiles():
    """Catches syntax errors in templates no test happens to render."""
    env = build_environment(FjkitConfig(template_dir=TEMPLATE_DIR, auto_reload=False))
    for name in env.list_templates(extensions=("html", "jinja")):
        env.get_template(name)


def test_templates_stay_inside_the_fjkit_vocabulary():
    """No utility classes, no colour literals. This is the check that makes
    "the app needs no CSS build" true rather than aspirational."""
    assert_templates_clean(TEMPLATE_DIR)


def test_the_app_ships_no_stylesheet_of_its_own():
    """The kit's stylesheet is served from the installed package, and nothing
    the app serves is generated.

    This used to assert that `app/static/` did not exist at all. The charts
    page ended that: it vendors Plotly, which fjkit's JS budget will not carry
    (CHARTER §7), plus the script that binds it to the colour tokens. So the
    assertion moved to the invariant the old one was standing in for — an app
    author runs no build. A `.css` file here would mean a stylesheet pipeline;
    a `package.json` or a `node_modules` would mean a front-end one. Vendored,
    committed, human-readable assets are neither.
    """
    assert not list((ROOT / "app").rglob("*.css")), "the kit's stylesheet is the app's stylesheet"
    assert not list(ROOT.rglob("package.json")), "no npm in the demo, not even a manifest"
    assert not (ROOT / "node_modules").exists()


def test_every_vendored_asset_is_pinned_by_a_script():
    """Anything under `static/vendor/` got there by a vendoring script that
    names its version, never by a hand-copied download. That is what makes the
    bytes in the diff reviewable and the version bump a one-line change."""
    vendored = list((ROOT / "app" / "static" / "vendor").rglob("*.js"))
    assert vendored, "the vendor directory exists because something is vendored"

    script = (ROOT / "scripts" / "vendor_plotly.py").read_text()
    for path in vendored:
        assert path.name in script, f"{path.name} is served but no script says where it came from"
