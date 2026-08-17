"""The closed vocabulary and the loader override, which are the two mechanisms
the whole no-build promise rests on.
"""

from __future__ import annotations

import pytest
from fjkit import FjkitConfig, build_environment
from fjkit.cli.check import check_templates
from fjkit.cli.vocabulary import component_classes


class TestVocabulary:
    def test_component_classes_are_derived_not_hand_maintained(self):
        """Harvested from Basecoat's stylesheets, so the allow-list cannot
        drift from what actually ships."""
        classes = component_classes()
        for name in ("btn", "card", "badge", "input", "label", "field", "table", "empty", "kbd"):
            assert name in classes, f"{name} should be part of the component vocabulary"

    def test_utilities_are_not_component_classes(self):
        classes = component_classes()
        for name in ("flex", "gap-4", "grid-cols-3", "text-muted-foreground"):
            assert name not in classes


class TestCheck:
    def test_component_classes_pass(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="card"><button class="btn">Go</button></div>')
        assert check_templates(tmp_path) == []

    def test_utility_classes_are_rejected(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="flex gap-4">x</div>')
        violations = check_templates(tmp_path)
        assert {v.token for v in violations} == {"flex", "gap-4"}
        assert "layout or component macro" in violations[0].reason

    def test_colour_literals_are_rejected(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="bg-blue-600" style="color:#ff0000">x</div>')
        tokens = {v.token for v in check_templates(tmp_path)}
        assert "bg-blue-600" in tokens
        assert "#ff0000" in tokens

    def test_absolute_white_is_rejected(self, tmp_path):
        """It bets that the brand colour stays dark forever, instead of using
        its contrast token."""
        (tmp_path / "page.html").write_text('<span class="text-white">x</span>')
        assert any(v.token == "text-white" for v in check_templates(tmp_path))

    def test_interpolated_classes_are_skipped(self, tmp_path):
        """The checker cannot evaluate them; the 'never interpolate a class'
        rule is enforced in review instead."""
        (tmp_path / "page.html").write_text('<div class="card {{ extra }}">x</div>')
        assert check_templates(tmp_path) == []

    def test_variant_prefixes_are_judged_on_the_bare_class(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="sm:gap-4">x</div>')
        violations = check_templates(tmp_path)
        assert [v.token for v in violations] == ["sm:gap-4"]

    def test_multiline_class_attributes_are_scanned(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="card\n            flex">x</div>')
        assert [v.token for v in check_templates(tmp_path)] == ["flex"]

    def test_violation_reports_a_line_number(self, tmp_path):
        (tmp_path / "page.html").write_text('<div>a</div>\n<div>b</div>\n<div class="flex">c</div>')
        assert check_templates(tmp_path)[0].line == 3


class TestLoaderOverride:
    def test_app_templates_shadow_the_kit(self, tmp_path):
        """The mechanism behind `fjkit eject` — a file at the same path in the
        app wins, with no import change at any call site."""
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "button.html").write_text("{% macro button(label) %}<em>{{ label }}</em>{% endmacro %}")

        env = build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))
        html = env.from_string('{% from "ui/button.html" import button %}{{ button("Go") }}').render()
        assert html == "<em>Go</em>"

    def test_kit_templates_resolve_when_the_app_has_no_override(self, tmp_path):
        env = build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))
        html = env.from_string('{% from "ui/button.html" import button %}{{ button("Go") }}').render()
        assert 'class="btn"' in html

    def test_every_kit_template_compiles(self):
        """Catches syntax errors in templates no test happens to render."""
        env = build_environment(FjkitConfig(auto_reload=False))
        names = env.list_templates(extensions=("html", "jinja"))
        assert names, "the kit should ship templates"
        for name in names:
            env.get_template(name)


class TestIcons:
    def test_the_full_set_ships(self):
        from fjkit.icons import names

        assert len(names()) > 1000

    def test_unknown_name_raises_with_a_suggestion(self):
        from fjkit.icons import path

        with pytest.raises(KeyError, match="arrow-right"):
            path("arrow-rght")

    def test_icons_carry_no_colour(self):
        """`stroke="currentColor"` on the wrapper is why icons never needed a
        token of their own — a hard-coded fill in the path data would break it."""
        from fjkit.icons import names, path

        for name in names()[:200]:
            assert "#" not in path(name), f"{name} contains a colour literal"
