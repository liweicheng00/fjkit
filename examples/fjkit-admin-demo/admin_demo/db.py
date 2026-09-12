"""The engine and the session factory.

One module, so a caller that needs its own database — the test suite does — has
one thing to replace. `create_app(engine=…)` takes it as an argument for that
reason: nothing has to reach in and rebind a name.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from admin_demo.config import settings


def build_engine(url: str | None = None) -> Engine:
    """An engine on `url`, defaulting to the configured database.

    `check_same_thread=False` because Starlette runs `def` handlers in the
    threadpool, so the connection a request uses is not the one that opened it.
    """
    return create_engine(url or settings.database_url, connect_args={"check_same_thread": False})


def build_sessions(engine: Engine) -> sessionmaker:
    """A session factory on `engine`.

    `expire_on_commit=False` so a row stays readable after the commit that saved
    it — the admin renders the object it just wrote.
    """
    return sessionmaker(engine, expire_on_commit=False)


engine = build_engine()
