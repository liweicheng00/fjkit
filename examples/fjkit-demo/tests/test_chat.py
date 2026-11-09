"""The chat page: a reply streamed into a bubble over server-sent events.

Every stream test reads the wire, because what htmx-ext-sse does with it is
decided by the frames: which event comes first, whether `done` comes at all.
"""

from __future__ import annotations

import asyncio
import re

import pytest
from app.schemas.chat import INTERRUPTED, ReplyState
from app.services.chat import ChatService
from app.services.chat.agent import script


@pytest.fixture
def chat(client):
    """The app's chat service with every delay set to zero."""
    service = client.app.state.chat
    service.token_seconds = 0
    service.tool_seconds = 0
    return service


def read(client, url: str) -> list[tuple[str, str]]:
    """The (event, data) pairs of one stream, in order, pings left out."""
    with client.stream("GET", url) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    events = []
    for block in body.split("\n\n"):
        lines = block.split("\n")
        names = [line.removeprefix("event: ") for line in lines if line.startswith("event: ")]
        if names:
            data = "\n".join(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
            events.append((names[0], data))
    return events


def test_the_page_loads_the_extension(client):
    response = client.get("/chat")
    assert response.status_code == 200
    assert "vendor/htmx/sse.min.js" in response.text
    assert 'id="chat-log"' in response.text
    assert 'name="question"' in response.text


def test_asking_appends_a_turn_whose_reply_connects(htmx, chat):
    response = htmx.post("/chat", data={"question": "What is <htmx>?"})

    assert response.status_code == 200
    assert "What is &lt;htmx&gt;?" in response.text
    assert 'hx-ext="sse"' in response.text
    assert 'sse-connect="/chat/1/stream"' in response.text
    assert 'sse-close="done"' in response.text
    assert 'sse-swap="snapshot"' in response.text
    assert 'sse-swap="token"' in response.text


def test_an_empty_question_is_rejected(htmx, chat):
    assert htmx.post("/chat", data={"question": ""}).status_code == 422


def test_the_stream_opens_with_a_snapshot_and_ends_with_done(htmx, chat):
    htmx.post("/chat", data={"question": "Explain SSE"})

    events = read(htmx, "/chat/1/stream")

    names = [name for name, _ in events]
    assert names[0] == "snapshot"
    assert names[-2:] == ["status", "done"]
    assert set(names[1:-2]) == {"token"}
    text = events[0][1] + "".join(data for name, data in events if name == "token")
    assert text == script("Explain SSE").replace('"', "&#34;")
    assert "Done" in events[-2][1]


def test_tokens_are_escaped(htmx, chat):
    htmx.post("/chat", data={"question": "<script>alert(1)</script>"})

    events = read(htmx, "/chat/1/stream")

    tokens = "".join(data for name, data in events if name in ("snapshot", "token"))
    assert "<script>" not in tokens
    assert "&lt;script&gt;" in tokens


def test_a_second_read_replays_the_reply_as_one_snapshot(htmx, chat):
    """A reconnect is a fresh `EventSource`: it gets the whole text again, as
    a snapshot the bubble replaces itself with, rather than tokens appended to
    what it already shows."""
    htmx.post("/chat", data={"question": "Explain SSE"})
    first = read(htmx, "/chat/1/stream")

    again = read(htmx, "/chat/1/stream")

    full = first[0][1] + "".join(data for name, data in first if name == "token")
    assert [name for name, _ in again] == ["snapshot", "status", "done"]
    assert again[0][1] == full


def test_an_unknown_reply_is_a_200_that_closes(htmx, chat):
    """A 404 would not stop the extension reconnecting; this does."""
    events = read(htmx, "/chat/99/stream")

    assert [name for name, _ in events] == ["snapshot", "failure", "done"]
    assert INTERRUPTED in events[1][1]
    assert 'class="alert"' in events[1][1]


def test_a_failing_model_ends_in_an_error_and_done(htmx, chat):
    htmx.post("/chat", data={"question": "Please fail halfway"})

    events = read(htmx, "/chat/1/stream")

    names = [name for name, _ in events]
    assert names[-3:] == ["failure", "status", "done"]
    assert "stopped responding" in events[-3][1]
    assert chat.get(1).state is ReplyState.FAILED


def test_the_page_draws_finished_replies_without_a_connection(htmx, client, chat):
    htmx.post("/chat", data={"question": "Explain SSE"})
    read(htmx, "/chat/1/stream")

    page = client.get("/chat").text

    assert "sse-connect" not in page
    assert script("Explain SSE")[:40].replace('"', "&#34;") in page


def test_the_page_reconnects_a_reply_still_streaming(htmx, client, chat):
    htmx.post("/chat", data={"question": "Explain SSE"})

    page = client.get("/chat").text

    assert 'sse-connect="/chat/1/stream"' in page


def test_a_reply_that_runs_too_long_is_stopped(htmx, chat):
    chat.token_seconds = 0.05
    chat.max_seconds = 0.1
    htmx.post("/chat", data={"question": "Explain SSE"})

    events = read(htmx, "/chat/1/stream")

    assert [name for name, _ in events][-3:] == ["failure", "status", "done"]
    assert "took longer than" in events[-3][1]


def test_nobody_reading_stops_generation_after_the_grace_period():
    """Closing the tab must not stop the reply at once — a reconnect looks the
    same for a moment — but a reply nobody comes back for stops costing tokens."""

    async def main() -> ChatService:
        service = ChatService(token_seconds=0.01, tool_seconds=0, grace_seconds=0.05)
        reply = service.ask("Explain SSE")
        stream = service.follow(reply.id)
        await anext(stream)
        await stream.aclose()
        await asyncio.sleep(0.5)
        return service

    service = asyncio.run(main())
    reply = service.get(1)
    assert reply.state is ReplyState.FAILED
    assert "Nobody was reading" in reply.error
    assert len(reply.text) < len(script("Explain SSE"))


def test_the_sidebar_links_the_page(client):
    assert re.search(r'href="/chat"', client.get("/").text)
