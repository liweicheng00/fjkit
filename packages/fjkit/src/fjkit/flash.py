"""`FlashPlugin` — a message that survives a redirect.

`HX-Trigger` cannot carry one. It names an event for the page to fire, and a
redirect replaces the page: the document that would have listened is gone
before the header arrives. A full navigation has no JavaScript involved at all.

What does survive is the cookie jar. So a flash is written as a short-lived
signed cookie on the response that redirects, read back on the request that
lands, rendered into the next page, and cleared in the same breath — which is
why it appears exactly once and not again on reload.

Registering it is the whole setup. `ui/shell.html` already renders a toaster
region and fills it from `flash`, so no template in the app changes:

    flash = FlashPlugin(secret=os.environ["FJKIT_SECRET"])
    config = FjkitConfig(template_dir=…, plugins=(flash,))

Nothing here is specific to sessions. `AuthPlugin` takes one of these to
explain why it bounced you, but so can a route that just finished something:

    flash.add(response, "Saved", category="success")
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from fjkit.plugins import AppSetup, EnvSetup
from fjkit.signing import sign, unsign

__all__ = ["FlashMessage", "FlashPlugin"]

Category = Literal["info", "success", "warning", "error"]


@dataclass(frozen=True, slots=True)
class FlashMessage:
    """One message. `category` is what picks the toast's icon and timeout."""

    title: str
    text: str | None = None
    category: Category = "info"


class FlashPlugin:
    """Messages that outlive the response that produced them.

    The cookie is signed rather than encrypted: its contents are strings the
    app is about to show the user anyway, so there is nothing in it to hide.
    The signature is there so that a message cannot be *written* by whoever
    holds the browser — an unsigned flash cookie is a way to make a site
    display any text an attacker likes, which is a phishing tool.
    """

    name = "flash"

    def __init__(
        self,
        *,
        secret: str | bytes,
        cookie_name: str = "fjkit_flash",
        max_age: timedelta = timedelta(minutes=5),
        path: str = "/",
        secure: bool = True,
    ) -> None:
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.path = path
        self.secure = secure

    # ---------------------------------------------------------------- plugin

    def mount(self, setup: AppSetup) -> None:
        setup.add_middleware(_FlashMiddleware, plugin=self)

    def extend(self, setup: EnvSetup) -> None:
        setup.add_context_processor(self._read, provides=["flash"])

    def _read(self, request: Request) -> dict[str, object]:
        """Hand the template a queue that knows when it has been read."""
        return {"flash": _Queue(getattr(request.state, "flash", ()), request)}

    # ------------------------------------------------------------- app-facing

    def add(
        self,
        response: Response,
        title: str,
        text: str | None = None,
        *,
        category: Category = "info",
    ) -> None:
        """Queue a message for whatever page the browser lands on next.

        Set on the response that redirects, not on the one that renders — a
        message rendered into the page it was raised on does not need a cookie
        to get there.
        """
        self.set(response, [FlashMessage(title=title, text=text, category=category)])

    def set(self, response: Response, messages: Sequence[FlashMessage]) -> None:
        """Replace the queue outright. `add` is the one-message form."""
        payload = json.dumps(
            [{"title": m.title, "text": m.text, "category": m.category} for m in messages],
            separators=(",", ":"),
        ).encode("utf-8")
        response.set_cookie(
            self.cookie_name,
            self._sign(payload),
            max_age=int(self.max_age.total_seconds()),
            path=self.path,
            secure=self.secure,
            httponly=True,
            samesite="lax",
        )

    def clear(self, response: Response) -> None:
        response.delete_cookie(self.cookie_name, path=self.path)

    # -------------------------------------------------------------- internals

    def load(self, request: Request) -> tuple[FlashMessage, ...]:
        raw = request.cookies.get(self.cookie_name)
        if not raw:
            return ()
        payload = self._unsign(raw)
        if payload is None:
            return ()
        try:
            data = json.loads(payload)
            return tuple(
                FlashMessage(
                    title=str(item["title"]),
                    text=item.get("text"),
                    category=item.get("category", "info"),
                )
                for item in data
            )
        except (ValueError, TypeError, KeyError):
            # A cookie this process cannot read is not a message. Dropping it
            # beats 500-ing every page until the user clears their cookies.
            return ()

    def _sign(self, payload: bytes) -> str:
        return sign(self.secret, payload)

    def _unsign(self, raw: str) -> bytes | None:
        return unsign(self.secret, raw)


class _Queue:
    """The messages, plus the fact of having been looked at.

    Clearing the cookie on any request that merely carried it is not good
    enough. A page load fires more requests than the page: an htmx poll, a
    prefetch, a stylesheet. Every one of them would consume the message, and
    the page it belonged to would render an empty toaster.

    Nor is "a render happened" enough — an htmx swap renders a partial, and a
    partial has no toaster in it.

    So consumption is iteration. `{% for m in flash %}` marks it read;
    `{% if flash %}` does not, because asking whether there is anything to show
    is not showing it. This is what Django's messages framework does, for the
    same reason.
    """

    __slots__ = ("_messages", "_request")

    def __init__(self, messages: Sequence[FlashMessage], request: Request) -> None:
        self._messages = messages
        self._request = request

    def __bool__(self) -> bool:
        return bool(self._messages)

    def __len__(self) -> int:
        return len(self._messages)

    def __iter__(self):
        if self._messages:
            self._request.state.flash_rendered = True
        return iter(self._messages)


class _FlashMiddleware(BaseHTTPMiddleware):
    """Read on the way in, clear on the way out — but only once it was shown."""

    def __init__(self, app: Any, *, plugin: FlashPlugin) -> None:
        super().__init__(app)
        self.plugin = plugin

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request.state.flash = self.plugin.load(request)
        request.state.flash_rendered = False

        response = await call_next(request)

        shown = request.state.flash and getattr(request.state, "flash_rendered", False)
        # Not if the handler set a *new* flash on its way out — that one is for
        # the next page, and clearing it here would swallow the message.
        replaced = any(
            cookie.startswith(f"{self.plugin.cookie_name}=") for cookie in response.headers.getlist("set-cookie")
        )
        if shown and not replaced:
            self.plugin.clear(response)
        return response
