"""Server-sent events: the frames `fjkit.sse.events()` writes, and the
`Templates.fragment()` that renders a partial into one.

The frame tests read the wire as text, because every trap the helper exists to
close is a property of the bytes: a stray blank line, a missing header, a
connection that goes silent, a stream that never says it is finished.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, mount_fjkit
from fjkit.sse import Event, events, frame
from markupsafe import Markup


class TestFrame:
    def test_one_line(self):
        assert frame(Event("token", Markup("hi"))) == "event: token\ndata: hi\n\n"

    def test_every_line_of_markup_gets_its_own_data_field(self):
        """A newline inside one `data:` field ends the field, and a blank line
        ends the event: the rest of the partial would arrive as junk fields."""
        html = Markup('<div class="alert">\n  <h2>Failed</h2>\n\n</div>')
        assert frame(Event("failure", html)) == (
            'event: failure\ndata: <div class="alert">\ndata:   <h2>Failed</h2>\ndata: \ndata: </div>\n\n'
        )

    @pytest.mark.parametrize("newline", ["\r\n", "\r"])
    def test_every_line_ending_the_browser_splits_on(self, newline):
        assert frame(Event("token", f"a{newline}b")) == "event: token\ndata: a\ndata: b\n\n"

    def test_text_is_escaped_and_markup_is_not(self):
        """A token from a model is text. `beforeend` parses what it is handed as
        HTML, so the escaping Jinja's autoescape would have done happens here."""
        assert frame(Event("token", "<b>&")) == "event: token\ndata: &lt;b&gt;&amp;\n\n"
        assert frame(Event("token", Markup("<b>"))) == "event: token\ndata: <b>\n\n"

    def test_an_empty_payload_still_has_a_data_field(self):
        """An event with no `data:` line is discarded by `EventSource`, so a
        `done` with nothing to say would never close the connection."""
        assert frame(Event("done")) == "event: done\ndata: \n\n"

    @pytest.mark.parametrize("name", ["", "two\nlines", "a\rb"])
    def test_a_name_that_is_not_one_line_is_refused(self, name):
        with pytest.raises(ValueError):
            Event(name)

    @pytest.mark.parametrize("name", ["error", "open"])
    def test_the_names_eventsource_uses_for_itself_are_refused(self, name):
        """An event named `error` is dispatched to `EventSource.onerror` as
        well as to `sse-swap`, so htmx-ext-sse reports a connection error for a
        message — seen in Chrome as `htmx:sseError` with a `MessageEvent`."""
        with pytest.raises(ValueError, match="EventSource"):
            Event(name)


def _app(source, **options) -> FastAPI:
    app = FastAPI()

    @app.get("/stream")
    async def stream():
        return events(source(), **options)

    return app


def _read(app: FastAPI) -> tuple[dict[str, str], str]:
    with TestClient(app) as client, client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        return dict(response.headers), "".join(response.iter_text())


class TestEvents:
    def test_the_headers_that_keep_a_proxy_from_buffering(self):
        async def source() -> AsyncIterator[Event]:
            yield Event("token", "x")

        headers, _ = _read(_app(source))
        assert headers["content-type"].startswith("text/event-stream")
        assert headers["cache-control"] == "no-cache"
        assert headers["x-accel-buffering"] == "no"

    def test_caller_headers_are_added(self):
        async def source() -> AsyncIterator[Event]:
            yield Event("token", "x")

        headers, _ = _read(_app(source, headers={"X-Reply": "7"}))
        assert headers["x-reply"] == "7"
        assert headers["cache-control"] == "no-cache"

    def test_the_stream_ends_with_the_close_event(self):
        """htmx-ext-sse reconnects forever on a closed connection. The close
        event is the only thing that stops it, so the helper sends it, not the
        app."""

        async def source() -> AsyncIterator[Event]:
            yield Event("token", "a")
            yield Event("token", "b")

        _, body = _read(_app(source))
        assert body == "event: token\ndata: a\n\nevent: token\ndata: b\n\nevent: done\ndata: \n\n"

    def test_the_close_event_can_be_renamed(self):
        async def source() -> AsyncIterator[Event]:
            yield Event("token", "a")

        _, body = _read(_app(source, close="end"))
        assert body.endswith("event: end\ndata: \n\n")

    def test_a_failing_source_still_closes_the_stream(self, caplog):
        """The status is already 200, so the exception cannot become an error
        page. Without the close event the browser would reconnect and hit the
        same failure every 0.5–64 seconds, forever."""

        async def source() -> AsyncIterator[Event]:
            yield Event("token", "a")
            raise RuntimeError("model went away")

        _, body = _read(_app(source))
        assert body == "event: token\ndata: a\n\nevent: done\ndata: \n\n"
        assert "model went away" in caplog.text

    def test_a_silent_source_gets_pinged(self):
        """A comment line keeps a proxy's idle timer from dropping the
        connection during a long tool call. It is not an event, so nothing on
        the page swaps."""

        async def source() -> AsyncIterator[Event]:
            await asyncio.sleep(0.35)
            yield Event("token", "late")

        _, body = _read(_app(source, ping=0.1))
        before, _, after = body.partition("event: token")
        assert before.count(": ping\n\n") >= 2
        assert after == "\ndata: late\n\nevent: done\ndata: \n\n"

    def test_a_busy_source_is_not_pinged(self):
        async def source() -> AsyncIterator[Event]:
            for n in range(3):
                yield Event("token", str(n))

        _, body = _read(_app(source, ping=0.1))
        assert ": ping" not in body


class TestFragment:
    def test_renders_a_partial_to_markup_under_the_root_path(self, tmp_path):
        """The frame needs a string, and `frame()` escapes a plain one. A
        rendered partial is already HTML, so it comes back as `Markup` — and
        its asset URLs carry the mount prefix, as `page()`'s do."""
        (tmp_path / "_bubble.html").write_text(
            '{% from "ui/swap.html" import sse_scripts %}<p>{{ who }}</p>{{ sse_scripts() }}', encoding="utf-8"
        )
        app = FastAPI(root_path="/ui")
        mount_fjkit(app, FjkitConfig(template_dir=tmp_path, auto_reload=False))
        seen: list[object] = []

        @app.get("/fragment")
        def fragment(request: Request) -> dict[str, str]:
            html = request.app.state.templates.fragment(request, "_bubble.html", {"who": "<you>"})
            seen.append(html)
            return {"html": str(html)}

        with TestClient(app) as client:
            html = client.get("/fragment").json()["html"]
        assert isinstance(seen[0], Markup)
        assert "<p>&lt;you&gt;</p>" in html
        assert 'src="/ui/' in html


class TestDisconnect:
    def test_a_closed_stream_closes_the_source_and_sends_nothing_more(self):
        """A client that leaves while the source is waiting: the pending read is
        cancelled and the source's own cleanup runs, so an app can count who is
        still listening."""
        from fjkit.sse import frames

        cleaned: list[str] = []

        async def source() -> AsyncIterator[Event]:
            try:
                yield Event("token", "a")
                await asyncio.sleep(60)
                yield Event("token", "never")
            finally:
                cleaned.append("source")

        async def main() -> list[str]:
            stream = frames(source(), ping=None)
            first = await anext(stream)
            pending = asyncio.ensure_future(anext(stream))
            await asyncio.sleep(0.05)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            await stream.aclose()
            return [first]

        assert asyncio.run(main()) == ["event: token\ndata: a\n\n"]
        assert cleaned == ["source"]
