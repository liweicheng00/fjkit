"""The demo's `TokenSource`: one fixed account, no token refresh."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from fjkit.auth import Session

#: The single demo account.
DEMO_USERNAME = "ada"
DEMO_PASSWORD = "lovelace"


class BadCredentials(Exception):
    """Raised when the username or password is wrong."""


class DemoSource:
    """`TokenSource` that checks credentials against the demo account."""

    async def exchange(self, credentials: Mapping[str, Any]) -> Session:
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))

        user_ok = secrets.compare_digest(username, DEMO_USERNAME)
        password_ok = secrets.compare_digest(password, DEMO_PASSWORD)
        if not (user_ok and password_ok):
            raise BadCredentials

        return Session(claims={"username": username})
