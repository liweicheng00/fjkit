"""Wire contracts for the chat page, and the updates its stream is built from.

A reply is the record the stream reads, not the stream itself. That split is
what makes the stream endpoint safe to open twice: htmx-ext-sse reconnects
whenever the connection drops, a reconnect sends no `Last-Event-ID`, and so
every open starts from the reply as it stands now.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, computed_field


class ReplyState(StrEnum):
    STREAMING = "streaming"
    DONE = "done"
    FAILED = "failed"


#: Reply state -> badge variant.
STATE_VARIANT: dict[ReplyState, str] = {
    ReplyState.STREAMING: "info",
    ReplyState.DONE: "success",
    ReplyState.FAILED: "destructive",
}

#: Reply state -> badge label.
STATE_LABEL: dict[ReplyState, str] = {
    ReplyState.STREAMING: "Writing",
    ReplyState.DONE: "Done",
    ReplyState.FAILED: "Stopped",
}

#: What a stream says about a reply this process has never heard of — the
#: in-memory store is gone after a restart or a `fastapi dev` reload. A 404
#: would not stop htmx-ext-sse reconnecting; a 200 that says so and closes does.
INTERRUPTED = "This reply was interrupted: the server restarted before it finished."


class Ask(BaseModel):
    """Form body of the question box."""

    question: str = Field(min_length=1, max_length=500)


class Reply(BaseModel):
    id: int
    question: str
    text: str = ""
    state: ReplyState = ReplyState.STREAMING
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def streaming(self) -> bool:
        """True until the reply is finished. Only a streaming bubble opens a connection."""
        return self.state is ReplyState.STREAMING

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state_variant(self) -> str:
        return STATE_VARIANT[self.state]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state_label(self) -> str:
        return STATE_LABEL[self.state]


class ChatResponse(BaseModel):
    """The whole conversation, oldest first: a reload shows every turn so far."""

    replies: list[Reply]


class TurnResponse(BaseModel):
    """One question and the reply to it — what `POST /chat` appends to the log."""

    reply: Reply


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The reply's text so far. First on every open, so a reconnect redraws
    the bubble instead of appending to what it already shows."""

    text: str


@dataclass(frozen=True, slots=True)
class Delta:
    """Text added since the last update."""

    text: str


@dataclass(frozen=True, slots=True)
class Ended:
    """The reply is finished. `reply` is `None` when the id is unknown."""

    reply: Reply | None
    reason: str | None = None


#: What `ChatService.follow()` yields: a snapshot, deltas, then one `Ended`.
Update = Snapshot | Delta | Ended
