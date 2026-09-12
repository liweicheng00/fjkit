"""The demo's `TokenSource`: one fixed account, and no token to refresh.

A class with one method, which a service otherwise should not be. `fjkit.auth`
takes a `TokenSource` and calls `exchange` on it, so the shape is the kit's seam
rather than this feature's choice. The credentials it checks against are passed
in by `main` from the settings; a service reads no configuration of its own.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from fjkit.auth import Session


class BadCredentials(Exception):
    """Raised when the username or password is wrong."""


class DemoSource:
    """`TokenSource` that checks credentials against the one demo account."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

    async def exchange(self, credentials: Mapping[str, Any]) -> Session:
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))

        user_ok = secrets.compare_digest(username, self._username)
        password_ok = secrets.compare_digest(password, self._password)
        if not (user_ok and password_ok):
            raise BadCredentials

        return Session(claims={"username": username})
