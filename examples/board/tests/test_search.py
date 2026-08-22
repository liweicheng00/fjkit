"""The out-of-band contract: one reply, five regions — and a swap inside one.

Everything here is really one assertion said four ways — every fragment the
search reply carries must land somewhere on the search page. An out-of-band
swap is addressed by id and fails *silently* when the id is not on the page:
htmx drops the fragment, the region keeps the numbers from the last query, and
nothing anywhere reports an error. So the ids are pinned from both ends.
"""

from __future__ import annotations

import re

REGIONS = ("search-stats", "search-matches", "search-progress", "search-facets", "search-detail")

#: The four regions that are a *view of the answer*. The fifth, the detail
#: panel, is deliberately not one: every search resets it, so it is the one
#: region that must NOT differ between two queries. `test_a_new_query_empties_
#: the_panel` is what holds it to that instead.
DATA_REGIONS = tuple(r for r in REGIONS if r != "search-detail")

#: The element that `hx-target` names, and therefore the one fragment in the
#: reply that must NOT be flagged out-of-band — htmx lifts every flagged
#: element out of the response before swapping what is left into the target.
TARGET = "search-matches"

OOB = re.compile(r'<div id="([\w-]+)" hx-swap-oob="true">')
REGION = re.compile(r'<div id="(search-[\w-]+)"')


def test_the_page_declares_every_region(client):
    page = client.get("/search")
    assert page.status_code == 200
    for region in REGIONS:
        assert page.text.count(f'id="{region}"') == 1, f"{region} must appear exactly once"


def test_a_cold_page_swaps_nothing_out_of_band(client):
    """`hx-swap-oob` in a page's own markup describes a swap that never
    happened. It belongs to the reply, not to the first paint."""
    assert not OOB.search(client.get("/search").text)


def test_the_reply_carries_five_fragments(htmx):
    reply = htmx.get("/search?q=cache")
    assert reply.status_code == 200
    assert "<!doctype html>" not in reply.text.lower()
    assert reply.text.lstrip().startswith(f'<div id="{TARGET}">')
    assert set(REGION.findall(reply.text)) == set(REGIONS)


def test_only_the_target_arrives_in_band(htmx):
    out_of_band = set(OOB.findall(htmx.get("/search?q=cache").text))
    assert out_of_band == set(REGIONS) - {TARGET}


def test_every_out_of_band_id_exists_on_the_page(client, htmx):
    """The swap is addressed by id, so a fragment whose id is not on the page
    is dropped without a word. This is the test that catches a renamed region
    before the browser does not."""
    page = client.get("/search").text
    for region in OOB.findall(htmx.get("/search?q=cache").text):
        assert f'id="{region}"' in page


def test_one_query_moves_every_data_region(htmx):
    everything = htmx.get("/search").text
    narrowed = htmx.get("/search?q=cache").text
    for region in DATA_REGIONS:
        before = everything[everything.index(f'id="{region}"') :]
        after = narrowed[narrowed.index(f'id="{region}"') :]
        assert before != after, f"{region} did not react to the query"


def test_matching_narrows_the_table(htmx):
    everything = htmx.get("/search").text
    narrowed = htmx.get("/search?q=cache").text
    assert 0 < narrowed.count("<tr>") < everything.count("<tr>")


def test_notes_and_owners_are_searchable(htmx):
    """Not just titles: the seed data hides "bytecode" in one task's notes and
    nowhere in any title."""
    assert "Turn off auto_reload" in htmx.get("/search?q=bytecode").text
    assert htmx.get("/search?q=kai").text.count("<tr>") == 3  # header + kai's two


def test_nothing_matched(htmx):
    reply = htmx.get("/search?q=zzzz").text
    assert "No match" in reply
    assert "Nothing matched." in reply


def test_the_page_answers_without_htmx(client, htmx):
    """The form carries a plain `action`/`method="get"` beside the htmx
    attributes, so pressing Enter — or arriving with JavaScript off — has to
    render the same result as a whole page. One route serves both: `partial=`
    is the only thing that differs between these two responses."""
    page = client.get("/search?q=cache")
    assert page.status_code == 200
    assert "<!doctype html>" in page.text.lower()
    assert page.text.count("<tr>") == htmx.get("/search?q=cache").text.count("<tr>")


# --------------------------------------------------------------------------- #
# The nested swap: rows delivered by one reply trigger the next one.
# --------------------------------------------------------------------------- #

DETAIL_TRIGGER = re.compile(r'hx-get="([^"]*/search/task/\d+)"')


def test_every_match_row_carries_a_detail_trigger(htmx):
    reply = htmx.get("/search?q=cache")
    assert reply.text.count("<tr>") - 1 == len(DETAIL_TRIGGER.findall(reply.text)) > 0
    assert reply.text.count('hx-target="#search-detail"') == len(DETAIL_TRIGGER.findall(reply.text))


def test_the_trigger_and_its_target_arrive_in_the_same_reply(htmx):
    """This is the nesting, stated as one assertion: the reply contains both
    the buttons and the panel they aim at. htmx processes what it swaps in, so
    nothing has to register the new rows afterwards."""
    reply = htmx.get("/search?q=cache").text
    assert DETAIL_TRIGGER.search(reply)
    assert 'id="search-detail" hx-swap-oob="true"' in reply


def test_opening_a_match_swaps_only_the_panel(htmx):
    detail = htmx.get("/search/task/5")
    assert detail.status_code == 200
    assert detail.text.lstrip().startswith('<div id="search-detail">')
    assert "hx-swap-oob" not in detail.text, "the panel is the target here, not a passenger"
    assert "Warm the bytecode cache at build time" in detail.text


def test_the_panel_shows_what_the_row_does_not(htmx):
    """The row has four cells. The panel is why opening one is worth a request
    — notes, the created stamp, the flags the edit form sets."""
    detail = htmx.get("/search/task/4").text
    assert "Needs the bytecode cache warmed first" in detail
    assert "Blocked" in detail
    assert "2026-" in detail  # the created stamp


def test_a_missing_task_is_a_404(htmx):
    assert htmx.get("/search/task/999").status_code == 404


def test_a_new_query_empties_the_panel(htmx):
    """Whatever was open may not be in the next result set, so the search reply
    resets the panel out-of-band rather than leaving a card describing a row
    that is no longer on screen."""
    assert "Warm the bytecode cache" in htmx.get("/search/task/5").text
    reply = htmx.get("/search?q=readme").text
    assert "Nothing open" in reply
    assert "Warm the bytecode cache" not in reply


def test_the_page_opens_with_an_empty_panel(client):
    page = client.get("/search").text
    assert page.count('id="search-detail"') == 1
    assert "Nothing open" in page
