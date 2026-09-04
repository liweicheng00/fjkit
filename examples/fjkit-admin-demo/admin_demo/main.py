"""The fjkit-admin demo: SQLite, two models, one plugin, the app's own shell.

    uv run fastapi dev examples/fjkit-admin-demo/admin_demo/main.py

The database is a file next to this module, created and seeded on first
start, so every restart shows the same rows and every edit survives one.
"""

from __future__ import annotations

import datetime as dt
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fjkit import FjkitConfig, mount_fjkit
from fjkit_admin import AdminPlugin, ModelAdmin, action, display
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from admin_demo.models import Base, Project, Status, Task

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR.parent / "admin-demo.sqlite"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class ProjectAdmin(ModelAdmin, model=Project):
    icon = "folder"
    list_display = ("name", "owner", "task_count")
    search_fields = ("name", "owner")

    @display("Tasks")
    def task_count(self, project: Project) -> int:
        return len(project.tasks)


class TaskAdmin(ModelAdmin, model=Task):
    icon = "list-checks"
    list_display = ("title", "project", "status", "priority", "due", "done")
    list_filter = ("status", "project", "done")
    search_fields = ("title", "notes")
    ordering = ("priority", "title")
    list_per_page = 10
    page_sizes = (10, 25, 50)
    readonly_fields = ("created",)
    actions = ("mark_done", "delete_selected")

    @action("Mark done", confirm="Mark the selected tasks as done?")
    def mark_done(self, request: Request, session: Session, tasks: list[Task]) -> str:
        for task in tasks:
            task.done = True
            task.status = Status.DONE
        return f"{len(tasks)} marked done"


def seed(session: Session) -> None:
    if session.scalar(select(Project).limit(1)) is not None:
        return
    core = Project(name="Core platform", owner="Mina")
    docs = Project(name="Documentation", owner="Ravi")
    session.add_all([core, docs])
    titles = [
        ("Ship the sortable table", 1, core),
        ("Write the pagination lesson", 2, docs),
        ("Audit keyboard focus in dialogs", 2, core),
        ("Rebrand walkthrough", 3, docs),
        ("Cut the CSS budget by 1 KB", 3, core),
        ("Translate the components page", 4, docs),
        ("Profile the render bench", 2, core),
        ("Fix the dark-mode toast contrast", 1, core),
        ("Record the eject screencast", 5, docs),
        ("Draft the 1.0 deprecation policy", 4, docs),
        ("Benchmark streaming buffers", 3, core),
        ("Answer the combobox question", 2, core),
        ("Proofread the plugins page", 5, docs),
        ("Add row numbers to Records", 3, core),
    ]
    for index, (title, priority, project) in enumerate(titles):
        session.add(
            Task(
                title=title,
                notes="Blocked on review." if index % 5 == 0 else None,
                status=list(Status)[index % 3],
                priority=priority,
                due=dt.date(2026, 9, 8 + index) if index % 2 == 0 else None,
                done=index % 3 == 2,
                project=project,
            )
        )
    session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="fjkit-admin demo", lifespan=lifespan)
    admin = AdminPlugin(
        SessionLocal,
        views=(TaskAdmin, ProjectAdmin),
        title="Board admin",
        base_template="base.html",
        home_url="/",
        home_label="Back to the board",
    )
    mount_fjkit(app, FjkitConfig(template_dir=APP_DIR / "templates", plugins=(admin,)))

    @app.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/admin")

    return app


app = create_app()
