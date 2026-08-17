"""Contracts for the `@render` decorator.

The decorator sits between FastAPI and the handler, so most of what can go
wrong is invisible in a normal request: a signature FastAPI cannot solve, a
sync handler quietly promoted to async, a header set by the handler and then
dropped. Each of those is a test here.
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, Templates, render
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
    """An app whose Environment serves the templates above and nothing else."""

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
    """The point of the annotation: it documents the JSON without a second
    declaration. If FastAPI cannot see through the wrapper, the schema is a
    bare `{}` and nobody notices until a client reads it."""
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
    """The whole point of the rule below is that an app states it nowhere."""
    assert FjkitConfig().render_mode == "auto"


def test_auto_gives_a_fragment_route_to_htmx_and_the_model_to_everyone_else(make_app):
    """The fragment endpoint is the app's API. htmx already announces itself on
    every request it makes, so nothing is configured on either side."""
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
    """The request a page exists for — someone typing the URL, a reload, a
    bookmark, a crawler — carries no htmx header at all. If that answered with
    JSON the default would be unusable, so `auto` asks whether the route has a
    page rather than whether the caller is htmx."""
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
    # page. It is the convention every template already follows.
    assert client.get("/named-page").text.startswith("<!doctype html>")
    # And `partial=` settles it outright — it exists because `template` is the
    # page a navigation gets.
    assert client.get("/with-partial").text.startswith("<!doctype html>")
    assert client.get("/with-partial", headers={"HX-Request": "true"}).text == "<div id=fragment>World</div>"


def test_auto_answers_a_boosted_request_in_html(make_app):
    """A boosted link is htmx doing an ordinary navigation. It is excluded from
    the page-or-fragment decision on purpose — but it is still a browser waiting
    for markup, so excluding it here too would hand JSON to a link click."""
    router = APIRouter()

    @router.get("/thing")
    @render("_partial.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    response = make_app(router).get("/thing", headers={"HX-Request": "true", "HX-Boosted": "true"})
    assert response.text == "<div id=fragment>World</div>"


def test_a_route_can_still_pin_either_representation(make_app):
    """`auto` is a default, not a rule. A fragment that must never be published
    says `html`; a page that is only ever read by a client says `json`."""
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
    """Without this a cache is free to answer a navigation with the fragment it
    kept from a swap — a page with no shell, and no error anywhere."""
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
    # One representation for every caller — the header changes nothing, so the
    # reply does not have to tell a cache it might.
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
    nested model is the normal case, and `model_dump()` would have flattened it
    to a dict two levels down."""

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
    """hx-boost is htmx doing an ordinary navigation. Swapping a fragment into
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
    """The wrapper's __globals__ is fjkit's, so a string annotation left for
    FastAPI to evaluate would raise NameError on names defined here."""

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
    """They are appended to the signature, so they are visible to FastAPI —
    but as `Request`/`Response`, never as something a client could send."""
    router = APIRouter()

    @router.get("/thing")
    @render("page.html")
    def thing() -> Payload:
        return Payload(title="Hello", body="World")

    schema = make_app(router).get("/openapi.json").json()
    assert "parameters" not in schema["paths"]["/thing"]["get"]


def test_a_sync_handler_keeps_a_sync_wrapper():
    """Starlette only sends `def` endpoints to the threadpool. An async wrapper
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
    decorator builds this one, so it has to carry it across."""
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
        # A streamed reply cannot know its length up front; the missing header
        # is the observable proof that nothing was buffered server-side.
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


def test_the_kit_still_imports_nothing_but_fastapi_and_jinja2():
    """CHARTER §7 budgets fjkit at two runtime dependencies, and §11.2 makes a
    third a human decision. `@render` handles pydantic models, so the tempting
    line is `from pydantic import BaseModel` — which is exactly what would turn
    a package FastAPI already installs into a dependency fjkit declares."""
    import ast
    from pathlib import Path

    import fjkit

    #: `starlette` and `markupsafe` are the declared two seen from the inside:
    #: FastAPI *is* Starlette's routing, and `markupsafe.Markup` is the type
    #: Jinja2's autoescaping is built on — Jinja 3 stopped re-exporting it, so
    #: `ui/icon` has nowhere else to get it. Pydantic is the one that looks like
    #: it belongs on this list and does not: it is a separate framework whose
    #: API fjkit would be putting in front of its users.
    declared = {"fastapi", "starlette", "jinja2", "markupsafe", "fjkit"}
    offenders: list[str] = []
    for path in Path(fjkit.__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            else:
                continue
            for root in roots:
                # Anything in the stdlib is free; a third-party root is not.
                if root not in declared and root not in sys.stdlib_module_names:
                    offenders.append(f"{path.name}: {root}")
    assert not offenders, f"undeclared runtime dependency: {offenders}"


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
