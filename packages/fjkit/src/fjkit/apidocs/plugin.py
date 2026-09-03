"""`ApiDocsPlugin` — the API reference and console, mounted by registering it.

Setup is one line, matching what FastAPI's own `/docs` costs; a replacement
costing more would not be used:

    config = FjkitConfig(template_dir=…, plugins=(auth, ApiDocsPlugin()))

No route to write, no template to render, no static files to serve. The plugin
adds its own router at `url`, renders out of its own `templates/apidocs/`, and,
finding an `AuthPlugin` in the same `plugins` tuple, wires its sign-in panel to
that plugin's `TokenSource`. Turn FastAPI's built-in docs off with
`FastAPI(docs_url=None, redoc_url=None)` to keep only this one.

**Why it exists.** Swagger UI's "Authorize" dialog can only express what an
OpenAPI document describes: an API key, an HTTP scheme, an OAuth2 flow. An app
whose sessions are `fjkit.auth` — a signed HttpOnly cookie over a server-side
token — matches none of those, and Swagger's console could not send one anyway:
it runs in JavaScript, and the credential is deliberately out of JavaScript's
reach. So this console does not run in the browser. It replays the request
through the app in-process, forwarding the caller's own cookie
(`fjkit.apidocs.console`). Sign-in is a Python object the app supplies
(`fjkit.apidocs.flows`), the piece Swagger has no room for.

**What it is not.** It reads `/openapi.json` rather than replacing it. Client
generators, contract tests and other tools keep using the document, which stays
the single description of the API.
"""

from __future__ import annotations

import re
import secrets
import sys
from collections.abc import Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile

from fjkit.apidocs import console, spec
from fjkit.apidocs.flows import AuthFlow, FlowError, HeaderFlow, NoFlow, SessionFlow
from fjkit.plugins import AppSetup, EnvSetup
from fjkit.templating import get_templates

__all__ = ["ApiDocsPlugin"]

#: This plugin's own templates, handed to the loader by `extend`. Named
#: `templates/apidocs/` so the template names are `apidocs/…` — see `extend`.
TEMPLATE_DIR = Path(__file__).parent / "templates"

#: The ids the templates swap against. Constants rather than literals in four
#: files, because a typo in one of them gives a target that matches nothing and
#: an htmx click that appears to do nothing.
DETAIL_ID = "fjkit-apidocs-detail"
SESSION_ID = "fjkit-apidocs-session"
RESULT_ID = "fjkit-apidocs-result"
NAV_ID = "fjkit-apidocs-nav"

#: Form field holding the request body, the one holding extra headers, and the
#: sidebar filter's query.
_BODY_FIELD = "body"
_HEADERS_FIELD = "headers"
_QUERY_FIELD = "q"

#: Where one field's several values are separated. A `list[str]` query parameter
#: is `?tag=a&tag=b` on the wire, and one text box has to express that, so a
#: newline or a comma ends a value. A value containing a comma is the case this
#: cannot express; the extra-headers box beside it can.
_SEPARATORS = re.compile(r"[\n,]")

#: Stripped out of a multipart part's name and filename. RFC 7578 leaves
#: escaping inside the quoted string underspecified and servers disagree about
#: it, so the characters that would need escaping never go on the wire. A
#: filename is a label here, not a path the endpoint should trust.
_UNQUOTABLE = re.compile(r'[\r\n"\\]')


class ApiDocsPlugin:
    """Register in `FjkitConfig.plugins`. Everything else is defaults.

    :param url: where the page lives. Not `/docs`: FastAPI has claimed that by
        the time a plugin mounts, the first route registered wins, and a docs
        page that never renders is worse than a different URL.
    :param flow: how someone signs in from the page. Defaults to `SessionFlow`
        wrapping whichever `AuthPlugin` shares the config, and to `NoFlow` when
        there is none.
    :param dependencies: put on every route the plugin adds, which is how the
        page is gated. `dependencies=[Depends(auth.required)]` makes the docs
        staff-only; leaving it empty makes them public — the right default for
        a public API and the wrong one for an internal service.
    :param try_it: `False` renders the reference without the console, for an
        environment where replaying a request server-side is unacceptable.
    :param base_template: what the page extends. The kit's shell by default;
        name the app's own `base.html` to put the docs inside its chrome. This
        page fills the shell's `sidebar` block with the operation list, so a
        base that fills it too loses its own navigation here.
    :param home_url: a way back out, rendered in the sidebar's footer. Set it
        whenever the docs are part of a larger app: the operation list occupies
        the sidebar, so the page otherwise has no way out.
    """

    name = "apidocs"

    def __init__(
        self,
        *,
        url: str = "/api-docs",
        title: str = "",
        flow: AuthFlow | None = None,
        dependencies: Sequence[Any] = (),
        try_it: bool = True,
        base_template: str = "ui/shell.html",
        home_url: str = "",
        home_label: str = "Back to the app",
        timeout: timedelta = timedelta(seconds=30),
        max_body: int = 64 * 1024,
        route_name: str = "fjkit_apidocs",
    ) -> None:
        if not url.startswith("/") or url == "/":
            raise ValueError(f"ApiDocsPlugin(url={url!r}) must be an absolute path such as '/api-docs'.")
        self.url = url.rstrip("/")
        self.title = title
        #: `NoFlow` until `mount` inspects the sibling plugins. An app that
        #: named a flow settles the choice here, and the auto-detection in
        #: `_resolve_flow` never runs.
        self._flow_given = flow is not None
        self.flow: AuthFlow = flow if flow is not None else NoFlow()
        if isinstance(self.flow, HeaderFlow) and self.flow.cookie_path is None:
            # Scoped to the docs page. A token held for the whole origin would
            # be attached to nothing else, but the browser would still send it
            # to every other route on the site — a wider blast radius than this
            # feature needs.
            self.flow.cookie_path = self.url
        self.dependencies = list(dependencies)
        self.try_it = try_it
        self.base_template = base_template
        self.home_url = home_url
        self.home_label = home_label
        self.timeout = timeout
        self.max_body = max_body
        self.route_name = route_name
        #: (id of the OpenAPI dict, flattened form). FastAPI caches the dict on
        #: the app, so the identity check separates "same document" from
        #: "someone set `app.openapi_schema = None` and it was rebuilt".
        self._spec: tuple[int, spec.Spec] | None = None

    # ---------------------------------------------------------------- plugin

    def mount(self, setup: AppSetup) -> None:
        self._resolve_flow(setup)

        taken = next((r for r in setup.app.routes if getattr(r, "path", None) == self.url), None)
        if taken is not None:
            setup.warn(
                f"{self.url} is already routed by {getattr(taken, 'name', taken)!r}. Starlette matches "
                "the first route that fits, so this page will never render. Pass a different "
                "`url=`, or FastAPI(docs_url=None) if this is the built-in Swagger page."
            )

        setup.include_router(self._router())

    def extend(self, setup: EnvSetup) -> None:
        """Add this plugin's own `templates/` to the loader path.

        The files live beside the code that renders them, in
        `apidocs/templates/` rather than in the kit's shared `templates/`, so
        the feature is one directory and deleting it takes nothing else with it.

        The inner `apidocs/` is deliberate, not a doubled path: the loader is
        given the `templates/` directory, so the names stay `apidocs/page.html`
        and an app shadows any of them by writing its own
        `templates/apidocs/<name>.html`. Plugin directories are searched after
        the app's and before the kit's (CHARTER A5), which keeps that true.

        The cost is that `fjkit.css` has to scan here too, naming this directory
        in a second `@source`. A template the Tailwind build never reads ships
        with every utility class in it missing from the stylesheet, and the page
        then renders, looks broken, and reports nothing. The stylesheet test in
        `tests/test_apidocs.py` holds that.

        Nothing else is contributed: everything these templates need is per-page
        and comes from the routes. A plugin claiming `spec` or `flow` app-wide
        would collide with an app that has its own.
        """
        setup.add_template_dir(TEMPLATE_DIR)

    def _resolve_flow(self, setup: AppSetup) -> None:
        """Find the app's `AuthPlugin` and wrap it, unless a flow was named.

        Reading the sibling plugins rather than taking an `auth=` argument is
        the difference between two lines of setup and one, and it makes
        `plugins=(auth, ApiDocsPlugin())` produce a working sign-in panel. It is
        also the only code here that knows `fjkit.auth` exists.

        The `sys.modules` check is why an app with no sessions pays nothing for
        this. An `AuthPlugin` instance cannot be in `config.plugins` unless its
        class was imported first, so a missing module proves there is nothing to
        find, and importing one to discover that costs ~15 ms of startup for a
        search that is certainly empty.
        """
        if self._flow_given:
            return

        module = sys.modules.get("fjkit.auth.plugin")
        if module is None:
            return

        auth = next((p for p in setup.config.plugins if isinstance(p, module.AuthPlugin)), None)
        if auth is not None:
            self.flow = SessionFlow(auth)

    # ---------------------------------------------------------------- routes

    def _router(self) -> APIRouter:
        router = APIRouter(
            prefix=self.url,
            # Out of the app's own document, for the same reason FastAPI keeps
            # `/docs` out of it: these routes are a way of reading the API, not
            # part of it. It also keeps the console from being handed itself.
            include_in_schema=False,
            dependencies=self.dependencies,
        )
        router.add_api_route("", self._index, methods=["GET"], name=f"{self.route_name}_index")
        router.add_api_route(
            "/op/{operation_id}", self._operation, methods=["GET"], name=f"{self.route_name}_operation"
        )
        router.add_api_route(
            "/schema/{model_slug}", self._model, methods=["GET"], name=f"{self.route_name}_model"
        )
        # The filtered operation list, on its own so the input can swap it
        # without touching the panel the reader is looking at. A GET, so the
        # browser's back button and a bookmarked `?q=` both work.
        router.add_api_route("/nav", self._nav, methods=["GET"], name=f"{self.route_name}_nav")
        router.add_api_route("/auth", self._auth, methods=["POST"], name=f"{self.route_name}_auth")
        if self.try_it:
            router.add_api_route("/try/{operation_id}", self._try, methods=["POST"], name=f"{self.route_name}_try")
        return router

    # A `def` handler, so Starlette runs the render in the threadpool — the rule
    # every rendering route in this kit follows. The two that read a form are
    # `async def` because `await request.form()` requires it, and they render a
    # fragment rather than a page.
    def _index(self, request: Request, q: str = "") -> HTMLResponse:
        return self._render(request, "apidocs/page.html", self._context(request, query=q))

    def _operation(self, request: Request, operation_id: str, q: str = "") -> HTMLResponse:
        document = self._document(request)
        operation = document.index.get(operation_id)
        if operation is None:
            # 404 with the page rather than a bare error: a bookmarked
            # operation id stops being valid the moment a route is renamed, and
            # landing on the index with the list still there is recoverable.
            return self._render(request, "apidocs/page.html", self._context(request, query=q), status_code=404)
        swap = _is_swap(request)
        context = self._context(request, operation=operation, query=q, oob_nav=swap)
        return self._render(request, "apidocs/_operation.html" if swap else "apidocs/page.html", context)

    def _model(self, request: Request, model_slug: str, q: str = "") -> HTMLResponse:
        """Render one entry from `components.schemas`, in an operation's panel.

        The types an API exchanges are half of its contract — every generated
        client is built from them — which is why Swagger gives them a section.
        Here they are a second branch of the sidebar rather than a slab at the
        bottom of the page, because the sidebar is already the index and a
        hundred models is navigation.
        """
        document = self._document(request)
        model = document.model_index.get(model_slug)
        if model is None:
            return self._render(request, "apidocs/page.html", self._context(request, query=q), status_code=404)
        swap = _is_swap(request)
        context = self._context(request, model=model, query=q, oob_nav=swap)
        return self._render(request, "apidocs/_model.html" if swap else "apidocs/page.html", context)

    def _nav(self, request: Request, q: str = "") -> HTMLResponse:
        return self._render(request, "apidocs/_nav.html", self._context(request, query=q))

    async def _auth(self, request: Request) -> HTMLResponse:
        form = await request.form()
        values = {key: str(value) for key, value in form.items()}
        carrier = Response()
        error = ""
        try:
            if values.get("action") == "sign_out":
                await self.flow.sign_out(request, carrier)
            else:
                await self.flow.sign_in(request, carrier, values)
        except FlowError as exc:
            error = str(exc)

        state = self.flow.state(request)
        if error:
            state = state.with_error(error)
        response = self._render(request, "apidocs/_session.html", self._context(request, state=state))
        _carry_cookies(carrier, response)
        return response

    async def _try(self, request: Request, operation_id: str) -> HTMLResponse:
        document = self._document(request)
        operation = document.index.get(operation_id)
        if operation is None:
            # Answered with the result panel rather than a 404: this arrives as
            # an htmx POST, and htmx swaps nothing for a 4xx, so the button
            # would appear to do nothing.
            return self._render(
                request,
                "apidocs/_result.html",
                self._context(request) | {"result": _missing(operation_id), "curl": ""},
            )

        form = await request.form()
        values: dict[str, str] = {}
        uploads: dict[str, list[tuple[str, str, bytes]]] = {}
        for key, value in form.multi_items():
            if isinstance(value, UploadFile):
                data = await value.read()
                if value.filename or data:
                    # An untouched file input still posts a part, with an empty
                    # filename and no bytes. Sending it would put an empty file
                    # in the body of every call whose upload was optional and
                    # left alone.
                    uploads.setdefault(key, []).append(
                        (value.filename or key, value.content_type or "application/octet-stream", data)
                    )
            else:
                values[key] = str(value)

        path, query, headers, fields = self._compose(request, operation, values)
        files = [
            (param.name, *item)
            for param in operation.body_fields
            if param.control == "file"
            for item in uploads.get(param.field_name, ())
        ]

        content_type = ""
        if operation.multipart and (fields or files):
            body, content_type = _multipart(fields, files)
        elif fields:
            body = urlencode(fields).encode("ascii")
        elif operation.has_raw_body:
            body = (values.get(_BODY_FIELD) or "").strip().encode("utf-8")
        else:
            body = b""
        if body:
            headers.setdefault("content-type", content_type or operation.body_media)

        try:
            result = await console.call(
                request,
                method=operation.method,
                path=path,
                query=query,
                headers=headers,
                body=body,
                timeout=self.timeout.total_seconds(),
                max_body=self.max_body,
                forbidden_prefix=self.url,
            )
        except console.RecursionRefused as exc:
            result = console.Recorded(method=operation.method, url=path, status=0, error=str(exc))

        context = self._context(request, operation=operation)
        context["result"] = result
        context["curl"] = _curl(request, operation.method, path, query, headers, body, fields, files)
        return self._render(request, "apidocs/_result.html", context)

    # --------------------------------------------------------------- the call

    def _compose(
        self, request: Request, operation: spec.Operation, values: Mapping[str, str]
    ) -> tuple[str, list[tuple[str, str]], dict[str, str], list[tuple[str, str]]]:
        """Turn the submitted form into a path, a query, headers and a body.

        One loop over every declared parameter, with `location` deciding where
        each value goes. A form body's fields arrive as `location="form"` and
        leave as the fourth return value, for the caller to encode.
        """
        path = operation.path
        query: list[tuple[str, str]] = []
        headers: dict[str, str] = {}
        cookies: list[str] = []
        fields: list[tuple[str, str]] = []

        for param in (*operation.params, *operation.body_fields):
            value = (values.get(param.field_name) or "").strip()
            if not value:
                # An omitted optional parameter must be absent, not empty:
                # `?status=` and no `status` at all are different requests, and
                # only the second is what a blank box meant.
                continue
            # An array parameter goes on the wire as its own name repeated —
            # `?tag=a&tag=b` — which is what FastAPI parses `list[str]` back out
            # of. One box holding "a,b" would send that string whole and the
            # endpoint would receive a single-element list, so this is where one
            # field becomes the several values it stood for.
            many = _split(value) if param.multi else [value]
            if param.location == "path":
                path = path.replace("{" + param.name + "}", quote(value, safe=""))
            elif param.location == "query":
                query.extend((param.name, one) for one in many)
            elif param.location == "header":
                headers[param.name] = value
            elif param.location == "cookie":
                cookies.append(f"{param.name}={value}")
            elif param.location == "form":
                fields.extend((param.name, one) for one in many)

        for line in (values.get(_HEADERS_FIELD) or "").splitlines():
            name, sep, value = line.partition(":")
            if sep and name.strip():
                headers[name.strip()] = value.strip()

        if cookies:
            # Merged with what the browser sent rather than replacing it: the
            # session cookie is in there, and dropping it would sign the caller
            # out for the very call they were testing.
            existing = request.headers.get("cookie", "")
            headers["cookie"] = "; ".join(x for x in (existing, *cookies) if x)

        # Ask for what the document promises, rather than forwarding the
        # browser's `Accept: text/html`. A client that had read these docs would
        # send this, and it is what the endpoint sees. `SCOPE_RENDER_MODE` in
        # `console.call` already settles the representation a `@render` route
        # picks, but nothing else in the app knows that key, and a route or a
        # dependency branching on `Accept` should branch on the API's answer
        # rather than on this page's. Set, not forced: a hand-typed `Accept` in
        # the extra-headers box is a legitimate thing to test.
        documented = next((r.media_type for r in operation.responses if r.media_type), "")
        if documented:
            headers.setdefault("accept", documented)

        # The flow gets the last word: it knows what authenticates a call, and
        # a hand-typed header must not shadow it under a different
        # capitalisation.
        headers.update(self.flow.headers(request))
        return path, query, headers, fields

    # -------------------------------------------------------------- plumbing

    def _document(self, request: Request) -> spec.Spec:
        schema = request.app.openapi()
        cached = self._spec
        if cached is not None and cached[0] == id(schema):
            return cached[1]
        built = spec.build(schema, skip_prefix=self.url)
        self._spec = (id(schema), built)
        return built

    def _context(
        self,
        request: Request,
        *,
        operation: spec.Operation | None = None,
        model: spec.Model | None = None,
        state: Any = None,
        query: str = "",
        oob_nav: bool = False,
    ) -> dict[str, Any]:
        document = self._document(request)
        return {
            "docs": document,
            "operation": operation,
            "model": model,
            # The filter's text and its result. The templates never call
            # `docs.filter` themselves: an unfiltered `docs.groups` rendered
            # where the filtered list belonged is a sidebar that ignores what
            # was typed, and that bug is hard to see.
            "query": query,
            "groups": document.filter(query),
            # True only on a panel swap, where nothing else re-renders the
            # sidebar and its highlight would go stale. `_nav.html` turns it
            # into `hx-swap-oob`.
            "oob_nav": oob_nav,
            "flow": self.flow,
            "flow_state": state if state is not None else self.flow.state(request),
            "base_template": self.base_template,
            "docs_title": self.title or document.title,
            "home_url": self.home_url,
            "home_label": self.home_label,
            "try_it": self.try_it,
            # `run` and not `try`: the templates reach these by attribute, and
            # `routes.try` is a Jinja expression starting with a Python keyword
            # — a trap with no upside when the key can be named otherwise.
            "routes": {
                "index": f"{self.route_name}_index",
                "operation": f"{self.route_name}_operation",
                "model": f"{self.route_name}_model",
                "nav": f"{self.route_name}_nav",
                "auth": f"{self.route_name}_auth",
                "run": f"{self.route_name}_try",
            },
            "ids": {"detail": DETAIL_ID, "session": SESSION_ID, "result": RESULT_ID, "nav": NAV_ID},
            "body_field": _BODY_FIELD,
            "headers_field": _HEADERS_FIELD,
            "query_field": _QUERY_FIELD,
            # Present and empty so the result partial renders as the placeholder
            # the operation page needs, rather than tripping `strict_undefined`.
            "result": None,
            "curl": "",
        }

    def _render(
        self, request: Request, name: str, context: Mapping[str, Any], *, status_code: int = 200
    ) -> HTMLResponse:
        # `Vary: HX-Request` on every reply: the operation route answers one URL
        # with a page or a fragment, so a shared cache that ignored the header
        # would hand a navigation a fragment with no shell around it.
        return get_templates(request).page(
            request, name, context, status_code=status_code, headers={"vary": "HX-Request"}
        )


def _is_swap(request: Request) -> bool:
    """Report an htmx swap of part of the page, as against a boosted navigation.

    The same test `@render` makes. Not imported from `fjkit.rendering`: that
    copy is private to it, and this module is the second caller, not a reason to
    publish it.
    """
    headers = request.headers
    return headers.get("hx-request", "").lower() == "true" and headers.get("hx-boosted", "").lower() != "true"


def _carry_cookies(source: Response, target: Response) -> None:
    """Copy `Set-Cookie` from the flow's carrier onto the rendered reply.

    A flow is handed a bare `Response` to set cookies on, so it need not know it
    is writing to a Jinja render. Only the cookies move: the carrier's
    `content-length: 0` describes the empty response it is, not the HTML being
    sent.
    """
    for key, value in source.raw_headers:
        if key.lower() == b"set-cookie":
            target.raw_headers.append((key, value))


def _missing(operation_id: str) -> console.Recorded:
    return console.Recorded(
        method="",
        url="",
        status=0,
        error=(
            f"No operation {operation_id!r} in this API any more. It was renamed or removed "
            "since this page was loaded — reload to see the current list."
        ),
    )


def _split(value: str) -> list[str]:
    """Split one box's contents into the several values it stood for."""
    return [part.strip() for part in _SEPARATORS.split(value) if part.strip()]


def _multipart(
    fields: Sequence[tuple[str, str]], files: Sequence[tuple[str, str, str, bytes]]
) -> tuple[bytes, str]:
    """Encode a `multipart/form-data` body, and the content type that names it.

    This is what lets the console call an `UploadFile` endpoint. The browser
    posts the file to this route as multipart, Starlette parses it, and the
    bytes are re-encoded here into a body the in-process replay carries, so the
    endpoint under test receives what a real client would send.

    Written out rather than taken from a library: it is twenty lines, and the
    alternative is a runtime dependency on the client half of `httpx` for a
    string join. The boundary is random per call, because a fixed one occurring
    inside an uploaded file would split the body in the wrong place — and files
    whose contents the app does not control are what this feature is for.
    """
    boundary = f"fjkit{secrets.token_hex(16)}"
    marker = f"--{boundary}\r\n".encode("ascii")
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(marker)
        parts.append(f'Content-Disposition: form-data; name="{_quotable(name)}"\r\n\r\n'.encode())
        parts.append(value.encode("utf-8") + b"\r\n")
    for name, filename, media_type, data in files:
        parts.append(marker)
        parts.append(
            f'Content-Disposition: form-data; name="{_quotable(name)}"; '
            f'filename="{_quotable(filename)}"\r\n'
            f"Content-Type: {_quotable(media_type)}\r\n\r\n".encode()
        )
        parts.append(data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(parts), f"{spec.MULTIPART_MEDIA}; boundary={boundary}"


def _quotable(value: str) -> str:
    return _UNQUOTABLE.sub("", value)


def _curl(
    request: Request,
    method: str,
    path: str,
    query: Sequence[tuple[str, str]],
    headers: Mapping[str, str],
    body: bytes,
    fields: Sequence[tuple[str, str]] = (),
    files: Sequence[tuple[str, str, str, bytes]] = (),
) -> str:
    """Render the same call as a shell command, for a terminal or a bug report.

    Credentials become a placeholder rather than being printed. Rendering the
    caller's live session cookie into a copyable snippet would put it in every
    screenshot and every pasted bug report, and the point of this plugin is that
    the cookie is not readable from the page.
    """
    url = f"{request.base_url.scheme}://{request.base_url.netloc}{path}"
    if query:
        url += "?" + "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in query)

    parts = [f"curl -X {method} {_shell(url)}"]
    if request.headers.get("cookie"):
        parts.append("-H 'Cookie: <your session cookie>'")
    for key, value in headers.items():
        if key.lower() in ("cookie", "authorization"):
            parts.append(f"-H {_shell(f'{key}: <redacted>')}")
        elif key.lower() == "content-type" and files:
            # curl picks its own boundary, and one pasted from here would not
            # match the body `-F` builds. Letting curl write the header is the
            # only version of this command that runs.
            continue
        else:
            parts.append(f"-H {_shell(f'{key}: {value}')}")
    if files:
        # `-F` rather than `--data`, because the body is bytes from a file the
        # snippet does not contain. `@name` is curl's own syntax for "read this
        # path", so the command runs once the file sits beside it.
        for name, filename, media_type, _ in files:
            parts.append(f"-F {_shell(f'{name}=@{filename};type={media_type}')}")
        for name, value in fields:
            parts.append(f"-F {_shell(f'{name}={value}')}")
    elif body:
        parts.append(f"--data {_shell(body.decode('utf-8', errors='replace'))}")
    return " \\\n  ".join(parts)


def _shell(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
