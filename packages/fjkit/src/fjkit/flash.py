"""`FlashPlugin` — a message that survives a redirect.

`fjkit.messages` shows a message on the current response. This layer sits above
it and covers the one case that layer cannot reach: a redirect replaces the
page, so the document that would have shown the message is gone before the
response arrives. `HX-Trigger` cannot help — it names an event for a page about
to be discarded — and a full navigation runs no JavaScript at all.

The cookie jar does survive. A flash is written as a short-lived signed cookie
on the response that redirects, read back on the request that lands, queued
into `fjkit.messages` like any other message, and cleared once it has been
shown — so it appears exactly once and not again on reload.

That last step is why this is a plugin and `fjkit.messages` is core. Signing
needs a secret, and requiring one from every app — including one with no forms
and nothing to say — would stop `mount_fjkit(app)` from working with no config
at all. Everything that needs no secret is core.

Registering the plugin is the whole setup. `ui/shell.html` renders the toaster
region and fills it from the message queue, so no template in the app changes:

    flash = FlashPlugin(secret=os.environ["FJKIT_SECRET"])
    config = FjkitConfig(template_dir=…, plugins=(flash,))

Nothing here is specific to sessions. `AuthPlugin` takes one of these to
explain why it bounced you, and so can a route that just finished something:

    flash.add(response, "Saved", category="success")
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from fjkit.messages import Category, Message
from fjkit.messages import extend as _queue
from fjkit.messages import shown as _was_shown
from fjkit.plugins import AppSetup
from fjkit.signing import sign, unsign

__all__ = ["FlashMessage", "FlashPlugin"]

#: Core's `Message`, under the name this module shipped it as. A flash is an
#: ordinary message that took a longer route to the page, so a second type
#: would mean two names for one thing and a conversion between them at the seam.
FlashMessage = Message


class FlashPlugin:
    """Messages that outlive the response that produced them.

    The cookie is signed rather than encrypted: it holds strings the app is
    about to show the user anyway, so there is nothing to hide. The signature
    stops whoever holds the browser from writing a message — an unsigned flash
    cookie makes a site display any text an attacker likes, which is a phishing
    tool.
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

    #: No `extend`. This plugin contributes no context key of its own: the
    #: cookie is queued into `fjkit.messages`, which the shell already renders,
    #: so a template never learns that a message arrived by cookie rather than
    #: from the handler it is rendering. That is the point of layering the two —
    #: one loop in the shell, not one per delivery mechanism.

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

        Set it on the response that redirects, not on the one that renders: a
        message rendered into the page it was raised on needs no cookie to get
        there.
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


class _FlashMiddleware(BaseHTTPMiddleware):
    """Queue on the way in, clear on the way out — but only once it was shown.

    "Shown" is `fjkit.messages.shown()`, set by delivery: a template iterating
    the queue, or the queue being drained into an `HX-Trigger`. Carrying the
    cookie is not enough — a page load fires more requests than the page (an
    htmx poll, a prefetch), and any of them would otherwise eat the message and
    leave the page it belonged to empty.
    """

    def __init__(self, app: Any, *, plugin: FlashPlugin) -> None:
        super().__init__(app)
        self.plugin = plugin

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        carried = self.plugin.load(request)
        if carried:
            _queue(request, carried)

        response = await call_next(request)

        # Skip the clear when the handler set a new flash on its way out: that
        # one is for the next page, and clearing it here would swallow it.
        replaced = any(
            cookie.startswith(f"{self.plugin.cookie_name}=") for cookie in response.headers.getlist("set-cookie")
        )
        if carried and _was_shown(request) and not replaced:
            self.plugin.clear(response)
        return response
