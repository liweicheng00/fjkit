"""The board's opening rows.

Fixture data, not business logic, and separated for that reason: swapping a real
table in means deleting this file and nothing else.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count

from app.schemas.tasks import Label, Priority, Status, Task

#: Seed rows: title, status, priority, owner, notes, blocked, labels.
_SEED = [
    ("Ship the render benchmark", Status.DONE, Priority.HIGH, "livy", "", False, [Label.PERF]),
    ("Wire Basecoat tokens to the brand knob", Status.DONE, Priority.NORMAL, "livy", "", False, [Label.UI]),
    ("Move component includes to macros", Status.DOING, Priority.HIGH, "mei", "", False, [Label.PERF, Label.UI]),
    (
        "Turn off auto_reload in the prod image",
        Status.DOING,
        Priority.NORMAL,
        "kai",
        "Needs the bytecode cache warmed first, or the first request pays for every template.",
        True,
        [Label.INFRA, Label.PERF],
    ),
    ("Warm the bytecode cache at build time", Status.TODO, Priority.HIGH, "kai", "", False, [Label.INFRA]),
    ("Stream the CSV export instead of buffering", Status.TODO, Priority.NORMAL, "mei", "", False, []),
    ("Audit templates for hard-coded hues", Status.TODO, Priority.LOW, "unassigned", "", False, [Label.UI]),
    ("Add a dark-mode screenshot to the README", Status.TODO, Priority.LOW, "unassigned", "", False, []),
]


def seed_tasks(ids: count[int]) -> list[Task]:
    """Build the opening board, taking ids from the store's own counter.

    The counter is passed in rather than started here so the store keeps one
    sequence: a task created after the seed cannot collide with a seeded id.
    """
    now = datetime.now(UTC)
    return [
        Task(
            id=next(ids),
            title=title,
            status=status,
            priority=priority,
            owner=owner,
            notes=notes,
            blocked=blocked,
            labels=labels,
            created_at=now - timedelta(hours=offset * 7),
        )
        for offset, (title, status, priority, owner, notes, blocked, labels) in enumerate(_SEED)
    ]
