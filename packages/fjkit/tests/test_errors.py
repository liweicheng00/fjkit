"""What a browser is shown when a request fails, and how the pieces name it.

`fjkit.forms` names the failure, `fjkit.htmx` names the caller, and
`fjkit.errors` decides what goes back: FastAPI's JSON for a swap and for a JSON
client, an error page for a navigation.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import pytest
from fastapi import APIRouter, FastAPI, Form, Request, Response
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, htmx, messages, mount_fjkit, render
from fjkit.forms import NO_ERRORS, FieldErrors, field_errors, field_name, label
from jinja2 import DictLoader
from pydantic import BaseModel, Field, ValidationError

TEMPLATES = {
    "page.html": "<page>",
    "_board.html": "<board>",
    "errors/page.html": "<error-page status={{ status_code }}>{{ errors.title if errors else '' }}",
}

HTMX = {"HX-Request": "true"}
JSON = {"Accept": "application/json"}
BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


class TaskIn(BaseModel):
    """A model the handler builds itself, so its `loc` is model-scoped."""

    title: str


class Posted(BaseModel):
    """A body an endpoint takes whole, as `application/json`."""

    title: str = Field(min_length=3)


class RaisedError(RuntimeError):
    """Not a validation failure: nothing about it is the person's fault."""


def make_app(
    config: FjkitConfig | None = None,
    *,
    raise_server_exceptions: bool = False,
) -> TestClient:
    """Build routes covering every kind of caller a rejected request can have.

    Pass `raise_server_exceptions=False` where the status code is the subject.
    """
    router = APIRouter()

    @router.post("/toast")
    @render("page.html", partial="_board.html")
    def toast(title: Annotated[str, Form()]) -> dict[str, str]:
        return {}

    @router.post("/json")
    @render("page.html", partial="_board.html")
    def json_body(payload: Posted) -> dict[str, str]:
        """The same form as `/toast`, declared as a model instead of fields."""
        return {}

    @router.post("/fragment")
    @render("_board.html")
    def fragment(title: Annotated[str, Form()]) -> dict[str, str]:
        return {}

    @router.post("/save")
    def save(title: Annotated[str, Form()]) -> dict[str, str]:
        """No `@render` at all — the submit-and-redirect route."""
        return {}

    @router.post("/service")
    @render("_board.html")
    def service(title: Annotated[str, Form()]) -> dict[str, str]:
        """A model the handler builds, which fails the way a bug would."""
        TaskIn(title=0)  # type: ignore[arg-type]
        return {}

    @router.post("/boom")
    @render("page.html", partial="_board.html")
    def boom() -> dict[str, str]:
        raise RaisedError("the service is down")

    @router.post("/boom-fragment")
    @render("_board.html")
    def boom_fragment() -> dict[str, str]:
        """The same failure on a route that serves no page of its own."""
        raise RaisedError("the service is down")

    app = FastAPI()
    templates = mount_fjkit(app, config or FjkitConfig())
    templates.env.loader = DictLoader(TEMPLATES)
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def request_with(**headers: str) -> Request:
    """A `Request` carrying nothing but the headers under test."""
    raw = [(name.lower().replace("_", "-").encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw})


def toast_titles(response) -> list[str]:
    """Pull the titles out of an `HX-Trigger` toast payload."""
    payload = json.loads(response.headers["hx-trigger"])[messages.TOAST_EVENT]
    return [d["title"] for d in payload["messages"]]


def error(loc: tuple[Any, ...], msg: str, kind: str = "value_error") -> dict[str, Any]:
    """Build one entry of `.errors()`. `kind` is pydantic's `type`."""
    return {"loc": loc, "msg": msg, "type": kind}


class FakeExc:
    """Anything with `.errors()`. That is all `field_errors` looks for."""

    def __init__(self, *details: dict[str, Any]) -> None:
        self._details = details

    def errors(self) -> tuple[dict[str, Any], ...]:
        return self._details


# --------------------------------------------------------------------------- #
# forms — which field a failure belongs to
# --------------------------------------------------------------------------- #


def test_a_request_scoped_field_is_named_the_way_the_form_posted_it():
    """`body.title` is FastAPI's name for it and `title` is the form's. The
    form's is what a template writes in `name=`."""
    assert field_name(("body", "title"), request_scoped=True) == "title"


def test_a_nested_field_keeps_its_whole_path():
    """Flattening `items.0.title` to `title` would make every row of a repeated
    section share one message."""
    assert field_name(("body", "items", 0, "title"), request_scoped=True) == "items.0.title"


def test_a_failure_outside_the_body_is_not_a_field_on_this_form():
    """A bad query parameter is a real failure, but marking an input that shares
    its name blames the wrong control."""
    assert field_name(("query", "status"), request_scoped=True) is None


def test_a_body_with_nothing_under_it_names_no_field():
    """`("body",)` means the whole body is wrong, malformed JSON for example.
    No single input can carry that."""
    assert field_name(("body",), request_scoped=True) is None


def test_a_model_scoped_loc_has_no_prefix_to_strip():
    """A model the handler built has no request in it, so it reports the field
    and nothing else."""
    assert field_name(("title",), request_scoped=False) == "title"


def test_a_whole_model_validator_names_no_field():
    """An empty `loc` is what a model-level validator reports. It renders above
    the form, not under a control."""
    assert field_name((), request_scoped=False) is None


def test_a_model_field_called_body_survives_model_scoped_parsing():
    """Why `request_scoped=` exists instead of sniffing for a leading `"body"`:
    a model with a field of that name would have its error silently dropped, and
    nothing would report it."""
    assert field_name(("body",), request_scoped=False) == "body"
    assert field_name(("body", "title"), request_scoped=False) == "body.title"


# --------------------------------------------------------------------------- #
# forms — reading an exception
# --------------------------------------------------------------------------- #


def test_only_the_first_message_for_a_field_is_kept():
    """A control has one `<p>` under it, and pydantic reports constraints in
    declaration order, so the first is the one closest to what was typed."""
    errors = field_errors(
        FakeExc(error(("body", "title"), "Field required"), error(("body", "title"), "String too short")),
        request_scoped=True,
    )

    assert errors.title == "Field required"


def test_a_message_belonging_to_no_field_goes_to_general():
    """It has nowhere to render inline, so the form shows it above itself and a
    toast reads it out. Dropping it would lose the failure."""
    errors = field_errors(
        FakeExc(error(("query", "status"), "Not a status"), error(("body", "title"), "Field required")),
        request_scoped=True,
    )

    assert errors.general == ("Not a status",)
    assert dict(errors) == {"title": "Field required"}


def test_a_body_that_could_not_be_read_names_no_field():
    """`json_invalid` reports `("body", 12)`: a text offset, not a field."""
    errors = field_errors(FakeExc(error(("body", 12), "JSON decode error", kind="json_invalid")), request_scoped=True)

    assert dict(errors) == {}
    assert errors.general == ("JSON decode error",)


def test_the_first_item_of_a_list_body_is_still_a_field():
    """The guard on the test above, and why it reads the `type` rather than the
    shape: a body that is itself a list reports `("body", 0)` about its first
    item, which is a real field with a place to render."""
    errors = field_errors(
        FakeExc(error(("body", 0), "Input should be a valid string", kind="string_type")),
        request_scoped=True,
    )

    assert dict(errors) == {"0": "Input should be a valid string"}
    assert errors.general == ()


def test_an_exception_with_nothing_to_say_yields_nothing():
    """`field_errors` is duck-typed, and an object without `.errors()` is no
    reason to raise a second exception on top of the first."""
    errors = field_errors(object(), request_scoped=True)

    assert len(errors) == 0
    assert errors.general == ()


def test_a_field_that_is_fine_reads_as_none_rather_than_raising():
    """`text_field(error=errors.title)` is written once and rendered both on
    first paint and on the way back from a 422. Under `strict_undefined` a plain
    dict would turn the valid case into a 500."""
    errors = FieldErrors({"owner": "Field required"})

    assert errors.title is None
    with pytest.raises(KeyError):
        errors["title"]


def test_the_errors_are_an_ordinary_mapping():
    """Attribute access is for templates. A caller asserting that a key is
    present still gets `in`, `len` and iteration."""
    errors = FieldErrors({"title": "Field required", "owner": "Unknown"})

    assert len(errors) == 2
    assert "title" in errors
    assert sorted(errors) == ["owner", "title"]


def test_a_message_names_its_field_the_way_a_person_reads_it():
    """A toast appears away from the control it is about, so `Field required` on
    its own leaves the reader searching for the field."""
    errors = FieldErrors({"owner_name": "Field required"}, ["Pick at least one."])

    assert errors.messages() == ("Owner name: Field required", "Pick at least one.")


# --------------------------------------------------------------------------- #
# forms — saying a field name out loud
# --------------------------------------------------------------------------- #


def test_a_wire_name_loses_its_underscores_when_it_is_read_out():
    assert label("owner_name") == "Owner name"


def test_an_index_in_a_field_name_is_shown_one_based():
    """`items.0.title` names the first item to everyone but a programmer."""
    assert label("items.0.title") == "Items 1 title"


# --------------------------------------------------------------------------- #
# htmx — what kind of request is this
# --------------------------------------------------------------------------- #


def test_an_ordinary_request_is_neither_htmx_nor_a_swap():
    request = request_with(accept="text/html")

    assert htmx.is_htmx(request) is False
    assert htmx.is_boosted(request) is False
    assert htmx.is_swap(request) is False


def test_a_swap_is_htmx_and_not_boosted():
    request = request_with(hx_request="true")

    assert htmx.is_htmx(request) is True
    assert htmx.is_boosted(request) is False
    assert htmx.is_swap(request) is True


def test_a_boosted_navigation_is_htmx_but_not_a_swap():
    """It wants a whole document. A fragment leaves the browser on a page with
    no shell."""
    request = request_with(hx_request="true", hx_boosted="true")

    assert htmx.is_htmx(request) is True
    assert htmx.is_boosted(request) is True
    assert htmx.is_swap(request) is False


def test_hx_boosted_without_hx_request_is_not_htmx_at_all():
    """htmx sends both headers. One on its own is a client making it up, and it
    must not change what the app returns."""
    request = request_with(hx_boosted="true")

    assert htmx.is_htmx(request) is False
    assert htmx.is_swap(request) is False


def test_the_header_value_is_matched_whatever_case_it_arrives_in():
    """The value, not the name: a case-sensitive `== "true"` turns
    `HX-Request: True` into a page that never swaps."""
    request = request_with(hx_request="True")

    assert htmx.is_htmx(request) is True
    assert htmx.is_swap(request) is True


def test_the_target_and_the_prompt_are_none_when_htmx_named_neither():
    """An empty header is the same as no header; it is not an element id."""
    assert htmx.target(request_with(hx_target="board")) == "board"
    assert htmx.prompt(request_with(hx_prompt="Delete it")) == "Delete it"
    assert htmx.target(request_with(hx_target="")) is None
    assert htmx.prompt(request_with()) is None


# --------------------------------------------------------------------------- #
# htmx — correcting where the reply lands
# --------------------------------------------------------------------------- #


def test_retargeting_also_says_how_to_swap():
    """`hx-swap` was written for the original target. Changing what it applies
    to while leaving it alone lets a form replace a region it does not own."""
    response = Response()

    htmx.retarget(response, "#new-form", swap="outerHTML")

    assert response.headers["hx-retarget"] == "#new-form"
    assert response.headers["hx-reswap"] == "outerHTML"


def test_a_retarget_with_no_swap_leaves_the_swap_style_alone():
    """`swap=None` means the caller says the existing style still fits."""
    response = Response()

    htmx.retarget(response, "#new-form")

    assert response.headers["hx-retarget"] == "#new-form"
    assert "hx-reswap" not in response.headers


def test_headers_can_be_written_into_a_plain_dict():
    """The caller this exists for is an exception handler, which builds its
    headers before it has a response to put them on."""
    headers: dict[str, str] = {}

    htmx.retarget(headers, "#new-form", swap="outerHTML")

    assert headers == {"HX-Retarget": "#new-form", "HX-Reswap": "outerHTML"}


def test_a_swap_style_can_be_overridden_on_its_own():
    response = Response()

    htmx.reswap(response, "none")

    assert response.headers["hx-reswap"] == "none"


# --------------------------------------------------------------------------- #
# errors — a rejected swap is FastAPI's own 422, and the page draws it
# --------------------------------------------------------------------------- #


def test_a_rejected_swap_gets_fastapis_list_back_unchanged():
    """The reply is FastAPI's list, unchanged: no markup, no retarget, no toast
    header. `js/errors.js` draws it in the form still on the page.
    """
    client = make_app()

    response = client.post("/toast", data={}, headers=HTMX)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"][0]["loc"] == ["body", "title"]
    assert "hx-trigger" not in response.headers
    assert "hx-retarget" not in response.headers


def test_a_rejected_json_submit_is_answered_the_same_way():
    """`encoding="json"` changes what the submit carries, not what comes back.
    FastAPI prefixes a JSON body's `loc` with `body` exactly as it does a
    form's, so the script finds the field by the same name."""
    client = make_app()

    response = client.post("/json", json={"title": "no"}, headers=HTMX)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "title"]


def test_an_unreadable_json_body_still_comes_back_as_the_list():
    """There is no field to draw it on, because the body never got as far as
    having fields. The script raises what it cannot place as a toast, so the
    reply keeps its shape and the browser decides."""
    client = make_app()

    reply = client.post("/json", content=b"{not json", headers={"content-type": "application/json", **HTMX})

    assert reply.status_code == 422
    assert reply.json()["detail"][0]["type"] == "json_invalid"


def test_a_navigation_to_a_route_with_no_render_gets_a_rendered_error_page():
    """A route with no `@render` is recognised by `Accept`, and a navigation
    gets a document."""
    client = make_app()

    response = client.post("/save", data={}, headers=BROWSER)

    assert response.status_code == 422
    assert response.text == "<error-page status=422>Field required"


def test_a_boosted_navigation_is_a_navigation():
    """`hx-boost` is htmx doing what a link does. No form is left on the page to
    draw into, so it gets the document a plain navigation gets."""
    client = make_app()

    response = client.post("/toast", data={}, headers={**HTMX, "HX-Boosted": "true"})

    assert response.status_code == 422
    assert response.text.startswith("<error-page")


# --------------------------------------------------------------------------- #
# errors — a model the handler built itself
# --------------------------------------------------------------------------- #


def test_a_model_error_inside_a_handler_is_not_dressed_up():
    """A `ValidationError` raised inside a handler is not caught, because it has
    the shape of a bug. Declare the model in the signature instead."""
    client = make_app(raise_server_exceptions=True)

    with pytest.raises(ValidationError):
        client.post("/service", data={"title": "typed"}, headers=HTMX)


# --------------------------------------------------------------------------- #
# errors — the API contract, untouched
# --------------------------------------------------------------------------- #


def test_a_json_client_still_gets_fastapis_own_reply():
    """Turning an API's error into an HTML page is a worse bug than the one this
    module fixes."""
    client = make_app()

    response = client.post("/fragment", data={}, headers=JSON)

    assert response.status_code == 422
    assert response.json() == {
        "detail": [{"type": "missing", "loc": ["body", "title"], "msg": "Field required", "input": None}]
    }


# --------------------------------------------------------------------------- #
# errors — everything that is not a rejected form
# --------------------------------------------------------------------------- #


def test_an_unhandled_error_is_not_swallowed_by_default():
    """In development a traceback beats a tidy apology; a handler that catches
    one turns a real bug into a mystery."""
    client = make_app(raise_server_exceptions=True)

    with pytest.raises(RaisedError):
        client.post("/boom", headers=HTMX)


def test_a_caught_unhandled_error_reaches_a_swap_as_a_toast():
    """500 and no body: the page stays where it is, and the person is told that
    something broke and nothing more."""
    client = make_app(FjkitConfig(catch_unexpected_errors=True))

    response = client.post("/boom", headers=HTMX)

    assert response.status_code == 500
    assert response.text == ""
    assert toast_titles(response) == ["Something went wrong"]


def test_the_unexpected_message_can_be_one_fixed_message():
    """`unexpected_error=Message(...)` changes the words, not the mechanism."""
    config = FjkitConfig(
        catch_unexpected_errors=True,
        unexpected_error=messages.Message("Oops", "We are on it.", category="warning"),
    )
    client = make_app(config)

    response = client.post("/boom", headers=HTMX)

    assert response.status_code == 500
    assert response.text == ""
    payload = json.loads(response.headers["hx-trigger"])[messages.TOAST_EVENT]["messages"]
    assert payload == [{"category": "warning", "title": "Oops", "description": "We are on it."}]


def test_the_unexpected_message_can_be_chosen_per_exception():
    """A callable sees the request and the exception, so the words can depend
    on what actually broke."""

    def choose(request: Request, exc: Exception) -> messages.Message:
        if isinstance(exc, RaisedError):
            return messages.Message(f"Service down on {request.url.path}")
        return messages.Message("Something else")

    client = make_app(FjkitConfig(catch_unexpected_errors=True, unexpected_error=choose))

    response = client.post("/boom", headers=HTMX)

    assert response.status_code == 500
    assert toast_titles(response) == ["Service down on /boom"]


def test_a_chooser_that_raises_falls_back_to_the_default(caplog):
    """The chooser runs inside the last handler there is. If it raises, that is
    logged and the kit's own wording goes out, so the person still hears
    something and the original traceback is not replaced by a second one."""

    def broken(request: Request, exc: Exception) -> messages.Message:
        raise KeyError("no words for this")

    client = make_app(FjkitConfig(catch_unexpected_errors=True, unexpected_error=broken))

    with caplog.at_level("ERROR", logger="fjkit.errors"):
        response = client.post("/boom", headers=HTMX)

    assert response.status_code == 500
    assert toast_titles(response) == ["Something went wrong"]
    assert "unexpected_error raised" in caplog.text


def test_a_caught_unhandled_error_reaches_a_navigation_as_a_page():
    """A navigation has no page left to put a toast on."""
    client = make_app(FjkitConfig(catch_unexpected_errors=True))

    response = client.post("/boom", headers=BROWSER)

    assert response.status_code == 500
    assert response.text == "<error-page status=500>"


def test_a_caught_unhandled_error_leaves_a_json_client_with_a_plain_500():
    """That caller was not reading a page, and an HTML apology is no improvement
    on `Internal Server Error`. A route that serves a page is a different case:
    it has markup waiting either way."""
    client = make_app(FjkitConfig(catch_unexpected_errors=True))

    response = client.post("/boom-fragment", headers=JSON)

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


def test_a_field_that_is_fine_renders_no_message():
    """`None`, not `""`. `error=` is a truthiness switch in `ui/form.html`, and
    the empty string is still a value handed to a macro."""
    assert NO_ERRORS.title is None
