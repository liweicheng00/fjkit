"""The demo app, built on fjkit.

Compare with the pre-fjkit version (`git show 2ef74c9:app/main.py`): the
Environment, the vendored assets and the whole stylesheet pipeline are gone.
What is left is two lines of wiring — a config and a mount — and the
app's own routes.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fjkit import FjkitConfig, FlashPlugin, mount_fjkit
from fjkit.auth import AuthPlugin, CookieSpec, MemoryStore
from fjkit.vendored import STYLE_PACKS

from app.features.auth.router import protected as auth_protected_router
from app.features.auth.router import router as auth_router
from app.features.auth.service import DemoSource
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

#: Where this demo runs. Named rather than derived from the `Host` header,
#: which a request controls — a CSRF check that trusts a value the request
#: supplied is not a check. A deployed app lists its real origin here.
TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

#: Fixed so that `fastapi dev` reloading does not sign you out mid-demo. A real
#: app reads this from the environment and never commits it; the sessions it
#: signs are only as private as this file is.
DEMO_SECRET = "fjkit-demo-not-a-secret"

#: The app's templates are searched before fjkit's, so dropping a file at
#: `templates/ui/button.html` would shadow the kit's — that is `fjkit eject`.
config = FjkitConfig(
    template_dir=APP_DIR / "templates",
    bytecode_cache_dir=ROOT_DIR / ".jinja-cache",
    static_url=STATIC_URL,
    globals={"style_sheets": STYLE_SHEETS},
)


def build_plugins() -> tuple[FlashPlugin, AuthPlugin]:
    """One set per app, for the same reason the services are.

    The session store is in-memory, so two apps sharing one would share their
    sessions — which is exactly what the test suite must not have. A deployed
    app builds these once and gives auth a `RedisStore`.

    `flash` is handed to `auth` rather than imported by it. Neither plugin
    depends on the other: auth works without a flash, and flash is useful to
    any route that just finished something. The app is what connects them.
    """
    flash = FlashPlugin(secret=DEMO_SECRET, secure=False)
    auth = AuthPlugin(
        flash=flash,
        secret=DEMO_SECRET,
        store=MemoryStore(),
        source=DemoSource(),
        trusted_origins=TRUSTED_ORIGINS,
        # Where an unauthenticated request is sent. This demo's login form is
        # on the session page rather than a page of its own, so that is where
        # the plugin points; the default is "/login".
        login_url="/session",
        # The demo is served over plain http. A real app leaves this at its
        # default of True and serves https, which is the only way the cookie is
        # protected in transit at all.
        cookie=CookieSpec(secure=False),
    )
    return flash, auth


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

    # The session plugin. Registering it is the whole of the wiring: it brings
    # its own middleware, its own 401 behaviour and the `session` every template
    # gets. `app.state.auth` is here because two routes call `issue`/`revoke`
    # and want the same instance the middleware is using.
    flash, auth = build_plugins()
    app.state.auth = auth
    app.state.flash = flash

    # Serves fjkit's stylesheet and the vendored htmx/Basecoat JS straight out
    # of the installed package, and builds the Jinja Environment once. The app
    # has no static assets of its own.
    mount_fjkit(app, replace(config, plugins=(flash, auth)))

    app.include_router(dashboard_router)
    app.include_router(tasks_router)
    app.include_router(jobs_router)
    app.include_router(auth_router)
    app.include_router(auth_protected_router)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
