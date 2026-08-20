"""The demo app, built on fjkit.

Compare with the pre-fjkit version (`git show 2ef74c9:app/main.py`): the
Environment, the vendored assets and the whole stylesheet pipeline are gone.
What is left is two lines of wiring — a config and a mount — and the
app's own routes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI
from fjkit import FjkitConfig, mount_fjkit
from fjkit.vendored import STYLE_PACKS

from app.features.dashboard.router import router as dashboard_router
from app.features.jobs.router import router as jobs_router
from app.features.jobs.service import JobService
from app.features.tasks.router import router as tasks_router
from app.features.tasks.service import TaskService

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent

#: Where the kit's assets are served from. Spelled out rather than left to the
#: default because the picker below builds URLs under the same prefix, and two
#: places guessing it separately is how a mount and a link drift apart.
STATIC_URL = "/_fjkit"

#: Every style pack, and the URL its stylesheet is served from.
#:
#: fjkit resolves exactly one pack per process (`FjkitConfig.style`), and that
#: stays true here — the shell links `fjkit-vega.css` like it always did. What
#: this feeds is the demo's picker: all eight packs ship in the wheel and
#: `mount_fjkit` serves the whole static directory, so the browser can be pointed
#: at another one to compare them without a restart. That is an affordance of
#: this demo, not something the kit does, which is why the map is built here.
#:
#: A dict rather than a list because the picker's script looks a pack up in it:
#: a value that is not one of the eight has no URL, so a stale or hand-edited
#: `localStorage` entry cannot turn into a 404 and an unstyled page.
STYLE_SHEETS = {pack: f"{STATIC_URL}/dist/fjkit-{pack}.css" for pack in STYLE_PACKS}

#: The app's templates are searched before fjkit's, so dropping a file at
#: `templates/ui/button.html` would shadow the kit's — that is `fjkit eject`.
config = FjkitConfig(
    template_dir=APP_DIR / "templates",
    bytecode_cache_dir=ROOT_DIR / ".jinja-cache",
    static_url=STATIC_URL,
    globals={"style_sheets": STYLE_SHEETS},
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.tasks = TaskService()
    # Background jobs live here for the same reason tasks do: one store per
    # process, so a job started by one request is visible to the poll that
    # follows it. A real app swaps this for a queue; the routes do not change.
    app.state.jobs = JobService()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="fjkit demo — task board", lifespan=lifespan)

    @app.middleware("http")
    async def server_timing(request, call_next):
        """Publish wall time as `Server-Timing`, so the browser's network panel
        shows the server cost of every page and every htmx swap."""
        started = perf_counter()
        response = await call_next(request)
        response.headers["Server-Timing"] = f"app;dur={(perf_counter() - started) * 1000:.2f}"
        return response

    # Serves fjkit's stylesheet and the vendored htmx/Basecoat JS straight out
    # of the installed package, and builds the Jinja Environment once. The app
    # has no static assets of its own.
    mount_fjkit(app, config)

    app.include_router(dashboard_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
