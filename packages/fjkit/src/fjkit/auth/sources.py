"""The source for an app with no upstream — which is also the default."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fjkit.auth.types import Session

__all__ = ["LocalSource"]


class LocalSource:
    """No token exchange: the claims you pass in are the session.

    This is what makes "I just want a login" and "I hold an upstream OAuth
    token" the same code path. Without it, `AuthPlugin` would need a `source is
    None` branch in `issue`, in the refresh check and in every message about
    either — one class is cheaper than a special case that spreads.

        await auth.issue(request, response, {"user_id": user.id})
    """

    async def exchange(self, credentials: Mapping[str, Any]) -> Session:
        return Session(claims=dict(credentials))
