"""The fixture app: two related models in SQLite, registered with the admin."""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from fjkit import FjkitConfig, mount_fjkit
from fjkit_admin import AdminPlugin, ModelAdmin, action
from sqlalchemy import Enum, ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Status(enum.Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(
        String(80), info={"admin": {"label": "Project name", "help": "Shown in every task list."}}
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="project")

    def __str__(self) -> str:
        return self.name


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.TODO)
    due: Mapped[dt.date | None]
    created: Mapped[dt.datetime] = mapped_column(default=lambda: dt.datetime(2026, 1, 1, 9, 0))
    done: Mapped[bool] = mapped_column(default=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    project: Mapped[Project] = relationship(back_populates="tasks")


class ProjectAdmin(ModelAdmin, model=Project):
    search_fields = ("name",)
    icon = "folder"


class TaskAdmin(ModelAdmin, model=Task):
    list_display = ("title", "status", "project", "due", "done")
    search_fields = ("title", "notes")
    list_filter = ("status", "project", "done")
    ordering = ("title",)
    list_per_page = 5
    page_sizes = (5, 10)
    readonly_fields = ("created",)
    actions = ("delete_selected", "mark_done")

    @action("Mark done")
    def mark_done(self, request: Request, session: Session, tasks: list[Task]) -> str:
        for task in tasks:
            task.done = True
        return f"{len(tasks)} marked done"


TITLES = [
    "Alpha brief",
    "Beta review",
    "Charlie draft",
    "Delta launch",
    "Echo notes",
    "Foxtrot plan",
    "Golf report",
    "Hotel audit",
    "India sync",
    "Juliet demo",
    "Kilo cleanup",
    "Lima retro",
]


def seed(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        core = Project(name="Core")
        docs = Project(name="Docs")
        session.add_all([core, docs])
        session.flush()
        for index, title in enumerate(TITLES):
            session.add(
                Task(
                    title=title,
                    notes="urgent" if index % 3 == 0 else None,
                    status=list(Status)[index % 3],
                    due=dt.date(2026, 9, 1 + index) if index % 2 == 0 else None,
                    done=index % 4 == 0,
                    project=core if index % 2 == 0 else docs,
                )
            )
        session.commit()


def make_app(*views: type[ModelAdmin], **admin_kwargs: Any) -> tuple[FastAPI, sessionmaker[Session], AdminPlugin]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    seed(factory)
    app = FastAPI()
    admin = AdminPlugin(factory, views=views or (TaskAdmin, ProjectAdmin), **admin_kwargs)
    mount_fjkit(app, FjkitConfig(plugins=(admin,)))
    return app, factory, admin


@pytest.fixture
def stack() -> tuple[FastAPI, sessionmaker[Session], AdminPlugin]:
    return make_app()


@pytest.fixture
def client(stack) -> TestClient:
    app, _, _ = stack
    return TestClient(app)


@pytest.fixture
def db(stack) -> sessionmaker[Session]:
    return stack[1]


#: The headers an htmx swap sends.
HX = {"HX-Request": "true"}
