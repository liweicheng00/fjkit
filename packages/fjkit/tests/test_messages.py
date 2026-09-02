"""`fjkit.messages` — the message that rides out on whichever channel fits.

A full page carries its own toaster, a fragment does not. The caller never says
which, so the choice is made in `_deliver_messages`, and getting it wrong is
either a message shown twice or a message shown never.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Message, messages, mount_fjkit, render
from jinja2 import DictLoader

#: The page reads `fjkit_messages()`; the fragment deliberately does not, because
#: an htmx swap replaces a region that has no toaster in it.
TEMPLATES = {
    "page.html": "{% for m in fjkit_messages() %}[{{ m.category }}:{{ m.title }}:{{ m.text }}]{% endfor %}",
    "_frag.html": "<div id=frag>fragment</div>",
}

HTMX = {"HX-Request": "true"}


def make_app(existing_trigger: str | None = None) -> TestClient:
    """An app whose routes queue a message and then render something.

    `existing_trigger` is written by the handler onto its own `Response`, which
    is how an app raises an event of its own alongside a toast.
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
    """The toast payload out of an `HX-Trigger`, parsed."""
    return json.loads(response.headers["hx-trigger"])[messages.TOAST_EVENT]["messages"]


# --------------------------------------------------------------------------- #
# picking the channel
# --------------------------------------------------------------------------- #


def test_a_message_on_a_full_page_render_goes_into_the_toaster():
    """The shell is on its way out already, so the message travels in the
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
    """Delivering twice is the failure this split exists to prevent: one message
    would show as a toast and again in the toaster the swap did not replace."""
    client = make_app()

    page = client.get("/swap")
    fragment = client.get("/swap", headers=HTMX)

    assert page.text == "[success:Saved:Two rows changed.]"
    assert "hx-trigger" not in page.headers
    assert "Saved" not in fragment.text
    assert messages.TOAST_EVENT in fragment.headers["hx-trigger"]


def test_a_swap_with_nothing_queued_sets_no_trigger_header():
    """`trigger_header` returns what it was given when the queue is empty, so a
    route that raises nothing stays a route that says nothing."""
    client = make_app()

    assert "hx-trigger" not in client.get("/quiet", headers=HTMX).headers


# --------------------------------------------------------------------------- #
# merging with the handler's own event
# --------------------------------------------------------------------------- #


def test_a_trigger_the_handler_set_as_json_survives_alongside_the_toast():
    """Dropping the handler's event because a toast happened to be queued is a
    bug that only appears when both are in play."""
    client = make_app('{"myEvent":null}')

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert events[messages.TOAST_EVENT]["messages"][0]["title"] == "Saved"


def test_a_bare_event_name_is_promoted_rather_than_overwritten():
    """htmx accepts `HX-Trigger: myEvent`, so a handler is entitled to write it.
    Adding a toast has to turn that into an object, not replace it."""
    client = make_app("myEvent")

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert messages.TOAST_EVENT in events


def test_a_comma_separated_list_of_event_names_keeps_every_name():
    """The multi-event form of the same header. All of them are the handler's
    intent, so all of them survive."""
    client = make_app("myEvent, otherEvent")

    events = json.loads(client.get("/swap", headers=HTMX).headers["hx-trigger"])

    assert events["myEvent"] is None
    assert events["otherEvent"] is None
    assert messages.TOAST_EVENT in events


def test_the_handlers_header_is_found_under_the_name_starlette_stored_it_as():
    """A handler writes `HX-Trigger`; `MutableHeaders` lowercases it, so what
    reaches `_deliver_messages` is `hx-trigger`. A case-sensitive lookup would
    miss it and emit two conflicting headers."""
    client = make_app('{"myEvent":null}')

    response = client.get("/swap", headers=HTMX)

    assert len(response.headers.get_list("hx-trigger")) == 1
    assert json.loads(response.headers["hx-trigger"])["myEvent"] is None


def test_a_trigger_header_the_kit_did_not_write_is_left_alone():
    """No message, no reason to touch it — least of all to reserialise it."""
    client = make_app("myEvent")

    assert client.get("/quiet", headers=HTMX).headers["hx-trigger"] == "myEvent"


# --------------------------------------------------------------------------- #
# order
# --------------------------------------------------------------------------- #


def test_several_messages_keep_their_order_on_a_page():
    """Queue order is the order they were raised in, which is the order the
    handler meant them to be read in."""
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
    """Basecoat's toaster renders the description slot when the key is there, so
    an absent body has to be an absent key rather than a null."""
    assert Message("Saved").as_detail() == {"category": "info", "title": "Saved"}


def test_a_message_with_text_carries_it_as_description():
    """`text` is fjkit's name for the field and `description` is Basecoat's. The
    rename happens here and nowhere else."""
    detail = Message("Saved", "Two rows changed.", category="success").as_detail()

    assert detail == {"category": "success", "title": "Saved", "description": "Two rows changed."}


# --------------------------------------------------------------------------- #
# the queue
# --------------------------------------------------------------------------- #


def fake_request() -> Request:
    """A `Request` with nothing but state — all the queue ever touches."""
    return Request({"type": "http", "headers": [], "method": "GET", "path": "/", "state": {}})


def test_iterating_the_queue_marks_the_messages_shown():
    """`shown()` is what `FlashPlugin` reads before clearing its cookie, and a
    message that reached a template is a message that reached the browser."""
    request = fake_request()
    messages.add(request, "Saved")

    assert list(messages.queue(request)) == [Message("Saved")]
    assert messages.shown(request) is True


def test_asking_whether_there_is_anything_to_show_does_not_show_it():
    """`{% if fjkit_messages() %}` guards a region; it does not render one. Mark
    on that and a flash cookie is cleared by a page that never drew it."""
    request = fake_request()
    messages.add(request, "Saved")
    queue = messages.queue(request)

    assert bool(queue) is True
    assert len(queue) == 1
    assert messages.shown(request) is False


def test_iterating_an_empty_queue_shows_nothing():
    """A page that reads the toaster and finds it empty has not shown anything,
    so a message queued later on the same request must still get out."""
    request = fake_request()

    assert list(messages.queue(request)) == []
    assert messages.shown(request) is False


def test_draining_the_queue_empties_it_and_marks_it_shown():
    """The header channel takes the messages away, which is what stops the same
    response delivering them a second time through a template."""
    request = fake_request()
    messages.add(request, "Saved", category="warning")
    queue = messages.queue(request)

    assert queue.drain() == (Message("Saved", category="warning"),)
    assert len(queue) == 0
    assert messages.shown(request) is True


def test_the_queue_is_the_same_object_on_every_lookup():
    """Two calls that returned different queues would mean a message added
    through `add()` is invisible to the template that reads it."""
    request = fake_request()

    assert messages.queue(request) is messages.queue(request)


def test_a_render_with_no_request_gets_an_empty_queue():
    """The docs-site builder and `bench/render_bench.py` drive the shell with
    `request=None`, and the shell reads the toaster on every page."""
    queue = messages.queue(None)

    assert bool(queue) is False
    assert len(queue) == 0
    assert list(queue) == []
