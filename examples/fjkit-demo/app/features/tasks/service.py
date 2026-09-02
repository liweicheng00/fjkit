"""In-memory store for the task board."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from itertools import count
from threading import Lock

from app.features.tasks.schemas import (
    PRIORITY_VARIANT,
    BoardStats,
    Facet,
    Label,
    Priority,
    Status,
    Task,
    TaskCreate,
    TaskUpdate,
)

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


class TaskService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ids = count(1)
        self._tasks: dict[int, Task] = {}
        now = datetime.now(UTC)
        for offset, (title, status, priority, owner, notes, blocked, labels) in enumerate(_SEED):
            task = Task(
                id=next(self._ids),
                title=title,
                status=status,
                priority=priority,
                owner=owner,
                notes=notes,
                blocked=blocked,
                labels=labels,
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
        """Apply an edit. Returns `None` if the task does not exist."""
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
                    "labels": list(payload.labels),
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
        """Number of tasks on the board."""
        return len(self._tasks)

    def search(self, query: str) -> list[Task]:
        """Case-insensitive substring match over title, owner and notes. Empty query matches all."""
        needle = query.strip().casefold()
        tasks = self.list()
        if not needle:
            return tasks
        return [t for t in tasks if needle in f"{t.title} {t.owner} {t.notes}".casefold()]

    def owner_facets(self, tasks: list[Task]) -> list[Facet]:
        """Match counts per owner, alphabetical."""
        counts = Counter(t.owner for t in tasks)
        return [Facet(label=owner, count=n) for owner, n in sorted(counts.items())]

    def priority_facets(self, tasks: list[Task]) -> list[Facet]:
        """Match counts per priority, highest first, omitting empty levels."""
        counts = Counter(t.priority for t in tasks)
        return [
            Facet(label=p.value.capitalize(), count=counts[p], variant=PRIORITY_VARIANT[p])
            for p in reversed(list(Priority))
            if counts[p]
        ]

    def stats(self, tasks: list[Task] | None = None) -> BoardStats:
        """Status counts over the whole board, or over `tasks` if given."""
        tasks = list(self._tasks.values()) if tasks is None else tasks
        return BoardStats(
            total=len(tasks),
            todo=sum(t.status is Status.TODO for t in tasks),
            doing=sum(t.status is Status.DOING for t in tasks),
            done=sum(t.status is Status.DONE for t in tasks),
        )
