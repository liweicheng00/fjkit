"""Tests for the panels page — lesson 07's fragments moved into tabs.

The page inverts the broadcast trade. On `/search` every region is on screen, so
an event reaching all of them is the point; here three of the four are `hidden`,
so a panel fetches when it is *shown* and hears an event only while it is
showing. Two things carry that, and both are asserted below: the attributes
`tab_panel(lazy=…)` emits, and the header the pick broadcasts on.

What no test here can see is the browser. `hidden` is `display:none`, and the
reason `revealed` is wrong is that a display:none element reports an all-zero
rect that passes htmx's visibility check — a page built with it fetches every
panel at load and looks, on the wire, exactly like this one. `test_no_panel_is
_lazy_by_revealed` is the guard that the wrong attribute never comes back.
"""

from __future__ import annotations

import re

import pytest
from app.features.search.schemas import CHANGED_EVENT, SELECTED_EVENT

#: The page's panels, in the order the tabs declare them.
PANELS = ("panel-detail", "panel-related", "panel-counters")

#: Panel -> the events it hears while it is visible. This table is the page.
SUBSCRIPTIONS = {
    "panel-detail": {SELECTED_EVENT, CHANGED_EVENT},
    "panel-related": {SELECTED_EVENT, CHANGED_EVENT},
    # A pick changes no count.
    "panel-counters": {CHANGED_EVENT},
}

#: Panel -> the endpoint it fetches its body from.
ENDPOINTS = {
    "panel-detail": "/panels/detail",
    "panel-related": "/panels/related",
    "panel-counters": "/panels/counters",
}

#: The panels that send an id. The counters take none, which is why `include`
#: is a parameter rather than something the component assumes.
WITH_ID = ("panel-detail", "panel-related")

PANEL_TAG = re.compile(r'<div id="(panel-[\w-]+)" role="tabpanel"([^>]*)>')

HIDDEN_INPUT = re.compile(r'<input type="hidden" name="task_id" value="([^"]*)">')

#: `hx-include="[name=x]"` -> x, so a test can collect what the page would send.
INCLUDE_SELECTOR = re.compile(r'hx-include="\[name=(\w+)\]"')
HX_GET = re.compile(r'hx-get="([^"]*)"')


@pytest.fixture
def page(client):
    return client.get("/panels").text


def _attrs(page: str) -> dict[str, str]:
    """Panel id -> its attribute text, as the page declares it."""
    return {m.group(1): m.group(2) for m in PANEL_TAG.finditer(page)}


def test_the_page_declares_every_panel(page):
    assert set(_attrs(page)) == set(PANELS)


def test_no_panel_is_lazy_by_revealed(page):
    """The trap this whole page is built around.

    htmx tests `revealed` with getBoundingClientRect, and a panel hidden by
    `display:none` reports an all-zero rect: `top < innerHeight` and
    `bottom >= 0` both hold. Every panel would fetch at page load, with no
    error and nothing empty to notice — and a response body identical to this
    one, which is why the assertion is on the attribute rather than on any
    behaviour.
    """
    assert "revealed" not in page


@pytest.mark.parametrize("panel", PANELS)
def test_each_panel_fetches_when_it_is_shown(page, panel):
    attrs = _attrs(page)[panel]
    assert f'hx-get="{ENDPOINTS[panel]}"' in attrs
    assert 'hx-trigger="intersect' in attrs


@pytest.mark.parametrize("panel", PANELS)
def test_each_panel_hears_exactly_the_events_it_has_a_reason_to(page, panel):
    attrs = _attrs(page)[panel]
    heard = {name for name in (SELECTED_EVENT, CHANGED_EVENT) if f"{name}[" in attrs}
    assert heard == SUBSCRIPTIONS[panel]


@pytest.mark.parametrize("panel", PANELS)
def test_every_broadcast_is_filtered_on_the_panel_being_visible(page, panel):
    """The events are raised on <body>, which a hidden panel hears as well as
    the open one. Without the filter this page costs three requests per
    broadcast and shows one of them."""
    attrs = _attrs(page)[panel]
    for name in SUBSCRIPTIONS[panel]:
        assert f"{name}[!this.hidden] from:body" in attrs, "each event needs its own filter and its own from:body"


@pytest.mark.parametrize("panel", PANELS)
def test_each_panel_survives_its_own_reply(page, panel):
    """A panel replaced by markup that also asked for `intersect` would be
    processed on screen, fire at once, and loop."""
    attrs = _attrs(page)[panel]
    assert 'hx-target="this"' in attrs
    assert 'hx-swap="innerHTML"' in attrs


@pytest.mark.parametrize("panel", PANELS)
def test_only_the_panels_that_need_an_id_send_one(page, panel):
    attrs = _attrs(page)[panel]
    assert ('hx-include="[name=task_id]"' in attrs) is (panel in WITH_ID)


def test_the_table_writes_the_open_id_down_only_when_there_is_one(client):
    """`intersect` carries no event, and a panel hidden at the time of the pick
    never heard one. The page is the only thing both paths can read.

    Nothing picked is an *absent* input, not an empty one. `hx-include` sends
    whatever it selects, so `value=""` would send `task_id=`, and an empty
    string is not an integer — the first panel to open on a fresh page would
    answer 422 before anyone had picked anything.
    """
    assert HIDDEN_INPUT.search(client.get("/panels").text) is None
    picked = client.get("/panels/select/1", headers={"HX-Request": "true"})
    assert HIDDEN_INPUT.search(picked.text).group(1) == "1"


@pytest.mark.parametrize("panel", PANELS)
def test_the_request_the_page_actually_makes_is_answered(client, htmx, panel):
    """Issue what the browser will issue, rather than what the route can take.

    A panel is opened by `intersect`, which fires on the visible tab as the page
    settles — before any pick. So the request under test is the page's own
    markup resolved against the page's own inputs, and the failure this catches
    is a value the page can produce and the route cannot parse.
    """
    page = client.get("/panels").text
    attrs = _attrs(page)[panel]
    url = HX_GET.search(attrs).group(1)

    params = {}
    for name in INCLUDE_SELECTOR.findall(attrs):
        for value in re.findall(rf'<input[^>]*name="{name}"[^>]*value="([^"]*)"', page):
            params[name] = value

    got = htmx.get(url, params=params)
    assert got.status_code == 200, f"the page sends {params or 'no parameters'} and the route refused it"


@pytest.mark.parametrize(
    ("method", "url", "event"),
    [("GET", "/panels/select/1", SELECTED_EVENT), ("POST", "/panels/advance/1", CHANGED_EVENT)],
)
def test_an_action_broadcasts_after_its_own_swap(htmx, method, url, event):
    """`HX-Trigger` fires *before* the reply is swapped in, so a panel reading
    the page would read the id this very reply is about to replace.
    `HX-Trigger-After-Swap` is the header that makes `hx-include` correct."""
    got = htmx.request(method, url)
    assert got.status_code == 200
    assert got.headers["HX-Trigger-After-Swap"] == event
    assert "HX-Trigger" not in got.headers, "the id is on the page; nothing needs to ride in the event"


@pytest.mark.parametrize("panel", PANELS)
def test_every_panel_body_renders_standalone(htmx, panel):
    """A panel body is returned by its own route and never by the page, so a
    missing import shows up as a 500 on the swap and nowhere else."""
    got = htmx.get(ENDPOINTS[panel])
    assert got.status_code == 200
    assert got.text.strip()
    assert "role=\"tabpanel\"" not in got.text, "the tab panel is the wrapper; the body is only its contents"


@pytest.mark.parametrize("url", [ENDPOINTS[p] for p in WITH_ID])
def test_a_panel_reads_the_id_off_the_query_string(htmx, url):
    """What `hx-include` sends. Absent is the cold state, not an error."""
    assert htmx.get(url).status_code == 200
    assert htmx.get(url, params={"task_id": 1}).status_code == 200
    assert htmx.get(url, params={"task_id": 9999}).status_code == 404


def test_the_advance_button_refuses_the_panels_swap(htmx):
    """`hx-target` and `hx-swap` are inherited, and this button sits inside a
    panel that sets them to `this` and `innerHTML`. Inheriting them would make
    it replace the panel it is drawn in — taking the panel's id with it, so
    every later show of that tab would find no target and do nothing."""
    body = htmx.get("/panels/detail", params={"task_id": 1}).text
    button = re.search(r"<button[^>]*/panels/advance/1[^>]*>", body)
    assert button is not None, "the detail panel draws the advance button"
    assert 'hx-target="#panels-matches"' in button.group(0)
    assert 'hx-swap="outerHTML"' in button.group(0)


def test_the_counters_take_no_id_at_all(htmx):
    """The route's signature is the argument for `include` being per panel."""
    assert htmx.get("/panels/counters", params={"task_id": 9999}).status_code == 200
