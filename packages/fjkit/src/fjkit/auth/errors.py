"""The failures this plugin raises, and the response each one implies.

Two shapes rather than one. `NotAuthenticated` sends the browser to the login
screen. `CsrfRejected` leaves the browser where it is and answers 403, because
the request may come from an attacker and its victim has no login to do.
"""

from __future__ import annotations

__all__ = ["AuthError", "CsrfRejected", "NotAuthenticated", "RefreshFailed"]


class AuthError(Exception):
    """Base for everything this plugin raises."""


class NotAuthenticated(AuthError):
    """No usable session: no cookie, an unknown sid, or an expired store entry."""


class RefreshFailed(NotAuthenticated):
    """The upstream refused to renew the token.

    A subclass rather than a sibling, because a failed refresh also means the
    user logs in again: one handler covers both, and no caller has to remember
    the second name.
    """


class CsrfRejected(AuthError):
    """A cookie-authenticated write arrived without a trusted `Origin`."""
