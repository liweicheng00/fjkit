"""Tests for the Records page — 0.4's acceptance test.

Four capabilities on one table, each only half done in the markup. The other
half is the URL: people bookmark an order, a page and a size, so all three have
to survive a plain GET with no htmx involved.

Every assertion is on what the server sends, so the file is organised by what
the server decides — what it sorted by, where it cut the page, how it numbered
the rows, and what the selection reached.

No test here runs a browser, so none of them sees the header checkbox tick its
column; that is `js/select.js`. They cover the half the server owns: that the
markup the script keys off is present and correctly named.
"""

from __future__ import annotations

import json
import re

import pytest
from app.features.records.router import PER_PAGE
from app.features.records.schemas import (
    DEFAULT_SORT,
    PAGE_SIZES,
    SORT_LABELS,
    columns,
    page_url,
    parse_page_size,
    parse_sort,
)
from app.features.records.service import RecordService

#: The row order the page opens on.
FIRST_PAGE = "/records"


def names(html: str) -> list[str]:
    """The dataset names on a page, in the order the table lists them.

    Read out of the row checkboxes' labels, because that is the one place the
    row's identity and its position are both written down.
    """
    return re.findall(r'data-fjkit-select="selected"[^>]*aria-label="Select ([^"]+)"', html)


def picked_page(html: str) -> str:
    """The page number the strip marks as current."""
    return re.search(r'aria-current="page"[^>]*>(\d+)<', html).group(1)


# --------------------------------------------------------------------------- #
# sorting
# --------------------------------------------------------------------------- #


class TestSorting:
    def test_every_sortable_column_has_a_header_link(self, client):
        html = client.get(FIRST_PAGE).text
        for key in SORT_LABELS:
            assert f"o={key}&amp;per_page=" in html or f"o=-{key}&amp;per_page=" in html

    def test_the_open_order_is_the_one_announced(self, client):
        """`aria-sort` is what a screen reader reads out of the header, and it
        has to describe the rows actually below it."""
        html = client.get(FIRST_PAGE).text
        assert html.count('aria-sort="descending"') == 1
        assert html.count('aria-sort="ascending"') == 0
        assert 'aria-sort="none"' in html

    def test_clicking_the_sorted_column_reverses_it(self, client):
        """And clicking any other one sorts by it ascending. That rule is why
        the column spec is built per request instead of being a constant."""
        html = client.get("/records?o=name").text
        assert f'href="/records?o=-name&amp;per_page={PER_PAGE}"' in html
        assert f'href="/records?o=owner&amp;per_page={PER_PAGE}"' in html

    def test_a_header_link_drops_the_page_number(self, client):
        """Re-ranking every row leaves the page number describing nothing."""
        href = re.search(r'href="(/records\?o=-name[^"]*)"', client.get("/records?o=name&page=5").text).group(1)
        assert "page=" not in href.replace("per_page=", "")

    def test_sorting_reorders_the_rows_and_not_only_the_header(self, htmx):
        """The assertion the header attributes cannot make: a table that says
        ascending over unsorted rows passes every other test in this file."""
        assert names(htmx.get("/records?o=name").text) == sorted(names(htmx.get("/records?o=name").text))
        ascending = names(htmx.get("/records?o=owner").text)
        descending = names(htmx.get("/records?o=-owner").text)
        assert ascending != descending

    def test_an_unknown_sort_key_falls_back_instead_of_refusing(self, client):
        """`o=` is part of a URL people keep. A 422 for a stale one loses the
        whole page over a detail nobody chose."""
        response = client.get("/records?o=dropped_column")
        assert response.status_code == 200
        assert names(response.text) == names(client.get(FIRST_PAGE).text)

    def test_the_headers_swap_rather_than_reload(self, client):
        html = client.get(FIRST_PAGE).text
        assert 'hx-target="#records"' in html
        assert 'hx-push-url="true"' in html

    def test_a_header_is_a_link_before_it_is_a_swap(self, client):
        """With JavaScript off, sorting still works: every `hx-get` has an
        `href` beside it carrying the same URL."""
        for anchor in re.findall(r"<a [^>]*hx-get=[^>]*>", client.get(FIRST_PAGE).text):
            assert re.search(r'href="([^"]+)"', anchor).group(1) == re.search(r'hx-get="([^"]+)"', anchor).group(1)


# --------------------------------------------------------------------------- #
# pagination
# --------------------------------------------------------------------------- #


class TestPaging:
    def test_the_first_page_holds_one_page_of_rows(self, htmx):
        assert len(names(htmx.get(FIRST_PAGE).text)) == PER_PAGE

    def test_the_strip_counts_the_whole_table(self, htmx):
        html = htmx.get(FIRST_PAGE).text
        assert f"1–{PER_PAGE} of 137" in html

    def test_a_later_page_holds_different_rows(self, htmx):
        """Paging that renders the same rows under a different number is the
        failure this catches, and it looks correct in a screenshot."""
        first = names(htmx.get(FIRST_PAGE).text)
        third = names(htmx.get("/records?page=3").text)
        assert not set(first) & set(third)
        assert picked_page(htmx.get("/records?page=3").text) == "3"

    def test_the_last_page_holds_the_remainder(self, htmx):
        html = htmx.get("/records?page=12").text
        assert len(names(html)) == 137 - 11 * PER_PAGE
        assert "133–137 of 137" in html

    def test_no_row_is_lost_or_repeated_across_the_pages(self, htmx):
        """The tie-break in the sort key is what this is really testing: two
        rows that compare equal must not swap places between two requests, or
        paging drops one and shows another twice."""
        seen = [name for page in range(1, 13) for name in names(htmx.get(f"/records?o=owner&page={page}").text)]
        assert len(seen) == 137
        assert len(set(seen)) == 137

    def test_a_page_number_past_the_end_lands_on_the_last_page(self, htmx):
        """A stale bookmark, not an error worth a 404 — and a page that answers
        it with an empty table explains nothing."""
        assert picked_page(htmx.get("/records?page=900").text) == "12"
        assert picked_page(htmx.get("/records?page=0").text) == "1"

    def test_the_page_links_keep_the_order(self, client):
        """Otherwise page 2 of a sorted list is page 2 of a different list."""
        html = client.get("/records?o=-rows").text
        assert f'href="/records?o=-rows&amp;per_page={PER_PAGE}&amp;page=2"' in html

    def test_a_page_link_is_a_link_before_it_is_a_swap(self, client):
        strip = client.get(FIRST_PAGE).text.split('aria-label="Pagination"')[1]
        for anchor in re.findall(r"<a [^>]*hx-get=[^>]*>", strip):
            assert re.search(r'href="([^"]+)"', anchor).group(1) == re.search(r'hx-get="([^"]+)"', anchor).group(1)


class TestPageSizeControl:
    """The page-size control.

    Most of these cover one failure: a view setting carried by only some of the
    links is lost as soon as somebody uses the others.
    """

    def test_the_control_offers_the_whitelisted_sizes(self, htmx):
        html = htmx.get(FIRST_PAGE).text
        for size in PAGE_SIZES:
            assert f'<option value="{size}"' in html

    def test_it_shows_the_size_the_server_used_not_the_one_asked_for(self, htmx):
        """The control reports the size in use, so it shows what the router
        clamped to rather than what the query string asked for."""
        html = htmx.get("/records?per_page=500").text
        assert f'<option value="{PER_PAGE}" selected>' in html
        assert len(names(html)) == PER_PAGE

    def test_choosing_a_size_changes_how_many_rows_come_back(self, htmx):
        assert len(names(htmx.get("/records?per_page=50").text)) == 50
        assert "1–50 of 137" in htmx.get("/records?per_page=50").text

    def test_a_bigger_size_means_fewer_pages(self, htmx):
        html = htmx.get("/records?per_page=50").text
        assert re.search(r'aria-current="page"[^>]*>(\d+)<', html).group(1) == "1"
        assert "page=3" in html
        assert "page=4" not in html

    def test_the_form_posts_to_a_url_with_no_query_string(self, htmx):
        """A native GET submit throws the action's query away, so anything in
        it would survive the htmx path and vanish on the other one."""
        action = re.search(r'<form[^>]*action="([^"]+)"', htmx.get(FIRST_PAGE).text).group(1)
        assert action == "/records"
        assert "?" not in action

    def test_the_order_survives_a_size_change(self, htmx):
        """It travels as a hidden field, because it cannot travel in the action."""
        html = htmx.get("/records?o=name").text
        assert '<input type="hidden" name="o" value="name">' in html

    def test_the_page_number_does_not_survive_a_size_change(self, htmx):
        """Page 12 of 12 at twelve rows is page 3 of 3 at fifty: the number
        means something different on the other side of the change."""
        html = htmx.get("/records?o=name&page=8").text
        form = html.split("<form")[1].split("</form>")[0]
        assert 'name="page"' not in form

    def test_the_size_survives_a_sort(self, htmx):
        """Otherwise sorting puts the table back to twelve rows, with nothing
        on the page to say why."""
        html = htmx.get("/records?per_page=50").text
        for href in re.findall(r'<th[^>]*>\s*<a[^>]*href="([^"]+)"', html):
            assert "per_page=50" in href

    def test_the_size_survives_paging(self, htmx):
        strip = htmx.get("/records?per_page=25").text.split('aria-label="Pagination"')[1]
        for href in re.findall(r'href="([^"]+)"', strip):
            assert "per_page=25" in href

    def test_the_size_survives_a_bulk_action(self, htmx):
        html = htmx.post("/records/archive?o=&page=2&per_page=50", data={}).text
        assert len(names(html)) == 50
        assert '<option value="50" selected>' in html

    def test_the_control_is_reachable_at_every_size(self, htmx):
        """It sits outside `pagination`, which renders nothing at one page or
        fewer. Inside it, the size that produces one page would trap you."""
        html = htmx.get("/records?per_page=100").text
        assert 'aria-label="Pagination"' in html  # 137 rows still needs two
        big = htmx.get("/records?per_page=100&page=2").text
        assert "<form" in big and 'name="per_page"' in big

    def test_an_unoffered_size_falls_back(self):
        assert parse_page_size(50) == 50
        assert parse_page_size(51) == PER_PAGE
        assert parse_page_size(None) == PER_PAGE
        assert parse_page_size(0) == PER_PAGE


class TestRowNumbers:
    """The serial number column.

    It needs no kit macro — a numbered cell is `cell` with three parameters it
    already has — so what is left to test is the arithmetic.
    """

    def numbers(self, html: str) -> list[int]:
        """The row numbers, read out of the second cell of every row."""
        rows = html.split("<tbody>")[1].split("</tbody>")[0].split("<tr")[1:]
        return [int(re.search(r"tabular-nums[^>]*>\s*(\d+)", row).group(1)) for row in rows]

    def test_the_first_page_starts_at_one(self, htmx):
        assert self.numbers(htmx.get(FIRST_PAGE).text) == list(range(1, PER_PAGE + 1))

    def test_a_later_page_continues_rather_than_restarting(self, htmx):
        """`loop.index` restarts at 1 on every page, numbering all twelve pages
        1 to 12 — which looks correct on any single page."""
        assert self.numbers(htmx.get("/records?page=3").text)[0] == 2 * PER_PAGE + 1

    def test_the_last_page_ends_at_the_total(self, htmx):
        assert self.numbers(htmx.get("/records?page=12").text)[-1] == 137

    def test_the_numbering_follows_the_page_size(self, htmx):
        """The offset is rows-before-this-page, so it has to be computed from
        the size actually used and not from the default."""
        assert self.numbers(htmx.get("/records?per_page=50&page=2").text)[0] == 51

    def test_every_row_is_numbered_exactly_once_across_the_whole_table(self, htmx):
        seen = [n for page in range(1, 13) for n in self.numbers(htmx.get(f"/records?page={page}").text)]
        assert seen == list(range(1, 138))

    def test_the_number_is_the_position_not_the_id(self, htmx):
        """Sorting renumbers every row. A column showing the id would match on
        the default order and be wrong on every other."""
        first = htmx.get("/records?o=name").text
        assert self.numbers(first)[0] == 1
        ids = re.findall(r'name="selected" value="(\d+)"', first)
        assert ids[0] != "1"

    def test_the_header_shrinks_to_the_digits_and_is_not_sortable(self, htmx):
        """It sits against the checkbox column, not at the far side of a fixed
        width. And it numbers the order, so it cannot be an order of its own."""
        header = htmx.get(FIRST_PAGE).text.split("<thead>")[1].split("</thead>")[0]
        assert re.search(r'<th class="w-px text-right"[^>]*>#</th>', header)
        assert "aria-sort" not in header.split("#</th>")[0].rsplit("<th", 1)[-1]

    def test_the_header_is_not_announced_as_the_actions_column(self, htmx):
        """`width="min"` used to add `aria-label="Actions"` to any column that
        asked for it, and `aria-label` replaces the text rather than adding to
        it — so this column would have read out as "Actions"."""
        header = htmx.get(FIRST_PAGE).text.split("<thead>")[1].split("</thead>")[0]
        assert "Actions" not in header.split("#</th>")[0]


# --------------------------------------------------------------------------- #
# batch selection
# --------------------------------------------------------------------------- #


class TestSelection:
    def test_every_row_carries_a_checkbox_named_for_the_action(self, htmx):
        html = htmx.get(FIRST_PAGE).text
        assert html.count('data-fjkit-select="selected"') == PER_PAGE
        assert html.count('name="selected"') == PER_PAGE

    def test_the_header_box_shares_the_rows_name(self, htmx):
        """That name is the key `js/select.js` joins the two halves on, and it
        is the field the selection posts under. One name, both jobs."""
        assert 'data-fjkit-select-all="selected"' in htmx.get(FIRST_PAGE).text

    def test_every_row_checkbox_is_labelled_by_its_row(self, htmx):
        """A column of unlabelled boxes announces itself as "checkbox,
        checkbox, checkbox"."""
        assert len(set(names(htmx.get(FIRST_PAGE).text))) == PER_PAGE

    def test_the_action_collects_the_selection_by_selector(self, htmx):
        """No hidden field, no list maintained anywhere: htmx omits an unticked
        checkbox exactly as a form does."""
        html = htmx.get(FIRST_PAGE).text
        assert 'hx-include="[data-fjkit-select]"' in html

    def test_archiving_moves_the_selected_rows(self, client, htmx):
        target = re.search(r'name="selected" value="(\d+)"', client.get(FIRST_PAGE).text).group(1)
        response = htmx.post("/records/archive", data={"selected": [target]})
        assert response.status_code == 200
        assert "Archived" in response.headers["HX-Trigger"]

    def test_the_reply_is_the_table_the_rows_were_ticked_in(self, client, htmx):
        """Not a redirect and not a fragment of one row: the whole region, so
        the strip under it is counted against the same data."""
        body = htmx.post("/records/archive?o=name&page=3", data={"selected": []}).text
        assert 'id="records"' in body
        assert picked_page(body) == "3"
        assert 'aria-sort="ascending"' in body

    def test_an_empty_selection_is_answered_not_refused(self, htmx):
        """The button is reachable with nothing ticked. Saying so is more use
        than a 422 that swaps the table away."""
        response = htmx.post("/records/archive", data={})
        assert response.status_code == 200
        trigger = json.loads(response.headers["HX-Trigger"])["fjkit:toast"]["messages"][0]
        assert trigger["category"] == "warning"

    def test_a_stale_id_does_not_lose_the_rest_of_the_batch(self, client, htmx):
        """The selection was made against a page that may since have been
        re-sorted."""
        real = re.search(r'name="selected" value="(\d+)"', client.get(FIRST_PAGE).text).group(1)
        response = htmx.post("/records/archive", data={"selected": [real, 99999]})
        message = json.loads(response.headers["HX-Trigger"])["fjkit:toast"]["messages"][0]
        assert message["title"] == "Archived 1 of 2"

    def test_the_count_carries_its_own_words(self, htmx):
        """`js/select.js` contains no English, so a translated page can move
        these two strings without touching the kit."""
        html = htmx.get(FIRST_PAGE).text
        assert 'data-fjkit-select-label="{n} selected"' in html
        assert 'data-fjkit-select-zero="None selected"' in html

    def test_the_page_loads_the_script_the_column_needs(self, client):
        """Per page, never the shell: the pages without a select column must
        not download it."""
        assert "js/select.js" in client.get(FIRST_PAGE).text
        assert "js/select.js" not in client.get("/tasks").text


# --------------------------------------------------------------------------- #
# the two pure functions the URLs come out of
# --------------------------------------------------------------------------- #


class TestSortContract:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("name", ("name", False)), ("-name", ("name", True)), (None, ("updated", True)), ("nope", ("updated", True))],
    )
    def test_parse_sort(self, raw, expected):
        assert parse_sort(raw) == expected

    def test_columns_open_with_the_selection_column(self):
        assert columns("/records", None)[0] == {"select": True}

    def test_columns_mark_exactly_one_as_sorted(self):
        marked = [c for c in columns("/records", "owner") if c.get("sort")]
        assert [c["label"] for c in marked] == ["Owner"]

    def test_page_url_carries_no_page_number(self):
        """`pagination()` appends one, and a URL that already has one produces
        a link with two."""
        assert page_url("/records", "-rows") == f"/records?o=-rows&per_page={PER_PAGE}"
        assert page_url("/records", None) == f"/records?o={DEFAULT_SORT}&per_page={PER_PAGE}"


class TestService:
    def test_the_fixture_is_deterministic(self):
        """Two runs must sort identically, or a test naming the rows on page 3
        cannot exist."""
        assert [r.name for r in RecordService().page(None, 1, 5)[0]] == [
            r.name for r in RecordService().page(None, 1, 5)[0]
        ]

    def test_the_page_number_comes_back_clamped(self):
        assert RecordService().page(None, 900, 12)[1:] == (12, 12)

    def test_archiving_is_idempotent(self):
        service = RecordService()
        assert service.archive([1, 2]) == 2
        assert service.archive([1, 2]) == 0
