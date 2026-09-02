"""The demo app: fjkit config, plugins, and the feature routers."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI, Request
from fjkit import FjkitConfig, FlashPlugin, Message, mount_fjkit
from fjkit.apidocs import ApiDocsPlugin, FlowField, SessionFlow
from fjkit.auth import AuthPlugin, CookieSpec, MemoryStore
from fjkit.charts import ChartsPlugin
from fjkit.vendored import STYLE_PACKS

from app.features.auth.router import protected as auth_protected_router
from app.features.auth.router import router as auth_router
from app.features.auth.service import DEMO_PASSWORD, DEMO_USERNAME, DemoSource
from app.features.charts.router import router as charts_router
from app.features.dashboard.router import router as dashboard_router
from app.features.failures.router import router as failures_router
from app.features.jobs.router import router as jobs_router
from app.features.jobs.service import JobService
from app.features.panels.router import router as panels_router
from app.features.search.router import router as search_router
from app.features.tasks.router import router as tasks_router
from app.features.tasks.service import TaskService

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent

#: URL prefix the kit's static assets are served from.
STATIC_URL = "/_fjkit"

#: Style pack name -> stylesheet URL, used by the shell's style picker.
STYLE_SHEETS = {pack: f"{STATIC_URL}/dist/fjkit-{pack}.css" for pack in STYLE_PACKS}


def _dev_port(default: str = "8000") -> str:
    """Return the port this process serves on: `PORT`, then `--port` in argv, then `default`."""
    if (from_env := os.environ.get("PORT")) is not None:
        return from_env
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--port="):
            return arg.split("=", 1)[1]
    return default


#: Origins the CSRF check accepts. Both loopback spellings of the dev port.
TRUSTED_ORIGINS = [f"http://localhost:{_dev_port()}", f"http://127.0.0.1:{_dev_port()}"]

#: Signing secret for the flash and session cookies. Fixed so reloads keep sessions.
DEMO_SECRET = "fjkit-demo-not-a-secret"

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
    flash = FlashPlugin(secret=DEMO_SECRET, secure=False)
    auth = AuthPlugin(
        flash=flash,
        secret=DEMO_SECRET,
        store=MemoryStore(),
        source=DemoSource(),
        trusted_origins=TRUSTED_ORIGINS,
        login_url="/session",
        cookie=CookieSpec(secure=False),
    )

    # The API console, with a sign-in flow through `auth`.
    docs = ApiDocsPlugin(
        title="Fjkit Demo API",
        home_url="/",
        flow=SessionFlow(
            auth,
            fields=(
                FlowField("username", "Username", placeholder=DEMO_USERNAME, hint="the demo account"),
                FlowField("password", "Password", type="password", placeholder=DEMO_PASSWORD),
            ),
            describe=lambda session: (
                ("username", session.claims.get("username", "—")),
                ("source", "DemoSource"),
                ("token expiry", "never (this source issues none)"),
            ),
        ),
    )

    charts = ChartsPlugin()

    return flash, auth, docs, charts


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tasks = TaskService()
    app.state.jobs = JobService()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Fjkit Demo", lifespan=lifespan)

    flash, auth, docs, charts = build_plugins()
    app.state.auth = auth
    app.state.flash = flash

    mount_fjkit(app, replace(config, plugins=(flash, auth, docs, charts)))

    app.include_router(dashboard_router)
    app.include_router(charts_router)
    app.include_router(tasks_router)
    app.include_router(search_router)
    app.include_router(panels_router)
    app.include_router(jobs_router)
    app.include_router(failures_router)
    app.include_router(auth_router)
    app.include_router(auth_protected_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
