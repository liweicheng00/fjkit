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
    """The kit's stylesheet is served from the installed package. An app that
    grows a static/ directory has started down the road back to a build step."""
    assert not (ROOT / "app" / "static").exists()
