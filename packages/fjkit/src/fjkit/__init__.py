"""fjkit — a server-rendered UI kit for FastAPI.

Jinja2 for templates, Basecoat for component CSS, htmx for interactivity. The
stylesheet is built when fjkit is released, not when your app runs: there is no
Tailwind, no package.json and no build step on your side.

    from fastapi import FastAPI
    from fjkit import FjkitConfig, Templates, mount_ui

    config = FjkitConfig(template_dir=Path(__file__).parent / "templates")
    app = FastAPI()
    mount_ui(app, config)
    app.state.templates = Templates.create(config)

Routes name their template on a decorator and return data:

    @router.get("/tasks")
    @render("tasks/page.html", partial="tasks/_board.html")
    def tasks_page(service: ServiceDep) -> BoardResponse:
        return BoardResponse(...)
"""

from __future__ import annotations

from fjkit.config import FjkitConfig, RenderMode
from fjkit.mounting import mount_ui
from fjkit.rendering import render
from fjkit.templating import Templates, build_environment, get_templates

__all__ = [
    "FjkitConfig",
    "RenderMode",
    "Templates",
    "build_environment",
    "get_templates",
    "mount_ui",
    "render",
]
