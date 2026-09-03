"""Tests for the search page, where both htmx mechanisms are in use at once.

A query is one question the server answers completely: one reply, five
`hx-swap-oob` passengers. A pick is not: one region in band, an event, and the
subscribers fetch themselves. The two halves share a page and a rule — a
fragment a route answers with must not subscribe to the event that route raises.
"""

from __future__ import annotations

import json
import re

import pytest
from app.features.search.schemas import CHANGED_EVENT, SELECTED_EVENT, SELECTED_KEY

#: Every region the page declares.
REGIONS = (
    "search-stats",
    "search-matches",
    "search-progress",
    "search-facets",
    "search-detail",
    "search-related",
)

#: The region a query's reply names with `hx-target`; the rest ride out of band.
QUERY_TARGET = "search-matches"

#: Region -> the events that fragment subscribes to. This table is the page.
SUBSCRIPTIONS = {
    "search-matches": {CHANGED_EVENT},
    "search-stats": {CHANGED_EVENT},
    "search-progress": {CHANGED_EVENT},
    "search-facets": set(),
    "search-detail": {SELECTED_EVENT},
    "search-related": {SELECTED_EVENT, CHANGED_EVENT},
}

#: The region each action answers with in band, and the event that action raises.
#: A region may not subscribe to the event of the route that replaces it.
IN_BAND = {
    "search-matches": SELECTED_EVENT,
    "search-detail": CHANGED_EVENT,
}

#: fragment endpoint -> the region it answers with.
FRAGMENTS = {
    "/search/matches": "search-matches",
    "/search/stats": "search-stats",
    "/search/progress": "search-progress",
    "/search/facets": "search-facets",
    "/search/detail": "search-detail",
    "/search/related": "search-related",
}

#: The endpoints that take an id.
WITH_ID = ("/search/matches", "/search/detail", "/search/related")

OOB = re.compile(r'<div id="([\w-]+)" hx-swap-oob="true"')
REGION = re.compile(r'<div id="(search-[\w-]+)"')


def opening_tag(html: str, region: str) -> str:
    """The opening `<div>` of one region, where the htmx attributes live."""
    return html[html.index(f'id="{region}"') :].split(">", 1)[0]


def listens_for(html: str, region: str) -> set[str]:
    """The events one region's `hx-trigger` names."""
    match = re.search(r'hx-trigger="([^"]*)"', opening_tag(html, region))
    if match is None:
        return set()
    return {part.strip().split(" ")[0] for part in match.group(1).split(",")}


def buttons_for(html: str, selector: str) -> list[str]:
    found = re.findall(rf"<button[^>]*hx-(?:get|post)=\"{selector}[^>]*>", html)
    assert found, f"no button calls {selector}"
    return found


@pytest.fixture
def open_page(client, htmx):
    """The page, plus a detail panel with a task open — Advance renders only then."""
    return client.get("/search").text + htmx.get("/search/detail", params={"task_id": 3}).text


# --------------------------------------------------------------------------- #
# one reply, many regions
# --------------------------------------------------------------------------- #


def test_the_page_declares_every_region(client):
    page = client.get("/search")
    assert page.status_code == 200
    for region in REGIONS:
        assert page.text.count(f'id="{region}"') == 1, f"{region} must appear exactly once"


def test_a_cold_page_swaps_nothing_out_of_band(client):
    assert not OOB.search(client.get("/search").text)


def test_the_reply_carries_every_region(htmx):
    reply = htmx.get("/search?q=cache")
    assert reply.status_code == 200
    assert "<!doctype html>" not in reply.text.lower()
    assert reply.text.lstrip().startswith(f'<div id="{QUERY_TARGET}"')
    assert set(REGION.findall(reply.text)) == set(REGIONS)


def test_only_the_target_arrives_in_band(htmx):
    assert set(OOB.findall(htmx.get("/search?q=cache").text)) == set(REGIONS) - {QUERY_TARGET}


def test_every_out_of_band_id_exists_on_the_page(client, htmx):
    page = client.get("/search").text
    for region in OOB.findall(htmx.get("/search?q=cache").text):
        assert f'id="{region}"' in page


def test_matching_narrows_the_table(htmx):
    everything = htmx.get("/search").text
    narrowed = htmx.get("/search?q=cache").text
    assert narrowed.count("<tr>") < everything.count("<tr>")


def test_a_query_clears_the_selection(htmx):
    """A new query invalidates whatever was open, so the panels come back empty."""
    reply = htmx.get("/search?q=cache").text
    assert "Nothing picked" in reply
    assert "No owner yet" in reply


# --------------------------------------------------------------------------- #
# one id, many fragments
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("region", "events"), sorted(SUBSCRIPTIONS.items()))
def test_each_region_hears_what_it_has_a_reason_to(client, region, events):
    assert listens_for(client.get("/search").text, region) == events


def test_the_facets_hear_nothing(client):
    """Advancing a task changes no owner and no priority, so this one stays still."""
    assert listens_for(client.get("/search").text, "search-facets") == set()
    assert "hx-get" not in opening_tag(client.get("/search").text, "search-facets")


@pytest.mark.parametrize(("region", "raised"), sorted(IN_BAND.items()))
def test_a_regions_own_route_event_is_not_one_it_subscribes_to(client, region, raised):
    """The rule that keeps one click to one fetch per fragment.

    A region that is a route's in-band reply is already being replaced. Hearing
    that route's event as well fetches it a second time for the same click — and
    on a fragment that is its own target, it never stops.
    """
    assert raised not in listens_for(client.get("/search").text, region), (
        f"{region} is the in-band reply to the route that raises {raised}"
    )


def test_picking_answers_with_the_table_and_the_event(htmx):
    """One round trip: the reply is the swap, the header is what the panels hear."""
    reply = htmx.get("/search/select/3")
    assert reply.status_code == 200
    assert reply.text.lstrip().startswith('<div id="search-matches"')
    assert json.loads(reply.headers["HX-Trigger"]) == {SELECTED_EVENT: {SELECTED_KEY: 3}}


def test_picking_marks_the_row_in_the_reply(htmx):
    """The badge arrives in band. Nothing else on the page can put it there."""
    assert ">open</span>" not in htmx.get("/search/matches").text
    assert ">open</span>" in htmx.get("/search/select/3").text


def test_the_trigger_value_is_an_object(htmx):
    """htmx wraps a non-object as `{value: …}`, and `event.detail.task_id` would be undefined."""
    detail = json.loads(htmx.get("/search/select/3").headers["HX-Trigger"])[SELECTED_EVENT]
    assert isinstance(detail, dict)


def test_picking_keeps_the_query(htmx):
    """The table is filtered, so the reply has to be too — `hx-include` sends the box."""
    assert htmx.get("/search/select/3", params={"q": "cache"}).text.count("<tr>") < (
        htmx.get("/search/select/3").text.count("<tr>")
    )


def test_picking_a_task_that_is_gone_is_404(htmx):
    assert htmx.get("/search/select/9999").status_code == 404


def test_a_plain_get_of_a_fragment_route_is_json_and_silent(client):
    """`HX-Trigger` is htmx's protocol, and this caller has no htmx in it."""
    reply = client.get("/search/select/3")
    assert reply.status_code == 200
    assert reply.json()["selected_id"] == 3
    assert "HX-Trigger" not in reply.headers


# --------------------------------------------------------------------------- #
# the route that renders and broadcasts the second event
# --------------------------------------------------------------------------- #


def test_advance_answers_with_the_panel_and_the_event(htmx):
    reply = htmx.post("/search/advance/3")
    assert reply.status_code == 200
    assert reply.text.lstrip().startswith('<div id="search-detail"')
    assert json.loads(reply.headers["HX-Trigger"]) == {CHANGED_EVENT: {SELECTED_KEY: 3}}


def test_advance_moves_the_task(htmx):
    before = htmx.get("/search/detail", params={"task_id": 5}).text
    htmx.post("/search/advance/5")
    assert htmx.get("/search/detail", params={"task_id": 5}).text != before


def test_advancing_a_task_that_is_gone_is_404(htmx):
    assert htmx.post("/search/advance/9999").status_code == 404


# --------------------------------------------------------------------------- #
# the fragments
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", list(FRAGMENTS), ids=lambda p: p.rsplit("/", 1)[-1])
def test_each_endpoint_answers_with_one_region(htmx, path):
    reply = htmx.get(path, params={"task_id": 3} if path in WITH_ID else None)
    assert reply.status_code == 200
    assert "<!doctype html>" not in reply.text.lower()
    assert reply.text.lstrip().startswith(f'<div id="{FRAGMENTS[path]}"')
    assert set(REGION.findall(reply.text)) == {FRAGMENTS[path]}
    assert "hx-swap-oob" not in reply.text


@pytest.mark.parametrize("path", list(FRAGMENTS), ids=lambda p: p.rsplit("/", 1)[-1])
def test_a_swapped_fragment_still_subscribes(htmx, path):
    """The reply replaces the element carrying the attributes, so it must carry them too."""
    region = FRAGMENTS[path]
    reply = htmx.get(path, params={"task_id": 3} if path in WITH_ID else None)
    assert listens_for(reply.text, region) == SUBSCRIPTIONS[region]


def test_only_the_regions_that_need_the_query_ask_for_it(client):
    """`hx-include` is on the counters and the table, whose content is the matches."""
    page = client.get("/search").text
    for region in ("search-matches", "search-stats", "search-progress"):
        assert "hx-include" in opening_tag(page, region), region
    for region in ("search-detail", "search-related"):
        assert "hx-include" not in opening_tag(page, region), region


def test_only_the_regions_that_need_the_id_are_sent_one(client):
    page = client.get("/search").text
    for region in ("search-matches", "search-detail", "search-related"):
        assert "hx-vals" in opening_tag(page, region), region
    for region in ("search-stats", "search-progress"):
        assert "hx-vals" not in opening_tag(page, region), region


def test_a_fragment_renders_cold(htmx):
    """No id is the first-paint state, not an error."""
    for path in FRAGMENTS:
        assert htmx.get(path).status_code == 200


def test_a_fragment_asked_for_a_missing_id_is_404(htmx):
    assert htmx.get("/search/detail", params={"task_id": 9999}).status_code == 404


def test_the_detail_panel_reacts_to_the_id(htmx):
    cold = htmx.get("/search/detail").text
    open_on_3 = htmx.get("/search/detail", params={"task_id": 3}).text
    assert "Nothing picked" in cold
    assert "Nothing picked" not in open_on_3


# --------------------------------------------------------------------------- #
# inheritance
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("selector", ["/search/select/", "/search/advance/"])
def test_a_button_inside_a_subscriber_refuses_the_inherited_vals(open_page, selector):
    """htmx merges inherited `hx-vals`, so an empty object here is merged, not obeyed.

    `unset` is the only value that stops the walk: htmx collects `hx-vals` on a
    path that never consults `hx-disinherit`. Without it every click goes out as
    `?task_id=undefined`, the `js:` expression having been evaluated against a
    click event whose `detail` is `0`.
    """
    for button in buttons_for(open_page, selector):
        assert 'hx-vals="unset"' in button


@pytest.mark.parametrize(
    ("selector", "target"),
    [("/search/select/", "#search-matches"), ("/search/advance/", "#search-detail")],
)
def test_a_button_inside_a_subscriber_names_its_target(open_page, selector, target):
    """`hx-target="this"` is inherited, and inside the button `this` is the button."""
    for button in buttons_for(open_page, selector):
        assert f'hx-target="{target}"' in button


def test_the_row_control_sends_the_query(client):
    """The reply is the filtered table, so the pick has to carry the search box."""
    for button in buttons_for(client.get("/search").text, "/search/select/"):
        assert "hx-include=" in button


def test_the_title_is_the_control(client):
    """No Open button: the row's own name opens it.

    A `link` variant, so it reads as the row's name rather than as a control
    parked beside it, and still a `<button>`, which keeps Tab, Enter and Space
    working now that nothing else in the row is focusable.
    """
    page = client.get("/search").text
    for button in buttons_for(page, "/search/select/"):
        assert 'data-variant="link"' in button
    assert ">Open<" not in page, "the row control is the title now, not a separate button"


def test_a_row_has_exactly_one_control(client):
    """The whole row is the hit target, so a button beside the title would be
    covered by that trigger and could never be clicked on its own."""
    page = client.get("/search").text
    body = page[page.index("<tbody>") : page.index("</tbody>")]
    assert body.count("<button") == body.count("<tr>"), "one control per row, and it is the title"


def test_the_whole_row_is_the_hit_target(client):
    """`from:closest tr` listens on the row, so anywhere in it opens the task.

    The attribute sits on the button, not the `<tr>`: a `<tr>` takes no focus and
    announces nothing, so `hx-get` there would be mouse-only. The button keeps
    Tab, Enter and Space, and the click those fire bubbles to the row the trigger
    watches.
    """
    page = client.get("/search").text
    buttons = buttons_for(page, "/search/select/")
    for button in buttons:
        assert 'hx-trigger="click from:closest tr"' in button
    assert page.count('hx-trigger="click from:closest tr"') == len(buttons)


def test_the_row_trigger_still_lives_on_a_focusable_element(client):
    """The keyboard path is the button. Nothing may move `hx-get` onto the `<tr>`."""
    page = client.get("/search").text
    assert not re.search(r"<tr[^>]*hx-(?:get|post)=", page), (
        "a <tr> cannot be focused, so an htmx attribute there is mouse-only"
    )
