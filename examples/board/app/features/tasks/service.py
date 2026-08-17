"""Business logic for the task board.

No HTTP here, no Request, no template names — a service that a background job
could call. Storage is an in-process dict so the demo has no database; swapping
it for SQLModel means changing this file and nothing above it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from threading import Lock

from app.features.tasks.schemas import BoardStats, Priority, Status, Task, TaskCreate

_SEED = [
    ("Ship the render benchmark", Status.DONE, Priority.HIGH, "livy"),
    ("Wire Basecoat tokens to the brand knob", Status.DONE, Priority.NORMAL, "livy"),
    ("Move component includes to macros", Status.DOING, Priority.HIGH, "mei"),
    ("Turn off auto_reload in the prod image", Status.DOING, Priority.NORMAL, "kai"),
    ("Warm the bytecode cache at build time", Status.TODO, Priority.HIGH, "kai"),
    ("Stream the CSV export instead of buffering", Status.TODO, Priority.NORMAL, "mei"),
    ("Audit templates for hard-coded hues", Status.TODO, Priority.LOW, "unassigned"),
    ("Add a dark-mode screenshot to the README", Status.TODO, Priority.LOW, "unassigned"),
]


class TaskService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._ids = count(1)
        self._tasks: dict[int, Task] = {}
        now = datetime.now(UTC)
        for offset, (title, status, priority, owner) in enumerate(_SEED):
            task = Task(
                id=next(self._ids),
                title=title,
                status=status,
                priority=priority,
                owner=owner,
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

    def stats(self) -> BoardStats:
        tasks = list(self._tasks.values())
        return BoardStats(
            total=len(tasks),
            todo=sum(t.status is Status.TODO for t in tasks),
            doing=sum(t.status is Status.DOING for t in tasks),
            done=sum(t.status is Status.DONE for t in tasks),
        )
