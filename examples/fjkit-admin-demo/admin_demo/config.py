"""Every value the admin demo reads from outside itself.

`pydantic-settings`, so the database can be moved with a `FJKIT_ADMIN_DEMO_*`
variable or a line in `.env` without editing a module.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FJKIT_ADMIN_DEMO_", env_file=".env", extra="ignore")

    #: A file next to the package, created and seeded on first start, so every
    #: restart shows the same rows and every edit survives one.
    database_url: str = f"sqlite:///{APP_DIR.parent / 'admin-demo.sqlite'}"

    #: What the admin calls itself, and the link back out of it.
    title: str = "Board admin"
    home_url: str = "/"
    home_label: str = "Back to the board"


settings = Settings()
