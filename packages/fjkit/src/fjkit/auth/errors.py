"""What can go wrong, and who each one is aimed at.

Two shapes, deliberately not one. `NotAuthenticated` means *leave this page* —
the browser is sent to the login screen. `CsrfRejected` means *this request is
not yours* — the browser stays where it is and gets a 403, because sending a
possible attacker's victim to a login form is neither helpful nor honest.
"""

from __future__ import annotations

__all__ = ["AuthError", "CsrfRejected", "NotAuthenticated", "RefreshFailed"]


class AuthError(Exception):
    """Base for everything this plugin raises."""


class NotAuthenticated(AuthError):
    """No usable session: no cookie, an unknown sid, or an expired store entry."""


class RefreshFailed(NotAuthenticated):
    """The upstream would not renew the token.

    A subclass rather than a sibling: an app that cannot refresh is an app whose
    user has to log in again, so one handler covers both and no caller has to
    remember the second name.
    """


class CsrfRejected(AuthError):
    """A cookie-authenticated write arrived without a trusted `Origin`."""
