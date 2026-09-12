"""The rows the demo opens on.

A lifespan fixture, not business logic, and separate for that reason: a real app
deletes this file and keeps everything else.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from admin_demo.models import Project, Status, Task

_TITLES = [
    ("Ship the sortable table", 1, "core"),
    ("Write the pagination lesson", 2, "docs"),
    ("Audit keyboard focus in dialogs", 2, "core"),
    ("Rebrand walkthrough", 3, "docs"),
    ("Cut the CSS budget by 1 KB", 3, "core"),
    ("Translate the components page", 4, "docs"),
    ("Profile the render bench", 2, "core"),
    ("Fix the dark-mode toast contrast", 1, "core"),
    ("Record the eject screencast", 5, "docs"),
    ("Draft the 1.0 deprecation policy", 4, "docs"),
    ("Benchmark streaming buffers", 3, "core"),
    ("Answer the combobox question", 2, "core"),
    ("Proofread the plugins page", 5, "docs"),
    ("Add row numbers to Records", 3, "core"),
]


def seed(session: Session) -> None:
    """Fill an empty database. Does nothing once there is a project in it."""
    if session.scalar(select(Project).limit(1)) is not None:
        return
    projects = {
        "core": Project(name="Core platform", owner="Mina"),
        "docs": Project(name="Documentation", owner="Ravi"),
    }
    session.add_all(projects.values())
    for index, (title, priority, project) in enumerate(_TITLES):
        session.add(
            Task(
                title=title,
                notes="Blocked on review." if index % 5 == 0 else None,
                status=list(Status)[index % 3],
                priority=priority,
                due=dt.date(2026, 9, 8 + index) if index % 2 == 0 else None,
                done=index % 3 == 2,
                project=projects[project],
            )
        )
    session.commit()
