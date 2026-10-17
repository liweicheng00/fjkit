"""The failures this plugin raises, and the response each one implies.

Three shapes rather than one. `NotAuthenticated` sends the browser to the login
screen. `CsrfRejected` leaves the browser where it is and answers 403, because
the request may come from an attacker and its victim has no login to do.
`RefreshUnavailable` leaves the session in place and answers 503, because the
request was fine and the identity provider was not, and the token has expired
so there is nothing left to serve the request on.

`RefreshRefused` is the one exception here a `TokenSource` raises rather than
the plugin: it is how `refresh` says the upstream said no.
"""

from __future__ import annotations

__all__ = [
    "AuthError",
    "CsrfRejected",
    "NotAuthenticated",
    "RefreshFailed",
    "RefreshRefused",
    "RefreshUnavailable",
]


class AuthError(Exception):
    """Base for everything this plugin raises."""


class NotAuthenticated(AuthError):
    """No usable session: no cookie, an unknown sid, or an expired store entry."""


class RefreshFailed(NotAuthenticated):
    """The upstream refused to renew the token, and the session is gone.

    A subclass rather than a sibling, because a failed refresh also means the
    user logs in again: one handler covers both, and no caller has to remember
    the second name.
    """


class RefreshUnavailable(AuthError):
    """The upstream could not be asked to renew the token, and the session is kept.

    A sibling of `NotAuthenticated` rather than a subclass: sending the user to
    the login page would be wrong, because they are still logged in and the
    login page needs the same upstream. The request is answered 503 with a
    `Retry-After`, and the next request tries the refresh again.

    Raised only once the token has expired. Renewal starts `refresh_leeway`
    ahead of that, and a request inside the leeway is served on the token it
    still has. Logout never raises it: the plugin defers the refusal to
    whatever asks for the session, and a logout asks for nothing.
    """


class RefreshRefused(Exception):
    """Raised by `TokenSource.refresh` when the upstream said no.

    The one definitive answer: the refresh token is revoked, expired or
    unknown, and no retry will change that. Anything else `refresh` raises (a
    connection error, a timeout, an upstream 5xx) is read as transient. Not an
    `AuthError`, because it is the source's word to the plugin, not a response.
    """


class CsrfRejected(AuthError):
    """A cookie-authenticated write arrived without a trusted `Origin`."""
