"""Run one request against the app itself and record what came back.

The obvious implementation is the one Swagger UI uses: `fetch()` from the page.
It is also the one that cannot work here. The credential this kit issues is an
HttpOnly cookie — no script can read it, attach it, or refresh it — and the
whole point of `fjkit.auth` is that this is a feature. A console built on
`fetch()` would either send no credential at all or force the app to hand one
to JavaScript, which is the design being replaced.

So the call is made **server-side, in-process**: a fresh ASGI scope through
`app` itself. Everything the browser would have contributed is forwarded from
the console's own request — the session cookie above all — which means the
call travels the real middleware stack. `AuthPlugin` loads the session, renews
the token if it is expiring, and refuses the call if it cannot. What you see in
the result panel is what the endpoint does for *you*, right now.

No socket is opened and no server needs to be reachable from itself, so this
works behind a proxy, in a test client, and on a machine with no route to its
own public hostname.
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
from urllib.parse import urlencode

from fastapi import Request

from fjkit.rendering import SCOPE_RENDER_MODE

__all__ = ["Recorded", "RecursionRefused", "call"]

#: Request headers the console never forwards from its own request. Each one
#: describes the console's POST rather than the call being made: a length and a
#: content type that belong to the form, and the htmx headers, which name the
#: element *this page* is swapping. An app that reads `HX-Target` would act on
#: a target that has nothing to do with the endpoint it is answering.
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
#: can be refused rather than recursing until the stack runs out.
_DEPTH_KEY = "fjkit_apidocs_depth"

#: Where an escaping exception is written.
#:
#: This is the one thing an in-process replay genuinely takes away. A request
#: that arrives over a socket has a server above it — uvicorn, gunicorn — whose
#: job is to log the traceback of anything the app lets through. Here the caller
#: is this module, `except Exception` is what stops a failing endpoint from
#: 500-ing the docs page along with it, and without this line the traceback
#: would exist nowhere: the panel gets `ZeroDivisionError: division by zero` and
#: no file, no line, no frames. The report is for the person reading the page;
#: this is for the same person ten seconds later, reading the log.
_log = logging.getLogger("fjkit.apidocs.console")


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
    #: Set instead of a status when the call never produced a response — a
    #: timeout, or an exception escaping the app.
    error: str = ""
    request_headers: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400

    @property
    def reason(self) -> str:
        """The status line's phrase — `OK`, `Not Found` — or nothing.

        Driven by the status and not by `error`, because the two are
        independent: ServerErrorMiddleware sends a 500 and then re-raises, so a
        call can have both a real status and an escaped exception. Answering
        "no response" here put that phrase *next to the 500* the app had
        plainly sent, which is a debugging tool contradicting itself in one
        badge.
        """
        if not self.status:
            return ""
        try:
            return HTTPStatus(self.status).phrase
        except ValueError:
            return ""

    @property
    def tone(self) -> str:
        """The badge variant for the status. Closed set — see `ui/data.html`."""
        if self.error:
            return "destructive"
        if self.status >= 500:
            return "destructive"
        if self.status >= 400:
            return "warning"
        if self.status >= 300:
            return "info"
        return "success"

    @property
    def pretty(self) -> str:
        """The body, re-indented when it is JSON and left alone when it is not."""
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

    `request` is the console's own request, and it is the source of everything
    that makes the call *this caller's* call: the cookie jar, the origin, the
    client address, the root path a proxy put in front of the app.
    """
    app = request.app
    root_path: str = request.scope.get("root_path", "") or ""
    target = path if path.startswith("/") else f"/{path}"

    if forbidden_prefix and (target == forbidden_prefix or target.startswith(f"{forbidden_prefix}/")):
        raise RecursionRefused(
            f"{target} is the API console itself. Calling it from here would re-enter this "
            "handler, and the only thing it can report is that it is reporting."
        )
    if request.scope.get(_DEPTH_KEY):
        raise RecursionRefused("this request is already a console call")

    query_string = urlencode(list(_pairs(query)), doseq=False).encode("ascii")
    sent = _headers(request, headers or {}, body)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": request.url.scheme,
        # `root_path` included in `path`, which is what a server sends and what
        # Starlette's router expects to strip. Getting this wrong is invisible
        # until the app is mounted under a prefix, and then every call 404s.
        "path": f"{root_path}{target}",
        "raw_path": f"{root_path}{target}".encode(),
        "root_path": root_path,
        "query_string": query_string,
        "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in sent],
        "client": request.scope.get("client"),
        "server": request.scope.get("server"),
        # Whatever the server put in lifespan state — a connection pool, a
        # client — has to survive, or every app that keeps its dependencies
        # there gets a console that only knows how to raise. It is a shallow
        # copy: values are shared, but a key this call sets does not leak back
        # into the console's own request.
        "state": dict(request.scope.get("state") or {}),
        # Ask for the data, not the page. A console that showed a full HTML
        # document where the API returns a model is answering a question nobody
        # asked — and under `render_mode="auto"` that is what a page route hands
        # back, because `serves_a_page` is decided by the route's shape rather
        # than by who is calling. This says who is calling. A route that
        # declared `mode="html"` still wins: it has said it has no data form,
        # and the console is not the place to overrule that.
        SCOPE_RENDER_MODE: "json",
        _DEPTH_KEY: 1,
    }

    received = False

    async def receive() -> Mapping[str, Any]:
        nonlocal received
        if received:
            # An app that reads the body twice — or a middleware that does —
            # must not be left hanging on a message that never arrives.
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    recorded = Recorded(
        method=method.upper(),
        url=_display(target, query_string),
        status=0,
        request_headers=tuple(sent),
    )
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
            # Counted before the cap so a stream that never ends still stops
            # accumulating rather than stopping only once it fits.
            size += len(chunk)

    started = time.perf_counter()
    try:
        await asyncio.wait_for(app(scope, receive, send), timeout=timeout)
    except TimeoutError:
        recorded.error = f"the call did not finish within {timeout:g}s"
    except Exception as exc:  # noqa: BLE001 — the console's job is to report it
        # Reporting beats 500-ing the docs page, which would lose the request
        # the developer just spent a minute filling in. But reporting is not
        # swallowing: the traceback goes to the log first, because this module
        # is standing where a real server would be and nothing else is going to
        # write it down.
        #
        # `recorded.status` may well be set by the time this runs. Starlette's
        # ServerErrorMiddleware sends its 500 and *then* re-raises, so both
        # halves are true at once — the app answered, and something escaped
        # afterwards. The result panel shows both.
        _log.exception("fjkit apidocs: %s %s raised", method.upper(), target)
        recorded.error = f"{type(exc).__name__}: {exc}"
    recorded.elapsed_ms = (time.perf_counter() - started) * 1000

    raw = b"".join(chunks)
    recorded.truncated = size > max_body
    recorded.body = raw.decode("utf-8", errors="replace")
    return recorded


def _headers(request: Request, extra: Mapping[str, str], body: bytes) -> list[tuple[str, str]]:
    """The console's own headers, minus its plumbing, plus the flow's.

    Forwarding the cookie is the entire mechanism: it is what makes this the
    caller's session rather than an anonymous one. Forwarding `origin` matters
    almost as much — `fjkit.auth` checks it on every cookie-authenticated
    write, so a call made without it would be refused as CSRF and the console
    would look broken on exactly the endpoints it is most useful for.
    """
    # Lowercased, because ASGI says so and because Starlette's `Headers` takes
    # it literally: it lowercases the name you *ask* for and compares it to the
    # raw bytes in the scope. A header spelled `Authorization` there is invisible
    # to `request.headers["authorization"]` — present on the wire, absent to
    # every handler, and silent about it.
    out = [(k.lower(), v) for k, v in request.headers.items() if k.lower() not in _DROPPED]
    for key, value in extra.items():
        # A flow's header replaces rather than joins: two `Authorization`
        # headers is not a thing an app can act on.
        name = key.lower()
        out = [(k, v) for k, v in out if k != name]
        out.append((name, value))
    if body:
        out.append(("content-length", str(len(body))))
    return out


def _pairs(query: Mapping[str, list[str]] | Iterable[tuple[str, str]]) -> Iterable[tuple[str, str]]:
    if isinstance(query, Mapping):
        for key, values in query.items():
            for value in values:
                yield key, value
        return
    yield from query


def _display(path: str, query: bytes) -> str:
    return f"{path}?{query.decode('ascii')}" if query else path
