"""Contracts for the `@render` decorator.

The decorator sits between FastAPI and the handler, so most of what can go
wrong is invisible in a normal request: a signature FastAPI cannot solve, a
sync handler promoted to async, a header the handler set and the wrapper
dropped. Each of those has a test here.
"""

from __future__ import annotations

import inspect
import json
import sys
from dataclasses import dataclass
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Templates, messages, render
from jinja2 import DictLoader
from pydantic import BaseModel

TEMPLATES = {
    "page.html": "<!doctype html><title>{{ title }}</title><main>{{ body }}</main>",
    "_partial.html": "<div id=fragment>{{ body }}</div>",
    "rows.html": "{% for row in rows %}<p>{{ row }}</p>{% endfor %}",
}


class Payload(BaseModel):
    title: str
    body: str


@pytest.fixture
def make_app():
    """Build an app whose `Environment` serves `TEMPLATES` and nothing else."""

    def _make(router: APIRouter, config: FjkitConfig | None = None) -> TestClient:
        config = config or FjkitConfig()
        templates = Templates.create(config)
        templates.env.loader = DictLoader(TEMPLATES)
        app = FastAPI()
        app.state.templates = templates
        app.include_router(router)
        return TestClient(app)

    return _make


# --------------------------------------------------------------------------- #
# the two representations
# --------------------------------------------------------------------------- #


def test_html_mode_renders_the_template(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    response = make_app(router).get("/thing")
    assert response.status_code == 200
    assert response.text == "<!doctype html><title>Hello</title><main>World</main>"
    assert response.headers["content-type"].startswith("text/html")


def test_json_mode_returns_the_model_through_response_model(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", mode="json")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    response = make_app(router).get("/thing")
    assert response.json() == {"title": "Hello", "body": "World"}
    assert response.headers["content-type"].startswith("application/json")


def test_the_return_annotation_reaches_openapi(make_app):
    """The annotation documents the JSON without a second declaration. If
    FastAPI cannot see through the wrapper the schema is a bare `{}`, and nobody
    notices until a client reads it."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    schema = make_app(router).get("/openapi.json").json()
    content = schema["paths"]["/thing"]["get"]["responses"]["200"]["content"]
    ref = next(iter(content.values()))["schema"]["$ref"]
    assert ref.endswith("/Payload")
    assert set(schema["components"]["schemas"]["Payload"]["properties"]) == {"title", "body"}


def test_global_mode_applies_and_the_decorator_wins(make_app):
    router = APIRouter()

    @router.get("/default")
    @render("page.html")
    def default() -> Payload:
        return Payload(title="Hello", body="World")

    @router.get("/pinned")
    @render("page.html", mode="html")
    def pinned() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router, FjkitConfig(render_mode="json"))
    assert client.get("/default").json() == {"title": "Hello", "body": "World"}
    assert client.get("/pinned").text.startswith("<!doctype html>")


def test_auto_is_the_default(make_app):
    """The rule below only pays off if an app never has to state it."""
    assert FjkitConfig().render_mode == "auto"


def test_auto_gives_a_fragment_route_to_htmx_and_the_model_to_everyone_else(make_app):
    """The fragment endpoint is the app's API. htmx announces itself on every
    request it makes, so neither side is configured."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router)
    swap = client.get("/thing", headers={"HX-Request": "true"})
    assert swap.text == "<div id=fragment>World</div>"
    assert swap.headers["content-type"].startswith("text/html")

    api = client.get("/thing")
    assert api.json() == {"title": "Hello", "body": "World"}
    assert api.headers["content-type"].startswith("application/json")


def test_auto_gives_a_page_route_html_to_a_cold_navigation(make_app):
    """The request a page exists for (a typed URL, a reload, a bookmark, a
    crawler) carries no htmx header. Answering it with JSON would make the
    default unusable, so `auto` asks whether the route has a page rather than
    whether the caller is htmx."""
    router = APIRouter()

    @router.get("/named-page")
    @render("page.html")
    def named_page() -> Payload:
        return Payload(title="Hello", body="World")

    @router.get("/with-partial")
    @render("page.html", partial="_partial.html")
    def with_partial() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router)
    # Recognised by the filename: a fragment is `_*.html`, everything else is a
    # page — the convention every template already follows.
    assert client.get("/named-page").text.startswith("<!doctype html>")
    # `partial=` settles it outright: it exists because `template` is the page a
    # navigation gets.
    assert client.get("/with-partial").text.startswith("<!doctype html>")
    assert client.get("/with-partial", headers={"HX-Request": "true"}).text == "<div id=fragment>World</div>"


def test_auto_answers_a_boosted_request_in_html(make_app):
    """A boosted link is htmx doing an ordinary navigation, so it is excluded
    from the page-or-fragment decision. It is still a browser waiting for
    markup, so excluding it here too would hand JSON to a link click."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    response = make_app(router).get("/thing", headers={"HX-Request": "true", "HX-Boosted": "true"})
    assert response.text == "<div id=fragment>World</div>"


def test_a_route_can_still_pin_either_representation(make_app):
    """`auto` is a default, not a rule. A fragment that must never be published
    says `html`; a page only ever read by a client says `json`."""
    router = APIRouter()

    @router.get("/private")
    @render("_partial.html", mode="html")
    def private() -> Payload:
        return Payload(title="Hello", body="World")

    @router.get("/api")
    @render("page.html", mode="json")
    def api() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router)
    assert client.get("/private").text == "<div id=fragment>World</div>"
    assert client.get("/api", headers={"HX-Request": "true"}).json() == {"title": "Hello", "body": "World"}


def test_two_representations_on_one_url_vary_on_the_header(make_app):
    """Without `Vary` a cache may answer a navigation with the fragment it kept
    from a swap: a page with no shell, and no error anywhere."""
    router = APIRouter()

    @router.get("/page")
    @render("page.html", partial="_partial.html")
    def page() -> Payload:
        return Payload(title="Hello", body="World")

    @router.get("/fragment")
    @render("_partial.html")
    def fragment() -> Payload:
        return Payload(title="Hello", body="World")

    @router.get("/plain")
    @render("page.html")
    def plain() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router)
    assert client.get("/page").headers["vary"] == "HX-Request"
    assert client.get("/page", headers={"HX-Request": "true"}).headers["vary"] == "HX-Request"
    assert client.get("/fragment").headers["vary"] == "HX-Request"
    assert client.get("/fragment", headers={"HX-Request": "true"}).headers["vary"] == "HX-Request"
    # One representation for every caller: the header changes nothing, so the
    # reply need not tell a cache it might.
    assert "vary" not in client.get("/plain").headers


# --------------------------------------------------------------------------- #
# what the handler may return
# --------------------------------------------------------------------------- #


def test_a_mapping_is_the_context(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing():
        return {"title": "Hello", "body": "World"}

    assert "<title>Hello</title>" in make_app(router).get("/thing").text


def test_a_dataclass_is_spread_field_by_field(make_app):
    @dataclass
    class Plain:
        title: str
        body: str

    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing():
        return Plain(title="Hello", body="World")

    assert "<title>Hello</title>" in make_app(router).get("/thing").text


def test_nested_models_stay_objects_in_the_template(make_app):
    """Spread field by field, not dumped. A template calling a method on a
    nested model is the normal case, and `model_dump()` would flatten it to a
    dict two levels down."""

    class Inner(BaseModel):
        n: int

        @property
        def doubled(self) -> int:
            return self.n * 2

    class Outer(BaseModel):
        inner: Inner

    router = APIRouter()

    @router.get("/thing")
    @render("rows.html")
    def thing() -> Outer:
        return Outer(inner=Inner(n=21))

    client = make_app(router)
    client.app.state.templates.env.loader = DictLoader({"rows.html": "{{ inner.doubled }}"})
    assert client.get("/thing").text == "42"


def test_an_explicit_response_passes_through(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing():
        return RedirectResponse("/elsewhere", status_code=303)

    response = make_app(router).get("/thing", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/elsewhere"


def test_none_renders_an_empty_context(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("rows.html")
    def thing():
        return None

    client = make_app(router)
    client.app.state.templates.env.loader = DictLoader({"rows.html": "<p>static</p>"})
    assert client.get("/thing").text == "<p>static</p>"


def test_an_unusable_return_value_names_itself(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing():
        return ["not", "a", "context"]

    with pytest.raises(TypeError, match="got list"):
        make_app(router).get("/thing")


# --------------------------------------------------------------------------- #
# the htmx partial
# --------------------------------------------------------------------------- #


def test_partial_replaces_the_page_for_an_htmx_swap(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", partial="_partial.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    client = make_app(router)
    assert client.get("/thing").text.startswith("<!doctype html>")
    assert client.get("/thing", headers={"HX-Request": "true"}).text == "<div id=fragment>World</div>"


def test_a_boosted_request_still_gets_the_whole_page(make_app):
    """`hx-boost` is htmx doing an ordinary navigation. Swapping a fragment into
    it would leave the browser on a document with no shell."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", partial="_partial.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    headers = {"HX-Request": "true", "HX-Boosted": "true"}
    assert make_app(router).get("/thing", headers=headers).text.startswith("<!doctype html>")


def test_without_partial_the_header_changes_nothing(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    assert make_app(router).get("/thing", headers={"HX-Request": "true"}).text.startswith("<!doctype html>")


# --------------------------------------------------------------------------- #
# signature surgery
# --------------------------------------------------------------------------- #


def test_dependencies_and_query_params_survive_the_wrapper(make_app):
    """The wrapper's `__globals__` is fjkit's, so a string annotation left for
    FastAPI to evaluate raises `NameError` on names defined here."""

    def dependency() -> str:
        return "injected"

    Dep = Annotated[str, Depends(dependency)]

    router = APIRouter()

    @router.get("/thing/{n}")
    @render("page.html")
    def thing(n: int, dep: Dep, q: str = "default") -> Payload:
        return Payload(title=f"{n}-{q}", body=dep)

    response = make_app(router).get("/thing/7?q=given")
    assert "<title>7-given</title>" in response.text
    assert "<main>injected</main>" in response.text


def test_a_handler_may_still_declare_request_and_response(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing(request: Request, response: Response) -> Payload:
        response.headers["X-Seen"] = request.url.path
        return Payload(title="Hello", body="World")

    response = make_app(router).get("/thing")
    assert response.headers["X-Seen"] == "/thing"
    assert response.text.startswith("<!doctype html>")


def test_the_injected_parameters_are_not_query_parameters(make_app):
    """They are appended to the signature and so visible to FastAPI, but as
    `Request` and `Response`, never as something a client could send."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    schema = make_app(router).get("/openapi.json").json()
    assert "parameters" not in schema["paths"]["/thing"]["get"]


def test_a_sync_handler_keeps_a_sync_wrapper():
    """Starlette sends only `def` endpoints to the threadpool. An async wrapper
    around a sync handler would move every render onto the event loop."""

    @render("page.html")
    def sync_handler() -> Payload: ...

    @render("page.html")
    async def async_handler() -> Payload: ...

    assert not inspect.iscoroutinefunction(sync_handler)
    assert inspect.iscoroutinefunction(async_handler)


def test_an_async_handler_renders(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    async def thing() -> Payload:
        return Payload(title="Hello", body="World")

    assert "<title>Hello</title>" in make_app(router).get("/thing").text


def test_an_unresolvable_annotation_names_the_handler():
    with pytest.raises(TypeError, match="cannot resolve the annotations"):

        @render("page.html")
        def thing(x: NoSuchType) -> None:  # noqa: F821
            return None


# --------------------------------------------------------------------------- #
# status and headers
# --------------------------------------------------------------------------- #


def test_the_route_status_code_is_applied(make_app):
    """FastAPI applies `status_code=` only to replies it builds itself. The
    decorator builds this one, so it carries the code across."""
    router = APIRouter()

    @router.post("/thing", status_code=201)
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    assert make_app(router).post("/thing").status_code == 201


def test_headers_set_by_the_handler_are_carried_over(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing(response: Response) -> Payload:
        response.headers["HX-Trigger"] = "refresh"
        response.status_code = 202
        return Payload(title="Hello", body="World")

    got = make_app(router).get("/thing")
    assert got.status_code == 202
    assert got.headers["HX-Trigger"] == "refresh"


def test_httpexception_is_untouched(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        raise HTTPException(status_code=404, detail="nope")

    response = make_app(router).get("/thing")
    assert response.status_code == 404
    assert response.json() == {"detail": "nope"}


# --------------------------------------------------------------------------- #
# trigger
# --------------------------------------------------------------------------- #


def test_a_callable_trigger_reads_what_the_handler_returned(make_app):
    """Why the trigger takes a callable: the detail is per-request, the
    decorator is not."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", hx_trigger=lambda result: {"picked": {"id": result.title}})
    def thing() -> Payload:
        return Payload(title="7", body="b")

    got = make_app(router).get("/thing", headers={"HX-Request": "true"})
    assert json.loads(got.headers["HX-Trigger"]) == {"picked": {"id": "7"}}
    assert got.text == "<div id=fragment>b</div>", "the partial is still the body"


def test_a_trigger_returning_none_raises_nothing(make_app):
    """A route that broadcasts only sometimes must not send an empty header."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", hx_trigger=lambda result: {"picked": {}} if result.title else None)
    def thing(title: str = "") -> Payload:
        return Payload(title=title, body="b")

    client = make_app(router)
    assert "HX-Trigger" not in client.get("/thing").headers
    assert "HX-Trigger" in client.get("/thing", params={"title": "x"}).headers


def test_a_bare_name_stays_a_bare_name(make_app):
    """htmx accepts `HX-Trigger: refresh`, so a detail-free event need not pay
    for JSON."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", hx_trigger="refresh")
    def thing() -> Payload:
        return Payload(title="t", body="b")

    assert make_app(router).get("/thing").headers["HX-Trigger"] == "refresh"


def test_the_trigger_joins_a_header_the_handler_set(make_app):
    """Neither may drop the other; the failure only shows when both are in
    play."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", hx_trigger=lambda result: {"picked": {"id": 1}})
    def thing(response: Response) -> Payload:
        response.headers["HX-Trigger"] = "refresh"
        return Payload(title="t", body="b")

    events = json.loads(make_app(router).get("/thing").headers["HX-Trigger"])
    assert events == {"refresh": None, "picked": {"id": 1}}


def test_the_trigger_joins_a_queued_toast(make_app):
    """`messages` merges into whatever is already on the header, and a declared
    trigger is now one of those things."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", hx_trigger=lambda result: {"picked": {"id": 1}})
    def thing(request: Request) -> Payload:
        messages.add(request, "Saved", category="success")
        return Payload(title="t", body="b")

    events = json.loads(make_app(router).get("/thing", headers={"HX-Request": "true"}).headers["HX-Trigger"])
    assert events["picked"] == {"id": 1}
    assert events[messages.TOAST_EVENT]["messages"][0]["title"] == "Saved"


def test_a_json_reply_raises_nothing(make_app):
    """`HX-Trigger` is htmx's protocol, and no htmx is on this path.

    The same rule a toast follows. A route serving both representations declares
    the trigger once, and only the markup representation carries it; otherwise a
    JSON client receives a header it will never read.
    """
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", mode="json", hx_trigger=lambda result: {"picked": {"id": result.title}})
    def thing() -> Payload:
        return Payload(title="7", body="b")

    got = make_app(router).get("/thing")
    assert got.json()["title"] == "7"
    assert "HX-Trigger" not in got.headers


def test_a_response_returned_by_the_handler_is_still_untouched(make_app):
    """The escape hatch stays one: `@render` does not decorate a `Response`."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", hx_trigger=lambda result: {"picked": {"id": 1}})
    def thing() -> Payload:
        return Response(status_code=204)

    got = make_app(router).get("/thing")
    assert got.status_code == 204
    assert "HX-Trigger" not in got.headers


def test_a_trigger_reads_the_handler_s_own_parameters(make_app):
    """Why a callable and not a literal: the detail is a path parameter.

    Parameters are resolved by name out of what FastAPI handed the handler, so
    the event can be written where the route is declared. The decorator body
    cannot close over `task_id`, which does not exist until the request does.
    """
    router = APIRouter()

    @router.get("/thing/{task_id}")
    @render("page.html", hx_trigger=lambda task_id: {"picked": {"task_id": task_id}})
    def thing(task_id: int) -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing/7")
    assert json.loads(got.headers["HX-Trigger"]) == {"picked": {"task_id": 7}}


def test_a_trigger_may_ask_for_both(make_app):
    """`result` is available alongside the parameters, under that name."""
    router = APIRouter()

    @router.get("/thing/{task_id}")
    @render("page.html", hx_trigger=lambda task_id, result: {"picked": {"id": task_id, "was": result.title}})
    def thing(task_id: int) -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing/7")
    assert json.loads(got.headers["HX-Trigger"]) == {"picked": {"id": 7, "was": "t"}}


def test_a_trigger_declaring_kwargs_gets_everything(make_app):
    router = APIRouter()

    @router.get("/thing/{task_id}")
    @render("page.html", hx_trigger=lambda **kw: {"picked": sorted(kw)})
    def thing(task_id: int) -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing/7")
    assert json.loads(got.headers["HX-Trigger"]) == {"picked": ["result", "task_id"]}


def test_a_route_with_no_template_answers_with_headers_alone(make_app):
    """`template=None` is a route that broadcasts and renders nothing."""
    router = APIRouter()

    @router.get("/thing/{task_id}", status_code=204)
    @render(None, hx_trigger=lambda task_id: {"picked": {"task_id": task_id}})
    def thing(task_id: int) -> None:
        return None

    got = make_app(router).get("/thing/7")
    assert got.status_code == 204
    assert got.content == b""
    assert json.loads(got.headers["HX-Trigger"]) == {"picked": {"task_id": 7}}


def test_a_route_with_no_template_ignores_the_htmx_header(make_app):
    """No second representation exists to negotiate, so nothing varies on it."""
    router = APIRouter()

    @router.get("/thing", status_code=204)
    @render(None, hx_trigger="refresh")
    def thing() -> None:
        return None

    client = make_app(router)
    for headers in ({}, {"HX-Request": "true"}):
        got = client.get("/thing", headers=headers)
        assert got.status_code == 204
        assert got.headers["HX-Trigger"] == "refresh"
        assert "vary" not in got.headers


# --------------------------------------------------------------------------- #
# trigger, after the swap
# --------------------------------------------------------------------------- #


def test_after_swap_uses_its_own_header(make_app):
    """The two headers are two moments. Writing one into the other silently
    changes when a subscriber hears the event."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", hx_trigger_after_swap="task-selected")
    def thing() -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing", headers={"HX-Request": "true"})
    assert got.headers["HX-Trigger-After-Swap"] == "task-selected"
    assert "HX-Trigger" not in got.headers


def test_after_swap_takes_a_callable_like_the_other_one(make_app):
    """Same resolution rule, so a route learns no second convention."""
    router = APIRouter()

    @router.get("/thing/{task_id}")
    @render("page.html", hx_trigger_after_swap=lambda task_id: {"task-selected": {"task_id": task_id}})
    def thing(task_id: int) -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing/7")
    assert json.loads(got.headers["HX-Trigger-After-Swap"]) == {"task-selected": {"task_id": 7}}


def test_after_swap_returning_none_raises_nothing(make_app):
    router = APIRouter()

    @router.get("/thing")
    @render("page.html", hx_trigger_after_swap=lambda result: {"picked": {}} if result.title else None)
    def thing(title: str = "") -> Payload:
        return Payload(title=title, body="b")

    client = make_app(router)
    assert "HX-Trigger-After-Swap" not in client.get("/thing").headers
    assert "HX-Trigger-After-Swap" in client.get("/thing", params={"title": "x"}).headers


def test_one_route_may_raise_both_and_they_stay_apart(make_app):
    """Why both exist on one route: an event whose listeners read `event.detail`
    and one whose listeners read the page are different events, and a page can
    need both at the same moment."""
    router = APIRouter()

    @router.get("/thing/{task_id}")
    @render(
        "_partial.html",
        hx_trigger=lambda task_id: {"task-selected": {"task_id": task_id}},
        hx_trigger_after_swap="task-settled",
    )
    def thing(task_id: int) -> Payload:
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing/7", headers={"HX-Request": "true"})
    assert json.loads(got.headers["HX-Trigger"]) == {"task-selected": {"task_id": 7}}
    assert got.headers["HX-Trigger-After-Swap"] == "task-settled"


def test_a_queued_message_joins_hx_trigger_and_not_the_after_swap_one(make_app):
    """A toast is for the page it arrives on, so it rides the header the shell's
    listener reads. Merging it into the after-swap header would move every toast
    on a route that happens to use one."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html", hx_trigger_after_swap="task-selected")
    def thing(request: Request) -> Payload:
        messages.add(request, "Saved", category="success")
        return Payload(title="t", body="b")

    got = make_app(router).get("/thing", headers={"HX-Request": "true"})
    assert got.headers["HX-Trigger-After-Swap"] == "task-selected"
    assert "Saved" in got.headers["HX-Trigger"]


# --------------------------------------------------------------------------- #
# streaming
# --------------------------------------------------------------------------- #


def test_stream_produces_a_streaming_response(make_app):
    class Rows(BaseModel):
        rows: list[int]

    router = APIRouter()

    @router.get("/rows")
    @render("rows.html", stream=True)
    def rows() -> Rows:
        return Rows(rows=list(range(50)))

    with make_app(router).stream("GET", "/rows") as response:
        # A streamed reply cannot know its length up front, so the missing
        # header is the observable proof that nothing was buffered server-side.
        assert "content-length" not in response.headers
        body = response.read().decode()
    assert body.count("<p>") == 50


def test_stream_in_json_mode_still_returns_json(make_app):
    class Rows(BaseModel):
        rows: list[int]

    router = APIRouter()

    @router.get("/rows")
    @render("rows.html", stream=True, mode="json")
    def rows() -> Rows:
        return Rows(rows=[1, 2, 3])

    assert make_app(router).get("/rows").json() == {"rows": [1, 2, 3]}


# --------------------------------------------------------------------------- #
# wiring
# --------------------------------------------------------------------------- #


def test_the_kit_imports_nothing_outside_its_declared_dependencies():
    """CHARTER §7 budgets fjkit's runtime dependencies and §11.2 makes each one
    a human decision. This test makes the budget real: an import nobody signed
    off on fails here rather than turning up in a wheel."""
    from pathlib import Path

    import fjkit

    #: `starlette` and `markupsafe` are `fastapi` and `jinja2` seen from the
    #: inside: FastAPI is Starlette's routing, and `markupsafe.Markup` is the
    #: type Jinja2's autoescaping is built on. Jinja 3 stopped re-exporting it,
    #: so `ui/icon` has nowhere else to get it.
    #:
    #: `pydantic` was added in 0.3, deliberately (2026-08-23). It used to look
    #: like it belonged here and did not, and `fjkit/charts/` held a path
    #: exemption to keep it out; both are gone. `fastapi` requires
    #: `pydantic>=2.9.0` unconditionally — no extra marker, first line of
    #: `importlib.metadata.requires("fastapi")` after starlette — so it is
    #: already installed and already imported by the time `import fjkit`
    #: returns. Install cost and import cost are both zero, and an exemption
    #: saying "this directory is excused" is worth less than a list saying what
    #: the kit depends on.
    declared = {"fastapi", "starlette", "jinja2", "markupsafe", "pydantic", "fjkit"}

    package_root = Path(fjkit.__file__).parent
    offenders: list[str] = []
    for path in package_root.rglob("*.py"):
        for module_root in _imported_roots(path):
            # Anything in the stdlib is free; a third-party root is not.
            if module_root not in declared and module_root not in sys.stdlib_module_names:
                offenders.append(f"{path.relative_to(package_root)}: {module_root}")
    assert not offenders, f"undeclared runtime dependency: {offenders}"


def test_no_part_of_the_kit_imports_a_charting_library():
    """The half of the old charts exemption that still earns its keep.

    `fjkit.charts` ships Plotly's JavaScript (CHARTER §7 whitelists the bundle)
    but never the Python library: `figure_of` is duck-typed on
    `to_plotly_json()`. An `import plotly` anywhere in the package would quietly
    make the 20 MB `plotly.py` a runtime dependency of every install, and the
    only visible symptom would be a slower `uv sync`."""
    from pathlib import Path

    import fjkit

    banned = {"plotly", "pandas", "numpy", "matplotlib"}
    package_root = Path(fjkit.__file__).parent
    offenders = [
        f"{path.relative_to(package_root)}: {module_root}"
        for path in package_root.rglob("*.py")
        for module_root in _imported_roots(path)
        if module_root in banned
    ]
    assert not offenders, f"a charting library must not be imported by the kit: {offenders}"


def _imported_roots(path):
    """Yield every top-level package name imported anywhere in one module."""
    import ast

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_a_missing_templates_state_says_what_to_do():
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    app = FastAPI()
    app.include_router(router)
    with pytest.raises(RuntimeError, match="app.state.templates"), TestClient(app) as client:
        client.get("/thing")
