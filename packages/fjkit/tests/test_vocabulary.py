"""The closed vocabulary and the loader override, which are the two mechanisms
the whole no-build promise rests on.
"""

from __future__ import annotations

import pytest
from fjkit import FjkitConfig, build_environment
from fjkit.cli.check import check_templates
from fjkit.cli.ejected import STAMP, find_ejected, stale_ejects
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


class TestEjectStamp:
    """`fjkit eject` leaves a trail, so a copy that has fallen behind the kit
    can be found again. See `fjkit.cli.ejected`.
    """

    def _eject(self, tmp_path, name="button"):
        from fjkit.cli import main

        assert main(["eject", name, "--into", str(tmp_path)]) == 0
        return tmp_path / "ui" / f"{name}.html"

    def test_the_copy_is_stamped_with_its_origin(self, tmp_path):
        first = self._eject(tmp_path).read_text().splitlines()[0]
        assert STAMP.match(first), first
        assert STAMP.match(first)["name"] == "button"

    def test_the_stamp_is_a_jinja_comment_so_it_does_not_render(self, tmp_path):
        self._eject(tmp_path)
        env = build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))
        html = env.from_string('{% from "ui/button.html" import button %}{{ button("Go") }}').render()
        assert "fjkit:eject" not in html
        assert 'class="btn"' in html

    def test_a_fresh_eject_is_not_stale(self, tmp_path):
        self._eject(tmp_path)
        assert stale_ejects(tmp_path) == []

    def test_editing_the_copy_does_not_make_it_stale(self, tmp_path):
        """The digest is the *kit's* source at eject time, not the copy's.
        Diverging is the whole point of ejecting; only upstream moving matters.
        """
        target = self._eject(tmp_path)
        target.write_text(target.read_text() + "\n{# a local change #}\n")
        assert stale_ejects(tmp_path) == []

    def test_a_kit_change_makes_the_copy_stale(self, tmp_path):
        target = self._eject(tmp_path)
        text = target.read_text()
        target.write_text(text.replace("sha256:" + STAMP.match(text)["digest"], "sha256:000000000000"))

        stale = stale_ejects(tmp_path)
        assert [e.name for e in stale] == ["button"]
        assert stale[0].is_stale and not stale[0].is_orphaned

    def test_a_component_the_kit_no_longer_ships_is_orphaned(self, tmp_path):
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "gone.html").write_text("{# fjkit:eject gone 0.1.0 sha256:000000000000 #}\n")

        stale = stale_ejects(tmp_path)
        assert [e.name for e in stale] == ["gone"]
        assert stale[0].is_orphaned

    def test_an_unstamped_template_is_not_an_eject(self, tmp_path):
        (tmp_path / "page.html").write_text('<div class="card">x</div>')
        assert find_ejected(tmp_path) == []

    def test_a_stamp_below_the_first_line_is_not_a_stamp(self, tmp_path):
        """Documentation that quotes a stamp is not itself an ejected file."""
        (tmp_path / "page.html").write_text(
            "<p>a stamp looks like this:</p>\n{# fjkit:eject button 0.1.0 sha256:000000000000 #}\n"
        )
        assert find_ejected(tmp_path) == []

    def test_a_stale_eject_does_not_fail_the_check(self, tmp_path, capsys):
        from fjkit.cli.check import main as check_main

        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "gone.html").write_text("{# fjkit:eject gone 0.1.0 sha256:000000000000 #}\n")

        assert check_main(tmp_path) == 0
        assert "no longer ships" in capsys.readouterr().out
