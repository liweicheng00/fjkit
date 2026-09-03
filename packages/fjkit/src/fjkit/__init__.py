"""fjkit — a server-rendered UI kit for FastAPI.

Jinja2 for templates, Basecoat for component CSS, htmx for interactivity. The
stylesheet is built when fjkit is released, not when the app runs: no Tailwind,
no `package.json`, no build step in the app.

    from fastapi import FastAPI
    from fjkit import FjkitConfig, mount_fjkit

    config = FjkitConfig(template_dir=Path(__file__).parent / "templates")
    app = FastAPI()
    mount_fjkit(app, config)

Routes name their template on a decorator and return data:

    @router.get("/tasks")
    @render("tasks/page.html", partial="tasks/_board.html")
    def tasks_page(service: ServiceDep) -> BoardResponse:
        return BoardResponse(...)
"""

from __future__ import annotations

from fjkit import messages
from fjkit.config import FjkitConfig, RenderMode
from fjkit.flash import FlashMessage, FlashPlugin
from fjkit.messages import Message
from fjkit.mounting import mount_fjkit
from fjkit.plugins import AppSetup, EnvSetup, Plugin, PluginWarning
from fjkit.rendering import render
from fjkit.templating import Templates, build_environment, get_templates

__all__ = [
    "AppSetup",
    "EnvSetup",
    "FjkitConfig",
    "FlashMessage",
    "FlashPlugin",
    "Message",
    "Plugin",
    "PluginWarning",
    "RenderMode",
    "Templates",
    "build_environment",
    "get_templates",
    "messages",
    "mount_fjkit",
    "render",
]
