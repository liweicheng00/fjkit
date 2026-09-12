"""Every value the demo reads from outside itself, in one place.

`pydantic-settings`, so the same field is a default here, a `FJKIT_DEMO_*`
variable in the environment, and a line in `.env` — and no service has to know
which of the three it came from. Services are handed these values as arguments;
none of them imports this module.
"""

from __future__ import annotations

import os
import sys
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


def dev_port(default: str = "8000") -> str:
    """The port this process serves on: `PORT`, then `--port` in argv, then `default`.

    `fastapi dev --port 9000` never reaches the environment, so the CSRF check
    would otherwise trust an origin the browser is not sending.
    """
    if (from_env := os.environ.get("PORT")) is not None:
        return from_env
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--port" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--port="):
            return arg.split("=", 1)[1]
    return default


class Settings(BaseSettings):
    """The demo's configuration. Every default is the value a demo should have."""

    model_config = SettingsConfigDict(env_prefix="FJKIT_DEMO_", env_file=".env", extra="ignore")

    #: Signing secret for the flash and session cookies. Fixed by default so a
    #: reload during `fastapi dev` keeps the session that was signed in.
    secret: str = "fjkit-demo-not-a-secret"

    #: The single demo account, prefilled in the sign-in form.
    username: str = "ada"
    password: str = "lovelace"

    #: `False` because the demo is served over plain HTTP on localhost. A real
    #: app leaves this alone and gets `Secure` cookies.
    cookie_secure: bool = False

    @cached_property
    def port(self) -> str:
        return dev_port()

    @cached_property
    def trusted_origins(self) -> list[str]:
        """Origins the CSRF check accepts. Both loopback spellings of the dev port."""
        return [f"http://localhost:{self.port}", f"http://127.0.0.1:{self.port}"]


settings = Settings()
