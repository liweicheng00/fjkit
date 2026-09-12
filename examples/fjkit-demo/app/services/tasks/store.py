"""The board itself: the rows, and the operations that change them.

A class, because all three of the tests for one hold. There is a resource to
open — the seeded store; there are many operations on the same one; and they
share state the caller must not have to pass around. Reading and counting are
not here: they need no lock and no dictionary, so they are functions in
`queries` and `facets` that take the rows they work on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from threading import Lock

from app.schemas.tasks import Status, Task, TaskCreate, TaskUpdate
from app.services.tasks.seed import seed_tasks


class TaskService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ids = count(1)
        self._tasks: dict[int, Task] = {task.id: task for task in seed_tasks(self._ids)}

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

    def count(self) -> int:
        """Count the tasks on the board."""
        return len(self._tasks)

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
        """Apply an edit. Returns `None` when the task does not exist."""
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
