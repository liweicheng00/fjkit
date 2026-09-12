"""Marking tasks done — the demo's one piece of business logic.

Two columns say a task is finished, and they have to agree. That rule is the
reason this is not three lines inside the `@action` method: a `ModelAdmin` is
presentation configuration, and a rule about what `done` means belongs where a
second caller could reach it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from admin_demo.models import Status, Task


def mark_done(session: Session, tasks: list[Task]) -> int:
    """Mark every task in `tasks` finished. Returns how many were marked.

    The transaction is the caller's: the admin commits the session it handed in
    once the action returns, so this function stages the change and nothing else.
    """
    for task in tasks:
        task.done = True
        task.status = Status.DONE
    return len(tasks)
