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


def _headers(response: Response | Headers) -> Headers:
    """The headers of a `Response`, or the mapping itself."""
    return response.headers if isinstance(response, Response) else response
