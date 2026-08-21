"""Contract tests for the component macros.

These lock down the parts of a macro that callers depend on: which element it
emits, which attribute carries the variant, and that pass-through attributes
survive. Once a signature is published it cannot change (CHARTER.md A4), so
these are the tests that make a breaking change loud.
"""

from __future__ import annotations

import re

import pytest

BUTTON = '{% from "ui/button.html" import button %}'
DATA = '{% from "ui/data.html" import badge, card, stat, progress, empty_state, metric_group, link, kbd %}'
LAYOUT = '{% from "ui/layout.html" import stack, row, grid, split, page_header, section, divider %}'
TABLE = '{% from "ui/table.html" import table, cell, row_actions %}'
FORM = '{% from "ui/form.html" import text_field, select_field, form, field_row %}'
FEEDBACK = '{% from "ui/feedback.html" import spinner %}'
FEEDBACK_DIALOG = '{% from "ui/feedback.html" import dialog %}'
SIDEBAR = (
    '{% from "ui/sidebar.html" import sidebar, sidebar_group, sidebar_link,'
    ' sidebar_submenu, sidebar_trigger %}'
)


class TestButton:
    def test_renders_a_button_by_default(self, render):
        html = render(f'{BUTTON}{{{{ button("Save") }}}}')
        assert "<button" in html and 'class="btn"' in html
        assert 'type="button"' in html

    def test_href_switches_the_element_to_an_anchor(self, render):
        html = render(f'{BUTTON}{{{{ button("Docs", href="/docs") }}}}')
        assert "<a " in html and 'href="/docs"' in html
        assert "type=" not in html, "an anchor must not carry a button type"

    @pytest.mark.parametrize("variant", ["primary", "secondary", "outline", "ghost", "link", "destructive"])
    def test_variant_is_an_attribute_not_a_class(self, render, variant):
        """Basecoat's API is data-variant. A parallel `btn-primary` class would
        be a second way to say the same thing, and they would drift."""
        html = render(f'{BUTTON}{{{{ button("Go", variant="{variant}") }}}}')
        assert f'data-variant="{variant}"' in html
        assert f"btn-{variant}" not in html

    def test_unknown_kwargs_become_html_attributes(self, render):
        html = render(f'{BUTTON}{{{{ button("Go", hx_post="/x", hx_target="#board") }}}}')
        assert 'hx-post="/x"' in html
        assert 'hx-target="#board"' in html

    def test_true_renders_a_bare_boolean_attribute(self, render):
        html = render(f'{BUTTON}{{{{ button("Go", data_open=true) }}}}')
        assert "data-open>" in html or "data-open " in html
        assert 'data-open="True"' not in html

    def test_none_and_false_render_nothing(self, render):
        html = render(f'{BUTTON}{{{{ button("Go", data_a=none, data_b=false) }}}}')
        assert "data-a" not in html and "data-b" not in html


class TestLayout:
    def test_stack_gap_uses_a_closed_lookup(self, render):
        html = render(f"{LAYOUT}{{% call stack(6) %}}x{{% endcall %}}")
        assert "gap-6" in html and "flex-col" in html

    def test_unknown_gap_falls_back_rather_than_emitting_a_dead_class(self, render):
        """An interpolated `gap-99` would not exist in the stylesheet, so the
        element would silently lose its spacing."""
        html = render(f"{LAYOUT}{{% call stack(99) %}}x{{% endcall %}}")
        assert "gap-99" not in html
        assert "gap-4" in html

    def test_split_renders_both_slots_exactly_once(self, render):
        html = render(
            f"{LAYOUT}"
            "{% call(slot) split() %}"
            "{% if slot == 'main' %}MAIN{% else %}ASIDE{% endif %}"
            "{% endcall %}"
        )
        assert html.count("MAIN") == 1
        assert html.count("ASIDE") == 1
        assert html.index("MAIN") < html.index("ASIDE")

    def test_page_header_works_with_and_without_actions(self, render):
        plain = render(f'{LAYOUT}{{{{ page_header("Tasks", "All of them") }}}}')
        assert "<h1" in plain and "Tasks" in plain and "All of them" in plain

        with_actions = render(f'{LAYOUT}{{% call page_header("Tasks") %}}ACTION{{% endcall %}}')
        assert "ACTION" in with_actions

    @pytest.mark.parametrize("cols", [2, 3, 4])
    def test_grid_columns_are_responsive(self, render, cols):
        html = render(f"{LAYOUT}{{% call grid(cols={cols}) %}}x{{% endcall %}}")
        assert "sm:grid-cols-2" in html


class TestTable:
    COLUMNS = '[{"label": "Task"}, {"label": "Owner"}, {"width": "min"}]'

    def test_renders_a_header_per_column(self, render):
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}ROWS{{% endcall %}}")
        assert len(re.findall(r"<th\b", html)) == 3
        assert "ROWS" in html

    def test_actions_column_is_labelled_for_screen_readers(self, render):
        """A header cell with no text is invisible to a screen reader reading
        out the column of a focused button."""
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}x{{% endcall %}}")
        assert 'aria-label="Actions"' in html

    def test_empty_rows_render_the_empty_state_instead_of_the_table(self, render):
        html = render(f"{TABLE}{{% call table({self.COLUMNS}, rows=[], empty_title='Nothing') %}}ROWS{{% endcall %}}")
        assert "Nothing" in html
        assert "ROWS" not in html
        assert "<table" not in html

    def test_rows_none_always_renders_the_body(self, render):
        html = render(f"{TABLE}{{% call table({self.COLUMNS}, rows=none) %}}ROWS{{% endcall %}}")
        assert "ROWS" in html

    def test_cell_tone_is_a_closed_lookup(self, render):
        html = render(f'{TABLE}{{{{ cell("x", tone="muted") }}}}')
        assert "text-muted-foreground" in html

    def test_cell_rejects_arbitrary_tones_silently(self, render):
        html = render(f'{TABLE}{{{{ cell("x", tone="hotpink") }}}}')
        assert "hotpink" not in html


class TestForm:
    def test_field_wires_label_to_input(self, render):
        html = render(f'{FORM}{{{{ text_field("title", label="Title") }}}}')
        ids = re.findall(r'id="([^"]+)"', html)
        assert re.search(r'for="([^"]+)"', html).group(1) in ids

    def test_error_marks_the_control_invalid_and_describes_it(self, render):
        html = render(f'{FORM}{{{{ text_field("title", label="Title", error="Required") }}}}')
        assert 'aria-invalid="true"' in html
        assert "aria-describedby=" in html
        assert "Required" in html

    def test_error_replaces_the_hint_rather_than_stacking(self, render):
        html = render(f'{FORM}{{{{ text_field("t", hint="A hint", error="An error") }}}}')
        assert "An error" in html
        assert "A hint" not in html
        assert html.count("aria-describedby") == 1

    def test_select_marks_the_selected_option(self, render):
        html = render(f'{FORM}{{{{ select_field("p", options=[("a", "A"), ("b", "B")], selected="b") }}}}')
        assert '<option value="b" selected>' in html
        assert '<option value="a">' in html

    def test_form_target_emits_htmx_attributes(self, render):
        html = render(f'{FORM}{{% call form(action="/x", target="#board") %}}f{{% endcall %}}')
        assert 'hx-post="/x"' in html
        assert 'hx-target="#board"' in html

    def test_form_without_a_target_is_a_plain_form(self, render):
        """No target, no htmx: `action`/`method` and nothing else. An `hx-post`
        here would swap the reply into the form itself, which is never what a
        caller who omitted `target` meant."""
        html = render(f'{FORM}{{% call form(action="/x") %}}f{{% endcall %}}')
        assert 'action="/x"' in html
        assert 'method="post"' in html
        assert "hx-" not in html

    def test_form_method_reaches_both_kinds(self, render):
        plain = render(f'{FORM}{{% call form(action="/x", method="get") %}}f{{% endcall %}}')
        assert 'method="get"' in plain
        swapped = render(f'{FORM}{{% call form(action="/x", method="get", target="#t") %}}f{{% endcall %}}')
        assert 'hx-get="/x"' in swapped


class TestData:
    def test_card_actions_appear_in_the_header(self, render):
        html = render(f'{DATA}{{% call card("Title", actions="ACT") %}}BODY{{% endcall %}}')
        assert html.index("ACT") < html.index("BODY")

    def test_unpadded_card_with_a_header_gets_a_rule(self, render):
        """A flush body butting straight into header text reads as one block."""
        html = render(f'{DATA}{{% call card("Title", padded=false) %}}BODY{{% endcall %}}')
        assert "border-t" in html
        assert "<section>" not in html

    def test_unpadded_card_without_a_header_gets_no_stray_rule(self, render):
        html = render(f"{DATA}{{% call card(padded=false) %}}BODY{{% endcall %}}")
        assert "border-t" not in html

    def test_progress_exposes_its_value_to_assistive_tech(self, render):
        html = render(f"{DATA}{{{{ progress(42) }}}}")
        assert 'role="progressbar"' in html
        assert 'aria-valuenow="42"' in html

    def test_link_is_underlined_not_only_coloured(self, render):
        """A link distinguished only by colour fails for anyone who cannot see
        the colour."""
        html = render(f'{DATA}{{{{ link("Docs", "/docs") }}}}')
        assert "underline" in html

    def test_stat_tone_is_a_closed_lookup(self, render):
        assert "text-success" in render(f'{DATA}{{{{ stat("Done", 5, tone="success") }}}}')
        assert "magenta" not in render(f'{DATA}{{{{ stat("Done", 5, tone="magenta") }}}}')


class TestSpinner:
    def test_renders_one_animated_svg(self, render):
        html = render(f"{FEEDBACK}{{{{ spinner() }}}}")
        assert html.count("<svg") == 1
        assert "animate-spin" in html

    def test_takes_its_colour_from_context_not_from_a_hue(self, render):
        """`stroke="currentColor"` is why a spinner inside a primary button
        needs no tone at all — and why there is no colour literal to leak."""
        assert 'stroke="currentColor"' in render(f"{FEEDBACK}{{{{ spinner() }}}}")

    @pytest.mark.parametrize("size", ["xs", "sm", "default", "lg"])
    def test_every_size_renders(self, render, size):
        html = render(f'{FEEDBACK}{{{{ spinner(size="{size}") }}}}')
        assert re.search(r'width="\d+"', html)

    def test_unknown_size_falls_back_to_the_default(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(size="enormous") }}}}')
        assert 'width="16"' in html

    @pytest.mark.parametrize(
        ("tone", "expected"),
        [
            ("muted", "text-muted-foreground"),
            ("primary", "text-primary"),
            ("success", "text-success"),
            ("warning", "text-warning"),
            ("info", "text-info"),
            ("destructive", "text-destructive"),
        ],
    )
    def test_every_tone_maps_to_a_literal_class(self, render, tone, expected):
        assert expected in render(f'{FEEDBACK}{{{{ spinner(tone="{tone}") }}}}')

    def test_current_tone_emits_no_colour_class_at_all(self, render):
        """For a spinner inside a button, where the button already set the
        colour and a tone would override it."""
        html = render(f'{FEEDBACK}{{{{ spinner(tone="current") }}}}')
        assert "text-" not in html

    def test_unknown_tone_falls_back_rather_than_emitting_a_dead_class(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(tone="chartreuse") }}}}')
        assert "chartreuse" not in html
        assert "text-muted-foreground" in html

    def test_without_a_label_it_is_decorative(self, render):
        """Announcing the glyph as well as the "Saving…" text beside it would
        say the same thing twice."""
        html = render(f"{FEEDBACK}{{{{ spinner() }}}}")
        assert 'aria-hidden="true"' in html
        assert "role=" not in html

    def test_a_label_makes_it_the_announcement(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(label="Loading tasks") }}}}')
        assert 'role="status"' in html
        assert "sr-only" in html
        assert "Loading tasks" in html
        # role="status" already implies a polite live region.
        assert "aria-live" not in html

    def test_indicator_opts_into_htmxs_own_show_hide(self, render):
        """htmx injects the rule for this class itself, so an indicator needs
        no CSS from fjkit and no JavaScript from anyone."""
        assert "htmx-indicator" in render(f"{FEEDBACK}{{{{ spinner(indicator=true) }}}}")
        assert "htmx-indicator" not in render(f"{FEEDBACK}{{{{ spinner() }}}}")

    def test_unknown_kwargs_become_html_attributes(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(id="busy", data_test="x") }}}}')
        assert 'id="busy"' in html
        assert 'data-test="x"' in html


DIALOG_BODY = '{% call dialog("d1", title="Task 7") %}Body{% endcall %}'


def outer_tag(html: str) -> str:
    """The dialog element's own attributes, without the close button's — both
    carry a `data-size`, and only one of them is the component's contract."""
    return html.strip()[: html.strip().index(">") + 1]


class TestDialog:
    def test_it_is_a_popover_so_nothing_has_to_open_it(self, render):
        """The whole component rests on this attribute: with it the browser
        owns open state, the top layer, Escape and click-outside. Without it
        the macro would need a line of JavaScript to be worth anything."""
        html = render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")
        assert "popover" in html
        assert "showModal" not in html and "onclick" not in html

    def test_the_close_button_closes_it_declaratively(self, render):
        html = render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")
        assert 'popovertarget="d1"' in html
        assert 'popovertargetaction="hide"' in html
        assert 'aria-label="Close"' in html

    def test_dismissible_false_drops_the_close_button(self, render):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1", dismissible=false) %}}x{{% endcall %}}')
        assert "popovertargetaction" not in html

    def test_the_title_names_the_dialog(self, render):
        html = render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")
        assert 'role="dialog"' in html
        assert 'aria-labelledby="d1-title"' in html
        assert '<h2 id="d1-title">Task 7</h2>' in html

    def test_it_does_not_claim_modality_it_does_not_have(self, render):
        """A popover leaves the page behind it reachable. Saying aria-modal
        would tell a screen reader the opposite of what is true."""
        assert "aria-modal" not in render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")

    def test_no_title_means_no_dangling_label_reference(self, render):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1") %}}x{{% endcall %}}')
        assert "aria-labelledby" not in html
        assert "<header>" not in html

    def test_the_description_is_wired_to_the_dialog(self, render):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1", description="Six steps") %}}x{{% endcall %}}')
        assert 'aria-describedby="d1-description"' in html
        assert 'id="d1-description"' in html

    def test_the_body_carries_the_id_htmx_targets(self, render):
        """The published seam: a trigger fetches into `#<id>-body`, so the
        shell can render once and the contents only when it is opened."""
        assert '<section id="d1-body">Body</section>' in render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")

    @pytest.mark.parametrize("size", ["sm", "lg"])
    def test_size_is_an_attribute_not_a_class(self, render, size):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1", size="{size}") %}}x{{% endcall %}}')
        assert f'data-size="{size}"' in outer_tag(html)
        assert f"dialog-{size}" not in html

    def test_the_default_size_emits_nothing_so_basecoats_own_rule_holds(self, render):
        assert "data-size" not in outer_tag(render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}"))

    def test_unknown_size_falls_back_rather_than_emitting_a_dead_attribute(self, render):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1", size="enormous") %}}x{{% endcall %}}')
        assert "enormous" not in html
        assert "data-size" not in outer_tag(html)

    def test_the_footer_is_pre_rendered_markup_like_cards_actions(self, render):
        html = render(
            f"{FEEDBACK_DIALOG}"
            '{% set f %}<b>Close</b>{% endset %}'
            '{% call dialog("d1", footer=f) %}x{% endcall %}'
        )
        assert "<footer><b>Close</b></footer>" in html

    def test_no_footer_means_no_empty_footer_element(self, render):
        assert "<footer>" not in render(f"{FEEDBACK_DIALOG}{DIALOG_BODY}")

    def test_unknown_kwargs_become_html_attributes(self, render):
        html = render(f'{FEEDBACK_DIALOG}{{% call dialog("d1", hx_get="/x") %}}y{{% endcall %}}')
        assert 'hx-get="/x"' in html


class FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path
        self.query = ""


class FakeRequest:
    """As much of a Starlette request as `url_for` and `is_active` touch.

    A real request needs an app, a router and a scope to answer those two, and
    none of that is what these tests are about — the macro's contract is that it
    takes a *route name* and asks the globals, which a stub proves as well as a
    running app does.
    """

    def __init__(self, active: str | None = None) -> None:
        self.scope = {"route": type("Route", (), {"name": active})()}

    def url_for(self, name: str, **path_params) -> FakeURL:
        return FakeURL("/" + name)


NAV = '{% call sidebar() %}<i>nav</i>{% endcall %}'


class TestSidebar:
    def test_it_emits_basecoats_structure_because_the_css_depends_on_it(self, render):
        """`aside.sidebar > nav > section` is not a style choice — every rule in
        Basecoat's sidebar layer is written against that shape, so a macro that
        wrapped the body one element deeper would render unstyled."""
        html = render(f"{SIDEBAR}{NAV}")
        assert '<aside class="sidebar"' in html
        assert '<nav aria-label="Main">' in html
        assert "<section><i>nav</i></section>" in html

    def test_the_landmark_can_be_named(self, render):
        html = render(f'{SIDEBAR}{{% call sidebar(label="Account") %}}x{{% endcall %}}')
        assert 'aria-label="Account"' in html

    @pytest.mark.parametrize("side", ["left", "right"])
    def test_side_is_a_closed_lookup(self, render, side):
        html = render(f'{SIDEBAR}{{% call sidebar(side="{side}") %}}x{{% endcall %}}')
        assert f'data-side="{side}"' in html

    def test_unknown_side_falls_back_rather_than_killing_the_layout(self, render):
        """There is no rule for `data-side="middle"`: the panel would lose its
        border and the page would lose the margin that keeps it clear."""
        html = render(f'{SIDEBAR}{{% call sidebar(side="middle") %}}x{{% endcall %}}')
        assert "middle" not in html
        assert 'data-side="left"' in html

    def test_open_by_default_and_visible_to_assistive_tech(self, render):
        html = render(f"{SIDEBAR}{NAV}")
        assert 'aria-hidden="false"' in html
        assert "inert" not in html

    def test_closed_means_out_of_the_tab_order_not_merely_invisible(self, render):
        html = render(f'{SIDEBAR}{{% call sidebar(open=false) %}}x{{% endcall %}}')
        assert 'aria-hidden="true"' in html
        assert "inert" in html
        assert 'data-initial-open="false"' in html

    def test_header_and_footer_are_pre_rendered_markup_like_cards_actions(self, render):
        html = render(
            f"{SIDEBAR}"
            "{% set h %}<b>Acme</b>{% endset %}{% set f %}<i>v1</i>{% endset %}"
            "{% call sidebar(header=h, footer=f) %}x{% endcall %}"
        )
        assert "<header><b>Acme</b></header>" in html
        assert "<footer><i>v1</i></footer>" in html

    def test_no_slot_means_no_empty_element(self, render):
        html = render(f"{SIDEBAR}{NAV}")
        assert "<header>" not in html and "<footer>" not in html

    def test_unknown_kwargs_become_html_attributes(self, render):
        html = render(f'{SIDEBAR}{{% call sidebar(hx_get="/nav") %}}x{{% endcall %}}')
        assert 'hx-get="/nav"' in html

    def test_group_labels_itself_without_minting_an_id(self, render):
        """An id here would be an id a second copy of the same sidebar — an
        htmx swap, say — duplicates, and a duplicate `aria-labelledby` resolves
        to the wrong heading rather than to nothing."""
        html = render(f'{SIDEBAR}{{% call sidebar_group("Workspace") %}}<li>a</li>{{% endcall %}}')
        assert 'role="group"' in html and 'aria-label="Workspace"' in html
        assert "<h3>Workspace</h3>" in html
        assert "<ul><li>a</li></ul>" in html
        assert "id=" not in html
        assert "aria-labelledby" not in html

    def test_group_without_a_title_carries_no_dangling_label(self, render):
        html = render(f"{SIDEBAR}{{% call sidebar_group() %}}<li>a</li>{{% endcall %}}")
        assert "aria-label" not in html and "<h3>" not in html

    def test_link_takes_a_route_name_not_a_url(self, render):
        html = render(
            f'{SIDEBAR}{{{{ sidebar_link(request, "tasks_page", "Tasks") }}}}',
            request=FakeRequest(),
        )
        assert 'href="/tasks_page"' in html
        assert "<span>Tasks</span>" in html

    def test_the_label_sits_in_its_own_span_so_a_long_one_truncates(self, render):
        """Basecoat truncates the last span in the row. Text handed straight to
        the anchor would push the icon out of the panel instead."""
        html = render(
            f'{SIDEBAR}{{{{ sidebar_link(request, "tasks_page", "Tasks", icon_name="list-checks") }}}}',
            request=FakeRequest(),
        )
        assert "<svg" in html
        assert html.index("<svg") < html.index("<span>Tasks</span>")

    def test_the_current_page_is_marked_by_route_not_by_path(self, render):
        active = render(
            f'{SIDEBAR}{{{{ sidebar_link(request, "tasks_page", "Tasks") }}}}',
            request=FakeRequest(active="tasks_page"),
        )
        idle = render(
            f'{SIDEBAR}{{{{ sidebar_link(request, "tasks_page", "Tasks") }}}}',
            request=FakeRequest(active="dashboard"),
        )
        assert 'aria-current="page"' in active
        assert "aria-current" not in idle

    def test_link_passes_attributes_through(self, render):
        html = render(
            f'{SIDEBAR}{{{{ sidebar_link(request, "tasks_page", "T", hx_boost="true") }}}}',
            request=FakeRequest(),
        )
        assert 'hx-boost="true"' in html

    def test_submenu_is_a_details_so_the_browser_owns_the_disclosure(self, render):
        html = render(f'{SIDEBAR}{{% call sidebar_submenu("Reports") %}}<li>a</li>{{% endcall %}}')
        assert "<details>" in html and "<summary>" in html
        assert "<ul><li>a</li></ul>" in html
        assert "aria-expanded" not in html, "the element already announces its own state"

    def test_submenu_can_start_open_for_the_branch_the_page_is_in(self, render):
        html = render(f'{SIDEBAR}{{% call sidebar_submenu("Reports", open=true) %}}x{{% endcall %}}')
        assert "<details open>" in html

    def test_trigger_names_what_it_controls(self, render):
        html = render(f'{SIDEBAR}{{{{ sidebar_trigger("app-nav") }}}}')
        assert 'aria-controls="app-nav"' in html
        assert "getElementById(\'app-nav\')" in html
        assert 'aria-label="Toggle navigation"' in html

    def test_trigger_does_not_render_a_state_the_script_owns(self, render):
        """A server-rendered `aria-expanded` is a second copy of the open state,
        and the copy is stale the first time anyone clicks."""
        assert "aria-expanded" not in render(f"{SIDEBAR}{{{{ sidebar_trigger() }}}}")


SHELL_WITH_SIDEBAR = """
{% extends "ui/shell.html" %}
{% from "ui/sidebar.html" import sidebar %}
{% block sidebar %}{% call sidebar() %}<i>nav</i>{% endcall %}{% endblock %}
{% block content %}<main-content/>{% endblock %}
"""

SHELL_WITHOUT_SIDEBAR = """
{% extends "ui/shell.html" %}
{% block content %}<main-content/>{% endblock %}
"""


class TestShellSidebarSlot:
    def test_filling_the_block_switches_the_layout(self, render):
        html = render(SHELL_WITH_SIDEBAR)
        assert '<aside class="sidebar"' in html
        assert "max-w-6xl" not in html, "a centred wrapper would sit under the fixed panel"

    def test_the_wrapper_is_the_asides_immediate_sibling(self, render):
        """Basecoat gives the margin to `.sidebar + *`. Anything rendered
        between the two takes the margin instead, and the page slides under the
        panel — silently, and only once someone opens it."""
        html = render(SHELL_WITH_SIDEBAR)
        between = html[html.index("</aside>") + len("</aside>") : html.index("<div class=")]
        assert between.strip() == ""

    def test_a_sidebar_brings_its_own_toggle(self, render):
        assert "aria-controls=\"sidebar\"" in render(SHELL_WITH_SIDEBAR)

    def test_an_app_without_one_is_untouched(self, render):
        html = render(SHELL_WITHOUT_SIDEBAR)
        assert "sidebar" not in html
        assert "mx-auto flex min-h-screen max-w-6xl flex-col px-5" in html


TABS = '{% from "ui/tabs.html" import tabs, tab_panel %}'
CODE = '{% from "ui/data.html" import code_block, item_list, item %}'
GROUP = '{% from "ui/button.html" import button, button_group %}'

FILE_ITEMS = '[{"id": "a", "label": "main.py"}, {"id": "b", "label": "router.py"}]'


class TestTabs:
    """Basecoat's script drives `.tabs`, and it finds everything through the
    aria wiring. These lock the four attributes it reads — get any of them
    wrong and the tabs silently stop switching, with no error anywhere."""

    def test_each_tab_points_at_its_panel(self, render):
        html = render(
            f"{TABS}{{% call tabs({FILE_ITEMS}) %}}"
            '{% call tab_panel("a") %}A{% endcall %}'
            '{% call tab_panel("b") %}B{% endcall %}'
            "{% endcall %}"
        )
        assert 'aria-controls="a"' in html and 'id="a"' in html
        assert 'aria-controls="b"' in html and 'id="b"' in html
        assert html.count('role="tab"') == 2
        assert html.count('role="tabpanel"') == 2

    def test_the_first_tab_is_selected_by_default(self, render):
        html = render(f"{TABS}{{% call tabs({FILE_ITEMS}) %}}{{% endcall %}}")
        assert 'aria-controls="a"\n                aria-selected="true"' in html or (
            'aria-controls="a"' in html.split('aria-selected="true"')[0]
        )
        assert html.count('aria-selected="true"') == 1

    def test_selected_names_the_open_tab(self, render):
        """The server knows which tab the request was for, so this is a
        parameter rather than something a script decides after paint."""
        html = render(f'{TABS}{{% call tabs({FILE_ITEMS}, selected="b") %}}{{% endcall %}}')
        assert html.count('aria-selected="true"') == 1
        assert 'aria-controls="b"' in html.split('aria-selected="true"')[0]

    def test_orientation_is_a_closed_lookup(self, render):
        """`aria-orientation` is what the key handler reads to choose between
        Left/Right and Up/Down. Interpolating it would let a typo through and
        leave the arrow keys dead with no other symptom."""
        html = render(f'{TABS}{{% call tabs({FILE_ITEMS}, orientation="sideways") %}}{{% endcall %}}')
        assert 'aria-orientation="horizontal"' in html
        assert "sideways" not in html

    def test_panels_are_not_pre_hidden(self, render):
        """Basecoat hides the inactive panels on init. Rendering them hidden
        would make them invisible to a reader with scripting off."""
        html = render(
            f"{TABS}{{% call tabs({FILE_ITEMS}) %}}"
            '{% call tab_panel("b") %}second{% endcall %}{% endcall %}'
        )
        assert "hidden" not in html
        assert "second" in html


class TestCodeBlock:
    def test_a_scroll_region_is_reachable_by_keyboard(self, render):
        """A scroll container nothing can focus cannot be scrolled without a
        mouse. This is the reason the macro exists rather than being a <pre>."""
        html = render(f'{CODE}{{{{ code_block("x = 1") }}}}')
        assert 'tabindex="0"' in html

    def test_a_region_role_is_only_used_with_a_name(self, render):
        """An unlabelled region is a stop in the tab order that announces
        nothing — worse than no landmark at all."""
        bare = render(f'{CODE}{{{{ code_block("x = 1") }}}}')
        assert "role=" not in bare

        named = render(f'{CODE}{{{{ code_block("x = 1", label="main.py") }}}}')
        assert 'role="region"' in named and 'aria-label="main.py"' in named

    def test_source_is_escaped_not_interpreted(self, render):
        html = render(f'{CODE}{{{{ code_block("<script>alert(1)</script>") }}}}')
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_wrap_is_an_attribute(self, render):
        assert 'data-wrap="true"' in render(f'{CODE}{{{{ code_block("x", wrap=true) }}}}')
        assert "data-wrap" not in render(f'{CODE}{{{{ code_block("x") }}}}')


class TestItemList:
    def test_uses_basecoat_s_markup_contract(self, render):
        """`.item > section` is the text column and `.item > aside` the actions;
        the CSS keys off those elements, so they are not interchangeable."""
        html = render(f"{CODE}{{% call item_list() %}}{{{{ item(\"router.py\", \"routes\") }}}}{{% endcall %}}")
        assert 'class="item-group"' in html
        assert 'class="item"' in html
        assert "<section>" in html and "<h4>" in html

    def test_href_switches_the_row_to_an_anchor(self, render):
        html = render(f'{CODE}{{{{ item("Docs", href="/docs") }}}}')
        assert '<a class="item"' in html and 'href="/docs"' in html

    def test_clamp_false_releases_the_two_line_limit(self, render):
        """Basecoat clamps a row's description to two lines, which is right for
        a feed and wrong for a definition list."""
        assert 'data-clamp="false"' in render(f'{CODE}{{{{ item("t", "d", clamp=false) }}}}')
        assert "data-clamp" not in render(f'{CODE}{{{{ item("t", "d") }}}}')

    def test_description_accepts_markup(self, render):
        html = render(
            f'{CODE}{{% set body %}}<em>emphasis</em>{{% endset %}}{{{{ item("t", body) }}}}'
        )
        assert "<em>emphasis</em>" in html


class TestButtonGroupOrientation:
    def test_vertical_uses_basecoat_s_own_attribute(self, render):
        html = render(f'{GROUP}{{% call button_group(orientation="vertical") %}}x{{% endcall %}}')
        assert 'class="button-group"' in html
        assert 'data-orientation="vertical"' in html

    def test_extra_keywords_reach_the_element(self, render):
        """Every other component takes pass-through attributes; this one did
        not, which made it the only one you could not hang an id on."""
        for orientation in ("horizontal", "vertical"):
            html = render(
                f'{GROUP}{{% call button_group(orientation="{orientation}", id="filters") %}}x{{% endcall %}}'
            )
            assert 'id="filters"' in html
