"""fjkit-admin — a Django-style admin for FastAPI over SQLAlchemy, rendered with fjkit.

from fjkit_admin import AdminPlugin, ModelAdmin, action

class TaskAdmin(ModelAdmin, model=Task):
    list_display = ("title", "status", "project", "due")
    search_fields = ("title",)
    list_filter = ("status", "project")

admin = AdminPlugin(SessionLocal, views=(TaskAdmin,), base_template="base.html")
mount_fjkit(app, FjkitConfig(template_dir=…, plugins=(admin,)))
"""

from fjkit_admin.options import ModelAdmin, action, display
from fjkit_admin.plugin import AdminPlugin

__all__ = ["AdminPlugin", "ModelAdmin", "action", "display"]
