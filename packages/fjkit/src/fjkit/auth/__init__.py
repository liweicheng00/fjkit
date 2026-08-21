"""Sessions for a fjkit app — a cookie for the browser, a token for the server.

    from fjkit import FjkitConfig, mount_fjkit
    from fjkit.auth import AuthPlugin, RedisStore

    auth = AuthPlugin(
        secret=os.environ["FJKIT_SECRET"],
        store=RedisStore(redis.from_url(REDIS_URL)),
        trusted_origins=["https://app.example.com"],
    )
    mount_fjkit(app, FjkitConfig(template_dir=..., plugins=(auth,)))

Three seams, replaceable independently: where sessions live (`SessionStore`),
how credentials become tokens (`TokenSource`), and how a write proves it came
from this site (`Csrf`). Swapping any one of them touches no route and no
template.

See `fjkit.auth.plugin` for what the cookie holds and why, and
`fjkit.auth.csrf` for the CSRF trade a cookie brings back.
"""

from __future__ import annotations

from fjkit.auth.csrf import NoCsrf, OriginCsrf
from fjkit.auth.errors import AuthError, CsrfRejected, NotAuthenticated, RefreshFailed
from fjkit.auth.plugin import AuthPlugin, CookieSpec
from fjkit.auth.sources import LocalSource
from fjkit.auth.stores import MemoryStore, RedisStore, SyncStore
from fjkit.auth.types import (
    Csrf,
    RefreshableTokenSource,
    Session,
    SessionStore,
    TokenSource,
)

__all__ = [
    "AuthError",
    "AuthPlugin",
    "CookieSpec",
    "Csrf",
    "CsrfRejected",
    "LocalSource",
    "MemoryStore",
    "NoCsrf",
    "NotAuthenticated",
    "OriginCsrf",
    "RedisStore",
    "RefreshFailed",
    "RefreshableTokenSource",
    "Session",
    "SessionStore",
    "SyncStore",
    "TokenSource",
]
