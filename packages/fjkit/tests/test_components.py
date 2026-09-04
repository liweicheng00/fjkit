"""Contract tests for the component macros.

These lock down what callers depend on: which element a macro emits, which
attribute carries the variant, and that pass-through attributes survive. A
published signature cannot change (CHARTER.md A4), so these tests are what make
a breaking change loud.
"""

from __future__ import annotations

import re

import pytest

BUTTON = '{% from "ui/button.html" import button %}'
DATA = (
    '{% from "ui/data.html" import badge, card, stat, progress, empty_state, metric_group,'
    ' caption, link, kbd %}'
)
LAYOUT = (
    '{% from "ui/layout.html" import stack, row, grid, split, centered, page_header,'
    " section, divider %}"
)
TABLE = (
    '{% from "ui/table.html" import table, cell, row_actions, select_cell,'
    ' select_count, select_scripts, pagination, page_size %}'
)
FORM = (
    '{% from "ui/form.html" import text_field, select_field, form, field_row,'
    ' textarea_field, checkbox_field, switch_field, radio_group, fieldset, form_scripts %}'
)
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
        """Basecoat's API is `data-variant`. A parallel `btn-primary` class
        would be a second way to say the same thing, and the two would drift."""
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
        """An interpolated `gap-99` is not in the stylesheet, so the element
        would silently lose its spacing."""
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

    @pytest.mark.parametrize("width", ["xs", "sm", "md", "lg", "xl", "prose"])
    def test_centered_renders_every_width_it_offers(self, render, width):
        html = render(f'{LAYOUT}{{% call centered("{width}") %}}x{{% endcall %}}')
        assert f"max-w-{width}" in html
        assert "mx-auto" in html

    def test_centered_falls_back_rather_than_emitting_a_dead_class(self, render):
        """`max-w-24rem` is not in the stylesheet, so the column would render at
        full width with nothing to say why."""
        html = render(f'{LAYOUT}{{% call centered("24rem") %}}x{{% endcall %}}')
        assert "max-w-24rem" not in html
        assert "max-w-sm" in html

    def test_centered_is_a_stack_so_the_common_case_is_one_call(self, render):
        html = render(f"{LAYOUT}{{% call centered(gap=4) %}}x{{% endcall %}}")
        assert "flex-col" in html and "gap-4" in html


class TestTable:
    COLUMNS = '[{"label": "Task"}, {"label": "Owner"}, {"width": "min"}]'

    def test_renders_a_header_per_column(self, render):
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}ROWS{{% endcall %}}")
        assert len(re.findall(r"<th\b", html)) == 3
        assert "ROWS" in html

    def test_actions_column_is_labelled_for_screen_readers(self, render):
        """A header cell with no text is invisible to a screen reader reading out
        the column of a focused button."""
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}x{{% endcall %}}")
        assert 'aria-label="Actions"' in html

    def test_a_narrow_column_with_a_heading_keeps_it(self, render):
        """`aria-label` replaces the text rather than adding to it, so labelling
        every `width="min"` column would rename any that has a heading of its
        own — a row-number column would read out as "Actions"."""
        columns = '[{"label": "#", "width": "min", "align": "end"}]'
        html = render(f"{TABLE}{{% call table({columns}) %}}x{{% endcall %}}")
        assert "Actions" not in html
        assert ">#</th>" in html

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

class TestSortableHeaders:
    """0.4. A sorted column has to say so twice — once to the eye, once to
    `aria-sort` — and the two are keyed off one value so they cannot disagree.
    """

    SORTED = '[{"label": "Task", "sort": "asc", "sort_url": "/t?o=-title"}]'
    SORTABLE = '[{"label": "Task", "sort_url": "/t?o=title"}]'
    FIXED = '[{"label": "Task"}]'

    def test_a_fixed_column_is_not_announced_as_sortable(self, render):
        """`aria-sort` on a column that cannot be sorted tells a screen reader
        to look for a control that is not there."""
        html = render(f"{TABLE}{{% call table({self.FIXED}) %}}r{{% endcall %}}")
        assert "aria-sort" not in html
        assert "<a " not in html

    def test_sort_url_is_what_makes_a_column_sortable(self, render):
        html = render(f"{TABLE}{{% call table({self.SORTABLE}) %}}r{{% endcall %}}")
        assert 'href="/t?o=title"' in html
        assert 'aria-sort="none"' in html

    @pytest.mark.parametrize(
        ("state", "aria", "glyph"),
        [("asc", "ascending", "m5 12 7-7 7 7"), ("desc", "descending", "m19 12-7 7-7-7")],
    )
    def test_the_arrow_and_aria_sort_say_the_same_thing(self, render, state, aria, glyph):
        """The failure this guards is an arrow pointing up over a descending
        sort: it looks fine in review and is wrong on the page."""
        columns = f'[{{"label": "Task", "sort": "{state}", "sort_url": "/t"}}]'
        html = render(f"{TABLE}{{% call table({columns}) %}}r{{% endcall %}}")
        assert f'aria-sort="{aria}"' in html
        assert glyph in html

    def test_an_unsorted_column_still_shows_the_affordance(self, render):
        """Without a glyph, a sortable column is indistinguishable from a fixed
        one until somebody clicks it."""
        html = render(f"{TABLE}{{% call table({self.SORTABLE}) %}}r{{% endcall %}}")
        assert "m7 15 5 5 5-5" in html  # chevrons-up-down

    def test_the_glyph_is_hidden_from_the_screen_reader(self, render):
        """`aria-sort` has already said it; reading the icon too says
        "ascending" twice."""
        html = render(f"{TABLE}{{% call table({self.SORTED}) %}}r{{% endcall %}}")
        header = html.split("<th ")[1].split("</th>")[0]
        assert 'aria-hidden="true"' in header

    def test_no_target_still_sorts(self, render):
        """Sorting works with JavaScript off, and a sorted view is a URL."""
        html = render(f"{TABLE}{{% call table({self.SORTED}) %}}r{{% endcall %}}")
        assert 'href="/t?o=-title"' in html
        assert "hx-get" not in html

    def test_a_target_adds_the_swap_on_top_of_the_link(self, render):
        html = render(f'{TABLE}{{% call table({self.SORTED}, target="#board") %}}r{{% endcall %}}')
        assert 'href="/t?o=-title"' in html
        assert 'hx-get="/t?o=-title"' in html
        assert 'hx-target="#board"' in html
        assert 'hx-swap="outerHTML"' in html

    def test_the_swap_pushes_the_url_by_default(self, render):
        """Otherwise the back button leaves the page and the address bar
        describes a sort order nobody is looking at."""
        html = render(f'{TABLE}{{% call table({self.SORTED}, target="#board") %}}r{{% endcall %}}')
        assert 'hx-push-url="true"' in html
        off = render(f'{TABLE}{{% call table({self.SORTED}, target="#b", push_url=false) %}}r{{% endcall %}}')
        assert "hx-push-url" not in off

    def test_an_empty_table_renders_no_headers_to_sort(self, render):
        """The empty state replaces the table, so there is nothing to click."""
        html = render(f"{TABLE}{{% call table({self.SORTED}, rows=[]) %}}r{{% endcall %}}")
        assert "aria-sort" not in html


class TestSelectColumn:
    """0.4. The batch-selection column: a header box, a row box, and the
    readout that says what a bulk action is about to reach."""

    COLUMNS = '[{"select": true}, {"label": "Task"}]'

    def test_the_select_column_renders_a_header_checkbox(self, render):
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}r{{% endcall %}}")
        assert 'type="checkbox"' in html
        assert 'data-fjkit-select-all="selected"' in html

    def test_the_header_checkbox_is_labelled(self, render):
        """A bare checkbox in a header cell announces itself as "checkbox"."""
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}r{{% endcall %}}")
        assert 'aria-label="Select all rows"' in html

    def test_the_checkbox_role_is_written_out_for_basecoat(self, render):
        """Redundant on a native checkbox, and load-bearing: Basecoat's table
        rules select on `[role=checkbox]` to drop the cell's trailing padding.
        """
        html = render(f"{TABLE}{{% call table({self.COLUMNS}) %}}r{{% endcall %}}")
        assert 'role="checkbox"' in html
        assert 'role="checkbox"' in render(f"{TABLE}{{{{ select_cell(7) }}}}")

    def test_the_row_checkbox_posts_as_an_ordinary_repeated_field(self, render):
        """`selected=3&selected=7` — a route reads it as `list[int]`, and
        nothing here invents a wire format."""
        html = render(f"{TABLE}{{{{ select_cell(7) }}}}")
        assert 'name="selected"' in html
        assert 'value="7"' in html

    def test_the_name_is_the_key_that_joins_header_to_rows(self, render):
        """Two selections on one page are two names, because the name is
        already what decides what lands in one request."""
        header = render(f'{TABLE}{{% call table([{{"select": true}}], select_name="ids") %}}r{{% endcall %}}')
        row = render(f'{TABLE}{{{{ select_cell(7, name="ids") }}}}')
        assert 'data-fjkit-select-all="ids"' in header
        assert 'data-fjkit-select="ids"' in row

    def test_a_row_checkbox_is_labelled_by_its_row(self, render):
        html = render(f'{TABLE}{{{{ select_cell(7, label="Select Ship it") }}}}')
        assert 'aria-label="Select Ship it"' in html

    def test_an_unlabelled_row_checkbox_falls_back_to_the_value(self, render):
        """Never unlabelled, even though an id is not a label."""
        assert 'aria-label="Select 7"' in render(f"{TABLE}{{{{ select_cell(7) }}}}")

    def test_a_row_the_server_already_picked_renders_checked(self, render):
        assert " checked" in render(f"{TABLE}{{{{ select_cell(7, checked=true) }}}}")

    def test_the_count_carries_both_strings_so_a_page_can_translate_them(self, render):
        """`js/select.js` must not contain a word of English."""
        html = render(f'{TABLE}{{{{ select_count(label="已選取 {{n}} 筆", zero="尚未選取") }}}}')
        assert 'data-fjkit-select-label="已選取 {n} 筆"' in html
        assert 'data-fjkit-select-zero="尚未選取"' in html
        assert "尚未選取</span>" in html

    def test_a_count_with_no_zero_text_hides_itself(self, render):
        html = render(f"{TABLE}{{{{ select_count(zero=none) }}}}")
        assert "hidden" in html
        assert "data-fjkit-select-zero" not in html

    def test_the_script_is_opted_into_per_page(self, render):
        """CHARTER §7: the shell downloads htmx and Basecoat and nothing else."""
        assert "js/select.js" in render(f"{TABLE}{{{{ select_scripts() }}}}")


class TestPagination:
    """0.4. The strip under a table."""

    def test_one_page_renders_nothing(self, render):
        """A strip reading "1" with both arrows greyed out tells the reader
        nothing, and hiding it here saves every caller the same guard."""
        assert render(f'{TABLE}{{{{ pagination(1, 1, "/r") }}}}').strip() == ""
        assert render(f'{TABLE}{{{{ pagination(1, 0, "/r") }}}}').strip() == ""

    def test_every_page_is_a_real_link(self, render):
        """A paginated list has to survive JavaScript being off: page 4 of the
        results is a thing people bookmark and send to each other."""
        html = render(f'{TABLE}{{{{ pagination(1, 3, "/r") }}}}')
        assert 'href="/r?page=2"' in html
        assert "hx-get" not in html

    def test_a_target_adds_the_swap_on_top(self, render):
        html = render(f'{TABLE}{{{{ pagination(1, 3, "/r", target="#list") }}}}')
        assert 'href="/r?page=2"' in html
        assert 'hx-get="/r?page=2"' in html
        assert 'hx-target="#list"' in html
        assert 'hx-push-url="true"' in html

    def test_an_existing_query_string_is_joined_with_an_ampersand(self, render):
        html = render(f'{TABLE}{{{{ pagination(1, 3, "/r?status=open") }}}}')
        assert "/r?status=open&amp;page=2" in html

    def test_the_current_page_is_announced(self, render):
        html = render(f'{TABLE}{{{{ pagination(2, 5, "/r") }}}}')
        assert html.count('aria-current="page"') == 1
        assert 'aria-current="page"' in html.split(">2<")[0].rsplit("<a", 1)[-1]

    def test_the_page_number_is_clamped_to_the_range(self, render):
        """`page` arrives from a query string. A strip built around page 900 of
        9 renders links to nowhere and reports nothing."""
        for page in (0, -3, 900):
            html = render(f'{TABLE}{{{{ pagination({page}, 9, "/r") }}}}')
            assert html.count('aria-current="page"') == 1

    def test_a_dead_step_is_a_disabled_button_not_a_dead_link(self, render):
        """An anchor with no href is skipped by the keyboard entirely, so the
        arrow would vanish from tab order instead of announcing itself."""
        first = render(f'{TABLE}{{{{ pagination(1, 5, "/r") }}}}')
        assert "<button" in first.split("Previous")[0]
        assert "disabled" in first.split("Previous")[0]
        last = render(f'{TABLE}{{{{ pagination(5, 5, "/r") }}}}')
        assert "disabled" in last.rsplit("Next", 1)[0].rsplit("<button", 1)[-1] + "x"

    def test_the_steps_carry_rel(self, render):
        html = render(f'{TABLE}{{{{ pagination(3, 5, "/r") }}}}')
        assert 'rel="prev"' in html
        assert 'rel="next"' in html

    def test_the_strip_is_a_fixed_width_however_many_pages_there_are(self, render):
        """First and last always show; the jump to the window is an ellipsis.
        Nine thousand pages must not render nine thousand links."""
        html = render(f'{TABLE}{{{{ pagination(500, 9000, "/r") }}}}')
        assert html.count("…") == 2
        assert len(re.findall(r"page=\d+", html)) == 7  # prev, 1, 499, 500, 501, 9000, next
        assert "page=9000" in html and "page=1" in html

    def test_no_ellipsis_when_the_window_already_reaches_the_end(self, render):
        assert "…" not in render(f'{TABLE}{{{{ pagination(2, 3, "/r") }}}}')

    def test_no_page_is_listed_twice(self, render):
        """The first and last links are rendered outside the window, so a
        window that overlaps them must not print them again."""
        for page, pages in [(1, 2), (2, 3), (1, 4), (4, 4), (3, 5)]:
            html = render(f'{TABLE}{{{{ pagination({page}, {pages}, "/r") }}}}')
            numbers = re.findall(r'data-size="icon-sm"[^>]*>(\d+)<', html)
            assert numbers == sorted(set(numbers), key=int), f"{page}/{pages}: {numbers}"

    def test_the_summary_needs_both_halves(self, render):
        """A range with no total, or a total with no page size, is a number
        nobody can act on."""
        assert "of 210" not in render(f'{TABLE}{{{{ pagination(4, 9, "/r", total=210) }}}}')
        assert "of 210" not in render(f'{TABLE}{{{{ pagination(4, 9, "/r", per_page=25) }}}}')

    def test_the_summary_counts_from_the_current_page(self, render):
        html = render(f'{TABLE}{{{{ pagination(4, 9, "/r", total=210, per_page=25) }}}}')
        assert "76–100 of 210" in html

    def test_the_last_page_summary_stops_at_the_total(self, render):
        """`9 × 25` is 225, and there are 210 rows."""
        html = render(f'{TABLE}{{{{ pagination(9, 9, "/r", total=210, per_page=25) }}}}')
        assert "201–210 of 210" in html

    def test_the_strip_names_itself(self, render):
        """Two navs on one page — the site's and this one — need telling apart."""
        assert 'aria-label="Pagination"' in render(f'{TABLE}{{{{ pagination(2, 5, "/r") }}}}')


class TestPageSize:
    """0.4. The "Rows per page" control. A form, because a `<select>` cannot act
    on its own change and the kit adds no script for it."""

    CALL = '{{ page_size("/r", 25, options=[10, 25, 50]) }}'
    HTMX = '{{ page_size("/r", 25, options=[10, 25, 50], target="#list") }}'

    def test_it_is_a_get_form(self, render):
        html = render(f"{TABLE}{self.CALL}")
        assert '<form' in html and 'method="get"' in html and 'action="/r"' in html

    def test_the_size_in_use_is_the_one_selected(self, render):
        html = render(f"{TABLE}{self.CALL}")
        assert '<option value="25" selected>' in html
        assert '<option value="10">' in html

    def test_the_options_are_the_callers(self, render):
        """A closed list, so the control cannot offer a size the router would
        refuse."""
        assert '<option value="7"' in render(f'{TABLE}{{{{ page_size("/r", 7, options=[7]) }}}}')

    def test_the_select_is_labelled_and_wired_to_its_label(self, render):
        html = render(f"{TABLE}{self.CALL}")
        assert re.search(r'for="([^"]+)"', html).group(1) in re.findall(r'id="([^"]+)"', html)

    def test_both_strings_are_parameters(self, render):
        """So a translated page translates them without touching the kit."""
        html = render(f'{TABLE}{{{{ page_size("/r", 10, options=[10], label="每頁", apply_label="套用") }}}}')
        assert "每頁" in html and "套用" in html

    def test_without_a_target_the_button_is_the_only_way_to_apply(self, render):
        html = render(f"{TABLE}{self.CALL}")
        assert 'type="submit"' in html
        assert "<noscript>" not in html
        assert "hx-get" not in html

    def test_with_a_target_the_select_applies_itself(self, render):
        """`change`, not `submit`: a form's default trigger is its submit event
        and on this path nothing ever submits it."""
        html = render(f"{TABLE}{self.HTMX}")
        assert 'hx-get="/r"' in html
        assert 'hx-trigger="change"' in html
        assert 'hx-target="#list"' in html
        assert 'hx-push-url="true"' in html

    def test_with_a_target_the_button_is_only_there_without_scripting(self, render):
        """It has to exist — with JavaScript off the select cannot act — and it
        must not show when htmx is running the change for you."""
        html = render(f"{TABLE}{self.HTMX}")
        assert html.count('type="submit"') == 1
        assert re.search(r"<noscript>.*type=\"submit\".*</noscript>", html, re.S)

    def test_kept_values_travel_as_hidden_fields(self, render):
        """A native GET submit replaces the whole query string with the form's
        fields, so anything only in `action=` is dropped on that path and kept
        on the other — and the two would disagree about which filter is on."""
        html = render(f'{TABLE}{{{{ page_size("/r", 10, options=[10], keep={{"o": "-updated"}}) }}}}')
        assert '<input type="hidden" name="o" value="-updated">' in html

    def test_a_none_in_keep_sends_no_field(self, render):
        """An absent filter is absent, not an empty string the router then has
        to tell apart from a real one."""
        html = render(f'{TABLE}{{{{ page_size("/r", 10, options=[10], keep={{"q": none}}) }}}}')
        assert "hidden" not in html

    def test_the_url_carries_no_query_string_of_its_own(self, render):
        """Nothing enforces this — it is the caller's to get right — so the
        macro at least must not add one."""
        assert 'action="/r"' in render(f"{TABLE}{self.CALL}")


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
        """No target, no htmx: `action` and `method` and nothing else. An
        `hx-post` here would swap the reply into the form itself, which is never
        what a caller who omitted `target` meant."""
        html = render(f'{FORM}{{% call form(action="/x") %}}f{{% endcall %}}')
        assert 'action="/x"' in html
        assert 'method="post"' in html
        assert "hx-" not in html

    def test_form_method_reaches_both_kinds(self, render):
        plain = render(f'{FORM}{{% call form(action="/x", method="get") %}}f{{% endcall %}}')
        assert 'method="get"' in plain
        swapped = render(f'{FORM}{{% call form(action="/x", method="get", target="#t") %}}f{{% endcall %}}')
        assert 'hx-get="/x"' in swapped

    @pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
    def test_htmx_issues_every_verb(self, render, method):
        """htmx can send all five, so the macro can name all five."""
        html = render(f'{FORM}{{% call form(action="/x", method="{method}", target="#t") %}}f{{% endcall %}}')
        assert f'hx-{method}="/x"' in html

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    def test_a_browser_only_has_two_verbs_so_the_rest_post(self, render, method):
        """Every browser treats `<form method="put">` as GET, which drops the
        body: a save that silently becomes a read. Falling back to POST keeps
        what was typed, and losing it would be the quieter failure."""
        html = render(f'{FORM}{{% call form(action="/x", method="{method}") %}}f{{% endcall %}}')
        assert 'method="post"' in html
        assert f'method="{method}"' not in html

    def test_a_verb_nobody_ships_is_not_invented(self, render):
        """The same closed-lookup rule the encodings follow: a typo falls back
        rather than emitting an `hx-` attribute htmx has never heard of."""
        html = render(f'{FORM}{{% call form(action="/x", method="pust", target="#t") %}}f{{% endcall %}}')
        assert 'hx-post="/x"' in html
        assert "hx-pust" not in html

    def test_a_form_is_urlencoded_unless_it_says_otherwise(self, render):
        """The default stays the encoding that needs no extension loaded and no
        JavaScript to submit."""
        html = render(f'{FORM}{{% call form(action="/x", target="#b") %}}f{{% endcall %}}')
        assert "hx-ext" not in html

    def test_json_encoding_names_the_extension_that_carries_it(self, render):
        """`encoding="json"` is a fact about the body, and htmx expresses it as
        an extension on the element that submits."""
        html = render(f'{FORM}{{% call form(action="/x", target="#b", encoding="json") %}}f{{% endcall %}}')
        assert 'hx-ext="json-enc"' in html

    def test_json_encoding_does_nothing_without_a_target(self, render):
        """The browser submits a form with no target, sending urlencoded or
        multipart, and has never heard of an htmx extension. Emitting `hx-ext`
        there would describe something that cannot happen."""
        html = render(f'{FORM}{{% call form(action="/x", encoding="json") %}}f{{% endcall %}}')
        assert "hx-ext" not in html
        assert 'action="/x"' in html

    def test_an_encoding_nobody_ships_is_not_invented(self, render):
        """A closed enumeration read through `.get`: a typo falls back to the
        default rather than emitting an extension name that does not exist."""
        html = render(f'{FORM}{{% call form(action="/x", target="#b", encoding="jsonn") %}}f{{% endcall %}}')
        assert "hx-ext" not in html

    def test_form_scripts_loads_the_extension_after_htmx(self, render):
        """`defer`, because deferred scripts run in document order and htmx is
        deferred in the shell's head. Without it this script runs first and
        throws on an undefined `htmx`."""
        html = render(f"{FORM}{{{{ form_scripts() }}}}")
        assert "<script defer" in html
        assert "vendor/htmx/json-enc.js" in html

    def test_the_extension_is_actually_in_the_package(self):
        """The macro names a path, and nothing else checks that the vendoring
        script put a file there. A missing file is a 404 in the browser and a
        form that quietly posts urlencoded."""
        from fjkit.config import STATIC_DIR

        assert (STATIC_DIR / "vendor" / "htmx" / "json-enc.js").is_file()

    @pytest.mark.parametrize(
        "call",
        [
            'textarea_field("t", label="L", error="E")',
            'checkbox_field("t", label="L", error="E")',
            'switch_field("t", label="L", error="E")',
            'radio_group("t", label="L", options=[("a", "A")], error="E")',
        ],
    )
    def test_every_field_reports_an_error_the_same_way(self, render, call):
        """One contract across the set: `aria-invalid` on the control, and the
        message in a `<p>` the control names. A caller who learns it once for
        `text_field` knows it for all of them."""
        html = render(f"{FORM}{{{{ {call} }}}}")
        assert 'aria-invalid="true"' in html
        described = re.search(r'aria-describedby="([^"]+)"', html).group(1)
        assert f'id="{described}"' in html
        assert "E" in html

    @pytest.mark.parametrize(
        "call",
        [
            'textarea_field("t", label="L", hint="H", error="E")',
            'checkbox_field("t", label="L", hint="H", error="E")',
            'switch_field("t", label="L", hint="H", error="E")',
            'radio_group("t", label="L", options=[("a", "A")], hint="H", error="E")',
        ],
    )
    def test_every_field_replaces_the_hint_with_the_error(self, render, call):
        html = render(f"{FORM}{{{{ {call} }}}}")
        assert ">E<" in html
        assert ">H<" not in html

    def test_textarea_holds_its_value_as_content_not_an_attribute(self, render):
        html = render(f'{FORM}{{{{ textarea_field("notes", value="two\nlines") }}}}')
        assert ">two\nlines</textarea>" in html
        assert "value=" not in html

    def test_checkbox_and_switch_are_the_same_control_to_a_route(self, render):
        """Only `role` separates them, so a handler reads one name either way
        and swapping the presentation never touches the router."""
        box = render(f'{FORM}{{{{ checkbox_field("done", checked=true) }}}}')
        switch = render(f'{FORM}{{{{ switch_field("done", checked=true) }}}}')
        for html in (box, switch):
            assert 'type="checkbox"' in html
            assert 'name="done"' in html
            assert " checked" in html
        assert 'role="switch"' in switch
        assert 'role="switch"' not in box

    def test_switch_puts_the_control_after_its_label(self, render):
        """A settings row lines its switches up on one edge; a checkbox sits in
        front of the words it qualifies. That is the visual difference."""
        html = render(f'{FORM}{{{{ switch_field("d", label="Digest") }}}}')
        assert html.index("Digest") < html.index("<input")
        html = render(f'{FORM}{{{{ checkbox_field("d", label="Digest") }}}}')
        assert html.index("<input") < html.index("Digest")

    def test_radio_group_is_a_fieldset_with_one_name_and_distinct_ids(self, render):
        html = render(
            f'{FORM}{{{{ radio_group("p", label="Priority",'
            ' options=[("low", "Low"), ("high", "High")], selected="high") }}'
        )
        assert "<fieldset" in html and "<legend" in html
        assert 'role="radiogroup"' in html
        assert html.count('name="p"') == 2
        ids = re.findall(r'<input[^>]*id="([^"]+)"', html)
        assert len(set(ids)) == 2
        assert re.search(r'value="high"[^>]* checked', html)
        assert not re.search(r'value="low"[^>]* checked', html)

    def test_radio_group_takes_the_same_options_shape_as_select(self, render):
        """One shape for both, so swapping a select for radios is a one-word
        edit."""
        options = '[("a", "A"), ("b", "B")]'
        selected = "b"
        radios = render(f'{FORM}{{{{ radio_group("p", options={options}, selected="{selected}") }}}}')
        select = render(f'{FORM}{{{{ select_field("p", options={options}, selected="{selected}") }}}}')
        for html in (radios, select):
            assert ">A<" in html and ">B<" in html

    def test_fieldset_wraps_what_it_is_called_with(self, render):
        html = render(f'{FORM}{{% call fieldset("Group", hint="Why") %}}INNER{{% endcall %}}')
        assert "<fieldset" in html
        assert ">Group</legend>" in html
        assert html.index("Why") < html.index("INNER")

    def test_a_group_legend_outranks_a_field_legend(self, render):
        """`fieldset` names a section of the form; `radio_group`'s legend is a
        field label and has to match the labels beside it."""
        group = render(f'{FORM}{{% call fieldset("Group") %}}x{{% endcall %}}')
        field = render(f'{FORM}{{{{ radio_group("p", label="P", options=[("a", "A")]) }}}}')
        assert 'data-variant="legend"' in group
        assert 'data-variant="label"' in field


class TestData:
    def test_card_actions_appear_in_the_header(self, render):
        html = render(f'{DATA}{{% call card("Title", actions="ACT") %}}BODY{{% endcall %}}')
        assert html.index("ACT") < html.index("BODY")

    def test_unpadded_card_with_a_header_gets_a_rule(self, render):
        """A flush body running straight into header text reads as one block."""
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
        """A link distinguished only by colour fails anyone who cannot see the
        colour."""
        html = render(f'{DATA}{{{{ link("Docs", "/docs") }}}}')
        assert "underline" in html

    def test_caption_is_muted_and_small(self, render):
        """Why it is a macro at all: `text-muted-foreground` is a colour utility
        an app template may not write."""
        html = render(f'{DATA}{{{{ caption("Refreshed every five minutes.") }}}}')
        assert '<p class="text-muted-foreground text-sm">Refreshed every five minutes.</p>' in html

    def test_caption_takes_a_block_when_it_has_to_hold_a_link(self, render):
        html = render(f'{DATA}{{% call caption() %}}See {{{{ link("docs", "/d") }}}}{{% endcall %}}')
        assert "text-muted-foreground" in html
        assert 'href="/d"' in html

    def test_stat_tone_is_a_closed_lookup(self, render):
        assert "text-success" in render(f'{DATA}{{{{ stat("Done", 5, tone="success") }}}}')
        assert "magenta" not in render(f'{DATA}{{{{ stat("Done", 5, tone="magenta") }}}}')


class TestSpinner:
    def test_renders_one_animated_svg(self, render):
        html = render(f"{FEEDBACK}{{{{ spinner() }}}}")
        assert html.count("<svg") == 1
        assert "animate-spin" in html

    def test_takes_its_colour_from_context_not_from_a_hue(self, render):
        """`stroke="currentColor"` is why a spinner inside a primary button needs
        no tone, and why there is no colour literal to leak."""
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
        """For a spinner inside a button, where the button has already set the
        colour and a tone would override it."""
        html = render(f'{FEEDBACK}{{{{ spinner(tone="current") }}}}')
        assert "text-" not in html

    def test_unknown_tone_falls_back_rather_than_emitting_a_dead_class(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(tone="chartreuse") }}}}')
        assert "chartreuse" not in html
        assert "text-muted-foreground" in html

    def test_without_a_label_it_is_decorative(self, render):
        """Announcing the glyph as well as the "Saving…" text beside it says the
        same thing twice."""
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
        """htmx injects the rule for this class itself, so an indicator needs no
        CSS from fjkit and no JavaScript from anyone."""
        assert "htmx-indicator" in render(f"{FEEDBACK}{{{{ spinner(indicator=true) }}}}")
        assert "htmx-indicator" not in render(f"{FEEDBACK}{{{{ spinner() }}}}")

    def test_unknown_kwargs_become_html_attributes(self, render):
        html = render(f'{FEEDBACK}{{{{ spinner(id="busy", data_test="x") }}}}')
        assert 'id="busy"' in html
        assert 'data-test="x"' in html


DIALOG_BODY = '{% call dialog("d1", title="Task 7") %}Body{% endcall %}'


def outer_tag(html: str) -> str:
    """Return the dialog element's own attributes, without the close button's.
    Both carry a `data-size`, and only the dialog's is the component's
    contract."""
    return html.strip()[: html.strip().index(">") + 1]


class TestDialog:
    def test_it_is_a_popover_so_nothing_has_to_open_it(self, render):
        """The component rests on this attribute: with it the browser owns open
        state, the top layer, Escape and click-outside. Without it the macro
        would need JavaScript to be worth anything."""
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
        """A popover leaves the page behind it reachable. `aria-modal` would
        tell a screen reader the opposite of what is true."""
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
        """The published seam: a trigger fetches into `#<id>-body`, so the shell
        renders once and the contents only when it is opened."""
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

    A real request needs an app, a router and a scope to answer those two, none
    of which these tests are about. The macro's contract is that it takes a
    route name and asks the globals, which a stub proves as well as a running
    app does.
    """

    def __init__(self, active: str | None = None) -> None:
        self.scope = {"route": type("Route", (), {"name": active})()}

    def url_for(self, name: str, **path_params) -> FakeURL:
        return FakeURL("/" + name)


NAV = '{% call sidebar() %}<i>nav</i>{% endcall %}'


class TestSidebar:
    def test_it_emits_basecoats_structure_because_the_css_depends_on_it(self, render):
        """`aside.sidebar > nav > section` is not a style choice: every rule in
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
        """No rule matches `data-side="middle"`: the panel would lose its border
        and the page would lose the margin that keeps it clear."""
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
        """A second copy of the same sidebar — an htmx swap, say — would
        duplicate any id here, and a duplicate `aria-labelledby` resolves to the
        wrong heading rather than to nothing."""
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
        the anchor pushes the icon out of the panel instead."""
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
        and it goes stale the first time anyone clicks."""
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
        """Basecoat gives the margin to `.sidebar + *`. Anything rendered between
        the two takes the margin instead, and the page slides under the panel,
        silently, and only once someone opens it."""
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
    """Basecoat's script drives `.tabs` and finds everything through the aria
    wiring. These lock the four attributes it reads: get any of them wrong and
    the tabs silently stop switching, with no error anywhere."""

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
        """The server knows which tab the request was for, so this is a parameter
        rather than something a script decides after paint."""
        html = render(f'{TABS}{{% call tabs({FILE_ITEMS}, selected="b") %}}{{% endcall %}}')
        assert html.count('aria-selected="true"') == 1
        assert 'aria-controls="b"' in html.split('aria-selected="true"')[0]

    def test_orientation_is_a_closed_lookup(self, render):
        """The key handler reads `aria-orientation` to choose between Left/Right
        and Up/Down. Interpolating it would let a typo through and leave the
        arrow keys dead with no other symptom."""
        html = render(f'{TABS}{{% call tabs({FILE_ITEMS}, orientation="sideways") %}}{{% endcall %}}')
        assert 'aria-orientation="horizontal"' in html
        assert "sideways" not in html

    def test_panels_are_not_pre_hidden(self, render):
        """Basecoat hides the inactive panels on init. Rendering them hidden
        makes them invisible to a reader with scripting off."""
        html = render(
            f"{TABS}{{% call tabs({FILE_ITEMS}) %}}"
            '{% call tab_panel("b") %}second{% endcall %}{% endcall %}'
        )
        assert "hidden" not in html
        assert "second" in html


class TestLazyTabPanel:
    """`lazy` makes a panel fetch its own body when it is shown.

    Every assertion here is a way the hand-written version goes wrong without
    raising anything: the page is not lazy, or it fetches four times for one
    broadcast, or it loops. None of that shows up in a route test."""

    LAZY = '{% call tab_panel("p", lazy="/detail", on=["task-selected"], include="[name=task_id]") %}S{% endcall %}'

    def test_the_trigger_is_intersect_and_never_revealed(self, render):
        """`revealed` tests visibility with `getBoundingClientRect`, and a panel
        hidden by `display:none` reports an all-zero rect that passes the test.
        A `revealed` panel therefore fetches at page load: no error, no empty
        panel, just a page that is not lazy — which is the whole component."""
        html = render(f"{TABS}{self.LAZY}")
        assert "revealed" not in html
        assert 'hx-trigger="intersect' in html

    def test_a_broadcast_is_filtered_on_the_panel_being_visible(self, render):
        """The events are raised on `<body>`, so a hidden panel hears them as
        well as the open one. Without the filter, four tabs make four requests
        per broadcast and three are for markup nobody is looking at."""
        html = render(f"{TABS}{self.LAZY}")
        assert "task-selected[!this.hidden] from:body" in html

    def test_every_broadcast_carries_its_own_from_body(self, render):
        """A bare second name would be read as an event on this element."""
        html = render(
            f'{TABS}{{% call tab_panel("p", lazy="/x", on=["task-selected", "task-changed"]) %}}S{{% endcall %}}'
        )
        assert html.count("from:body") == 2
        assert "task-changed[!this.hidden] from:body" in html

    def test_the_panel_survives_its_own_reply(self, render):
        """An element carrying `intersect` that is replaced by markup carrying
        `intersect` is processed on screen, fires at once, and loops. The swap
        has to be `innerHTML` onto the panel itself."""
        html = render(f"{TABS}{self.LAZY}")
        assert 'hx-target="this"' in html
        assert 'hx-swap="innerHTML"' in html

    def test_include_is_what_the_panel_sends(self, render):
        """`intersect` carries no event, so the id cannot come from one. It is a
        selector because the page is the only thing both paths can read."""
        html = render(f"{TABS}{self.LAZY}")
        assert "hx-include=\"[name=task_id]\"" in html

    def test_a_panel_without_lazy_is_inert(self, render):
        """`on` and `include` are read only alongside `lazy`. A panel that
        fetched nothing but still subscribed would swap into itself."""
        html = render(
            f'{TABS}{{% call tab_panel("p", on=["task-selected"], include="[name=task_id]") %}}S{{% endcall %}}'
        )
        assert "hx-" not in html
        assert html.strip() == '<div id="p" role="tabpanel">S</div>'

    def test_pass_through_attributes_still_reach_the_panel(self, render):
        html = render(f'{TABS}{{% call tab_panel("p", lazy="/x", aria_label="Detail") %}}S{{% endcall %}}')
        assert 'aria-label="Detail"' in html
        assert 'hx-get="/x"' in html


class TestCodeBlock:
    def test_a_scroll_region_is_reachable_by_keyboard(self, render):
        """A scroll container nothing can focus cannot be scrolled without a
        mouse. That is why this is a macro rather than a bare `<pre>`."""
        html = render(f'{CODE}{{{{ code_block("x = 1") }}}}')
        assert 'tabindex="0"' in html

    def test_a_region_role_is_only_used_with_a_name(self, render):
        """An unlabelled region is a stop in the tab order that announces
        nothing, which is worse than no landmark at all."""
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
        """`.item > section` is the text column and `.item > aside` the actions.
        The CSS keys off those elements, so they are not interchangeable."""
        html = render(f"{CODE}{{% call item_list() %}}{{{{ item(\"router.py\", \"routes\") }}}}{{% endcall %}}")
        assert 'class="item-group"' in html
        assert 'class="item"' in html
        assert "<section>" in html and "<h4>" in html

    def test_href_switches_the_row_to_an_anchor(self, render):
        html = render(f'{CODE}{{{{ item("Docs", href="/docs") }}}}')
        assert '<a class="item"' in html and 'href="/docs"' in html

    def test_clamp_false_releases_the_two_line_limit(self, render):
        """Basecoat clamps a row's description to two lines, which suits a feed
        and not a definition list."""
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
        """Regression: every other component took pass-through attributes and
        this one did not, making it the only one you could not hang an id on."""
        for orientation in ("horizontal", "vertical"):
            html = render(
                f'{GROUP}{{% call button_group(orientation="{orientation}", id="filters") %}}x{{% endcall %}}'
            )
            assert 'id="filters"' in html


ALERT = '{% from "ui/feedback.html" import alert %}'
SKELETON = '{% from "ui/feedback.html" import skeleton %}'
BREADCRUMB = '{% from "ui/nav.html" import breadcrumb %}'
AVATAR = '{% from "ui/data.html" import avatar, avatar_group %}'
RANGE = '{% from "ui/form.html" import range_field %}'
DISCLOSURE = '{% from "ui/disclosure.html" import collapsible, accordion, tooltip %}'


class TestAlert:
    def test_renders_the_basecoat_structure(self, render):
        html = render(f'{ALERT}{{{{ alert("Saved", "Your changes are live.") }}}}')
        assert 'class="alert"' in html
        assert "<h2>Saved</h2>" in html
        assert "<section>Your changes are live.</section>" in html

    @pytest.mark.parametrize("variant", ["destructive", "success", "warning", "info"])
    def test_every_variant_renders(self, render, variant):
        html = render(f'{ALERT}{{{{ alert("Note", variant="{variant}") }}}}')
        assert f'data-variant="{variant}"' in html

    def test_destructive_interrupts_and_the_rest_do_not(self, render):
        """`alert` interrupts a screen reader; `status` waits for a pause. The
        variant already draws that distinction, so the role follows it."""
        assert 'role="alert"' in render(f'{ALERT}{{{{ alert("Failed", variant="destructive") }}}}')
        assert 'role="status"' in render(f'{ALERT}{{{{ alert("Saved", variant="success") }}}}')

    def test_the_variant_picks_an_icon_that_agrees_with_it(self, render):
        assert "circle-check" not in render(f'{ALERT}{{{{ alert("Failed", variant="destructive") }}}}')
        assert 'd="m9 12 2 2 4-4"' in render(f'{ALERT}{{{{ alert("Saved", variant="success") }}}}')

    def test_no_variant_means_no_icon(self, render):
        assert "<svg" not in render(f'{ALERT}{{{{ alert("Plain") }}}}')

    def test_actions_arrive_through_a_caller_block(self, render):
        html = render(f'{ALERT}{{% call alert("Update") %}}<button class="btn">Go</button>{{% endcall %}}')
        assert "<footer><button" in html.replace("\n", "")

    def test_passthrough_attributes_survive(self, render):
        assert 'hx-get="/status"' in render(f'{ALERT}{{{{ alert("Note", hx_get="/status") }}}}')


class TestSkeleton:
    @pytest.mark.parametrize(
        ("shape", "expected"),
        [("text", "h-4"), ("heading", "h-6"), ("control", "h-9"), ("avatar", "size-10"), ("block", "aspect-video")],
    )
    def test_every_shape_renders(self, render, shape, expected):
        assert expected in render(f'{SKELETON}{{{{ skeleton(shape="{shape}") }}}}')

    @pytest.mark.parametrize(
        ("width", "expected"),
        [("full", "w-full"), ("three-quarters", "w-3/4"), ("half", "w-1/2"), ("third", "w-1/3"), ("quarter", "w-1/4")],
    )
    def test_every_width_renders(self, render, width, expected):
        assert expected in render(f'{SKELETON}{{{{ skeleton(width="{width}") }}}}')

    def test_an_unknown_shape_falls_back_rather_than_emitting_a_dead_class(self, render):
        html = render(f'{SKELETON}{{{{ skeleton(shape="octagon") }}}}')
        assert "octagon" not in html
        assert "h-4" in html

    def test_the_last_line_of_a_paragraph_is_short(self, render):
        html = render(f'{SKELETON}{{{{ skeleton(lines=3) }}}}')
        assert html.count("skeleton") == 3
        assert html.count("w-3/4") == 1

    def test_one_live_region_for_the_whole_group(self, render):
        html = render(f'{SKELETON}{{{{ skeleton(lines=4) }}}}')
        assert html.count('role="status"') == 1
        assert html.count('aria-hidden="true"') == 4


class TestBreadcrumb:
    def test_the_last_crumb_is_not_a_link(self, render):
        html = render(f'{BREADCRUMB}{{{{ breadcrumb([("Home", "/"), ("Tasks", none)]) }}}}')
        assert '<a href="/">Home</a>' in html
        assert '<span aria-current="page">Tasks</span>' in html
        assert html.count("<a ") == 1

    def test_exactly_one_current_page(self, render):
        html = render(f'{BREADCRUMB}{{{{ breadcrumb([("A", "/a"), ("B", "/b"), ("C", none)]) }}}}')
        assert html.count('aria-current="page"') == 1

    def test_separators_are_hidden_and_sit_between_crumbs(self, render):
        html = render(f'{BREADCRUMB}{{{{ breadcrumb([("A", "/a"), ("B", "/b"), ("C", none)]) }}}}')
        assert html.count('<li aria-hidden="true">') == 2

    @pytest.mark.parametrize("separator", ["chevron", "slash", "dot"])
    def test_every_separator_renders(self, render, separator):
        html = render(f'{BREADCRUMB}{{{{ breadcrumb([("A", "/a"), ("B", none)], separator="{separator}") }}}}')
        assert "<svg" in html

    def test_only_the_chevron_is_mirrored_for_rtl(self, render):
        """A dot has no direction to flip."""
        assert "rtl:rotate-180" in render(f'{BREADCRUMB}{{{{ breadcrumb([("A", "/a"), ("B", none)]) }}}}')
        assert "rtl:rotate-180" not in render(
            f'{BREADCRUMB}{{{{ breadcrumb([("A", "/a"), ("B", none)], separator="dot") }}}}'
        )

    def test_the_nav_is_labelled(self, render):
        assert 'aria-label="Breadcrumb"' in render(f'{BREADCRUMB}{{{{ breadcrumb([("A", none)]) }}}}')


class TestAvatar:
    def test_initials_come_from_the_name(self, render):
        assert ">AL<" in render(f'{AVATAR}{{{{ avatar("Ada Lovelace") }}}}')

    def test_a_one_word_name_gives_one_letter(self, render):
        assert ">A<" in render(f'{AVATAR}{{{{ avatar("Ada") }}}}')

    def test_initials_stop_at_two_letters(self, render):
        html = render(f'{AVATAR}{{{{ avatar("Ada King Noel Byron") }}}}')
        assert ">AK<" in html

    def test_the_name_is_also_the_alt_text(self, render):
        """One parameter, so the accessible name and the initials cannot
        disagree."""
        assert 'alt="Ada Lovelace"' in render(f'{AVATAR}{{{{ avatar("Ada Lovelace", src="/a.png") }}}}')

    def test_initials_leave_the_tree_when_an_image_carries_the_name(self, render):
        html = render(f'{AVATAR}{{{{ avatar("Ada Lovelace", src="/a.png") }}}}')
        assert 'aria-hidden="true">AL<' in html

    def test_initials_stay_in_the_tree_when_there_is_no_image(self, render):
        assert 'aria-hidden="true">AL<' not in render(f'{AVATAR}{{{{ avatar("Ada Lovelace") }}}}')

    @pytest.mark.parametrize("size", ["sm", "lg"])
    def test_every_size_renders(self, render, size):
        assert f'data-size="{size}"' in render(f'{AVATAR}{{{{ avatar("Ada", size="{size}") }}}}')

    @pytest.mark.parametrize(
        ("tone", "expected"),
        [
            ("success", "bg-success"),
            ("warning", "bg-warning"),
            ("info", "bg-info"),
            ("destructive", "bg-destructive"),
            ("muted", "bg-muted-foreground"),
        ],
    )
    def test_the_badge_names_a_role_not_a_hue(self, render, tone, expected):
        html = render(f'{AVATAR}{{{{ avatar("Ada", badge_tone="{tone}") }}}}')
        assert f'class="avatar-badge {expected}"' in html

    def test_the_group_counts_its_overflow(self, render):
        html = render(f'{AVATAR}{{% call avatar_group(overflow=3) %}}{{{{ avatar("Ada") }}}}{{% endcall %}}')
        assert 'class="avatar-group"' in html
        assert "<span data-count>+3</span>" in html


class TestRangeField:
    def test_renders_a_native_range_input(self, render):
        html = render(f'{RANGE}{{{{ range_field("volume", "Volume") }}}}')
        assert 'type="range"' in html and 'class="input"' in html

    def test_the_fill_matches_the_value_on_first_paint(self, render):
        """Basecoat paints the track from `--slider-value` and only updates it
        from JS on drag. Without this the bar starts at upstream's 20%."""
        assert "--slider-value: 25.0%" in render(f'{RANGE}{{{{ range_field("v", value=25) }}}}')

    def test_the_fill_accounts_for_a_non_zero_minimum(self, render):
        assert "--slider-value: 50.0%" in render(f'{RANGE}{{{{ range_field("v", value=10, min=5, max=15) }}}}')

    def test_a_zero_width_range_does_not_divide_by_zero(self, render):
        render(f'{RANGE}{{{{ range_field("v", value=5, min=5, max=5) }}}}')

    def test_the_output_is_off_by_default(self, render):
        assert "<output" not in render(f'{RANGE}{{{{ range_field("v", "V") }}}}')
        assert "<output" in render(f'{RANGE}{{{{ range_field("v", "V", output=true) }}}}')

    def test_the_output_tracks_the_thumb(self, render):
        """Basecoat's range handler moves `--slider-value` and nothing else, and
        no browser populates an `<output>` on its own.

        Without this the number is right on first paint and then frozen — a
        slider reading 50 with its thumb at the far end, which is worse than
        printing no number at all.
        """
        html = render(f'{RANGE}{{{{ range_field("v", "V", output=true) }}}}')
        assert "oninput=" in html
        # The element, never the id: nothing from the template reaches a script.
        assert "f-v" not in html.split("oninput=")[1].split(">")[0]

    def test_no_handler_without_an_output_to_move(self, render):
        """The per-page JS budget is the point: a slider that prints no number
        emits no script. `output` with no label prints nothing either, because
        the element lives inside the label — so it must not emit one and then
        fail on a null."""
        assert "oninput=" not in render(f'{RANGE}{{{{ range_field("v", "V") }}}}')
        assert "oninput=" not in render(f'{RANGE}{{{{ range_field("v", output=true) }}}}')

    def test_an_error_marks_the_control_invalid(self, render):
        assert 'aria-invalid="true"' in render(f'{RANGE}{{{{ range_field("v", error="Too loud") }}}}')


class TestDisclosure:
    def test_collapsible_is_a_native_details(self, render):
        html = render(f'{DISCLOSURE}{{% call collapsible("More") %}}body{{% endcall %}}')
        assert "<summary" in html
        assert re.search(r"<details[^>]*>", html) and not re.search(r"<details[^>]*\sopen[\s>]", html)

    def test_open_starts_expanded(self, render):
        html = render(f'{DISCLOSURE}{{% call collapsible("More", open=true) %}}body{{% endcall %}}')
        assert re.search(r"<details[^>]*\sopen[\s>]", html)

    def test_the_marker_is_hidden_from_the_tree(self, render):
        """The summary already announces its own expanded state."""
        html = render(f'{DISCLOSURE}{{% call collapsible("More") %}}body{{% endcall %}}')
        assert 'aria-hidden="true"' in html

    def test_an_accordion_carries_the_class_basecoat_initialises(self, render):
        html = render(f'{DISCLOSURE}{{% call accordion() %}}x{{% endcall %}}')
        assert 'class="accordion"' in html

    def test_multiple_withholds_the_class_rather_than_adding_one(self, render):
        """Allowing several open panels means shipping no JS behaviour, rather
        than shipping JS that is asked to do nothing."""
        html = render(f'{DISCLOSURE}{{% call accordion(multiple=true) %}}x{{% endcall %}}')
        assert "accordion" not in html

    @pytest.mark.parametrize("side", ["top", "bottom", "left", "right"])
    def test_every_tooltip_side_renders(self, render, side):
        html = render(f'{DISCLOSURE}{{% call tooltip("Hint", side="{side}") %}}x{{% endcall %}}')
        assert f'data-side="{side}"' in html

    @pytest.mark.parametrize("align", ["start", "center", "end"])
    def test_every_tooltip_align_renders(self, render, align):
        html = render(f'{DISCLOSURE}{{% call tooltip("Hint", align="{align}") %}}x{{% endcall %}}')
        assert f'data-align="{align}"' in html

    def test_the_tooltip_wraps_its_trigger(self, render):
        html = render(f'{DISCLOSURE}{{% call tooltip("Save") %}}<button>S</button>{{% endcall %}}')
        assert 'data-tooltip="Save"' in html and "<button>S</button>" in html


OVERLAY = (
    '{% from "ui/overlay.html" import popover, dropdown_menu, menu_item, menu_group,'
    ' menu_separator, select_menu, combobox, drawer, drawer_trigger, command,'
    ' command_group, command_item, multiselect_scripts %}'
)
INPUT_GROUP = '{% from "ui/form.html" import input_group_field, reveal_scripts %}'


class TestOverlayIdWiring:
    """One id in, four out. A mismatch fails silently: the panel opens but is
    never announced, or never opens at all."""

    def test_popover_wires_trigger_to_panel(self, render):
        html = render(f'{OVERLAY}{{% call popover("p1", "Open") %}}body{{% endcall %}}')
        assert 'id="p1-trigger"' in html
        assert 'aria-controls="p1-popover"' in html
        assert 'id="p1-popover"' in html

    def test_dropdown_wires_trigger_to_menu_and_back(self, render):
        html = render(f'{OVERLAY}{{% call dropdown_menu("m1", "Open") %}}x{{% endcall %}}')
        assert 'aria-controls="m1-menu"' in html
        assert 'id="m1-menu"' in html
        assert 'aria-labelledby="m1-trigger"' in html

    def test_select_menu_wires_listbox(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("t", [("a", "A")]) }}}}')
        assert 'aria-controls="s-t-listbox"' in html and 'id="s-t-listbox"' in html

    def test_combobox_wires_listbox(self, render):
        html = render(f'{OVERLAY}{{{{ combobox("f", [("a", "A")]) }}}}')
        assert 'aria-controls="c-f-listbox"' in html and 'id="c-f-listbox"' in html

    def test_command_wires_input_to_menu(self, render):
        html = render(f'{OVERLAY}{{% call command("k") %}}x{{% endcall %}}')
        assert 'aria-controls="k-menu"' in html and 'id="k-menu"' in html


class TestOverlayStartingState:
    """First paint is the state before Basecoat's JS has run. A trigger with no
    `aria-expanded` is announced as a plain button."""

    def test_a_closed_popover_says_so_on_both_ends(self, render):
        html = render(f'{OVERLAY}{{% call popover("p", "Open") %}}b{{% endcall %}}')
        assert 'aria-expanded="false"' in html and 'aria-hidden="true"' in html

    def test_the_dropdown_trigger_declares_it_owns_a_menu(self, render):
        html = render(f'{OVERLAY}{{% call dropdown_menu("m", "Open") %}}x{{% endcall %}}')
        assert 'aria-haspopup="menu"' in html

    def test_the_select_trigger_declares_it_owns_a_listbox(self, render):
        assert 'aria-haspopup="listbox"' in render(f'{OVERLAY}{{{{ select_menu("t", [("a", "A")]) }}}}')


class TestMenuItem:
    def test_a_plain_item_is_a_menuitem(self, render):
        assert 'role="menuitem"' in render(f'{OVERLAY}{{{{ menu_item("Profile") }}}}')

    def test_a_checked_item_changes_role(self, render):
        """Reporting a checked state under `role="menuitem"` is a contradiction
        a screen reader cannot resolve."""
        html = render(f'{OVERLAY}{{{{ menu_item("Wrap", checked=true) }}}}')
        assert 'role="menuitemcheckbox"' in html and 'aria-checked="true"' in html

    def test_unchecked_still_reports_the_state(self, render):
        html = render(f'{OVERLAY}{{{{ menu_item("Wrap", checked=false) }}}}')
        assert 'role="menuitemcheckbox"' in html and 'aria-checked="false"' in html

    def test_a_radio_item_changes_role(self, render):
        html = render(f'{OVERLAY}{{{{ menu_item("Ascending", radio=true, checked=true) }}}}')
        assert 'role="menuitemradio"' in html

    def test_href_switches_the_element_to_an_anchor(self, render):
        html = render(f'{OVERLAY}{{{{ menu_item("Docs", href="/docs") }}}}')
        assert "<a " in html and 'href="/docs"' in html

    def test_a_shortcut_renders_a_kbd(self, render):
        assert "<kbd>⌘S</kbd>" in render(f'{OVERLAY}{{{{ menu_item("Save", shortcut="⌘S") }}}}')

    def test_disabled_is_announced_not_removed(self, render):
        assert 'aria-disabled="true"' in render(f'{OVERLAY}{{{{ menu_item("API", disabled=true) }}}}')

    def test_a_group_heading_labels_the_group(self, render):
        html = render(f'{OVERLAY}{{% call menu_group("My Account") %}}x{{% endcall %}}')
        assert 'aria-labelledby="h-my-account"' in html
        assert 'role="heading" id="h-my-account"' in html

    def test_a_separator_is_announced_as_one(self, render):
        assert '<hr role="separator">' in render(f'{OVERLAY}{{{{ menu_separator() }}}}')


class TestSelectMenuAndCombobox:
    def test_the_value_travels_in_a_hidden_input(self, render):
        """The visible trigger is a button, which submits nothing."""
        html = render(f'{OVERLAY}{{{{ select_menu("theme", [("d", "Dark")], selected="d") }}}}')
        assert '<input type="hidden" name="theme" value="d">' in html

    def test_the_hidden_input_is_prefilled_so_a_round_trip_keeps_the_choice(self, render):
        html = render(f'{OVERLAY}{{{{ combobox("fw", [("next", "Next.js")], selected="next") }}}}')
        assert 'name="fw" value="next"' in html

    def test_nothing_selected_is_not_an_error(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("t", [("a", "A")]) }}}}')
        assert 'value=""' in html
        assert "Select…" in html

    def test_the_trigger_shows_the_selected_label(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("t", [("a", "Apple"), ("b", "Pear")], selected="b") }}}}')
        assert ">Pear<" in html

    def test_the_selected_option_is_marked(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("t", [("a", "A"), ("b", "B")], selected="b") }}}}')
        assert html.count('aria-selected="true"') == 1

    def test_the_combobox_turns_off_browser_autofill(self, render):
        """The browser's own suggestions would cover the listbox."""
        html = render(f'{OVERLAY}{{{{ combobox("f", [("a", "A")]) }}}}')
        assert 'autocomplete="off"' in html and 'spellcheck="false"' in html

    def test_the_empty_message_is_never_blank(self, render):
        html = render(f'{OVERLAY}{{{{ combobox("f", [("a", "A")]) }}}}')
        assert 'data-empty="No results found."' in html


class TestScriptedControlsAsFields:
    """`combobox` and `select_menu` render a bare control until one of
    `visible_label`, `hint` or `error` is passed, and then render the same field
    every macro in `ui/form.html` renders.

    Both halves matter. Every existing call site gets the bare form, which must
    not move; the field form lets one of these sit in a form beside a
    `text_field` without the app hand-copying the wrapper.
    """

    OPTIONS = '[("1", "I"), ("2", "II")]'

    def test_a_bare_control_has_no_field_wrapper(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, label="Phase") }}}}')
        assert 'class="field"' not in html
        assert "<label" not in html
        assert 'aria-label="Phase"' in html

    def test_a_visible_label_points_at_the_trigger(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, visible_label="Phase") }}}}')
        assert 'class="field"' in html
        assert '<label class="label" for="s-phase-trigger">Phase</label>' in html

    def test_a_visible_label_replaces_the_aria_label(self, render):
        """With both, a screen reader reads the attribute instead of the text on
        the page: two names for one control, and the wrong one wins."""
        html = render(
            f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, label="Aria", visible_label="Phase") }}}}'
        )
        assert 'aria-label="' not in html
        assert ">Phase</label>" in html

    def test_a_combobox_label_points_at_its_input(self, render):
        html = render(f'{OVERLAY}{{{{ combobox("c", {self.OPTIONS}, visible_label="Continents") }}}}')
        assert '<label class="label" for="c-c-input">Continents</label>' in html
        assert 'id="c-c-input"' in html

    def test_a_hint_alone_is_enough_to_make_it_a_field(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, hint="Post-filter") }}}}')
        assert 'class="field"' in html
        assert '<p class="text-muted-foreground text-xs" id="s-phase-hint">Post-filter</p>' in html

    def test_the_trigger_names_the_message(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, hint="h") }}}}')
        trigger = html.split("</button>")[0]
        assert 'aria-describedby="s-phase-hint"' in trigger

    def test_the_hidden_input_names_the_message_too(self, render):
        """Not for a screen reader, which is never shown a hidden input. It is
        for `js/errors.js`, which finds the control a 422 names by `[name]`, and
        this is that input."""
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, hint="h") }}}}')
        assert 'name="phase" value="" aria-describedby="s-phase-hint"' in html

    def test_a_multiple_hidden_input_names_it_as_well(self, render):
        html = render(
            f'{OVERLAY}{{{{ combobox("c", {self.OPTIONS}, multiple=true, visible_label="C") }}}}'
        )
        assert "data-fjkit-multi" in html
        assert 'aria-describedby="c-c-hint"' in html

    def test_an_error_replaces_the_hint_and_marks_the_trigger(self, render):
        html = render(
            f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, hint="h", error="Pick one") }}}}'
        )
        assert '<p class="text-destructive text-xs" id="s-phase-hint">Pick one</p>' in html
        assert ">h</p>" not in html
        assert 'aria-invalid="true"' in html

    def test_a_field_with_nothing_to_say_still_reserves_the_paragraph(self, render):
        """`js/errors.js` creates its own `<p>` after the control when it finds
        none, and for these two the control is a hidden input at the end of the
        wrapper, so the 422 would draw inside the select box. The reserved
        paragraph gives it somewhere correct to land."""
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, visible_label="Phase") }}}}')
        assert '<p class="text-muted-foreground text-xs" id="s-phase-hint" hidden></p>' in html

    def test_the_message_sits_outside_the_control(self, render):
        html = render(f'{OVERLAY}{{{{ select_menu("phase", {self.OPTIONS}, hint="h") }}}}')
        assert html.index("</div>") < html.index('id="s-phase-hint"')


class TestMultipleSelection:
    """`multiple=true` is one attribute to Basecoat and a different wire format
    to the route. Both halves are asserted here, because either alone gives a
    control that looks right and posts something a signature cannot read."""

    OPTIONS = '[("bug", "Bug"), ("ui", "UI"), ("docs", "Docs")]'

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_the_listbox_is_what_basecoat_reads(self, render, macro):
        """The attribute goes on the listbox, not the root. Basecoat reads
        `listbox.getAttribute("aria-multiselectable")` and nothing else, so the
        same word on the wrapper gives a multi-select that silently is not
        one."""
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, multiple=true) }}}}')
        listbox = html[html.index('role="listbox"') :]
        assert 'aria-multiselectable="true"' in listbox[: listbox.index("</div>")]

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_single_selection_says_nothing_about_multiselectable(self, render, macro):
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}) }}}}')
        assert "aria-multiselectable" not in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_the_hidden_input_carries_a_json_array(self, render, macro):
        """Basecoat's own format, so the control and the first paint agree before
        any JS has run."""
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, selected=["bug", "ui"], multiple=true) }}}}')
        assert 'name="l" data-fjkit-multi value=\'["bug", "ui"]\'' in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_the_json_array_is_single_quoted(self, render, macro):
        """`tojson` escapes `<`, `>`, `&` and `'`, never `"`. Inside a
        double-quoted attribute the value is cut off at the first element, which
        is a one-item selection no test of the parsed result would catch."""
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, selected=["bug"], multiple=true) }}}}')
        assert "value='[" in html and 'value="[' not in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_nothing_selected_is_an_empty_array_not_an_empty_string(self, render, macro):
        """`""` parses to nothing useful. `[]` is the value Basecoat writes."""
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, multiple=true) }}}}')
        assert "value='[]'" in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_every_selected_option_is_marked(self, render, macro):
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, selected=["bug", "docs"], multiple=true) }}}}')
        assert html.count('aria-selected="true"') == 2

    def test_the_select_trigger_joins_the_labels(self, render):
        """What Basecoat's JS writes the moment it runs. Anything else here is a
        visible change at first paint."""
        html = render(f'{OVERLAY}{{{{ select_menu("l", {self.OPTIONS}, selected=["bug", "docs"], multiple=true) }}}}')
        assert ">Bug, Docs<" in html

    def test_the_combobox_filter_box_starts_empty(self, render):
        """It is the filter, not the display. A pre-filled one narrows the list
        to the label it was filled with before anybody types."""
        html = render(f'{OVERLAY}{{{{ combobox("l", {self.OPTIONS}, selected=["bug"], multiple=true) }}}}')
        text_input = html[html.index('role="combobox"') : html.index(">", html.index('role="combobox"'))]
        assert 'value=""' in text_input
        # The selection is still on the wire, in the input that carries it.
        assert 'data-fjkit-multi value=\'["bug"]\'' in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_the_panel_stays_open_by_default(self, render, macro):
        """Absent means "stay open" to Basecoat, which is the right default for
        a control whose point is picking more than one."""
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, multiple=true) }}}}')
        assert "data-close-on-select" not in html

    @pytest.mark.parametrize("macro", ["select_menu", "combobox"])
    def test_close_on_select_is_opt_in(self, render, macro):
        html = render(f'{OVERLAY}{{{{ {macro}("l", {self.OPTIONS}, multiple=true, close_on_select=true) }}}}')
        assert 'data-close-on-select="true"' in html

    def test_the_script_is_deferred_after_htmx(self, render):
        """Deferred scripts run in document order and htmx is deferred in the
        shell's head. An ordinary `<script>` would run first and register a
        listener for an event htmx has not defined yet."""
        html = render(f"{OVERLAY}{{{{ multiselect_scripts() }}}}")
        assert "<script defer" in html and "js/multiselect.js" in html


class TestDrawer:
    def test_a_drawer_is_a_native_dialog(self, render):
        html = render(f'{OVERLAY}{{% call drawer("d", "Goal") %}}b{{% endcall %}}')
        assert "<dialog" in html and 'class="drawer"' in html
        assert "<article>" in html

    @pytest.mark.parametrize("side", ["top", "right", "bottom", "left"])
    def test_every_side_renders(self, render, side):
        html = render(f'{OVERLAY}{{% call drawer("d", side="{side}") %}}b{{% endcall %}}')
        assert f'data-side="{side}"' in html

    def test_the_title_labels_the_dialog(self, render):
        html = render(f'{OVERLAY}{{% call drawer("d", "Move Goal") %}}b{{% endcall %}}')
        assert 'aria-labelledby="d-title"' in html and 'id="d-title"' in html

    def test_the_trigger_opens_it_modally(self, render):
        html = render(f'{OVERLAY}{{{{ drawer_trigger("Open", "d") }}}}')
        assert "showModal()" in html
        assert 'aria-haspopup="dialog"' in html and 'aria-controls="d"' in html

    def test_the_close_button_finds_its_dialog_structurally(self, render):
        """`closest('dialog')`, not the id, so a rename cannot break it."""
        html = render(f'{OVERLAY}{{% call drawer("d") %}}b{{% endcall %}}')
        assert "this.closest('dialog').close()" in html


class TestCommand:
    def test_the_dialog_flag_swaps_the_root_not_the_contents(self, render):
        standalone = render(f'{OVERLAY}{{% call command("k") %}}x{{% endcall %}}')
        modal = render(f'{OVERLAY}{{% call command("k", dialog=true) %}}x{{% endcall %}}')
        assert 'class="command border"' in standalone and "<dialog" not in standalone
        assert 'class="command-dialog"' in modal and "<dialog" in modal
        for html in (standalone, modal):
            assert 'id="k-input"' in html and 'id="k-menu"' in html

    def test_the_filter_defaults_to_the_label(self, render):
        assert 'data-filter="Calendar"' in render(f'{OVERLAY}{{{{ command_item("Calendar") }}}}')

    def test_keywords_extend_the_filter_beyond_what_is_on_screen(self, render):
        html = render(f'{OVERLAY}{{{{ command_item("Calendar", keywords="date event") }}}}')
        assert 'data-keywords="date event"' in html

    def test_the_listbox_is_permanently_expanded(self, render):
        """The dialog opens and closes, not the listbox."""
        assert 'aria-expanded="true"' in render(f'{OVERLAY}{{% call command("k") %}}x{{% endcall %}}')

    def test_a_command_group_heading_is_a_span(self, render):
        """Upstream's command markup uses a span, and its CSS selects on it."""
        html = render(f'{OVERLAY}{{% call command_group("Suggestions") %}}x{{% endcall %}}')
        assert '<span role="heading"' in html


class TestInputGroup:
    def test_addons_are_optional_and_leave_nothing_behind(self, render):
        """An empty addon still takes its padding, which is why these are slots
        rather than a caller block."""
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("q") }}}}')
        assert "data-align" not in html

    def test_both_ends_render_when_given(self, render):
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("q", start="$", end="USD") }}}}')
        assert 'data-align="start"' in html and 'data-align="end"' in html

    def test_the_inner_input_has_no_input_class(self, render):
        """Basecoat paints the border on the group. A second one draws a box
        inside the box."""
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("q") }}}}')
        assert 'class="input-group"' in html
        assert 'class="input"' not in html

    def test_the_input_stays_first_so_the_label_reads_naturally(self, render):
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("q", "Search", start="@") }}}}')
        assert html.index("<input") < html.index("data-align")

    def test_an_error_marks_the_control_invalid(self, render):
        assert 'aria-invalid="true"' in render(f'{INPUT_GROUP}{{{{ input_group_field("q", error="Required") }}}}')


class TestReveal:
    CALL = '{{ input_group_field("password", type="password", revealable=true) }}'

    def test_no_button_unless_asked_for(self, render):
        assert "data-fjkit-reveal" not in render(f'{INPUT_GROUP}{{{{ input_group_field("password") }}}}')

    def test_the_button_is_a_toggle_not_a_command(self, render):
        """`aria-pressed` is what tells a screen reader the field's state. A
        button without it announces the same thing in both states."""
        html = render(f"{INPUT_GROUP}{self.CALL}")
        assert 'aria-pressed="false"' in html
        assert "data-fjkit-reveal" in html

    def test_the_button_never_submits_the_form_it_sits_in(self, render):
        html = render(f"{INPUT_GROUP}{self.CALL}")
        assert 'type="button"' in html

    def test_the_button_names_the_input_it_controls(self, render):
        """`js/reveal.js` reads `aria-controls`, so this attribute is the wiring
        and not only an accessibility affordance."""
        html = render(f"{INPUT_GROUP}{self.CALL}")
        assert 'id="f-password"' in html
        assert 'aria-controls="f-password"' in html

    def test_a_custom_id_is_the_one_the_button_points_at(self, render):
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("password", id="pw", revealable=true) }}}}')
        assert 'aria-controls="pw"' in html
        assert 'aria-controls="f-password"' not in html

    def test_both_labels_travel_with_the_button(self, render):
        """The script reads both labels off the element, so it holds no
        English."""
        html = render(
            f'{INPUT_GROUP}{{{{ input_group_field("password", revealable=true,'
            ' reveal_show="Mostrar", reveal_hide="Ocultar") }}'
        )
        assert 'data-show="Mostrar"' in html and 'data-hide="Ocultar"' in html
        assert ">Mostrar<" in html.replace("\n", "").replace(" ", "")

    def test_a_caller_addon_and_the_reveal_share_one_end_group(self, render):
        html = render(f'{INPUT_GROUP}{{{{ input_group_field("password", end="USD", revealable=true) }}}}')
        assert html.count('data-align="end"') == 1
        assert html.index("USD") < html.index("data-fjkit-reveal"), "the reveal sits by the field's edge"

    def test_the_script_is_opt_in_per_page(self, render):
        """CHARTER §7: a page downloads htmx and Basecoat by default and nothing
        else. This macro is how a page says otherwise."""
        assert "js/reveal.js" not in render(f"{INPUT_GROUP}{self.CALL}")
        assert "js/reveal.js" in render(f"{INPUT_GROUP}{{{{ reveal_scripts() }}}}")
