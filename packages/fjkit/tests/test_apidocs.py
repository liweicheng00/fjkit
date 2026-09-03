"""The API console: what it reads, what it mounts, and whose session it calls with."""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import textwrap
import warnings
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal

import pytest
from fastapi import Body, Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, PluginWarning, mount_fjkit, render
from fjkit.apidocs import ApiDocsPlugin, FlowError, HeaderFlow, NoFlow, SessionFlow
from fjkit.apidocs import spec as specmod
from fjkit.apidocs.plugin import DETAIL_ID, RESULT_ID, SESSION_ID, TEMPLATE_DIR
from fjkit.auth import AuthPlugin, CookieSpec, NoCsrf
from fjkit.auth.types import Session
from fjkit.cli.vocabulary import component_classes, emitted_classes
from fjkit.config import STATIC_DIR
from pydantic import BaseModel
from pydantic import Field as PydanticField

SECRET = "unit-test-secret-value-32-chars!!"


class Task(BaseModel):
    id: int
    title: str
    status: Literal["todo", "doing", "done"] = "todo"


#: Module level, not inside the test that uses them. Pydantic resolves a model's
#: forward references against the module namespace, and one declared in a
#: function body is not in it: the schema build then fails with a rebuild error
#: that says nothing about where the model lives.
class Owner(BaseModel):
    name: str


class Job(BaseModel):
    owner: Owner


class Bounded(BaseModel):
    title: Annotated[str, PydanticField(min_length=1, max_length=64)]


class Colour(StrEnum):
    RED = "red"
    BLUE = "blue"


class PasswordSource:
    """A `TokenSource` of the shape only a Python object can express, which is
    why this plugin exists rather than an Authorize dialog."""

    async def exchange(self, credentials):
        if credentials.get("password") != "hunter2":
            raise ValueError("that password is not it")
        return Session(claims={"sub": credentials["username"], "scope": ["read", "write"]})


def build_app(*plugins, **kwargs):
    """Build a small but realistic API with the plugins under test on it."""
    kwargs.setdefault("docs_url", None)
    kwargs.setdefault("redoc_url", None)
    app = FastAPI(title="Board API", version="9.9", **kwargs)

    @app.get("/tasks", tags=["tasks"], summary="List tasks")
    def list_tasks(status: Literal["todo", "doing", "done"] | None = None, limit: int = 20) -> list[Task]:
        return [Task(id=1, title="write the console")]

    @app.post("/tasks", tags=["tasks"], summary="Create a task")
    def create_task(task: Task) -> Task:
        return task

    @app.get("/tasks/{task_id}", tags=["tasks"], summary="One task")
    def get_task(task_id: int) -> Task:
        return Task(id=task_id, title="a task")

    @app.get("/whoami", tags=["session"], summary="Who am I")
    def whoami(request: Request) -> dict:
        session = getattr(request.state, "auth", None)
        return {"sub": session.claims["sub"] if session else None}

    with warnings.catch_warnings():
        # `MemoryStore` under a non-reloading config, and `NoCsrf`. Both are
        # deliberate here, and both warnings are the plugin doing its job.
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=tuple(plugins), auto_reload=False))
    return app


def auth_plugin(**kwargs):
    return AuthPlugin(
        secret=SECRET,
        source=PasswordSource(),
        csrf=NoCsrf(),
        # TestClient speaks http, and a browser will not send a Secure cookie
        # over it, so a secure cookie here would test nothing but itself.
        cookie=CookieSpec(secure=False),
        **kwargs,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(build_app(auth_plugin(), ApiDocsPlugin()))


# ------------------------------------------------------------------- reading


def test_the_document_becomes_groups_and_operations():
    document = specmod.build(build_app().openapi())

    assert [g.name for g in document.groups] == ["session", "tasks"]
    tasks = next(g for g in document.groups if g.name == "tasks")
    assert {(o.method, o.path) for o in tasks.operations} == {
        ("GET", "/tasks"),
        ("POST", "/tasks"),
        ("GET", "/tasks/{task_id}"),
    }


def test_parameters_carry_enough_to_render_a_field():
    document = specmod.build(build_app().openapi())
    listing = next(o for o in document.index.values() if o.path == "/tasks" and o.method == "GET")

    status = next(p for p in listing.params if p.name == "status")
    assert status.location == "query"
    assert status.choices == ("todo", "doing", "done")
    assert status.control == "select"
    assert status.field_name == "p.query.status"

    limit = next(p for p in listing.params if p.name == "limit")
    assert limit.control == "number"
    assert limit.default == "20"  # the route's default, so the box starts usable


def test_a_boolean_parameter_is_a_three_state_select_not_a_checkbox():
    # Absent, true and false are three different requests; a checkbox sends two.
    app = FastAPI()

    @app.get("/x")
    def x(verbose: bool = False) -> dict:
        return {}

    param = next(iter(specmod.build(app.openapi()).index.values())).params[0]
    assert param.control == "select"
    assert param.choices == ("true", "false")


def test_a_ref_does_not_swallow_the_keywords_written_beside_it():
    """OpenAPI 3.1 allows `default` next to `$ref`, and FastAPI writes exactly
    that for `priority: Priority = Priority.NORMAL`. Resolving the ref and
    discarding its siblings loses the default: the select renders with nothing
    chosen, and the only symptom is a console that starts one step behind."""
    document = specmod.build(
        {
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/x": {
                    "get": {
                        "operationId": "x",
                        "parameters": [
                            {
                                "name": "priority",
                                "in": "query",
                                "schema": {"$ref": "#/components/schemas/Priority", "default": "normal"},
                            }
                        ],
                        "responses": {},
                    }
                }
            },
            "components": {"schemas": {"Priority": {"type": "string", "enum": ["low", "normal", "high"]}}},
        }
    )
    param = document.index["x"].params[0]
    assert param.choices == ("low", "normal", "high")
    assert param.default == "normal"


def test_a_form_body_becomes_fields_rather_than_a_text_box():
    # The body shape every htmx form in a fjkit app posts.
    app = FastAPI()

    @app.post("/things")
    def make(title: Annotated[str, Form()], size: Annotated[int, Form()] = 1) -> dict:
        return {}

    operation = next(iter(specmod.build(app.openapi()).index.values()))
    assert operation.body_media == specmod.FORM_MEDIA
    assert not operation.has_raw_body
    assert [(f.name, f.required, f.control) for f in operation.body_fields] == [
        ("title", True, "text"),
        ("size", False, "number"),
    ]
    assert operation.body_fields[0].field_name == "p.form.title"


def test_a_request_body_becomes_an_editable_example():
    document = specmod.build(build_app().openapi())
    create = next(o for o in document.index.values() if o.method == "POST")

    assert create.has_body
    assert create.body_media == "application/json"
    # Resolved through `$ref` into components, with the model's own default.
    assert '"title"' in create.body_example
    assert '"status": "todo"' in create.body_example


def test_a_self_referential_schema_terminates():
    # A tree node or a comment with replies: an ordinary model, and an infinite
    # example generator if nothing bounds the recursion.
    document = specmod.build(
        {
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/tree": {
                    "post": {
                        "operationId": "tree",
                        "requestBody": {
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}
                        },
                        "responses": {},
                    }
                }
            },
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "child": {"$ref": "#/components/schemas/Node"},
                        },
                    }
                }
            },
        }
    )
    assert '"name"' in document.index["tree"].body_example  # and it returned at all


def test_operation_ids_are_url_safe_and_never_collide():
    document = specmod.build(
        {
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/a b": {"get": {"responses": {}}},
                "/a/b": {"get": {"responses": {}}},
            },
        }
    )
    ids = list(document.index)
    assert len(ids) == 2
    assert len(set(ids)) == 2
    for value in ids:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", value), value


def test_the_console_is_never_in_its_own_index():
    document = specmod.build(
        {"info": {}, "paths": {"/api-docs/try/x": {"post": {"responses": {}}}, "/ok": {"get": {"responses": {}}}}},
        skip_prefix="/api-docs",
    )
    assert [o.path for o in document.index.values()] == ["/ok"]


# ------------------------------------------------------------------ mounting


def test_registering_the_plugin_is_the_whole_setup(client: TestClient):
    # No route written, no template named, no static file mounted by the app.
    page = client.get("/api-docs")
    assert page.status_code == 200
    assert "Board API" in page.text
    assert SESSION_ID in page.text
    assert DETAIL_ID in page.text


def test_its_own_routes_stay_out_of_the_schema(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/api-docs")]


def test_an_operation_answers_a_navigation_with_the_page_and_htmx_with_the_panel(client: TestClient):
    url = "/api-docs/op/list_tasks_tasks_get"

    page = client.get(url)
    assert page.status_code == 200
    assert page.text.lstrip().lower().startswith("<!doctype")
    assert "Try it" in page.text

    panel = client.get(url, headers={"HX-Request": "true"})
    assert "<!doctype" not in panel.text.lower()
    assert panel.text.lstrip().startswith(f'<div id="{DETAIL_ID}"')
    # One URL, two bodies: a shared cache has to be told.
    assert "HX-Request" in panel.headers["vary"]


def test_a_stale_operation_link_lands_on_the_index_rather_than_an_error(client: TestClient):
    gone = client.get("/api-docs/op/renamed-last-week")
    assert gone.status_code == 404
    assert "Board API" in gone.text  # the list is still there to click


def test_a_taken_url_is_reported_at_startup_not_discovered_by_clicking():
    # Starlette matches the first route that fits, so a docs page mounted under a
    # path FastAPI already claimed would never render and never say why.
    app = FastAPI(docs_url="/docs")
    with pytest.warns(PluginWarning, match="already routed"):
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(url="/docs"),), auto_reload=False))


def test_try_it_off_removes_the_route_and_documents_the_parameters_instead():
    client = TestClient(build_app(ApiDocsPlugin(try_it=False)))

    page = client.get("/api-docs/op/list_tasks_tasks_get")
    assert "Try it" not in page.text
    assert "Parameters" in page.text
    assert client.post("/api-docs/try/list_tasks_tasks_get").status_code == 404


def test_dependencies_are_how_the_page_is_gated():
    def refuse() -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=403)

    client = TestClient(build_app(ApiDocsPlugin(dependencies=[Depends(refuse)])))
    assert client.get("/api-docs").status_code == 403


# ------------------------------------------------------------------- the call


def test_a_call_carries_the_caller_s_own_session(client: TestClient):
    anonymous = client.post("/api-docs/try/whoami_whoami_get")
    assert "&#34;sub&#34;: null" in anonymous.text

    client.post("/api-docs/auth", data={"username": "ada", "password": "hunter2"})

    named = client.post("/api-docs/try/whoami_whoami_get")
    # The cookie the console forwarded went through the session middleware, so
    # the route saw a real session, which is what Swagger UI cannot do.
    assert "&#34;sub&#34;: &#34;ada&#34;" in named.text


def test_parameters_land_where_the_document_said_they_would(client: TestClient):
    result = client.post("/api-docs/try/get_task_tasks__task_id__get", data={"p.path.task_id": "42"})
    assert "&#34;id&#34;: 42" in result.text

    listing = client.post("/api-docs/try/list_tasks_tasks_get", data={"p.query.limit": "3"})
    assert "/tasks?limit=3" in listing.text


def test_a_blank_optional_parameter_is_omitted_rather_than_sent_empty(client: TestClient):
    # `?status=` and no `status` are different requests, and `?status=` 422s.
    result = client.post(
        "/api-docs/try/list_tasks_tasks_get",
        data={"p.query.status": "", "p.query.limit": ""},
    )
    assert "200" in result.text
    assert "status=" not in result.text


def test_a_body_is_posted_with_the_media_type_the_document_named(client: TestClient):
    result = client.post(
        "/api-docs/try/create_task_tasks_post",
        data={"body": '{"id": 7, "title": "x"}'},
    )
    assert "&#34;id&#34;: 7" in result.text
    assert "application/json" in result.text


def test_the_result_reports_a_refusal_rather_than_hiding_it(client: TestClient):
    result = client.post("/api-docs/try/get_task_tasks__task_id__get", data={"p.path.task_id": "not-a-number"})
    assert "422" in result.text
    assert RESULT_ID in result.text


def test_the_console_asks_for_the_model_and_a_route_mode_still_overrules_it(tmp_path):
    """Two halves of one rule, so they cannot drift apart.

    Under `"auto"` a page route hands a page to anyone who is not htmx, because
    the route's shape decides `serves_a_page`. The console is a caller rather
    than a shape, and it says so through the ASGI scope, which only something
    already inside the process can write. A route declaring `mode="html"` has
    said it has no data form, and keeps saying it.
    """
    (tmp_path / "page.html").write_text("<p>page {{ title }}</p>", encoding="utf-8")
    (tmp_path / "_frag.html").write_text("<p>frag {{ title }}</p>", encoding="utf-8")

    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/board", tags=["b"])
    @render("page.html", partial="_frag.html")
    def board() -> Task:
        return Task(id=1, title="from the model")

    @app.get("/only-html", tags=["b"])
    @render("page.html", mode="html")
    def only_html() -> Task:
        return Task(id=2, title="markup only")

    mount_fjkit(app, FjkitConfig(template_dir=tmp_path, plugins=(ApiDocsPlugin(),), auto_reload=False))
    client = TestClient(app)

    auto = client.post("/api-docs/try/board_board_get")
    assert "&#34;title&#34;: &#34;from the model&#34;" in auto.text
    assert "application/json" in auto.text
    assert "&lt;p&gt;page" not in auto.text

    declared = client.post("/api-docs/try/only_html_only_html_get")
    assert "&lt;p&gt;page markup only&lt;/p&gt;" in declared.text

    # The browser is unaffected: the scope key is unreachable from outside.
    assert client.get("/board").text == "<p>page from the model</p>"
    # Reachable only by hand-posting, but it prevents a stack overflow rather
    # than a wrong answer, so it is checked directly.
    from fjkit.apidocs import console

    app = client.app
    request = Request({"type": "http", "method": "POST", "path": "/x", "headers": [], "app": app})
    with pytest.raises(console.RecursionRefused):
        import asyncio

        asyncio.run(console.call(request, method="GET", path="/api-docs/op/x", forbidden_prefix="/api-docs"))


def test_the_curl_snippet_never_carries_the_credential(client: TestClient):
    client.post("/api-docs/auth", data={"username": "ada", "password": "hunter2"})
    cookie = next(iter(client.cookies.values()))

    result = client.post("/api-docs/try/list_tasks_tasks_get")
    assert "curl" in result.text
    assert cookie not in result.text


# --------------------------------------------------------------------- flows


def test_an_auth_plugin_in_the_same_config_is_found_without_being_passed():
    auth = auth_plugin()
    docs = ApiDocsPlugin()
    build_app(auth, docs)

    assert isinstance(docs.flow, SessionFlow)
    assert docs.flow.auth is auth


def test_an_app_with_no_sessions_still_gets_a_page():
    docs = ApiDocsPlugin()
    client = TestClient(build_app(docs))

    assert isinstance(docs.flow, NoFlow)
    assert client.get("/api-docs").status_code == 200


def test_an_app_with_no_auth_never_imports_the_auth_module():
    """The auto-detection must cost nothing to an app that has no sessions.

    An `AuthPlugin` instance cannot be in `config.plugins` unless its class was
    imported, so `_resolve_flow` treats a missing module as proof the search is
    empty. Run in a subprocess because this test module imports `fjkit.auth` at
    the top, which would make the check pass for the wrong reason.
    """
    source = textwrap.dedent(
        """
        import sys
        from fastapi import FastAPI
        from fjkit import FjkitConfig, mount_fjkit
        from fjkit.apidocs import ApiDocsPlugin

        app = FastAPI()
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

        leaked = [m for m in sys.modules if m.startswith("fjkit.auth")]
        assert not leaked, leaked
        assert app.state.templates is not None
        """
    )
    done = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_a_named_flow_wins_over_the_one_that_would_be_found():
    auth = auth_plugin()
    docs = ApiDocsPlugin(flow=NoFlow())
    build_app(auth, docs)

    assert isinstance(docs.flow, NoFlow)


def test_signing_in_runs_the_app_s_own_token_source(client: TestClient):
    panel = client.post("/api-docs/auth", data={"username": "ada", "password": "hunter2"})

    assert "Signed in as ada" in panel.text
    assert "read write" in panel.text  # the claims the source produced
    assert client.cookies.get("fjkit_session")


def test_a_refusal_from_the_token_source_reaches_the_panel(client: TestClient):
    panel = client.post("/api-docs/auth", data={"username": "ada", "password": "wrong"})

    assert "that password is not it" in panel.text
    assert "Not signed in" in panel.text
    assert not client.cookies.get("fjkit_session")


def test_a_missing_field_is_refused_before_the_source_is_troubled(client: TestClient):
    panel = client.post("/api-docs/auth", data={"username": "ada"})
    assert "Password required" in panel.text


def test_signing_out_drops_the_session(client: TestClient):
    client.post("/api-docs/auth", data={"username": "ada", "password": "hunter2"})
    panel = client.post("/api-docs/auth", data={"action": "sign_out"})

    assert "Not signed in" in panel.text
    assert client.post("/api-docs/try/whoami_whoami_get").text.count("&#34;sub&#34;: null") == 1


def test_a_header_flow_holds_the_token_where_the_page_cannot_read_it():
    docs = ApiDocsPlugin(flow=HeaderFlow(secret=SECRET, secure=False))
    client = TestClient(build_app(docs))

    saved = client.post("/api-docs/auth", data={"token": "s3cr3t-token-value"})
    assert "Token held" in saved.text
    # Masked on the page; the cookie is HttpOnly and scoped to the console.
    assert "s3cr3t-token-value" not in saved.text
    assert "s3cr" in saved.text
    cookie = next(h for h in saved.headers.get_list("set-cookie") if "fjkit_apidocs_token" in h)
    assert "HttpOnly" in cookie
    assert "Path=/api-docs" in cookie


def test_a_header_flow_puts_the_token_on_every_call():
    """Also the regression test for header casing. ASGI says header names in a
    scope are lowercase, and Starlette takes that literally: it lowercases the
    name you ask for and compares it to the raw bytes. So `Authorization`
    spelled with a capital A rides on the wire and is invisible to
    `request.headers["authorization"]`, with nothing anywhere saying so."""
    docs = ApiDocsPlugin(flow=HeaderFlow(secret=SECRET, secure=False))
    app = build_app(docs)

    @app.get("/echo-auth", tags=["debug"])
    def echo(request: Request) -> dict:
        return {"seen": request.headers.get("authorization")}

    app.openapi_schema = None  # the route was added after the first render
    client = TestClient(app)
    client.post("/api-docs/auth", data={"token": "abc123"})

    result = client.post("/api-docs/try/echo_echo_auth_get")
    assert "Bearer abc123" in result.text


def test_a_forged_token_cookie_is_not_a_token():
    flow = HeaderFlow(secret=SECRET, secure=False)
    docs = ApiDocsPlugin(flow=flow)
    client = TestClient(build_app(docs))

    client.cookies.set("fjkit_apidocs_token", "deadbeef.notasignature")
    panel = client.get("/api-docs")
    assert "No token held" in panel.text


def test_a_flow_error_is_the_way_to_refuse_without_leaking():
    class Picky:
        name = "picky"
        label = "Picky"

        def state(self, request):
            from fjkit.apidocs import FlowState

            return FlowState(signed_in=False, headline="Nope", fields=())

        async def sign_in(self, request, response, values):
            raise FlowError("come back later")

        async def sign_out(self, request, response):
            return None

        def headers(self, request):
            return {}

    client = TestClient(build_app(ApiDocsPlugin(flow=Picky())))
    assert "come back later" in client.post("/api-docs/auth", data={}).text


# ------------------------------------------------- what Swagger UI also shows
#
# The plugin exists for the half Swagger cannot do: a sign-in that is the app's
# own code, and a call that carries an HttpOnly cookie. That only argues for
# using it if the other half is all there — the schemas, the filter, the
# per-status examples, the padlock, the uploads. A console that wins on
# authentication and loses on everything else is not a replacement.


def build_rich_app(*plugins):
    """Build an app exercising the document features a small one never reaches."""
    app = FastAPI(
        title="Rich API",
        version="2.0",
        docs_url=None,
        redoc_url=None,
        servers=[{"url": "https://api.example.com", "description": "production"}],
        contact={"name": "The team", "email": "team@example.com"},
        license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        terms_of_service="https://example.com/terms",
    )

    @app.get(
        "/tasks",
        tags=["tasks"],
        summary="List tasks",
        responses={404: {"description": "no board", "headers": {"X-Trace": {"description": "trace id"}}}},
    )
    def list_tasks(tag: Annotated[list[str], Query()] = ()) -> list[Task]:
        return []

    @app.post("/upload", tags=["files"], summary="Upload one")
    async def upload(note: Annotated[str, Form()], attachment: Annotated[UploadFile, File()]) -> dict:
        return {"name": attachment.filename, "size": len(await attachment.read()), "note": note}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=tuple(plugins), auto_reload=False))
    return app


@pytest.fixture
def rich() -> TestClient:
    return TestClient(build_rich_app(ApiDocsPlugin()))


def test_the_types_the_api_exchanges_are_documented_too():
    """`components.schemas` is half the contract, and every generated client is
    built from it. An API reference that renders the paths and not the payloads
    has documented the easy half."""
    document = specmod.build(build_app().openapi())

    task = document.by_name["Task"]
    assert task.kind == "object"
    assert [f.name for f in task.fields] == ["id", "title", "status"]
    assert next(f for f in task.fields if f.name == "id").required
    assert not next(f for f in task.fields if f.name == "status").required
    # The reverse index: which endpoints carry this type.
    assert set(task.used_by) == {"list_tasks_tasks_get", "create_task_tasks_post", "get_task_tasks__task_id__get"}
    assert document.model_index[task.slug] is task


def test_a_schema_page_renders_and_links_back_to_the_operations(client: TestClient):
    slug = specmod.build(client.app.openapi()).by_name["Task"].slug
    page = client.get(f"/api-docs/schema/{slug}")

    assert page.status_code == 200
    assert "Task" in page.text
    assert "Exchanged by" in page.text
    assert "/api-docs/op/list_tasks_tasks_get" in page.text
    # Same panel an operation uses, so one sidebar swaps either into it.
    assert DETAIL_ID in page.text


def test_a_stale_schema_link_lands_on_the_index_rather_than_an_error(client: TestClient):
    reply = client.get("/api-docs/schema/renamed-last-week")
    assert reply.status_code == 404
    assert DETAIL_ID in reply.text  # the page, with the list still on it


def test_a_field_that_is_a_model_is_a_link_and_not_a_nested_table():
    """One level deep by design: `Task` holding an `owner: User` holding an
    `avatar: Image` is three tables before anyone has scrolled."""
    app = FastAPI()

    @app.get("/j")
    def j() -> Job:
        return Job(owner=Owner(name="ada"))

    document = specmod.build(app.openapi())
    row = document.by_name["Job"].fields[0]
    assert row.ref == "Owner"
    assert document.by_name["Owner"].slug  # so the template has somewhere to point


def test_the_bounds_a_422_would_otherwise_announce_are_on_the_field():
    app = FastAPI()

    @app.post("/b")
    def b(body: Bounded) -> Bounded:
        return body

    field = specmod.build(app.openapi()).by_name["Bounded"].fields[0]
    assert "≥ 1 chars" in field.constraints
    assert "≤ 64 chars" in field.constraints


def test_the_filter_narrows_the_list_and_says_so_when_nothing_matches(rich: TestClient):
    """Swagger has a filter box for the same reason: an app with two hundred
    routes has a sidebar nobody scrolls."""
    narrowed = rich.get("/api-docs/nav?q=upload")
    assert "Upload one" in narrowed.text
    assert "List tasks" not in narrowed.text

    assert "Nothing matches" in rich.get("/api-docs/nav?q=zzzz").text
    # The same `?q=` works on the page itself, so a filter is bookmarkable.
    assert "List tasks" not in rich.get("/api-docs?q=upload").text


def test_the_filter_matches_the_operation_id_and_the_tag_not_only_the_summary(rich: TestClient):
    # The name in the generated client, and the group: both are things people
    # type into a filter box, and neither is in the visible label.
    assert "Upload one" in rich.get("/api-docs/nav?q=upload_upload_post").text
    assert "Upload one" in rich.get("/api-docs/nav?q=files").text


def test_a_panel_swap_brings_the_sidebar_with_it_so_the_highlight_is_not_stale(rich: TestClient):
    """Clicking an operation replaces only the detail panel. Without an
    out-of-band nav the highlight stays on whatever was open three clicks ago:
    correct on a cold load and wrong for the rest of the session."""
    swap = rich.get("/api-docs/op/upload_upload_post", headers={"hx-request": "true"})

    assert 'hx-swap-oob="true"' in swap.text
    assert 'aria-current="page"' in swap.text
    # Never on a full page, where the sidebar renders itself and a second copy
    # would be a duplicate id.
    assert "hx-swap-oob" not in rich.get("/api-docs/op/upload_upload_post").text


def test_the_filter_survives_following_a_result(rich: TestClient):
    swap = rich.get("/api-docs/op/upload_upload_post?q=upload", headers={"hx-request": "true"})
    assert "List tasks" not in swap.text  # the re-rendered nav is still filtered


def test_every_documented_status_gets_its_own_example_not_just_the_first(rich: TestClient):
    """A page that documents four statuses and shows one example leaves the
    other three as shapes you discover from a failing call."""
    page = rich.get("/api-docs/op/list_tasks_tasks_get")

    assert "Example 200 response" in page.text
    assert "Example 422 response" in page.text


def test_a_documented_response_header_is_shown(rich: TestClient):
    """This is usually the only place a `Location` or a `Retry-After` is written
    down, and a client that has to follow one cannot guess it."""
    page = rich.get("/api-docs/op/list_tasks_tasks_get")
    assert "X-Trace" in page.text
    assert "trace id" in page.text


def test_the_document_s_masthead_is_rendered_rather_than_dropped(rich: TestClient):
    """Contact, licence, terms and servers are in the document because somebody
    meant them to be read. A reference that drops them tells the reader less
    than the file it was generated from."""
    page = rich.get("/api-docs")

    assert "team@example.com" in page.text
    assert "MIT" in page.text
    assert "https://example.com/terms" in page.text
    assert "https://api.example.com" in page.text


def test_every_worked_example_the_author_wrote_is_shown_not_only_the_first():
    """`openapi_examples=` is somebody writing out the minimal case, the full
    case and the one that fails. Swagger gives them a dropdown; showing the
    first and dropping the rest discards most of what was written."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.post("/notes")
    def write(
        note: Annotated[
            Task,
            Body(
                openapi_examples={
                    "minimal": {"summary": "The short one", "value": {"id": 1, "title": "hi"}},
                    "full": {"summary": "With a status", "value": {"id": 2, "title": "x", "status": "done"}},
                }
            ),
        ],
    ) -> Task:
        return note

    operation = next(iter(specmod.build(app.openapi()).index.values()))
    # The first named example prefills the box: a value somebody wrote beats one
    # this module invented from the schema.
    assert '"title": "hi"' in operation.body_example
    assert [label for label, _ in operation.body_examples] == ["With a status"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))
    assert "With a status" in TestClient(app).get(f"/api-docs/op/{operation.id}").text


def test_a_tag_s_own_description_and_link_are_rendered():
    """A `tags=` list is an information architecture, and a description on one of
    its entries is the paragraph saying what that group of endpoints is for. The
    sidebar has no room for it, and a newcomer reads it first."""
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_tags=[
            {
                "name": "notes",
                "description": "Everything about notes.",
                "externalDocs": {"url": "https://example.com/notes", "description": "The notes guide"},
            }
        ],
    )

    @app.get("/notes", tags=["notes"])
    def notes() -> dict:
        return {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

    page = TestClient(app).get("/api-docs")
    assert "Everything about notes." in page.text
    assert "https://example.com/notes" in page.text
    assert "The notes guide" in page.text


def test_the_docs_need_no_render_decorator_anywhere_in_the_app():
    """`@render` is not a prerequisite for being documented.

    The plugin reads `app.openapi()`, the same document `/openapi.json` serves,
    and knows nothing about `fjkit.rendering`. A plain FastAPI app, or one that
    mixes decorated and undecorated routes, gets the whole page: the operations,
    the console, and the schemas.
    """
    app = FastAPI(title="Plain", version="1", docs_url=None, redoc_url=None)

    @app.get("/tasks", tags=["tasks"], summary="No decorator at all")
    def tasks() -> list[Task]:
        return [Task(id=1, title="plain")]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))
    client = TestClient(app)

    page = client.get("/api-docs")
    assert page.status_code == 200
    assert "No decorator at all" in page.text
    assert "Task" in page.text  # the schemas branch, from components.schemas

    document = specmod.build(app.openapi())
    assert document.by_name["Task"].fields  # the type is documented, not just named

    # The console calls it and gets the model, because a route with no `@render`
    # was already returning JSON. `SCOPE_RENDER_MODE` never enters into it:
    # nothing reads that key unless `@render` is on the route.
    assert "&#34;title&#34;: &#34;plain&#34;" in client.post("/api-docs/try/tasks_tasks_get").text


def test_a_decorated_route_documents_exactly_as_an_undecorated_one(tmp_path):
    """`@render` contributes nothing to the document and must cost nothing.

    It has to eval the return annotation itself: under
    `from __future__ import annotations` that annotation is a string, and a
    wrapper that drops it leaves FastAPI unable to derive `response_model`. The
    symptom is a thinner docs page for the decorated half of an app, which is
    the opposite of what the decorator is for and hard to attribute.
    """
    (tmp_path / "page.html").write_text("<p>{{ title }}</p>", encoding="utf-8")

    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/plain", tags=["t"])
    def plain() -> Task:
        return Task(id=1, title="plain")

    @app.get("/decorated", tags=["t"])
    @render("page.html")
    def decorated() -> Task:
        return Task(id=2, title="decorated")

    mount_fjkit(app, FjkitConfig(template_dir=tmp_path, plugins=(ApiDocsPlugin(),), auto_reload=False))

    document = specmod.build(app.openapi())
    bare = document.index["plain_plain_get"].responses[0]
    wrapped = document.index["decorated_decorated_get"].responses[0]

    assert wrapped.shape is not None
    assert bare.shape.label == wrapped.shape.label == "Task"
    assert bare.example == wrapped.example


def test_the_plugin_adds_routes_and_nothing_else():
    """The plugin must not be able to reach the app's own rendering.

    A plugin may add middleware — `AppSetup` offers it — and middleware is
    exactly how a docs page would end up changing what every other route
    returns. This one adds a router and stops there, so installing it leaves an
    app's own `@render` decisions untouched.
    """
    before = FastAPI(docs_url=None, redoc_url=None)
    after = FastAPI(docs_url=None, redoc_url=None)

    @before.get("/x")
    def x_before() -> Task:
        return Task(id=1, title="x")

    @after.get("/x")
    def x_after() -> Task:
        return Task(id=1, title="x")

    config = FjkitConfig(auto_reload=False)
    mount_fjkit(before, config)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(after, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

    assert [type(m) for m in after.user_middleware] == [type(m) for m in before.user_middleware]
    assert set(after.exception_handlers) == set(before.exception_handlers)
    # The app-wide default is configuration the app owns. The plugin reads it and
    # never writes it.
    assert config.render_mode == FjkitConfig().render_mode

    # The route itself answers a browser exactly as it did without the plugin.
    assert TestClient(before).get("/x").json() == TestClient(after).get("/x").json()


def test_a_handler_that_raises_is_reported_on_the_page_and_logged_in_full(caplog):
    """The one thing an in-process replay takes away.

    A request over a socket has a server above it whose job is to log the
    traceback of anything the app lets through. Here the caller is the console,
    and `except Exception` stops a failing endpoint taking the docs page down
    with it — which would also leave the traceback recorded nowhere. So the
    panel gets the one-line report and the log gets the frames.
    """
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/boom", tags=["t"])
    def boom() -> Task:
        return 1 / 0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

    with caplog.at_level("ERROR", logger="fjkit.apidocs.console"):
        reply = TestClient(app).post("/api-docs/try/boom_boom_get")

    assert reply.status_code == 200  # the docs page survives its subject
    assert "ZeroDivisionError" in reply.text
    assert "fjkit.apidocs.console" in reply.text  # where to go for the rest

    record = next(r for r in caplog.records if r.name == "fjkit.apidocs.console")
    assert record.exc_info is not None
    assert "ZeroDivisionError" in caplog.text
    # The frames, not just the summary: that is the point of logging it.
    assert "boom" in caplog.text


def test_a_call_that_answered_and_then_raised_shows_both():
    """Starlette's `ServerErrorMiddleware` sends its 500 and then re-raises, so
    both are true at once. Reading the error first reported "no response" over a
    reply that was sitting right there: a debugging tool asserting something
    false about what happened, which is worse than showing less."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/boom", tags=["t"])
    def boom() -> Task:
        return 1 / 0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

    reply = TestClient(app).post("/api-docs/try/boom_boom_get").text
    assert "500" in reply
    assert "no response" not in reply  # reserved for a call that produced none
    assert "ZeroDivisionError" in reply


def test_no_response_still_means_no_response():
    """A timeout produces nothing at all, and must still say so."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/slow", tags=["t"])
    async def slow() -> Task:
        await asyncio.sleep(5)
        return Task(id=1, title="never")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(
            app,
            FjkitConfig(plugins=(ApiDocsPlugin(timeout=timedelta(milliseconds=20)),), auto_reload=False),
        )

    reply = TestClient(app).post("/api-docs/try/slow_slow_get").text
    assert "no response" in reply
    assert "did not finish" in reply


def test_the_schemas_branch_is_split_by_kind():
    """An object is a shape you are about to send; an enum is a vocabulary you
    check a spelling against. In one alphabetical run a handful of enums are
    scattered through thirty names, which is when a split earns its heading.

    A real `Enum` and not a `Literal`: FastAPI inlines a `Literal` into the
    property that uses it, so it never reaches `components.schemas` and there
    would be nothing here to group.
    """
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/coloured", tags=["t"])
    def coloured(colour: Colour = Colour.RED) -> Job:
        return Job(owner=Owner(name="ada"))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PluginWarning)
        mount_fjkit(app, FjkitConfig(plugins=(ApiDocsPlugin(),), auto_reload=False))

    document = specmod.build(app.openapi())
    assert [label for label, _ in document.model_groups] == ["Objects", "Enums"]

    grouped = dict(document.model_groups)
    assert all(m.kind == "object" for m in grouped["Objects"])
    assert {m.name for m in grouped["Enums"]} == {"Colour"}

    page = TestClient(app).get("/api-docs")
    assert "Objects" in page.text
    assert "Enums" in page.text


def test_a_kind_with_no_members_gets_no_heading():
    """An API with no enums must not grow an empty `Enums` band."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/j", tags=["t"])
    def j() -> Job:
        return Job(owner=Owner(name="ada"))

    document = specmod.build(app.openapi())
    assert [label for label, _ in document.model_groups] == ["Objects"]


def test_an_operation_that_needs_authentication_says_so():
    """The padlock. Every API browser marks a secured operation, because the
    alternative is learning about it from a 401."""
    document = specmod.build(
        {
            "info": {"title": "T", "version": "1"},
            "paths": {"/x": {"get": {"security": [{"OAuth2": []}], "responses": {}}}},
        }
    )
    assert next(iter(document.index.values())).security == ("OAuth2",)


def test_an_array_parameter_goes_on_the_wire_as_its_name_repeated(rich: TestClient):
    """FastAPI parses `list[str]` back out of `?tag=a&tag=b`. One box holding
    "a,b" would send that string whole, and the endpoint would receive a
    single-element list."""
    document = specmod.build(rich.app.openapi())
    tag = document.index["list_tasks_tasks_get"].params[0]
    assert tag.multi

    reply = rich.post("/api-docs/try/list_tasks_tasks_get", data={"p.query.tag": "a, b\nc"})
    assert "tag=a&amp;tag=b&amp;tag=c" in reply.text


def test_an_upload_endpoint_gets_a_file_control_and_the_bytes_arrive(rich: TestClient):
    """The console re-encodes what the browser posted into the multipart body the
    endpoint declared, so `UploadFile` is testable here rather than being the one
    shape you have to leave for curl."""
    document = specmod.build(rich.app.openapi())
    operation = document.index["upload_upload_post"]
    assert operation.multipart
    assert next(p for p in operation.body_fields if p.name == "attachment").control == "file"

    page = rich.get("/api-docs/op/upload_upload_post")
    assert 'type="file"' in page.text
    assert 'enctype="multipart/form-data"' in page.text
    assert 'hx-encoding="multipart/form-data"' in page.text

    reply = rich.post(
        "/api-docs/try/upload_upload_post",
        data={"p.form.note": "hello"},
        files={"p.form.attachment": ("cat.txt", b"meow meow", "text/plain")},
    )
    assert "cat.txt" in reply.text
    assert "9" in reply.text  # the endpoint read nine bytes back out
    # curl gets `-F`, not `--data`: the body is bytes from a file the snippet
    # does not contain, and `@name` tells curl to read it.
    assert "attachment=@cat.txt;type=text/plain" in reply.text


def test_an_untouched_file_input_does_not_post_an_empty_file(rich: TestClient):
    """A file input still sends a part when nothing was picked. Forwarding it
    would put a zero-byte file in the body of every call whose upload was
    optional and left alone."""
    reply = rich.post(
        "/api-docs/try/upload_upload_post",
        data={"p.form.note": "hello"},
        files={"p.form.attachment": ("", b"", "application/octet-stream")},
    )
    # No file part means FastAPI refuses it: the endpoint's answer, not the
    # console inventing an upload.
    assert "422" in reply.text


def test_a_file_is_recognised_in_both_of_openapi_s_two_spellings():
    """3.0 said `format: binary`; 3.1 dropped it for `contentMediaType`, and
    FastAPI emits 3.1. Reading only `format` renders every upload as a text box,
    which posts the filename as a string and fails inside the endpoint, a long
    way from the cause."""
    for schema in ({"type": "string", "format": "binary"}, {"type": "string", "contentMediaType": "image/png"}):
        document = specmod.build(
            {
                "info": {"title": "T", "version": "1"},
                "paths": {
                    "/u": {
                        "post": {
                            "requestBody": {
                                "content": {
                                    "multipart/form-data": {
                                        "schema": {"type": "object", "properties": {"f": schema}}
                                    }
                                }
                            },
                            "responses": {},
                        }
                    }
                },
            }
        )
        operation = next(iter(document.index.values()))
        assert operation.multipart
        assert operation.body_fields[0].control == "file", schema


# ---------------------------------------------------------------- the markup


def test_the_response_example_says_on_screen_which_status_it_is(client: TestClient):
    """Every example is captioned visibly with the status it belongs to.

    An `aria-label` alone told a screen reader and nobody else, and a page
    showing two examples with nothing naming either is worse than one showing
    none. The caption is a tab label when there is a schema to switch to and a
    heading when there is not; both are text on the screen."""
    page = client.get("/api-docs/op/list_tasks_tasks_get")

    statuses = [entry.status for entry in specmod.build(client.app.openapi()).index["list_tasks_tasks_get"].responses]
    assert statuses[-1] == "422"
    assert "Example 200 response" in page.text
    assert page.text.count("Example 200 response") == 2  # the caption and the region name


def test_every_class_in_the_console_s_templates_exists_in_the_stylesheet():
    """A class that is not in the built CSS has no effect, and nothing says so.

    These templates ship inside the wheel, so they may use the utilities an app
    may not — but only the ones `fjkit build-css` emitted. Getting this wrong
    produces a page that renders and looks broken, which is the hardest kind of
    failure to attribute.
    """
    known = component_classes() | emitted_classes() | {"htmx-indicator"}
    attribute = re.compile(r'class\s*=\s*"([^"]*)"', re.DOTALL)
    expression = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.DOTALL)

    templates = sorted((TEMPLATE_DIR / "apidocs").glob("*.html"))
    # These files live in the plugin's own directory, and the scan below passes
    # trivially if they are moved again and this test is not.
    assert templates, f"no console templates under {TEMPLATE_DIR / 'apidocs'}"
    source = (STATIC_DIR / "src" / "fjkit.css").read_text(encoding="utf-8")
    assert '@source "../../apidocs/templates";' in source, (
        "fjkit.css no longer scans the console's templates — every utility class "
        "in them would be missing from the built stylesheet"
    )

    unknown: set[str] = set()
    for path in templates:
        for match in attribute.finditer(path.read_text(encoding="utf-8")):
            for token in expression.sub(" ", match.group(1)).split():
                if "{" in token or "}" in token:
                    continue
                if token.rsplit(":", 1)[-1] not in known:
                    unknown.add(f"{path.name}: {token}")

    assert not unknown, f"classes absent from the stylesheet: {sorted(unknown)}"
