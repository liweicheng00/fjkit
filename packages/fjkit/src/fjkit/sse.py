"""Server-sent events: the frames htmx's `sse` extension reads.

A reply that arrives in pieces — an agent's answer token by token — is one
response the server keeps writing to. The app owns where the pieces come from;
this module owns how they are written, because the ways to write them wrongly
fail silently and identically in every app (CHARTER §2.3, gate 2):

* **A `data:` field is one line.** A rendered partial has newlines in it, and a
  blank line ends the event. Written as one field, the partial arrives cut off
  at its first blank line, and what follows is read as junk fields.
* **A proxy buffers by default.** nginx holds a response until it has enough
  bytes to be worth sending, which for a stream of single tokens is never.
  `Cache-Control: no-cache` and `X-Accel-Buffering: no` turn that off.
* **A silent connection gets dropped.** A model that spends forty seconds in a
  tool call writes nothing for forty seconds, and a proxy's idle timeout closes
  the connection. A comment line every `ping` seconds keeps it open, and the
  browser ignores it.
* **A stream that just stops is read again, forever.** htmx-ext-sse reconnects
  whenever the connection closes, for any reason and with any status code,
  until the event named in `sse-close` arrives. So the last frame is always that
  event — after the source finishes, and after it raises.

The app's stream endpoint therefore has to be re-readable: a reconnect is a
fresh `EventSource` that sends no `Last-Event-ID`, so whatever the endpoint
sends on open has to make sense the second time too. That is a property of the
app's data, not of the frames, and the demo's chat page shows one way to have
it.

No third-party dependency. `sse-starlette` covers the same ground and more, but
as a third runtime dependency (CHARTER §4.1) and a starlette floor that would
pin the user's FastAPI range. An app that prefers it maps each `Event` to its
`ServerSentEvent(event=e.name, data=str(escape(e.data)))`; it splits the lines
itself.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterable, AsyncIterator, Mapping
from contextlib import suppress
from dataclasses import dataclass

from fastapi.responses import StreamingResponse
from markupsafe import escape

__all__ = ["CLOSE_EVENT", "PING_SECONDS", "Event", "events", "frame", "frames"]

logger = logging.getLogger(__name__)

#: Seconds of silence before a `: ping` comment. Under the 60 s that nginx's
#: `proxy_read_timeout` defaults to, with room for a slow first byte.
PING_SECONDS = 15.0

#: The event a stream always ends with. The page's `sse-close` names the same
#: event, which is what stops the extension reconnecting.
CLOSE_EVENT = "done"

#: The three line endings `EventSource` splits a stream on. `str.splitlines()`
#: splits on eight more, so a form feed in a model's output would become a line
#: break the browser never wrote.
_LINE = re.compile(r"\r\n|\r|\n")

_PING = ": ping\n\n"


@dataclass(frozen=True, slots=True)
class Event:
    """One named event: `name` is what `sse-swap` listens for, `data` what it swaps in.

    `data` is escaped unless it is `Markup`, the same rule Jinja's autoescape
    applies. A token from a model is text, and `beforeend` parses whatever it is
    handed as HTML — a reply containing `<img onerror=…>` would otherwise run.
    A rendered partial is already HTML: `Templates.fragment()` returns it as
    `Markup`, so it passes through.
    """

    name: str
    data: str = ""

    def __post_init__(self) -> None:
        if not self.name or _LINE.search(self.name):
            raise ValueError(f"{self.name!r} is not an event name: it must be one non-empty line.")


def frame(event: Event) -> str:
    """The bytes of one event on the wire: an `event:` line, a `data:` line per
    line of the payload, and the blank line that dispatches it.

    An empty payload still gets its `data:` line. `EventSource` discards an event
    with no data, so a bare `done` would never reach `sse-close`.
    """
    lines = _LINE.split(str(escape(event.data)))
    return f"event: {event.name}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


async def frames(
    source: AsyncIterable[Event],
    *,
    ping: float | None = PING_SECONDS,
    close: str = CLOSE_EVENT,
) -> AsyncIterator[str]:
    """Write `source` as frames, a ping into every silence, and `close` last.

    `close` is sent after the source is exhausted and after it raises. The
    response is already a 200 by the time anything fails, so the exception
    cannot become an error page; it is logged, and the app that wants the person
    to see a failure yields an event for it before it gives up. Not sent when the
    client disconnects: there is nobody to send it to, and the cancellation
    propagates so the server stops writing.

    `ping=None` sends no pings.
    """
    iterator = aiter(source)
    pending: asyncio.Future[Event] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(iterator))
            # `wait`, not `wait_for`: a timeout here must not cancel the source,
            # which is still working on the next event while the ping goes out.
            done, _ = await asyncio.wait({pending}, timeout=ping)
            if not done:
                yield _PING
                continue
            finished, pending = pending, None
            try:
                event = finished.result()
            except StopAsyncIteration:
                break
            yield frame(event)
    except Exception:
        logger.exception("An event source raised; the stream was closed with %r.", close)
    finally:
        if pending is not None:
            pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()
    yield frame(Event(close))


def events(
    source: AsyncIterable[Event],
    *,
    ping: float | None = PING_SECONDS,
    close: str = CLOSE_EVENT,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> StreamingResponse:
    """A `text/event-stream` response over `source`, framed by `frames()`.

    Return it from an `async def` handler. The render-in-`def` rule is for a
    response that is finished when the handler returns; this one is open for as
    long as the source keeps yielding, and a sync generator would hold a
    threadpool thread for all of it.

        @router.get("/chat/{reply_id}/stream")
        async def stream(reply_id: int, request: Request, service: ChatDep):
            async def source():
                async for text in service.follow(reply_id):
                    yield Event("token", text)
            return events(source())

    `headers` are added to the two that keep a proxy from buffering, and win
    over them.
    """
    return StreamingResponse(
        frames(source, ping=ping, close=close),
        status_code=status_code,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **(headers or {})},
    )
