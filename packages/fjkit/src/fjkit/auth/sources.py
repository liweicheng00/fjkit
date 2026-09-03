"""The source for an app with no upstream, and the default source."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fjkit.auth.types import Session

__all__ = ["LocalSource"]


class LocalSource:
    """No token exchange: the claims passed in are the session.

    Puts a plain login and an upstream OAuth token on one code path. Without it,
    `AuthPlugin` would need a `source is None` branch in `issue`, in the refresh
    check and in every message about either.

        await auth.issue(request, response, {"user_id": user.id})
    """

    async def exchange(self, credentials: Mapping[str, Any]) -> Session:
        return Session(claims=dict(credentials))
