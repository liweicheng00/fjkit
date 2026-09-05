"""How the console gets a credential — the seam Swagger UI does not have.

OpenAPI can describe four kinds of authentication: an API key in a named place,
an HTTP scheme, an OAuth2 flow, and OpenID Connect. Swagger UI implements
exactly those, because it can only implement what the document can say. Every
other sign-in — a password posted to the app's own `/login`, an OIDC exchange
the server performs, a session cookie the browser may never read — is off the
map, and the "Authorize" dialog becomes a text box for a token obtained
somewhere else.

An `AuthFlow` is that dialog, written in Python by the app that owns the login.
It answers three questions:

* **What does the panel show?** `state()` — signed in or not, and the facts
  worth putting on screen.
* **How does someone sign in from here?** `sign_in()` — anything at all. The
  built-in `SessionFlow` calls `AuthPlugin.issue`, which runs the app's own
  `TokenSource`; the browser ends up holding the same HttpOnly cookie it would
  after using the app's real login form.
* **What does a call have to carry?** `headers()` — usually nothing, because
  the cookie is already travelling. `HeaderFlow` is the case where it is not.

The distinction that matters: the flow does not hand the console a credential
to attach. It puts the caller into the state the app defines, and the console
then makes a request as that caller. That is why refresh, revocation and expiry
work — `AuthPlugin` performs them, not this module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from fastapi import Request, Response
from fjkit.signing import sign_text, unsign_text

if TYPE_CHECKING:
    from fjkit.auth.plugin import AuthPlugin
    from fjkit.auth.types import Session

__all__ = [
    "AuthFlow",
    "FlowError",
    "FlowField",
    "FlowState",
    "HeaderFlow",
    "NoFlow",
    "SessionFlow",
]


#: Where `HeaderFlow` keeps a token for the rest of the request that saved it.
#: On `request.state` rather than an instance attribute, because the plugin is
#: one object shared by every concurrent request.
_STAGED = "fjkit_apidocs_token"


class FlowError(Exception):
    """A sign-in that failed for a reason the person can act on.

    Raise it for a bad password or a missing field. The panel prints the
    message verbatim, so the flow must make it useful to a developer and safe
    to show on a page.
    """


@dataclass(frozen=True, slots=True)
class FlowField:
    """One input on the sign-in panel."""

    name: str
    label: str
    type: Literal["text", "password", "email"] = "text"
    required: bool = True
    placeholder: str = ""
    hint: str = ""


@dataclass(frozen=True, slots=True)
class FlowState:
    """What the panel renders. Returned by `AuthFlow.state` on every render."""

    signed_in: bool
    headline: str
    detail: str = ""
    #: Label/value rows: who the caller is, what they may do, when the session
    #: runs out — whatever the flow finds worth showing.
    facts: tuple[tuple[str, str], ...] = ()
    #: Shown only when signed out. A flow with none is read-only.
    fields: tuple[FlowField, ...] = ()
    submit_label: str = "Sign in"
    sign_out_label: str = "Sign out"
    can_sign_out: bool = True
    error: str = ""

    def with_error(self, message: str) -> FlowState:
        from dataclasses import replace

        return replace(self, error=message)


@runtime_checkable
class AuthFlow(Protocol):
    """What `ApiDocsPlugin(flow=…)` accepts."""

    #: Identifies the flow in the panel's markup and in error messages.
    name: str
    #: The panel's heading.
    label: str

    def state(self, request: Request) -> FlowState:
        """Describe the panel. Synchronous, because it runs during a render.

        A flow needing I/O does it in `sign_in` and reads the result back off
        `request.state`, which is what `SessionFlow` does with the session
        `AuthPlugin`'s middleware already loaded.
        """

    async def sign_in(self, request: Request, response: Response, values: Mapping[str, str]) -> None:
        """Put the caller into the signed-in state. Raise `FlowError` to refuse.

        Cookies belong on `response`; the console copies them onto the reply
        that swaps the panel.
        """

    async def sign_out(self, request: Request, response: Response) -> None: ...

    def headers(self, request: Request) -> Mapping[str, str]:
        """Extra request headers for every call the console makes. Optional."""


# --------------------------------------------------------------------- flows


class NoFlow:
    """The panel for an app with no sign-in: a statement, not a form.

    The default when the docs plugin finds no `AuthPlugin` beside it. The page
    then has one shape rather than two — the session panel is always present,
    and on an open API it says so.
    """

    name = "none"
    label = "Authentication"

    def state(self, request: Request) -> FlowState:
        return FlowState(
            signed_in=False,
            headline="No sign-in configured",
            detail=(
                "Calls from this console go out with whatever this page's own request carried. "
                "Register an AuthPlugin, or pass ApiDocsPlugin(flow=…), to sign in from here."
            ),
            can_sign_out=False,
        )

    async def sign_in(self, request: Request, response: Response, values: Mapping[str, str]) -> None:
        raise FlowError("This API console has no sign-in flow configured.")

    async def sign_out(self, request: Request, response: Response) -> None:
        return None

    def headers(self, request: Request) -> Mapping[str, str]:
        return {}


class SessionFlow:
    """Sign in through the app's own `AuthPlugin`. The default when one exists.

    `sign_in` is `AuthPlugin.issue`, so the credentials go to whatever
    `TokenSource` the app configured — a password check, an OIDC exchange, an
    upstream token swap — and the browser is left holding the same signed
    HttpOnly cookie the app's real login form would set. From there the console
    carries no credential at all: it forwards the cookie, the session
    middleware does the rest, and the plugin refreshes a token that expires
    mid-session exactly as it would for a page.

        auth = AuthPlugin(secret=…, source=MyOIDCSource(), trusted_origins=[…])
        docs = ApiDocsPlugin()                     # finds `auth` by itself
        FjkitConfig(plugins=(auth, docs))

    Name the fields when the source wants something other than a username and
    a password. They reach `TokenSource.exchange` as a plain mapping, so a flow
    with one `api_key` field or three is the same code:

        ApiDocsPlugin(flow=SessionFlow(auth, fields=[FlowField("api_key", "API key")]))
    """

    name = "session"

    def __init__(
        self,
        auth: AuthPlugin,
        *,
        fields: Sequence[FlowField] | None = None,
        label: str = "Session",
        describe: Callable[[Session], Iterable[tuple[str, str]]] | None = None,
        attach_bearer: bool = False,
    ) -> None:
        self.auth = auth
        self.label = label
        self.fields = tuple(
            fields
            if fields is not None
            else (
                FlowField("username", "Username", placeholder="you@example.com"),
                FlowField("password", "Password", type="password"),
            )
        )
        #: Extra facts for the panel, from the app's own claims. The default
        #: shows what any session has; only the app knows that `claims["org"]`
        #: is the thing to check before calling anything.
        self.describe = describe
        #: For an API that reads the upstream token from `Authorization` rather
        #: than trusting the cookie. Off by default: putting the access token
        #: in a header the console composes is what the token-handler shape
        #: exists to avoid, and most fjkit apps do not need it.
        self.attach_bearer = attach_bearer

    def state(self, request: Request) -> FlowState:
        session = getattr(request.state, "auth", None)
        if session is None:
            return FlowState(
                signed_in=False,
                headline="Not signed in",
                detail=(
                    "Sign in here and every call below goes out as you — same cookie, same "
                    "session, same token refresh as the app's own pages."
                ),
                fields=self.fields,
            )
        return FlowState(
            signed_in=True,
            headline=_subject(session),
            detail="Calls carry this session. Nothing on this page can read the token.",
            facts=tuple(self._facts(session)),
        )

    def _facts(self, session: Session) -> Iterable[tuple[str, str]]:
        if self.describe is not None:
            yield from self.describe(session)
            return
        claims = dict(session.claims)
        for key in ("sub", "user_id", "email", "username", "name"):
            if key in claims:
                yield key, str(claims[key])
        scope = claims.get("scope") or claims.get("scopes")
        if scope:
            yield "scope", " ".join(scope) if isinstance(scope, (list, tuple)) else str(scope)
        yield "access token", "held server-side" if session.access else "none"
        if session.expires_at is not None:
            yield "expires", _relative(session.expires_at)
        yield "refresh token", "held" if session.refresh else "none"

    async def sign_in(self, request: Request, response: Response, values: Mapping[str, str]) -> None:
        missing = [f.label for f in self.fields if f.required and not values.get(f.name)]
        if missing:
            raise FlowError(f"{', '.join(missing)} required.")
        credentials = {f.name: values.get(f.name, "") for f in self.fields}
        try:
            await self.auth.issue(request, response, credentials)
        except FlowError:
            raise
        except Exception as exc:  # noqa: BLE001 — the source refused; say why
            # Reported rather than swallowed: whoever wrote the `TokenSource`
            # reads this page, and "sign-in failed" with the reason hidden
            # tells them nothing. An app that must not print the reason raises
            # `FlowError` with its own message from inside `exchange`.
            #
            # The class name alone when there is no message: `raise
            # BadCredentials` is an ordinary way to write a source, and
            # "BadCredentials: " with nothing after the colon reads as a bug in
            # this page rather than an answer from the app.
            detail = str(exc)
            raise FlowError(f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__) from exc

    async def sign_out(self, request: Request, response: Response) -> None:
        await self.auth.revoke(request, response)

    def headers(self, request: Request) -> Mapping[str, str]:
        if not self.attach_bearer:
            return {}
        session = getattr(request.state, "auth", None)
        access = getattr(session, "access", None)
        return {"Authorization": f"Bearer {access}"} if access else {}


class HeaderFlow:
    """Hold a token and put it on every call.

    For an API that authenticates with `Authorization: Bearer …` or an API key
    header, and for an app with no `AuthPlugin`. The difference from Swagger
    UI's version is where the value lives: in a signed, HttpOnly cookie this
    plugin owns, not in the page's JavaScript. Nothing running on the page can
    read it, it does not reach a bug report or a screen recording of the DOM,
    and it is scoped to the docs URL rather than to the origin.

        ApiDocsPlugin(flow=HeaderFlow(secret=os.environ["FJKIT_SECRET"]))
    """

    name = "header"

    def __init__(
        self,
        *,
        secret: str | bytes,
        header: str = "Authorization",
        scheme: str = "Bearer",
        label: str = "Token",
        field_label: str = "Token",
        hint: str = "",
        cookie_name: str = "fjkit_apidocs_token",
        cookie_path: str | None = None,
        max_age: timedelta = timedelta(hours=8),
        secure: bool = True,
    ) -> None:
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.header = header
        self.scheme = scheme
        self.label = label
        self.field_label = field_label
        self.hint = hint
        self.cookie_name = cookie_name
        #: Defaulted to the docs URL by `ApiDocsPlugin.mount`, so the token is
        #: only ever sent to the console. Set it yourself to widen that.
        self.cookie_path = cookie_path
        self.max_age = max_age
        self.secure = secure

    @property
    def _path(self) -> str:
        return self.cookie_path or "/"

    def _read(self, request: Request) -> str:
        # What this request just saved wins over what the browser sent. A
        # cookie set on the response is not in `request.cookies`, so without
        # this the panel rendered straight after "Save" would report no token
        # held, and the person would paste it again.
        staged = getattr(request.state, _STAGED, None)
        if staged is not None:
            return staged
        raw = request.cookies.get(self.cookie_name)
        if not raw:
            return ""
        body = unsign_text(self.secret, raw)
        if body is None:
            return ""
        try:
            return bytes.fromhex(body).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""

    def state(self, request: Request) -> FlowState:
        token = self._read(request)
        if not token:
            return FlowState(
                signed_in=False,
                headline=f"No {self.label.lower()} held",
                detail=(
                    f"Stored in an HttpOnly cookie scoped to this page and sent as "
                    f"`{self.header}` on every call. Nothing on the page can read it back."
                ),
                fields=(
                    FlowField(
                        "token",
                        self.field_label,
                        type="password",
                        hint=self.hint,
                        placeholder="paste it here",
                    ),
                ),
                submit_label="Save",
            )
        return FlowState(
            signed_in=True,
            headline=f"{self.label} held",
            detail=f"Sent as `{self.header}` on every call below.",
            facts=(("header", self.header), ("value", _mask(token))),
            sign_out_label="Forget",
        )

    async def sign_in(self, request: Request, response: Response, values: Mapping[str, str]) -> None:
        token = (values.get("token") or "").strip()
        if not token:
            raise FlowError(f"{self.field_label} required.")
        setattr(request.state, _STAGED, token)
        # Hex rather than base64url: the payload goes straight into a cookie
        # value, and hex has no `=` padding to strip and no `/` or `+` to
        # handle. The cost is doubling the length of a token nobody reads.
        response.set_cookie(
            self.cookie_name,
            sign_text(self.secret, token.encode("utf-8").hex()),
            max_age=int(self.max_age.total_seconds()),
            path=self._path,
            secure=self.secure,
            httponly=True,
            samesite="strict",
        )

    async def sign_out(self, request: Request, response: Response) -> None:
        setattr(request.state, _STAGED, "")
        response.delete_cookie(self.cookie_name, path=self._path)

    def headers(self, request: Request) -> Mapping[str, str]:
        token = self._read(request)
        if not token:
            return {}
        return {self.header: f"{self.scheme} {token}" if self.scheme else token}


# --------------------------------------------------------------------- bits


def _subject(session: Any) -> str:
    claims = dict(getattr(session, "claims", None) or {})
    for key in ("name", "email", "username", "sub", "user_id"):
        value = claims.get(key)
        if value:
            return f"Signed in as {value}"
    return "Signed in"


def _relative(moment: datetime) -> str:
    """Format `moment` against now: `in 12 min`, `4 s ago`.

    An absolute timestamp is the wrong unit for a token: a reader would have to
    do UTC arithmetic to find out whether the next call triggers a refresh.
    """
    delta = moment - datetime.now(UTC)
    seconds = int(abs(delta.total_seconds()))
    if seconds < 60:
        amount = f"{seconds} s"
    elif seconds < 3600:
        amount = f"{seconds // 60} min"
    elif seconds < 86400:
        amount = f"{seconds // 3600} h"
    else:
        amount = f"{seconds // 86400} d"
    return f"in {amount}" if delta.total_seconds() > 0 else f"{amount} ago"


def _mask(token: str) -> str:
    if len(token) <= 8:
        return "•" * len(token)
    return f"{token[:4]}{'•' * 6}{token[-4:]}"
