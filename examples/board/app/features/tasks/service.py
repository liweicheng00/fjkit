"""Business logic for the task board.

No HTTP here, no Request, no template names — a service that a background job
could call. Storage is an in-process dict so the demo has no database; swapping
it for SQLModel means changing this file and nothing above it.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import count
from threading import Lock

from app.features.tasks.schemas import (
    PRIORITY_VARIANT,
    BoardStats,
    Facet,
    Priority,
    Status,
    Task,
    TaskCreate,
    TaskUpdate,
)

#: title, status, priority, owner, notes, blocked
_SEED = [
    ("Ship the render benchmark", Status.DONE, Priority.HIGH, "livy", "", False),
    ("Wire Basecoat tokens to the brand knob", Status.DONE, Priority.NORMAL, "livy", "", False),
    ("Move component includes to macros", Status.DOING, Priority.HIGH, "mei", "", False),
    (
        "Turn off auto_reload in the prod image",
        Status.DOING,
        Priority.NORMAL,
        "kai",
        "Needs the bytecode cache warmed first, or the first request pays for every template.",
        True,
    ),
    ("Warm the bytecode cache at build time", Status.TODO, Priority.HIGH, "kai", "", False),
    ("Stream the CSV export instead of buffering", Status.TODO, Priority.NORMAL, "mei", "", False),
    ("Audit templates for hard-coded hues", Status.TODO, Priority.LOW, "unassigned", "", False),
    ("Add a dark-mode screenshot to the README", Status.TODO, Priority.LOW, "unassigned", "", False),
]


class TaskService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ids = count(1)
        self._tasks: dict[int, Task] = {}
        now = datetime.now(UTC)
        for offset, (title, status, priority, owner, notes, blocked) in enumerate(_SEED):
            task = Task(
                id=next(self._ids),
                title=title,
                status=status,
                priority=priority,
                owner=owner,
                notes=notes,
                blocked=blocked,
                created_at=now - timedelta(hours=offset * 7),
            )
            self._tasks[task.id] = task

    def list(self, status: Status | None = None, owner: str | None = None) -> list[Task]:
        tasks = self._tasks.values()
        if status is not None:
            tasks = (t for t in tasks if t.status is status)
        if owner:
            tasks = (t for t in tasks if t.owner == owner)
        return sorted(tasks, key=lambda t: (t.status is Status.DONE, -t.id))

    def get(self, task_id: int) -> Task | None:
        return self._tasks.get(task_id)

    def owners(self) -> list[str]:
        return sorted({t.owner for t in self._tasks.values()})

    def create(self, payload: TaskCreate) -> Task:
        with self._lock:
            task = Task(
                id=next(self._ids),
                title=payload.title.strip(),
                priority=payload.priority,
                owner=payload.owner.strip() or "unassigned",
                created_at=datetime.now(UTC),
            )
            self._tasks[task.id] = task
            return task

    def update(self, task_id: int, payload: TaskUpdate) -> Task | None:
        """Apply the edit form. `None` if the task is gone — the router 404s.

        `model_copy(update=…)` over named fields, not over the whole payload:
        `TaskUpdate` is the closed list of what an edit may touch, so status, id
        and created_at survive an edit by construction rather than by the form
        happening not to post them.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task = task.model_copy(
                update={
                    "title": payload.title.strip(),
                    "priority": payload.priority,
                    "owner": payload.owner.strip() or "unassigned",
                    "notes": payload.notes.strip(),
                    "blocked": payload.blocked,
                    "watching": payload.watching,
                }
            )
            self._tasks[task_id] = task
            return task

    def advance(self, task_id: int) -> Task | None:
        """Cycle todo -> doing -> done -> todo."""
        order = [Status.TODO, Status.DOING, Status.DONE]
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            nxt = order[(order.index(task.status) + 1) % len(order)]
            task = task.model_copy(update={"status": nxt})
            self._tasks[task_id] = task
            return task

    def delete(self, task_id: int) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def count(self) -> int:
        """How many tasks exist at all. The search page shows "N of M"."""
        return len(self._tasks)

    def search(self, query: str) -> list[Task]:
        """Substring match over the three fields a person actually types into a
        search box. Case-insensitive, no ranking, no index — this is a demo
        board of eight rows, and a scoring function here would be a claim about
        relevance that the data cannot support.

        An empty query matches everything rather than nothing, so the page has
        something to show before anyone types.
        """
        needle = query.strip().casefold()
        tasks = self.list()
        if not needle:
            return tasks
        return [t for t in tasks if needle in f"{t.title} {t.owner} {t.notes}".casefold()]

    def owner_facets(self, tasks: list[Task]) -> list[Facet]:
        """Who the matches belong to. Alphabetical, because owners have no
        order of their own and a count-descending list would reshuffle itself
        on every keystroke."""
        counts = Counter(t.owner for t in tasks)
        return [Facet(label=owner, count=n) for owner, n in sorted(counts.items())]

    def priority_facets(self, tasks: list[Task]) -> list[Facet]:
        """How urgent the matches are, highest first, and only the levels that
        actually appear — a facet reading "High 0" is a filter that leads
        nowhere."""
        counts = Counter(t.priority for t in tasks)
        return [
            Facet(label=p.value.capitalize(), count=counts[p], variant=PRIORITY_VARIANT[p])
            for p in reversed(list(Priority))
            if counts[p]
        ]

    def stats(self, tasks: list[Task] | None = None) -> BoardStats:
        """Counts over the whole board, or over a subset that was already
        selected — the search page wants the same four numbers about its
        matches, and a second counter that had to stay in step with this one is
        how "Done" ends up meaning two different things on two pages."""
        tasks = list(self._tasks.values()) if tasks is None else tasks
        return BoardStats(
            total=len(tasks),
            todo=sum(t.status is Status.TODO for t in tasks),
            doing=sum(t.status is Status.DOING for t in tasks),
            done=sum(t.status is Status.DONE for t in tasks),
        )
