"""The demo app: fjkit config, plugins, and the routers.

Nothing here computes. It reads the settings, builds the four plugins, puts the
three stores where `Depends` can reach them, and includes the routers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Request
from fjkit import FjkitConfig, FlashPlugin, Message, mount_fjkit
from fjkit.auth import AuthPlugin, CookieSpec, MemoryStore
from fjkit.vendored import STYLE_PACKS
from fjkit_apidocs import ApiDocsPlugin, FlowField, SessionFlow
from fjkit_charts import ChartsPlugin

from app.config import settings
from app.routers import auth, charts, dashboard, failures, jobs, panels, records, search, tasks
from app.services.auth import DemoSource
from app.services.jobs import JobService
from app.services.records import RecordService
from app.services.tasks import TaskService

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent

#: URL prefix for the kit's static assets.
STATIC_URL = "/_fjkit"

#: Style pack name -> stylesheet URL, used by the shell's style picker.
STYLE_SHEETS = {pack: f"{STATIC_URL}/dist/fjkit-{pack}.css" for pack in STYLE_PACKS}


def exception_handler(request: Request, exc: Exception) -> Message:
    """Build the `Message` shown for an unexpected exception, from its type and text."""
    return Message(
        "Something went wrong",
        f"{type(exc).__name__}: {exc}" if str(exc) else "The action was not completed. Nothing was saved.",
        category="error",
    )


config = FjkitConfig(
    template_dir=APP_DIR / "templates",
    bytecode_cache_dir=ROOT_DIR / ".jinja-cache",
    static_url=STATIC_URL,
    globals={"style_sheets": STYLE_SHEETS},
    catch_unexpected_errors=True,
    unexpected_error=exception_handler,
)


def build_plugins() -> tuple[FlashPlugin, AuthPlugin, ApiDocsPlugin, ChartsPlugin]:
    """Build the flash, auth, API-docs and charts plugins for one app instance."""
    flash = FlashPlugin(secret=settings.secret, secure=settings.cookie_secure)
    auth_plugin = AuthPlugin(
        flash=flash,
        secret=settings.secret,
        store=MemoryStore(),
        source=DemoSource(settings.username, settings.password),
        trusted_origins=settings.trusted_origins,
        login_url="/session",
        cookie=CookieSpec(secure=settings.cookie_secure),
    )

    # The API console, with a sign-in flow through `auth_plugin`.
    docs = ApiDocsPlugin(
        title="Fjkit Demo API",
        home_url="/",
        flow=SessionFlow(
            auth_plugin,
            fields=(
                FlowField("username", "Username", placeholder=settings.username, hint="the demo account"),
                FlowField("password", "Password", type="password", placeholder=settings.password),
            ),
            describe=lambda session: (
                ("username", session.claims.get("username", "—")),
                ("source", "DemoSource"),
                ("token expiry", "never (this source issues none)"),
            ),
        ),
    )

    return flash, auth_plugin, docs, ChartsPlugin()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tasks = TaskService()
    app.state.jobs = JobService()
    app.state.records = RecordService()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Fjkit Demo", lifespan=lifespan)

    flash, auth_plugin, docs, charts_plugin = build_plugins()
    app.state.auth = auth_plugin
    app.state.flash = flash

    mount_fjkit(app, replace(config, plugins=(flash, auth_plugin, docs, charts_plugin)))

    app.include_router(dashboard.router)
    app.include_router(charts.router)
    app.include_router(tasks.router)
    app.include_router(records.router)
    app.include_router(search.router)
    app.include_router(panels.router)
    app.include_router(jobs.router)
    app.include_router(failures.router)
    app.include_router(auth.router)
    app.include_router(auth.protected)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
