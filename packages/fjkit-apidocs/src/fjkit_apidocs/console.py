"""Run one request against the app itself and record the response.

Swagger UI calls `fetch()` from the page, which cannot work here. The credential
this kit issues is an HttpOnly cookie: no script can read it, attach it or
refresh it, and `fjkit.auth` treats that as a feature. A console built on
`fetch()` would either send no credential at all or force the app to hand one to
JavaScript, which is the design being replaced.

So the call runs server-side, in-process: a fresh ASGI scope through `app`
itself. Everything the browser would have contributed is forwarded from the
console's own request — the session cookie above all — so the call travels the
real middleware stack. `AuthPlugin` loads the session, renews an expiring token,
and refuses the call if it cannot. The result panel shows what the endpoint does
for this caller, now.

No socket is opened and no server has to be reachable from itself, so this works
behind a proxy, in a test client, and on a machine with no route to its own
public hostname.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote, urlencode

from fastapi import Request
from fjkit.rendering import SCOPE_RENDER_MODE

from fjkit_apidocs.spec import tone_for, within

__all__ = ["Recorded", "RecursionRefused", "call"]

#: Request headers the console never forwards. Each describes the console's own
#: POST rather than the call being made: the length and content type of the
#: form, and the htmx headers, which name the element this page is swapping. An
#: app that reads `HX-Target` would act on a target unrelated to the endpoint it
#: is answering.
_DROPPED = frozenset(
    {
        "content-length",
        "content-type",
        "hx-boosted",
        "hx-current-url",
        "hx-history-restore-request",
        "hx-prompt",
        "hx-request",
        "hx-target",
        "hx-trigger",
        "hx-trigger-name",
        "transfer-encoding",
    }
)

#: Marks a scope this module created, so a call that reaches the console again
#: is refused rather than recursing until the stack runs out.
_DEPTH_KEY = "fjkit_apidocs_depth"

#: Where an escaping exception is written.
#:
#: This is what an in-process replay takes away. A request arriving over a socket
#: has a server above it — uvicorn, gunicorn — that logs the traceback of
#: anything the app lets through. Here the caller is this module, and its
#: `except Exception` is what stops a failing endpoint from 500-ing the docs page
#: with it. Without this logger the traceback would exist nowhere: the panel gets
#: `ZeroDivisionError: division by zero` and no file, no line, no frames. The
#: panel serves the person reading the page; this serves the same person ten
#: seconds later, reading the log.
_log = logging.getLogger("fjkit_apidocs.console")


class RecursionRefused(RuntimeError):
    """The console was asked to call the console."""


@dataclass(slots=True)
class Recorded:
    """One round trip, as the result panel shows it."""

    method: str
    url: str
    status: int
    headers: tuple[tuple[str, str], ...] = ()
    body: str = ""
    media_type: str = ""
    elapsed_ms: float = 0.0
    truncated: bool = False
    #: Set instead of a status when the call produced no response: a timeout, or
    #: an exception escaping the app.
    error: str = ""
    request_headers: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400

    @property
    def reason(self) -> str:
        """Return the status line's phrase — `OK`, `Not Found` — or nothing.

        Driven by the status rather than by `error`, because the two are
        independent: ServerErrorMiddleware sends a 500 and then re-raises, so a
        call can have both a real status and an escaped exception. Answering
        "no response" here put that phrase next to the 500 the app had sent —
        one badge contradicting itself.
        """
        if not self.status:
            return ""
        try:
            return HTTPStatus(self.status).phrase
        except ValueError:
            return ""

    @property
    def tone(self) -> str:
        """The badge variant: an escaped exception is destructive whatever the status."""
        return "destructive" if self.error else tone_for(self.status)

    @property
    def shown_headers(self) -> tuple[tuple[str, str], ...]:
        """The response headers as the panel prints them.

        A `Set-Cookie` keeps its name and attributes and loses its value. The
        console swallows the response rather than relaying the cookie to the
        browser, so the only way the value could reach the page is this
        panel, and an `HttpOnly` cookie is one no script on the page may
        read. `headers` stays complete for a caller that is not a page.
        """
        return tuple((k, _without_value(v) if k.lower() == "set-cookie" else v) for k, v in self.headers)

    @property
    def pretty(self) -> str:
        """Return the body, re-indented when it is JSON and unchanged otherwise."""
        if "json" not in self.media_type or not self.body:
            return self.body
        try:
            return json.dumps(json.loads(self.body), indent=2, ensure_ascii=False)
        except ValueError:
            return self.body


async def call(
    request: Request,
    *,
    method: str,
    path: str,
    query: Mapping[str, list[str]] | Iterable[tuple[str, str]] = (),
    headers: Mapping[str, str] | None = None,
    body: bytes = b"",
    timeout: float = 30.0,
    max_body: int = 64 * 1024,
    forbidden_prefix: str = "",
) -> Recorded:
    """Send `method path` through `request.app` and record the response.

    `request` is the console's own request, and the source of everything that
    makes this the caller's own call: the cookie jar, the origin, the client
    address, and the root path a proxy put in front of the app.
    """
    app = request.app
    root_path: str = request.scope.get("root_path", "") or ""
    target = path if path.startswith("/") else f"/{path}"

    if forbidden_prefix and within(target, forbidden_prefix):
        raise RecursionRefused(
            f"{target} is the API console itself. Calling it from here would re-enter this "
            "handler, and the only thing it can report is that it is reporting."
        )
    if request.scope.get(_DEPTH_KEY):
        raise RecursionRefused("this request is already a console call")

    query_string = urlencode(list(_pairs(query)), doseq=False).encode("ascii")
    sent = _headers(request, headers or {}, body)

    recorded = Recorded(
        method=method.upper(),
        url=_display(target, query_string),
        status=0,
        request_headers=tuple(sent),
    )
    unsendable = _unsendable(sent)
    if unsendable:
        # Reported like a timeout: the call produced no response because it
        # could not be made. Not an exception: a typed `名` is not a bug in
        # the app, and the person needs the panel, not a 500 and a lost form.
        recorded.error = unsendable
        return recorded

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": request.url.scheme,
        # `path` includes `root_path`: that is what a server sends and what
        # Starlette's router strips. Getting this wrong stays invisible until
        # the app is mounted under a prefix, and then every call 404s.
        #
        # Decoded, as ASGI defines it and as a server fills it in from the
        # request line; `raw_path` keeps the escapes. A path parameter arrives
        # here percent-encoded, and leaving it so would hand the endpoint
        # `my%20report.txt` where a direct request delivers `my report.txt`.
        "path": f"{root_path}{unquote(target)}",
        "raw_path": f"{root_path}{target}".encode(),
        "root_path": root_path,
        "query_string": query_string,
        "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in sent],
        "client": request.scope.get("client"),
        "server": request.scope.get("server"),
        # Lifespan state — a connection pool, a client — has to survive, or an
        # app that keeps its dependencies there gets a console that only
        # raises. Shallow copy: values are shared, but a key this call sets
        # does not leak back into the console's own request.
        "state": dict(request.scope.get("state") or {}),
        # Ask for the data, not the page. Under `render_mode="auto"` a page
        # route hands back a full HTML document where the API returns a model,
        # because `serves_a_page` is decided by the route's shape rather than
        # by who is calling. This key says who is calling. A route that
        # declared `mode="html"` still wins: it has said it has no data form,
        # and the console does not overrule that.
        SCOPE_RENDER_MODE: "json",
        _DEPTH_KEY: 1,
    }

    received = False

    async def receive() -> Mapping[str, Any]:
        nonlocal received
        if received:
            # An app or a middleware that reads the body twice must not hang
            # waiting for a message that never arrives.
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    chunks: list[bytes] = []
    size = 0

    async def send(message: Mapping[str, Any]) -> None:
        nonlocal size
        if message["type"] == "http.response.start":
            recorded.status = int(message["status"])
            recorded.headers = tuple(
                (k.decode("latin-1"), v.decode("latin-1")) for k, v in message.get("headers") or ()
            )
            recorded.media_type = next((v for k, v in recorded.headers if k.lower() == "content-type"), "")
        elif message["type"] == "http.response.body":
            chunk = message.get("body") or b""
            if size < max_body:
                chunks.append(chunk[: max_body - size])
            # Count the whole chunk, not the slice kept, so an endless stream
            # passes `max_body` and stops accumulating.
            size += len(chunk)

    started = time.perf_counter()
    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=timeout)
    except TimeoutError:
        recorded.error = f"the call did not finish within {timeout:g}s"
    except Exception as exc:  # noqa: BLE001 — the console's job is to report it
        # Reporting beats 500-ing the docs page, which would lose the request
        # the developer just spent a minute filling in. Reporting is not
        # swallowing: the traceback goes to the log first, because this module
        # stands where a real server would and nothing else writes it down.
        #
        # `recorded.status` may already be set. Starlette's
        # ServerErrorMiddleware sends its 500 and then re-raises, so both are
        # true at once: the app answered, and something escaped afterwards. The
        # result panel shows both.
        _log.exception("fjkit apidocs: %s %s raised", method.upper(), target)
        recorded.error = f"{type(exc).__name__}: {exc}"
    recorded.elapsed_ms = (time.perf_counter() - started) * 1000

    raw = b"".join(chunks)
    recorded.truncated = size > max_body
    recorded.body = raw.decode("utf-8", errors="replace")
    return recorded


def _headers(request: Request, extra: Mapping[str, str], body: bytes) -> list[tuple[str, str]]:
    """Build the call's headers: the console's own, minus its plumbing, plus the flow's.

    Forwarding the cookie is the whole mechanism — it makes the call the
    caller's session rather than an anonymous one. Forwarding `origin` matters
    nearly as much: `fjkit.auth` checks it on every cookie-authenticated write,
    so a call without it is refused as CSRF and the console looks broken on
    exactly the endpoints it is most useful for.
    """
    # Lowercased, because ASGI requires it and Starlette's `Headers` takes it
    # literally: it lowercases the name asked for and compares it to the raw
    # bytes in the scope. A header spelled `Authorization` there is invisible to
    # `request.headers["authorization"]` — present on the wire, absent to every
    # handler, and silent about it.
    out = [(k.lower(), v) for k, v in request.headers.items() if k.lower() not in _DROPPED]
    for key, value in extra.items():
        # A flow's header replaces rather than joins: an app cannot act on two
        # `Authorization` headers.
        name = key.lower()
        out = [(k, v) for k, v in out if k != name]
        out.append((name, value))
    if body:
        out.append(("content-length", str(len(body))))
    return out


def _without_value(cookie: str) -> str:
    """Return `name=<redacted>; attributes` for one `Set-Cookie` value."""
    name, _, rest = cookie.partition("=")
    _, semicolon, attributes = rest.partition(";")
    return f"{name}=<redacted>{semicolon}{attributes}"


def _unsendable(headers: Iterable[tuple[str, str]]) -> str:
    """Name the first header HTTP cannot carry, or return nothing.

    A header is Latin-1 on the wire. Every client encodes it so, and the ASGI
    scope holds the same bytes, so a character beyond U+00FF has no spelling
    in it. Found before the scope is built, so the person is told which header
    rather than shown a traceback.
    """
    for name, value in headers:
        for text in (name, value):
            try:
                text.encode("latin-1")
            except UnicodeEncodeError as exc:
                held = text[exc.start : exc.end]
                return f"the header {name!r} holds {held!r}, which an HTTP header cannot carry (Latin-1 only)"
    return ""


def _pairs(query: Mapping[str, list[str]] | Iterable[tuple[str, str]]) -> Iterable[tuple[str, str]]:
    if isinstance(query, Mapping):
        for key, values in query.items():
            for value in values:
                yield key, value
        return
    yield from query


def _display(path: str, query: bytes) -> str:
    return f"{path}?{query.decode('ascii')}" if query else path
