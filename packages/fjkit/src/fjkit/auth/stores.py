"""The two backends that ship, and an adapter for a blocking third.

Neither imports a database driver. `RedisStore` takes a client the app already
built, which keeps fjkit's runtime dependencies at two (CHARTER §7) and also
works with Valkey, fakeredis, or anything else exposing the same four methods.
"""

from __future__ import annotations

from time import monotonic
from typing import Any, Protocol

from starlette.concurrency import run_in_threadpool

__all__ = ["MemoryStore", "RedisStore", "SyncStore"]


class MemoryStore:
    """A dict with expiry. Correct for one process, wrong for more than one.

    `AuthPlugin` warns when it sees this under a production config. The symptom
    otherwise is users logged out at random on a machine running four workers,
    with nothing in the traceback pointing here.

    No locking primitives: an event loop runs one task at a time between awaits,
    and no method below awaits anything, so the check-then-set in
    `acquire_refresh_lock` cannot be interleaved.
    """

    __slots__ = ("_items", "_locks")

    def __init__(self) -> None:
        self._items: dict[str, tuple[bytes, float]] = {}
        self._locks: dict[str, float] = {}

    async def get(self, sid: str) -> bytes | None:
        entry = self._items.get(sid)
        if entry is None:
            return None
        payload, expires = entry
        if expires <= monotonic():
            del self._items[sid]
            return None
        return payload

    async def put(self, sid: str, payload: bytes, ttl: int) -> None:
        self._items[sid] = (payload, monotonic() + ttl)

    async def delete(self, sid: str) -> None:
        self._items.pop(sid, None)
        self._locks.pop(sid, None)

    async def acquire_refresh_lock(self, sid: str, ttl: int) -> bool:
        now = monotonic()
        held = self._locks.get(sid)
        if held is not None and held > now:
            return False
        self._locks[sid] = now + ttl
        return True

    async def release_refresh_lock(self, sid: str) -> None:
        self._locks.pop(sid, None)


class _AsyncRedis(Protocol):
    """The client calls `RedisStore` makes. Structural, so no import is needed."""

    async def get(self, name: str) -> Any: ...
    async def set(self, name: str, value: Any, **kwargs: Any) -> Any: ...
    async def delete(self, *names: str) -> Any: ...


class RedisStore:
    """Store sessions in Redis, through a client the app owns.

    Expects an async client: `redis.asyncio.Redis` or equivalent. Put a blocking
    client behind `SyncStore`, so the threadpool hop stays visible in the app's
    wiring instead of hidden here.

    The refresh lock is `SET NX EX`, which is what lets several workers share
    this store and still refresh a token exactly once.
    """

    __slots__ = ("_client", "_prefix")

    def __init__(self, client: _AsyncRedis, *, prefix: str = "fjkit:sess:") -> None:
        self._client = client
        self._prefix = prefix

    def _key(self, sid: str) -> str:
        return f"{self._prefix}{sid}"

    def _lock_key(self, sid: str) -> str:
        return f"{self._prefix}refresh:{sid}"

    async def get(self, sid: str) -> bytes | None:
        value = await self._client.get(self._key(sid))
        if value is None:
            return None
        return value if isinstance(value, bytes) else str(value).encode("utf-8")

    async def put(self, sid: str, payload: bytes, ttl: int) -> None:
        await self._client.set(self._key(sid), payload, ex=ttl)

    async def delete(self, sid: str) -> None:
        await self._client.delete(self._key(sid), self._lock_key(sid))

    async def acquire_refresh_lock(self, sid: str, ttl: int) -> bool:
        return bool(await self._client.set(self._lock_key(sid), b"1", nx=True, ex=ttl))

    async def release_refresh_lock(self, sid: str) -> None:
        await self._client.delete(self._lock_key(sid))


class SyncStore:
    """Run a blocking store's five methods in the threadpool.

    For a backend with no async driver: a synchronous Redis client, a database
    session, a file. The hop costs a thread per call, so it is an explicit
    wrapper rather than something the plugin applies on its own.
    """

    __slots__ = ("_inner",)

    def __init__(self, store: Any) -> None:
        self._inner = store

    async def get(self, sid: str) -> bytes | None:
        return await run_in_threadpool(self._inner.get, sid)

    async def put(self, sid: str, payload: bytes, ttl: int) -> None:
        await run_in_threadpool(self._inner.put, sid, payload, ttl)

    async def delete(self, sid: str) -> None:
        await run_in_threadpool(self._inner.delete, sid)

    async def acquire_refresh_lock(self, sid: str, ttl: int) -> bool:
        return await run_in_threadpool(self._inner.acquire_refresh_lock, sid, ttl)

    async def release_refresh_lock(self, sid: str) -> None:
        await run_in_threadpool(self._inner.release_refresh_lock, sid)
