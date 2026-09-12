"""What the admin shows for each model: columns, filters, ordering, actions.

Presentation only. Every attribute here names a field the model already has, and
the one action delegates the rule it applies to `services.tasks`.
"""

from __future__ import annotations

from fastapi import Request
from fjkit_admin import ModelAdmin, action, display
from sqlalchemy.orm import Session

from admin_demo.models import Project, Task
from admin_demo.services import tasks as task_service


class ProjectAdmin(ModelAdmin, model=Project):
    icon = "folder"
    list_display = ("name", "owner", "task_count")
    search_fields = ("name", "owner")

    @display("Tasks")
    def task_count(self, project: Project) -> int:
        return len(project.tasks)


class TaskAdmin(ModelAdmin, model=Task):
    icon = "list-checks"
    list_display = ("title", "project", "status", "priority", "due", "done")
    list_filter = ("status", "project", "done")
    search_fields = ("title", "notes")
    ordering = ("priority", "title")
    list_per_page = 10
    page_sizes = (10, 25, 50)
    readonly_fields = ("created",)
    actions = ("mark_done", "delete_selected")

    @action("Mark done", confirm="Mark the selected tasks as done?")
    def mark_done(self, request: Request, session: Session, tasks: list[Task]) -> str:
        return f"{task_service.mark_done(session, tasks)} marked done"
