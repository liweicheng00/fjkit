"""The fjkit-admin demo: SQLite, two models, one plugin, the app's own shell.

    uv run fastapi dev examples/fjkit-admin-demo/admin_demo/main.py

The database is a file next to this package, created and seeded on first start,
so every restart shows the same rows and every edit survives one.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fjkit import FjkitConfig, mount_fjkit
from fjkit_admin import AdminPlugin
from sqlalchemy import Engine

from admin_demo import db
from admin_demo.admin import ProjectAdmin, TaskAdmin
from admin_demo.config import settings
from admin_demo.models import Base
from admin_demo.seed import seed

APP_DIR = Path(__file__).resolve().parent


def create_app(engine: Engine | None = None) -> FastAPI:
    """Build the app on `engine`, defaulting to the configured database.

    The engine is a parameter so a caller with its own database — the test suite
    has one per test — passes it in rather than rebinding a module attribute.
    """
    engine = engine or db.engine
    sessions = db.build_sessions(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Base.metadata.create_all(engine)
        with sessions() as session:
            seed(session)
        yield

    app = FastAPI(title="fjkit-admin demo", lifespan=lifespan)
    admin = AdminPlugin(
        sessions,
        views=(TaskAdmin, ProjectAdmin),
        title=settings.title,
        base_template="base.html",
        home_url=settings.home_url,
        home_label=settings.home_label,
    )
    mount_fjkit(app, FjkitConfig(template_dir=APP_DIR / "templates", plugins=(admin,)))

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/admin")

    return app


app = create_app()
