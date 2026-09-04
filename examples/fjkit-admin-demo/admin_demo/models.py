"""The demo's models: a project, its tasks, and the enum a task's status is."""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Status(enum.Enum):
    TODO = "todo"
    DOING = "doing"
    DONE = "done"


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), info={"admin": {"help": "Shown wherever a task names its project."}})
    owner: Mapped[str | None] = mapped_column(String(80))
    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")

    def __str__(self) -> str:
        return self.name


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.TODO)
    priority: Mapped[int] = mapped_column(default=3, info={"admin": {"help": "1 is urgent, 5 can wait."}})
    due: Mapped[dt.date | None]
    created: Mapped[dt.datetime] = mapped_column(default=dt.datetime.now)
    done: Mapped[bool] = mapped_column(default=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"))
    project: Mapped[Project] = relationship(back_populates="tasks")

    def __str__(self) -> str:
        return self.title
