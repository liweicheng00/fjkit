"""The three seams an app can replace, and the record they all move around.

Storage and credential exchange are separate protocols because they vary
independently: swapping password login for OpenID Connect (OIDC) should not
touch a Redis call, and moving from memory to Redis should not touch login code.
One combined interface would force both rewrites.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from fastapi import Request, Response

__all__ = [
    "Csrf",
    "RefreshableTokenSource",
    "Session",
    "SessionStore",
    "TokenSource",
    "decode",
    "encode",
]


@dataclass(frozen=True, slots=True)
class Session:
    """One login, as the server holds it. Nothing here reaches the browser.

    `access is None` is the ordinary state for an app with no upstream API, and
    is what `LocalSource` produces. `claims` is the app's own data and must be
    JSON-serialisable: the payload is encoded with the standard library, which
    is the price of fjkit's two runtime dependencies (CHARTER §7) and the only
    place that price shows.

    `expires_at` must carry a timezone, and is what enables refresh. A source
    that reports none gets no refresh, because nothing triggers it.
    """

    claims: Mapping[str, Any] = field(default_factory=dict)
    access: str | None = None
    refresh: str | None = None
    expires_at: datetime | None = None


def encode(session: Session) -> bytes:
    """Serialise a `Session` to the bytes a store keeps."""
    return json.dumps(
        {
            "claims": dict(session.claims),
            "access": session.access,
            "refresh": session.refresh,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def decode(payload: bytes) -> Session:
    """Invert `encode`. Raises `ValueError` on anything else."""
    data = json.loads(payload)
    expires_at = data.get("expires_at")
    return Session(
        claims=data.get("claims") or {},
        access=data.get("access"),
        refresh=data.get("refresh"),
        expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
    )


@runtime_checkable
class SessionStore(Protocol):
    """Where sessions live. Moves opaque bytes, not `Session` objects.

    Encoding belongs to the plugin, so no backend reimplements it, and a store
    that never inspects the payload cannot grow an opinion about its contents.

    Every method is `async`, and there is no synchronous variant: two parallel
    hierarchies would make every implementer pick a side, while `MemoryStore`
    shows an async signature over synchronous work costs nothing. Wrap a
    blocking implementation in `SyncStore`.
    """

    async def get(self, sid: str) -> bytes | None: ...

    async def put(self, sid: str, payload: bytes, ttl: int) -> None:
        """Store `payload`, expiring after `ttl` seconds."""

    async def delete(self, sid: str) -> None: ...

    async def acquire_refresh_lock(self, sid: str, ttl: int) -> bool:
        """Return True if this caller may refresh, False if another already is.

        Without the lock, a page firing four htmx swaps at once sends four
        refreshes, and an upstream that rotates refresh tokens revokes the whole
        family when the second arrives, logging the user out mid-click.

        The loser does not block here. The plugin polls `get` until the winner
        writes, which keeps this protocol at five methods and the waiting policy
        in one place.

        `ttl` bounds the damage when the winner dies: the lock expires and the
        next request tries again.
        """

    async def release_refresh_lock(self, sid: str) -> None: ...


class TokenSource(Protocol):
    """Turns whatever the user submitted into a `Session`."""

    async def exchange(self, credentials: Any) -> Session: ...


class RefreshableTokenSource(TokenSource, Protocol):
    """A source that can also renew.

    Split from `TokenSource` so `AuthPlugin` can report at startup, rather than
    at the first expiry in production, that a source handing out expiring tokens
    has no way to replace them.
    """

    async def refresh(self, session: Session) -> Session: ...


class Csrf(Protocol):
    """How a cookie-authenticated write proves it came from this site."""

    async def verify(self, request: Request) -> None:
        """Return if the request is trusted, raise `CsrfRejected` if not."""

    def on_issue(self, response: Response, sid: str) -> None:
        """Run when a session is issued.

        `OriginCsrf` does nothing here. The hook exists so a token-based
        strategy can plant its token later without changing this protocol.
        """
