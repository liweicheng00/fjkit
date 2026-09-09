"""The `HX-*` headers, named once.

    from fjkit import htmx

    if htmx.is_swap(request):
        htmx.retarget(response, "#board", swap="outerHTML")
"""

from __future__ import annotations

from collections.abc import MutableMapping

from fastapi import Request, Response

__all__ = [
    "is_boosted",
    "is_htmx",
    "is_swap",
    "prompt",
    "push_url",
    "reswap",
    "retarget",
    "target",
]

#: Anything that accepts `headers["HX-Retarget"] = …`: a `Response`, a
#: `MutableHeaders`, or the plain dict `@render` builds a reply from. Typed as
#: the intersection rather than as `Response`, because the caller that matters
#: is an exception handler that has not built its response yet.
Headers = MutableMapping[str, str]


def is_htmx(request: Request) -> bool:
    """True for any request htmx made, boosted navigations included."""
    return request.headers.get("hx-request", "").lower() == "true"


def is_boosted(request: Request) -> bool:
    """True when htmx is performing an ordinary navigation on a link's behalf."""
    return request.headers.get("hx-boosted", "").lower() == "true"


def is_swap(request: Request) -> bool:
    """True for an htmx request that is replacing part of the page — htmx and
    not boosted.
    """
    return is_htmx(request) and not is_boosted(request)


def target(request: Request) -> str | None:
    """The id of the element this swap is aimed at, if htmx named one."""
    return request.headers.get("hx-target") or None


def prompt(request: Request) -> str | None:
    """Whatever `hx-prompt` collected, if the trigger asked for something."""
    return request.headers.get("hx-prompt") or None


def retarget(response: Response | Headers, selector: str, *, swap: str | None = None) -> None:
    """Set `HX-Retarget`, and `HX-Reswap` when `swap` is given. Pass `swap`:
    `hx-swap` was written for the original target.
    """
    headers = _headers(response)
    headers["HX-Retarget"] = selector
    if swap is not None:
        headers["HX-Reswap"] = swap


def reswap(response: Response | Headers, swap: str) -> None:
    """Override `hx-swap` for this response only. `retarget` usually implies it."""
    _headers(response)["HX-Reswap"] = swap


def push_url(response: Response | Headers, url: str) -> None:
    """Set `HX-Push-Url`: put this swap in the address bar and in history.

    For the swap that changes what the page is looking at — the row that was
    picked, the record that was opened — rather than for every swap. The state
    that decides a region's content belongs in the URL, where a reload, a
    bookmark, the back button and a second tab can all read it, and the route
    that renders the page already takes it as a parameter. A selection kept
    anywhere else is a selection the address bar cannot describe.

    The URL given must be one the app answers with a whole page, because that
    is what a reload of it asks for. Root-relative, for the reason `url_for`
    returns root-relative: an absolute one pins the reply to the host and the
    scheme the app happened to see.

    `hx-push-url="true"` on the trigger says the same thing when the request
    URL is already the one to show. This header is for when it is not: a pick
    posted to `/panels/select/3` shows as `/panels?task_id=3`.
    """
    _headers(response)["HX-Push-Url"] = url


def _headers(response: Response | Headers) -> Headers:
    """The headers of a `Response`, or the mapping itself."""
    return response.headers if isinstance(response, Response) else response
