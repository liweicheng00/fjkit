"""The demo's `TokenSource` — the auth plugin's extension point, at its smallest.

A real one calls an identity provider: `exchange` posts the credentials and
comes back with an access token, a refresh token and an expiry, and `refresh`
trades the refresh token for the next pair. This one compares against a pair
written in the file, which is enough to show the part that is actually
interesting — that swapping this class is the whole of "use OIDC instead", and
that nothing in the routers or the templates knows which one is installed.

There is no `refresh` here on purpose. `Session.expires_at` stays `None`, so
the plugin has nothing to renew and never tries; the session simply lasts as
long as the cookie does. That is a whole configuration, not a missing half —
which is why the plugin says nothing about it until it actually meets a token
that expires with no way to renew it.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from fjkit.auth import Session

#: One account, both halves in the open. The form is prefilled with them.
DEMO_USERNAME = "ada"
DEMO_PASSWORD = "lovelace"


class BadCredentials(Exception):
    """Wrong username or password. Caught by the router, shown in the panel."""


class DemoSource:
    """`TokenSource`: turns a username and password into a `Session`."""

    async def exchange(self, credentials: Mapping[str, Any]) -> Session:
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))

        # Both compared in constant time, and both compared even when the first
        # already failed — a demo is exactly where someone reads how it is done.
        user_ok = secrets.compare_digest(username, DEMO_USERNAME)
        password_ok = secrets.compare_digest(password, DEMO_PASSWORD)
        if not (user_ok and password_ok):
            raise BadCredentials

        return Session(claims={"username": username})
