"""Chat routes: the page, the question box, and the stream a reply arrives on."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import StreamingResponse
from fjkit import render
from fjkit.sse import Event, events

from app.dependencies import ChatServiceDep, TemplatesDep
from app.schemas.chat import Ask, ChatResponse, Delta, Ended, Snapshot, TurnResponse

router = APIRouter(tags=["chat"])


@router.get("/chat", name="chat_page")
@render("chat/page.html")
def chat_page(service: ChatServiceDep) -> ChatResponse:
    """Render the conversation so far. A reply still being written reconnects."""
    return ChatResponse(replies=service.list())


@router.post("/chat", name="chat_ask")
@render("chat/_turn.html")
def ask(service: ChatServiceDep, payload: Annotated[Ask, Form()]) -> TurnResponse:
    """Record the question and answer with the turn the log appends: the
    question, and an empty reply bubble that opens its own stream."""
    return TurnResponse(reply=service.ask(payload.question))


@router.get("/chat/{reply_id}/stream", name="chat_stream", include_in_schema=False)
async def chat_stream(
    request: Request, service: ChatServiceDep, templates: TemplatesDep, reply_id: int
) -> StreamingResponse:
    """The reply as server-sent events: `snapshot`, `token`s, then `status` — and,
    when it failed, `failure` first. `fjkit.sse` adds the pings and the closing `done`.

    `async def`, unlike the routes that render: this response stays open while
    the reply is written, and a sync generator would hold a threadpool thread
    for all of it. The partials it renders are a few hundred bytes each.

    Always a 200, even for an id this process never issued. htmx-ext-sse
    reconnects on any closed connection whatever its status, so the only answer
    that ends the bubble's retries is a stream that says why and closes.
    """

    async def source() -> AsyncIterator[Event]:
        async for update in service.follow(reply_id):
            match update:
                case Snapshot(text):
                    yield Event("snapshot", text)
                case Delta(text):
                    yield Event("token", text)
                case Ended(reply, reason):
                    if reason:
                        error = templates.fragment(request, "chat/_error.html", {"reason": reason})
                        yield Event("failure", error)
                    if reply is not None:
                        status = templates.fragment(request, "chat/_status.html", {"reply": reply})
                        yield Event("status", status)

    return events(source())
