"""The conversation, the replies being written, and the readers following them.

**A producer and any number of readers, never one generator.** The stream
endpoint is opened again every time htmx-ext-sse reconnects — after a network
drop, a proxy timeout, a reload — and a reconnect sends no `Last-Event-ID`. If
the endpoint were the generator, a dropped connection would cancel the reply
and the reconnect would start a second one. So generation runs as its own task,
writing into the reply, and `follow()` only reads: a snapshot of the text so
far, then each addition, then the end.

**Generation starts on the first read**, and a second read finds it running.
`ask()` only records the question, so the route that takes it can stay a `def`
— and a reply whose bubble never connects never costs a token.

Three ways a reply stops without finishing, each ending in `FAILED` with a
reason the bubble shows: the model raises; the reply runs past `max_seconds`;
or nobody has been reading for `grace_seconds`. The grace period is why a
closed tab does not stop the reply at once: for a moment a reconnect and a
departure look the same.

**One process only.** Replies live in this object's memory, so a reconnect
that lands on another uvicorn worker finds nothing and is told the reply was
interrupted. More than one worker needs the replies in a shared store — Redis,
a table — or sticky sessions.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from itertools import count
from threading import Lock
from time import monotonic

from app.schemas.chat import INTERRUPTED, Delta, Ended, Reply, ReplyState, Snapshot, Update
from app.services.chat.agent import AgentError, answer


@dataclass
class _Live:
    """A reply, and the bookkeeping that is not part of it."""

    reply: Reply
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    readers: int = 0
    #: When the last reader left; `None` while somebody is reading.
    left_at: float | None = None


class ChatService:
    def __init__(
        self,
        token_seconds: float = 0.06,
        tool_seconds: float = 2.5,
        grace_seconds: float = 60.0,
        max_seconds: float = 120.0,
    ) -> None:
        # Seconds between tokens, and of the pause a tool call makes; tests pass 0.
        self.token_seconds = token_seconds
        self.tool_seconds = tool_seconds
        self.grace_seconds = grace_seconds
        self.max_seconds = max_seconds
        self._lock = Lock()
        self._ids = count(1)
        self._live: dict[int, _Live] = {}

    def list(self) -> list[Reply]:
        """Every reply, oldest first."""
        return [live.reply for live in self._live.values()]

    def get(self, reply_id: int) -> Reply | None:
        live = self._live.get(reply_id)
        return live.reply if live else None

    def ask(self, question: str) -> Reply:
        """Record a question and an empty reply to it."""
        with self._lock:
            reply = Reply(id=next(self._ids), question=question)
            self._live[reply.id] = _Live(reply)
            return reply

    async def follow(self, reply_id: int) -> AsyncIterator[Update]:
        """The reply as it is now, then as it grows, then how it ended."""
        live = self._live.get(reply_id)
        if live is None:
            yield Snapshot("")
            yield Ended(None, INTERRUPTED)
            return

        if live.task is None and live.reply.streaming:
            live.task = asyncio.create_task(self._write(live))
        live.readers += 1
        live.left_at = None
        try:
            sent = len(live.reply.text)
            yield Snapshot(live.reply.text)
            while True:
                # Both taken before the first `yield`: the writer runs while this
                # reader is suspended there. The event, so a change made then
                # sets the one about to be waited on; the reply, so its text and
                # its state are read from the same moment — read the state
                # afterwards, and a reply that finished meanwhile ends without
                # its last words.
                changed = live.changed
                reply = live.reply
                if len(reply.text) > sent:
                    yield Delta(reply.text[sent:])
                    sent = len(reply.text)
                if not reply.streaming:
                    yield Ended(reply, reply.error)
                    return
                await changed.wait()
        finally:
            live.readers -= 1
            if live.readers == 0:
                live.left_at = monotonic()

    async def _write(self, live: _Live) -> None:
        """Generate the reply into `live`, until it ends one way or another."""
        try:
            async with asyncio.timeout(self.max_seconds):
                async for token in answer(
                    live.reply.question, token_seconds=self.token_seconds, tool_seconds=self.tool_seconds
                ):
                    if self._abandoned(live):
                        self._end(live, "Nobody was reading, so the reply was stopped.")
                        return
                    self._update(live, text=live.reply.text + token)
        except AgentError as exc:
            self._end(live, str(exc))
        except TimeoutError:
            self._end(live, f"The reply took longer than {self.max_seconds:g} seconds and was stopped.")
        else:
            self._update(live, state=ReplyState.DONE)

    def _abandoned(self, live: _Live) -> bool:
        return live.left_at is not None and monotonic() - live.left_at > self.grace_seconds

    def _end(self, live: _Live, reason: str) -> None:
        self._update(live, state=ReplyState.FAILED, error=reason)

    def _update(self, live: _Live, **changes: object) -> None:
        """Replace the reply and wake every reader waiting on it."""
        live.reply = live.reply.model_copy(update=changes)
        changed, live.changed = live.changed, asyncio.Event()
        changed.set()

    async def aclose(self) -> None:
        """Cancel every reply still being written. Called when the app shuts down."""
        tasks = [live.task for live in self._live.values() if live.task and not live.task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
