"""Wire contracts for the session panel."""

from __future__ import annotations

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """What the panel needs, whichever of its two states it is in.

    `username` is echoed from the session rather than read out of the template's
    `session` global, because a partial reads what its router put in the context
    (CLAUDE.md). The `session` global is demonstrated where it earns its keep —
    the sidebar, on every page, with no router involved.
    """

    signed_in: bool
    username: str | None = None
    #: Set only after a failed attempt. The panel comes back with a 200 so htmx
    #: swaps it: htmx leaves the DOM alone on a 4xx, so an error rendered with
    #: a 401 would be a form that silently does nothing.
    error: str | None = None
    #: Shown in the form, because this demo has exactly one account and hiding
    #: it would only mean writing it in a comment nobody reads.
    demo_username: str
    demo_password: str


class SecretResponse(BaseModel):
    """The protected fragment. Small on purpose — the interesting part is that
    the route answers at all."""

    username: str
