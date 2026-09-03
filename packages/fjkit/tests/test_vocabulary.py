"""The closed vocabulary and the loader override — the two mechanisms the
no-build promise rests on.
"""

from __future__ import annotations

import shutil

import pytest
from fjkit import FjkitConfig, build_environment
from fjkit.cli.check import check_templates
from fjkit.cli.eject import components, parse_or_none
from fjkit.cli.ejected import STAMP, find_ejected, stale_ejects
from fjkit.cli.vocabulary import component_classes
from fjkit.config import TEMPLATE_DIR

#: Every component `fjkit eject <name>` copies, and every macro inside one.
#: Derived rather than listed, so a component added later is covered by the same
#: tests without anyone remembering to add it here.
EJECTABLE = sorted(p.stem for p in (TEMPLATE_DIR / "ui").glob("*.html"))
MACROS = [
    (component, macro)
    for component, path in components().items()
    for macro in parse_or_none(path)
    if not macro.startswith("_")
]


class TestVocabulary:
    def test_component_classes_are_derived_not_hand_maintained(self):
        """Harvested from Basecoat's stylesheets, so the allow-list cannot drift
        from what ships."""
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
        """It bets that the brand colour stays dark forever instead of naming
        the contrast token."""
        (tmp_path / "page.html").write_text('<span class="text-white">x</span>')
        assert any(v.token == "text-white" for v in check_templates(tmp_path))

    def test_interpolated_classes_are_skipped(self, tmp_path):
        """The checker cannot evaluate them. The "never interpolate a class"
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

    def test_a_jinja_comment_is_not_scanned(self, tmp_path):
        """A comment never reaches the browser, so a hue named inside one cannot
        break a rebrand. Scanning comments left the rule unable to describe
        itself.
        """
        (tmp_path / "page.html").write_text(
            "{# upstream writes bg-green-600 here; we name a role instead #}\n<div class=\"card\">x</div>"
        )
        assert check_templates(tmp_path) == []

    def test_a_multiline_comment_does_not_shift_later_line_numbers(self, tmp_path):
        """Comments are blanked, not removed. A report pointing at the wrong
        line is worse than no report."""
        (tmp_path / "page.html").write_text("{#\n  bg-green-600\n#}\n<div class=\"flex\">x</div>")
        assert [(v.line, v.token) for v in check_templates(tmp_path)] == [(4, "flex")]

    def test_a_colour_outside_a_comment_is_still_caught(self, tmp_path):
        (tmp_path / "page.html").write_text('{# fine #}\n<div class="bg-green-600">x</div>')
        assert {v.token for v in check_templates(tmp_path)} == {"bg-green-600"}


class TestLoaderOverride:
    def test_app_templates_shadow_the_kit(self, tmp_path):
        """The mechanism behind `fjkit eject`: a file at the same path in the
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

    def test_the_reserved_namespace_reaches_the_kit_through_an_override(self, tmp_path):
        """Shadowing takes away the one thing an override needs: a name for the
        file it is shadowing."""
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "button.html").write_text(
            '{% import "fjkit/ui/button.html" as _fjkit %}'
            "{% macro button(label) %}<em>{{ label }}</em>{% endmacro %}"
            "{% set button_group = _fjkit.button_group %}"
        )

        env = build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))
        html = env.from_string(
            '{% from "ui/button.html" import button, button_group %}'
            "{{ button('Go') }}{% call button_group() %}x{% endcall %}"
        ).render()
        # `button` is the override's. `button_group` is still the kit's, and it
        # renders through a `{% call %}` block and its own `row` import.
        assert html.startswith("<em>Go</em>")
        assert html.endswith(">x</div>")

    def test_an_app_cannot_hijack_the_reserved_namespace(self, tmp_path):
        """The reserved namespace is first in the chain, so an override cannot
        be tricked into re-exporting from something the app wrote."""
        hijack = tmp_path / "fjkit" / "ui"
        hijack.mkdir(parents=True)
        (hijack / "button.html").write_text("{% macro button(label) %}<hijacked>{% endmacro %}")

        env = build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))
        html = env.from_string('{% from "fjkit/ui/button.html" import button %}{{ button("Go") }}').render()
        assert "hijacked" not in html
        assert 'class="btn"' in html

    def test_the_reserved_namespace_lists_nothing(self):
        """Its files are already listed under their bare names, and a second
        entry each would double every compile-everything sweep."""
        env = build_environment(FjkitConfig(auto_reload=False))
        assert [n for n in env.list_templates() if n.startswith("fjkit/")] == []

    def test_every_kit_template_compiles(self):
        """Catch syntax errors in templates no other test happens to render."""
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
        token of their own. A hard-coded fill in the path data would break it."""
        from fjkit.icons import names, path

        for name in names()[:200]:
            assert "#" not in path(name), f"{name} contains a colour literal"


class TestEjectStamp:
    """`fjkit eject` leaves a trail, so a copy that has fallen behind the kit can
    be found again. See `fjkit.cli.ejected`.
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
        """The digest covers the kit's source at eject time, not the copy's.
        Diverging is the point of ejecting; only upstream moving matters.
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
        """Documentation quoting a stamp is not itself an ejected file."""
        (tmp_path / "page.html").write_text(
            "<p>a stamp looks like this:</p>\n{# fjkit:eject button 0.1.0 sha256:000000000000 #}\n"
        )
        assert find_ejected(tmp_path) == []

    @pytest.mark.parametrize("name", EJECTABLE)
    def test_ejecting_a_component_leaves_the_build_gate_green(self, tmp_path, name):
        """The escape hatch has to be walkable. A kit macro writes utilities, so
        that an app never has to; judging the copy by the app's rules made
        `fjkit eject` produce a red build for every component but four."""
        self._eject(tmp_path, name)
        assert check_templates(tmp_path) == []

    def test_an_ejected_file_is_still_judged_on_colour(self, tmp_path):
        """Utilities stop being a violation, hues do not. A hard-coded green in
        an ejected macro breaks a rebrand exactly as it would anywhere else."""
        target = self._eject(tmp_path)
        target.write_text(target.read_text() + '\n<div class="bg-green-600 flex gap-4">x</div>\n')

        assert [v.token for v in check_templates(tmp_path)] == ["bg-green-600"]

    def test_an_unstamped_copy_gets_no_amnesty(self, tmp_path):
        """The stamp is what says "the kit wrote this". A macro pasted in by
        hand is an app template, and the closed vocabulary still applies."""
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "button.html").write_text('<div class="flex gap-4">x</div>')
        assert {v.token for v in check_templates(tmp_path)} == {"flex", "gap-4"}

    def test_a_stale_eject_does_not_fail_the_check(self, tmp_path, capsys):
        from fjkit.cli.check import main as check_main

        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "gone.html").write_text("{# fjkit:eject gone 0.1.0 sha256:000000000000 #}\n")

        assert check_main(tmp_path) == 0
        assert "no longer ships" in capsys.readouterr().out


class TestMacroEject:
    """`fjkit eject badge` takes one macro and leaves the rest of `ui/data.html`
    with the kit. See `fjkit.cli.eject`.
    """

    def _eject(self, tmp_path, name, expect=0):
        from fjkit.cli import main

        assert main(["eject", name, "--into", str(tmp_path)]) == expect
        return tmp_path

    def _env(self, tmp_path):
        return build_environment(FjkitConfig(template_dir=tmp_path, auto_reload=False))

    def _render(self, tmp_path, body):
        return self._env(tmp_path).from_string(body).render()

    def _fork_the_kit(self, tmp_path, monkeypatch, component, before, after):
        """Copy the kit with one macro edited, standing in for an upgrade.

        The reserved namespace and the fallback loader both read
        `fjkit.templating.TEMPLATE_DIR`, so redirecting it is the whole trick.
        """
        fork = tmp_path / "upstream"
        shutil.copytree(TEMPLATE_DIR, fork)
        patched = fork / "ui" / f"{component}.html"
        assert before in patched.read_text()
        patched.write_text(patched.read_text().replace(before, after))
        monkeypatch.setattr("fjkit.templating.TEMPLATE_DIR", fork)
        return fork

    @pytest.mark.parametrize("target", MACROS, ids=lambda t: f"{t[0]}.{t[1]}")
    def test_every_macro_ejects_into_a_clean_build(self, tmp_path, target):
        component, macro = target
        self._eject(tmp_path, f"{component}.{macro}")
        assert check_templates(tmp_path) == []

    @pytest.mark.parametrize("target", MACROS, ids=lambda t: f"{t[0]}.{t[1]}")
    def test_an_override_exports_exactly_what_the_kit_did(self, tmp_path, target):
        """A re-export that dropped a macro would break a call site that never
        asked to be involved."""
        component, macro = target
        self._eject(tmp_path, f"{component}.{macro}")

        env = self._env(tmp_path)
        mine = env.get_template(f"ui/{component}.html").make_module()
        kit = env.get_template(f"fjkit/ui/{component}.html").make_module()
        assert {n for n in dir(mine) if not n.startswith("_")} == {n for n in dir(kit) if not n.startswith("_")}

    def test_the_override_owns_one_macro_and_re_exports_the_rest(self, tmp_path):
        text = (self._eject(tmp_path, "badge") / "ui" / "data.html").read_text()
        assert "{% macro badge(" in text
        assert "{% macro card(" not in text
        assert "{% set card = _fjkit.card %}" in text
        assert len(text.splitlines()) < len((TEMPLATE_DIR / "ui" / "data.html").read_text().splitlines()) // 3

    def test_a_re_export_keeps_receiving_upstream_fixes(self, tmp_path, monkeypatch):
        """The point of the exercise: you own `badge`, and the kit's next fix to
        `card` still reaches you."""
        self._eject(tmp_path, "badge")
        self._fork_the_kit(tmp_path, monkeypatch, "data", '<div class="card"', '<div class="card" data-fixed')

        html = self._render(tmp_path, '{% from "ui/data.html" import card %}{% call card() %}x{% endcall %}')
        assert "data-fixed" in html

    def test_a_macro_you_own_does_not_move_under_you(self, tmp_path, monkeypatch):
        self._eject(tmp_path, "badge")
        self._fork_the_kit(tmp_path, monkeypatch, "data", '<span class="badge"', '<span class="badge" data-fixed')

        html = self._render(tmp_path, '{% from "ui/data.html" import badge %}{{ badge("Done") }}')
        assert "data-fixed" not in html
        assert 'class="badge"' in html

    def test_kwargs_and_call_blocks_survive_a_re_export(self, tmp_path):
        """`{% set card = _fjkit.card %}` binds the kit's macro object itself
        rather than a wrapper, so `**kwargs` and `caller()` are untouched."""
        self._eject(tmp_path, "badge")

        html = self._render(
            tmp_path,
            '{% from "ui/data.html" import card %}'
            '{% call card("Throughput", hx_post="/x") %}<p>body</p>{% endcall %}',
        )
        assert 'hx-post="/x"' in html
        assert "<p>body</p>" in html
        assert "Throughput" in html

    def test_kwargs_survive_on_the_macro_you_own(self, tmp_path):
        self._eject(tmp_path, "badge")
        html = self._render(tmp_path, '{% from "ui/data.html" import badge %}{{ badge("Done", hx_get="/y") }}')
        assert 'hx-get="/y"' in html

    def test_a_private_helper_is_copied_because_it_cannot_be_borrowed(self, tmp_path):
        """Jinja keeps `_`-prefixed names out of a module's namespace, so
        `_fjkit._message` does not exist and a copy is the only option."""
        text = (self._eject(tmp_path, "text_field") / "ui" / "form.html").read_text()
        assert "{% macro _message(" in text
        assert "_fjkit._message" not in text
        assert STAMP.match(text.splitlines()[0])["macros"].split(",")[-1].startswith("_message=")

    def test_the_kit_keeps_using_its_own_copy_of_the_private_helper(self, tmp_path):
        """The copy is yours. `select_field` is still the kit's, and it calls the
        kit's `_message` rather than the one in your file."""
        target = self._eject(tmp_path, "text_field") / "ui" / "form.html"
        target.write_text(target.read_text().replace('id="{{ field_id }}-hint"', 'id="mine"'))

        env = self._env(tmp_path)
        mine = env.from_string(
            '{% from "ui/form.html" import text_field %}{{ text_field("a", hint="h") }}'
        ).render()
        theirs = env.from_string(
            '{% from "ui/form.html" import select_field %}{{ select_field("b", hint="h") }}'
        ).render()
        assert 'id="mine"' in mine
        assert 'id="mine"' not in theirs
        assert 'id="f-b-hint"' in theirs

    def test_only_the_lookup_tables_the_macro_reads_come_along(self, tmp_path):
        """A `_ROWS` copied beside a macro that never reads it is dead weight
        that looks live: it falls behind the kit while the macro that does read
        it, the re-exported `field_row`, goes on using the kit's."""
        text = (self._eject(tmp_path, "text_field") / "ui" / "form.html").read_text()
        assert "_ROWS" not in text
        assert '{% from "ui/attrs.html" import attrs %}' in text

        rows = (self._eject(tmp_path, "field_row") / "ui" / "form.html").read_text()
        assert "{% set _ROWS = {" in rows
        assert "wide-then-actions" in rows, "a multi-line {% set %} must be taken whole"

    def test_a_second_eject_rewrites_rather_than_refusing(self, tmp_path):
        """Wanting a second macro is the ordinary next step; refusing would leave
        hand-editing as the only answer."""
        self._eject(tmp_path, "badge")
        text = (self._eject(tmp_path, "stat") / "ui" / "data.html").read_text()

        assert "{% macro badge(" in text
        assert "{% macro stat(" in text
        assert "{% set badge = _fjkit.badge %}" not in text
        owned = STAMP.match(text.splitlines()[0])["macros"]
        assert sorted(e.split("=")[0] for e in owned.split(",")) == ["badge", "stat"]

    def test_taking_a_macro_you_already_own_is_refused(self, tmp_path):
        self._eject(tmp_path, "badge")
        self._eject(tmp_path, "badge", expect=1)

    def test_a_file_fjkit_did_not_write_is_never_overwritten(self, tmp_path):
        ui = tmp_path / "ui"
        ui.mkdir()
        (ui / "data.html").write_text("{% macro badge(label) %}mine{% endmacro %}")
        self._eject(tmp_path, "badge", expect=1)
        assert (ui / "data.html").read_text() == "{% macro badge(label) %}mine{% endmacro %}"

    def test_a_whole_file_copy_has_nothing_left_to_take(self, tmp_path):
        self._eject(tmp_path, "data")
        self._eject(tmp_path, "badge", expect=1)

    def test_a_file_name_still_means_the_whole_file(self, tmp_path):
        """`table` is both a component and a macro inside it. Nothing that worked
        before may change meaning, so the file wins."""
        from fjkit.cli.eject import resolve

        assert resolve("table") == ("table", None)
        assert resolve("table.table") == ("table", "table")
        assert resolve("badge") == ("data", "badge")

    def test_a_name_two_components_share_asks_which(self, tmp_path, monkeypatch):
        from fjkit.cli import eject

        monkeypatch.setattr(eject, "components", lambda: {"a": ..., "b": ...})
        monkeypatch.setattr(eject, "parse_or_none", lambda path: {"twin": ...})
        with pytest.raises(eject.Ambiguous, match="a.twin, b.twin"):
            eject.resolve("twin")

    def test_an_unknown_name_lists_what_there_is(self, tmp_path, capsys):
        self._eject(tmp_path, "nosuchthing", expect=1)
        err = capsys.readouterr().err
        assert "badge" in err and "data" in err

    def test_a_page_skeleton_has_no_macros_to_take(self, tmp_path):
        """`shell.html` is a base template, not a macro library. `eject shell`
        still copies the file; `eject shell.anything` has nothing to take."""
        self._eject(tmp_path, "shell")
        self._eject(tmp_path, "shell.head", expect=1)


class TestPerMacroStamp:
    """The digest is per macro, so the report can name which one moved."""

    def _stamp(self, tmp_path, macros):
        from fjkit.cli.ejected import macro_stamp

        ui = tmp_path / "ui"
        ui.mkdir(exist_ok=True)
        (ui / "data.html").write_text(macro_stamp("data", "0.1.0", macros) + "\n")
        return tmp_path

    def _kit(self, *names):
        from fjkit.cli.eject import kit_macro_digests

        return kit_macro_digests("data", list(names))

    def test_a_fresh_eject_is_not_stale(self, tmp_path):
        from fjkit.cli import main

        assert main(["eject", "badge", "--into", str(tmp_path)]) == 0
        assert stale_ejects(tmp_path) == []

    def test_only_the_macros_you_own_can_go_stale(self, tmp_path):
        """Why the digest is per macro: a file-wide digest called your copy of
        `badge` stale because the kit had changed `avatar`."""
        digests = self._kit("badge", "stat")
        self._stamp(tmp_path, {"badge": digests["badge"], "stat": "000000000000"})

        stale = stale_ejects(tmp_path)
        assert [e.moved for e in stale] == [("stat",)]
        assert "'stat'" in stale[0].render(tmp_path)
        assert "'badge'" not in stale[0].render(tmp_path)

    def test_a_macro_the_kit_dropped_is_orphaned_on_its_own(self, tmp_path):
        digests = self._kit("badge")
        self._stamp(tmp_path, {"badge": digests["badge"], "gone": "000000000000"})

        stale = stale_ejects(tmp_path)
        assert stale[0].missing == ("gone",)
        assert stale[0].is_orphaned and not stale[0].is_stale
        assert "no longer ships" in stale[0].render(tmp_path)

    def test_the_doc_comment_is_not_part_of_the_digest(self, tmp_path):
        """Rewording a paragraph must not report the copy as fallen behind. The
        digest covers the `{% macro %}` block and nothing else."""
        from fjkit.cli.eject import components, parse
        from fjkit.cli.ejected import digest

        component = parse(components()["data"])
        stamped = self._kit("badge")["badge"]
        assert stamped == digest(component.macros["badge"].body)
        assert component.macros["badge"].doc, "badge should have a signature comment"
        assert component.macros["badge"].doc not in component.macros["badge"].body

    def test_a_per_macro_stamp_never_fails_the_build(self, tmp_path, capsys):
        from fjkit.cli.check import main as check_main

        self._stamp(tmp_path, {"badge": "000000000000"})
        assert check_main(tmp_path) == 0
        assert "'badge'" in capsys.readouterr().out
