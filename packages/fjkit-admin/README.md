# fjkit-admin

A Django-style admin for FastAPI. Register SQLAlchemy models, get a list with
search, filters, sortable headers, pagination and bulk actions, plus add,
change and delete forms. Every page is rendered by fjkit's macros and every
interaction is an htmx swap, so the app ships no JavaScript of its own.

```python
from fjkit import FjkitConfig, mount_fjkit
from fjkit_admin import AdminPlugin, ModelAdmin, action


class TaskAdmin(ModelAdmin, model=Task):
    list_display = ("title", "status", "project", "due")
    search_fields = ("title", "notes")
    list_filter = ("status", "project")
    ordering = ("-created",)

    @action("Mark done", confirm="Mark the selected tasks done?")
    def mark_done(self, request, session, tasks):
        for task in tasks:
            task.done = True
        return f"{len(tasks)} marked done"


admin = AdminPlugin(SessionLocal, views=(TaskAdmin,), url="/admin", base_template="base.html")
mount_fjkit(app, FjkitConfig(template_dir=TEMPLATES, plugins=(admin,)))
```

Options follow Django's `ModelAdmin` names: `list_display`,
`list_display_links`, `search_fields`, `list_filter`, `ordering`,
`sortable_by`, `list_per_page`, `fields`, `exclude`, `readonly_fields`,
`labels`, `help_texts`, `widgets`, `actions`, plus `@action` for bulk actions and
`@display` to name a method column; hooks `get_queryset`,
`has_view/add/change/delete_permission`, `save_model`, `delete_model`,
`label_for`.

Dependencies: `fjkit` and `sqlalchemy>=2.0`. A SQLModel `table=True` class
registers like any mapped class; its own validators run on submit through
`model_validate`.

0.1 is synchronous: pass `sessionmaker(engine)`. Inline formsets and file
upload are not in this version.
