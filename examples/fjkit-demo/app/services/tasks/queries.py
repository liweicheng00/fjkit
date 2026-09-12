"""Reading the board: every question that takes rows and returns rows.

Functions rather than methods, because none of them touches the store's lock or
its dictionary. A database would answer all four with a `WHERE`, and the caller
would still be the one to say which rows it asked about.
"""

from __future__ import annotations

from app.schemas.tasks import Task


def search(tasks: list[Task], query: str) -> list[Task]:
    """Match `query` as a case-insensitive substring of title, owner or notes.

    An empty query matches every task.
    """
    needle = query.strip().casefold()
    if not needle:
        return tasks
    return [t for t in tasks if needle in f"{t.title} {t.owner} {t.notes}".casefold()]


def siblings(tasks: list[Task], selected: Task | None) -> list[Task]:
    """Everything else assigned to the picked task's owner.

    The search page and the panels page both show this, which is why it is one
    function: the two pages differ in how a panel is fetched, not in what a
    sibling is.
    """
    if selected is None:
        return []
    return [t for t in tasks if t.owner == selected.owner and t.id != selected.id]


def owners_including(owners: list[str], owner: str) -> list[str]:
    """`owners` with `owner` on the end when it is missing.

    The edit form's select must be able to show the owner the task already has,
    even after that person's last other task was deleted — otherwise opening the
    form silently reassigns the task on save.
    """
    return owners if owner in owners else [*owners, owner]


def repeat(tasks: list[Task], rows: int) -> list[Task]:
    """Cycle `tasks` until there are `rows` of them, for the streamed report.

    Here rather than in the router because a handler that builds five thousand
    rows is doing the work, not choosing a template.
    """
    return [tasks[i % len(tasks)] for i in range(max(rows, 1))]
