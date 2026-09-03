"""`fjkit.messages` — picking the channel a message rides out on.

A full page carries its own toaster; a fragment does not. The caller never says
which, so `_deliver_messages` decides. Getting it wrong shows a message twice
or never.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Message, messages, mount_fjkit, render
from jinja2 import DictLoader

#: The page reads `fjkit_messages()`; the fragment deliberately does not,
#: because an htmx swap replaces a region with no toaster in it.
TEMPLATES = {
    "page.html": "{% for m in fjkit_messages() %}[{{ m.category }}:{{ m.title }}:{{ m.text }}]{% endfor %}",
    "_frag.html": "<div id=frag>fragment</div>",
}

HTMX = {"HX-Request": "true"}


def make_app(existing_trigger: str | None = None) -> TestClient:
    """Build an app whose routes queue a message and then render something.

    The handler writes `existing_trigger` onto its own `Response`, which is how
    an app raises an event of its own alongside a toast.
    """
    router = APIRouter()

    @router.get("/page")
    @render("page.html")
    def page(request: Request) -> dict[str, str]:
        messages.add(request, "Saved", "Two rows changed.", category="success")
        return {}

    @router.get("/swap")
    @render("page.html", partial="_frag.html")
    def swap(request: Request, response: Response) -> dict[str, str]:
        messages.add(request, "Saved", "Two rows changed.", category="success")
        if existing_trigger is not None:
            response.headers["HX-Trigger"] = existing_trigger
        return {}

    @router.get("/many")
    @render("page.html", partial="_frag.html")
    def many(request: Request) -> dict[str, str]:
        messages.add(request, "First", category="info")
        messages.add(request, "Second", category="error")
        return {}

    @router.get("/quiet")
    @render("page.html", partial="_frag.html")
    def quiet(response: Response) -> dict[str, str]:
        if existing_trigger is not None:
            response.headers["HX-Trigger"] = existing_trigger
        return {}

    app = FastAPI()
    templates = mount_fjkit(app, FjkitConfig())
    templates.env.loader = DictLoader(TEMPLATES)
    app.include_router(router)
    return TestClient(app)


def toast_detail(response) -> list[dict[str, str]]:
    """Parse the toast payload out of an `HX-Trigger` header."""
    return json.loads(response.headers["hx-trigger"])[messages.TOAST_EVENT]["messages"]


# --------------------------------------------------------------------------- #
# picking the channel
# --------------------------------------------------------------------------- #


def test_a_message_on_a_full_page_render_goes_into_the_toaster():
    """The shell is already on its way out, so the message travels in the
    document rather than in a header."""
    client = make_app()

    response = client.get("/page")

    assert response.text == "[success:Saved:Two rows changed.]"
    assert "hx-trigger" not in response.headers


def test_a_message_on_an_htmx_swap_goes_out_as_a_trigger_header():
    """A fragment has no toaster in it. The header is the only way out."""
    client = make_app()

    response = client.get("/swap", headers=HTMX)

    assert toast_detail(response) == [
        {"category": "success", "title": "Saved", "description": "Two rows changed."}
    ]
    assert "Saved" not in response.text


def test_the_same_route_never_uses_both_channels():
    """Delivering twice is the failure this split prevents: one message shown as
    a toast and again in the toaster the swap did not replace."""
    client = make_app()

    page = client.get("/swap")
    fragment = client.get("/swap", headers=HTMX)

    assert page.text == "[success:Saved:Two rows changed.]"
    assert "hx-trigger" not in page.headers
    assert "Saved" not in fragment.text
    assert messages.TOAST_EVENT in fragment.headers["hx-trigger"]


def test_a_swap_with_nothing_queued_sets_no_trigger_header():
    """`trigger_header` returns what it was given when the queue is empty, so a
    route that raises nothing sends nothing."""
    client = make_app()

    assert "hx-trigger" not in client.get("/quiet", headers=HTMX).headers


# --------------------------------------------------------------------------- #
# merging with the handler's own event
# --------------------------------------------------------------------------- #


def test_a_trigger_the_handler_set_as_json_survives_alongside_the_toast():
    """Dropping the handler's event because a toast was queued is a bug that
    appears only when both are in play."""
    client = make_app('{"myEvent":null}')

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert events[messages.TOAST_EVENT]["messages"][0]["title"] == "Saved"


def test_a_bare_event_name_is_promoted_rather_than_overwritten():
    """htmx accepts `HX-Trigger: myEvent`, so a handler may write it. Adding a
    toast turns that into an object rather than replacing it."""
    client = make_app("myEvent")

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert messages.TOAST_EVENT in events


def test_a_comma_separated_list_of_event_names_keeps_every_name():
    """The multi-event form of the same header. Every name is the handler's
    intent, so every name survives."""
    client = make_app("myEvent, otherEvent")

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert events["otherEvent"] is None
    assert messages.TOAST_EVENT in events


def test_the_handlers_header_is_found_under_the_name_starlette_stored_it_as():
    """A handler writes `HX-Trigger`; `MutableHeaders` lowercases it, so
    `_deliver_messages` sees `hx-trigger`. A case-sensitive lookup would miss it
    and emit two conflicting headers."""
    client = make_app('{"myEvent":null}')

    response = client.get("/swap", headers=HTMX)

    assert len(response.headers.get_list("hx-trigger")) == 1
    assert json.loads(response.headers["hx-trigger"])["myEvent"] is None


def test_a_trigger_header_the_kit_did_not_write_is_left_alone():
    """No message means no reason to touch the header, least of all to
    reserialise it."""
    client = make_app("myEvent")

    assert client.get("/quiet", headers=HTMX).headers["hx-trigger"] == "myEvent"


# --------------------------------------------------------------------------- #
# order
# --------------------------------------------------------------------------- #


def test_several_messages_keep_their_order_on_a_page():
    """Queue order is the order the handler raised them in, which is the order
    it meant them to be read in."""
    client = make_app()

    assert client.get("/many").text == "[info:First:None][error:Second:None]"


def test_several_messages_keep_their_order_in_the_trigger_header():
    """Same guarantee, other channel. Serialising must not reorder them."""
    client = make_app()

    details = toast_detail(client.get("/many", headers=HTMX))

    assert [d["title"] for d in details] == ["First", "Second"]
    assert [d["category"] for d in details] == ["info", "error"]


# --------------------------------------------------------------------------- #
# Message
# --------------------------------------------------------------------------- #


def test_a_message_without_text_carries_no_description():
    """Basecoat's toaster renders the description slot whenever the key is
    present, so an absent body must be an absent key rather than a null."""
    assert Message("Saved").as_detail() == {"category": "info", "title": "Saved"}


def test_a_message_with_text_carries_it_as_description():
    """`text` is fjkit's name for the field, `description` is Basecoat's. The
    rename happens here and nowhere else."""
    detail = Message("Saved", "Two rows changed.", category="success").as_detail()

    assert detail == {"category": "success", "title": "Saved", "description": "Two rows changed."}


# --------------------------------------------------------------------------- #
# the queue
# --------------------------------------------------------------------------- #


def fake_request() -> Request:
    """A `Request` carrying only `state`, which is all the queue touches."""
    return Request({"type": "http", "headers": [], "method": "GET", "path": "/", "state": {}})


def test_iterating_the_queue_marks_the_messages_shown():
    """`FlashPlugin` reads `shown()` before clearing its cookie, and a message
    that reached a template reached the browser."""
    request = fake_request()
    messages.add(request, "Saved")

    assert list(messages.queue(request)) == [Message("Saved")]
    assert messages.shown(request) is True


def test_asking_whether_there_is_anything_to_show_does_not_show_it():
    """`{% if fjkit_messages() %}` guards a region rather than rendering one.
    Marking on that would let a page clear a flash cookie it never drew."""
    request = fake_request()
    messages.add(request, "Saved")
    queue = messages.queue(request)

    assert bool(queue) is True
    assert len(queue) == 1
    assert messages.shown(request) is False


def test_iterating_an_empty_queue_shows_nothing():
    """A page that reads an empty toaster has shown nothing, so a message queued
    later on the same request must still get out."""
    request = fake_request()

    assert list(messages.queue(request)) == []
    assert messages.shown(request) is False


def test_draining_the_queue_empties_it_and_marks_it_shown():
    """The header channel takes the messages away, which stops the same response
    delivering them a second time through a template."""
    request = fake_request()
    messages.add(request, "Saved", category="warning")
    queue = messages.queue(request)

    assert queue.drain() == (Message("Saved", category="warning"),)
    assert len(queue) == 0
    assert messages.shown(request) is True


def test_the_queue_is_the_same_object_on_every_lookup():
    """Two calls returning different queues would make a message added through
    `add()` invisible to the template that reads it."""
    request = fake_request()

    assert messages.queue(request) is messages.queue(request)


def test_a_render_with_no_request_gets_an_empty_queue():
    """The docs-site builder and `bench/render_bench.py` drive the shell with
    `request=None`, and the shell reads the toaster on every page."""
    queue = messages.queue(None)

    assert bool(queue) is False
    assert len(queue) == 0
    assert list(queue) == []
