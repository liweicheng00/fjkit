"""The task feature's public face. Other layers import from here, not from the modules.

    from app.services import tasks as task_service

    task_service.search(service.list(), q)

The alias is the convention across the demo: `search` and `stats` are names a
router would otherwise shadow with one of its own.
"""

from __future__ import annotations

from app.services.tasks.facets import owner_facets, priority_facets, stats
from app.services.tasks.queries import owners_including, repeat, search, siblings
from app.services.tasks.store import TaskService

__all__ = [
    "TaskService",
    "owner_facets",
    "owners_including",
    "priority_facets",
    "repeat",
    "search",
    "siblings",
    "stats",
]
