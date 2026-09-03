"""A message shown to the person who made the current request.

Three layers deep, and this is the middle one:

1. **The surface** — `ui/feedback.html`'s `toaster()` region and `toast()`
   macro. Already core: `ui/shell.html` renders the region on every page,
   whether or not anything is in it.
2. **Getting a message onto this response** — here.
3. **Surviving a redirect** — `fjkit.flash`, a plugin rather than core because
   it needs a signing secret.

Layer 3 is not a superset of layer 2. `FlashPlugin` writes a signed cookie,
because a redirect replaces the page and the document that would have shown the
message is gone before it arrives. The reverse holds too: on a response that is
not a redirect, a cookie is a round trip for a message about to be rendered
anyway. So the two are layered rather than merged, and flash queues into this
module.

    from fjkit import messages

    messages.add(request, "Saved", category="success")

How it reaches the browser depends on what the response is, and the caller
never has to know which:

    full page render   ->  the shell renders it, straight into the toaster
    htmx swap          ->  `HX-Trigger`, and the shell's listener raises it

`HX-Trigger` rather than markup, because a fragment carries no toaster: an htmx
swap replaces one region, and the region a toast belongs in is elsewhere on the
page. It also works on a response htmx will not swap at all — htmx reads
`HX-Trigger` in `handleAjaxResponse` before it consults `responseHandling` for
the status code, so a 422 or a 500 can still raise a toast on the page the user
is looking at. That is the whole delivery mechanism for `fjkit.errors`.

A message is consumed by being **iterated**, not by being looked at. See
`_Queue`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import Request

__all__ = [
    "TOAST_EVENT",
    "Category",
    "Message",
    "add",
    "extend",
    "queue",
    "shown",
    "trigger_header",
]

#: What a message means, not what colour it is. `toast()` maps each to an icon
#: and a timeout, and `fjkit.css` maps each to a role token — so "error is red"
#: is decided once, in the stylesheet, and survives a rebrand.
Category = Literal["info", "success", "warning", "error"]

#: The DOM event `HX-Trigger` names, and the one `ui/shell.html` listens for.
#: Namespaced because it lands on `document.body`, where an app's own events
#: live too.
TOAST_EVENT = "fjkit:toast"

_SLOT = "fjkit_messages"
_SHOWN = "fjkit_messages_shown"


@dataclass(frozen=True, slots=True)
class Message:
    """One message. `category` picks the icon, the timeout and the role colour."""

    title: str
    text: str | None = None
    category: Category = "info"

    def as_detail(self) -> dict[str, str]:
        """Return the shape Basecoat's toaster constructor takes.

        `text` is renamed to `description` here rather than in the dataclass:
        the field is called `text` everywhere in fjkit and in `toast()`, and a
        vendored library's parameter name is not a reason to rename a field
        across the kit's own API.
        """
        detail: dict[str, str] = {"category": self.category, "title": self.title}
        if self.text is not None:
            detail["description"] = self.text
        return detail


def queue(request: Request | None) -> _Queue:
    """Return this request's messages, creating the queue on first use.

    Lazy rather than built in middleware: core adds no middleware, so an app
    that never raises a message pays nothing — not a stack frame, not an
    attribute.

    `request` may be `None`. The docs-site builder and the render benchmark
    drive the same templates with `request=None`, and the shell reads this on
    every page; a render with nowhere to put a message has none.
    """
    state = getattr(request, "state", None)
    if state is None:
        return _Queue(None)
    existing = getattr(state, _SLOT, None)
    if existing is None:
        existing = _Queue(request)
        setattr(state, _SLOT, existing)
    return existing


def add(request: Request, title: str, text: str | None = None, *, category: Category = "info") -> None:
    """Show a message on this response. The one-message form of `extend`."""
    queue(request).append(Message(title=title, text=text, category=category))


def extend(request: Request, messages: Sequence[Message]) -> None:
    """Queue several at once. `FlashPlugin` uses it to hand over its cookie."""
    queue(request).extend(messages)


def shown(request: Request) -> bool:
    """Whether this request's messages actually reached the browser.

    True once they have been iterated into a template or serialised into an
    `HX-Trigger`. `FlashPlugin` reads it to decide whether to clear its cookie:
    a message queued but never rendered has not been shown, and clearing it
    would lose it.
    """
    return bool(getattr(request.state, _SHOWN, False))


def trigger_header(request: Request, existing: str | None = None) -> str | None:
    """The `HX-Trigger` value carrying this request's messages, or `None`.

    Shaped as `{"fjkit:toast": {"messages": [...]}}`.

    Merges rather than replaces. A handler may already have set `HX-Trigger`
    for its own event, and dropping it because a toast happened to be queued is
    a bug that surfaces only when both are in play. htmx accepts a bare event
    name as well as a JSON object, so a plain string is promoted to
    `{"<name>": null}` before ours is added.
    """
    pending = getattr(request.state, _SLOT, None)
    if not pending:
        return existing

    events: dict[str, Any] = {}
    if existing:
        text = existing.strip()
        if text.startswith("{"):
            try:
                events = json.loads(text)
            except ValueError:
                # Not ours to repair, and not ours to discard either: keep it
                # as an event name so the handler's intent survives.
                events = {text: None}
        else:
            events = {name.strip(): None for name in text.split(",") if name.strip()}

    # `{"messages": [...]}` and not the bare list, because htmx unwraps the two
    # differently: a plain object becomes `event.detail`, while anything else —
    # an array included — is wrapped as `{value: …}`. Sending an object keeps
    # the payload in the shape the listener reads, rather than making the shell
    # depend on a rule inside a vendored file.
    events[TOAST_EVENT] = {"messages": [message.as_detail() for message in pending.drain()]}
    return json.dumps(events, separators=(",", ":"))


class _Queue:
    """The messages, plus the fact of having been delivered.

    Consumption is **iteration**. `{% for m in fjkit_messages(request) %}` marks
    them shown; `{% if fjkit_messages(request) %}` does not, because asking
    whether there is anything to show is not showing it.

    That distinction is load-bearing for `FlashPlugin`, which clears its cookie
    only once the message reached a page. A page load fires more requests than
    the page — an htmx poll, a prefetch — and "this request carried the cookie"
    would let any of them eat the message. "A render happened" is not enough
    either: an htmx swap renders a partial, and a partial carries no toaster.
    Django's messages framework draws the line in the same place, for the same
    reason.
    """

    __slots__ = ("_messages", "_request")

    def __init__(self, request: Request | None) -> None:
        self._messages: list[Message] = []
        self._request = request

    def append(self, message: Message) -> None:
        self._messages.append(message)

    def extend(self, messages: Sequence[Message]) -> None:
        self._messages.extend(messages)

    def drain(self) -> tuple[Message, ...]:
        """Take the messages for delivery down a channel that is not a template.

        Emptying the queue stops a message being delivered twice when a
        response both carries an `HX-Trigger` and renders a toaster.
        """
        self._mark()
        taken = tuple(self._messages)
        self._messages.clear()
        return taken

    def _mark(self) -> None:
        if self._request is not None:
            setattr(self._request.state, _SHOWN, True)

    def __bool__(self) -> bool:
        return bool(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self) -> Iterator[Message]:
        if self._messages:
            self._mark()
        return iter(tuple(self._messages))
