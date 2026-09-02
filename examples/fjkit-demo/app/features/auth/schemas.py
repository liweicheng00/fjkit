"""Wire contracts for the session panel."""

from __future__ import annotations

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Context for the session panel, signed in or out."""

    signed_in: bool
    username: str | None = None
    #: Error text after a failed sign-in.
    error: str | None = None
    #: The demo credentials, prefilled in the form.
    demo_username: str
    demo_password: str


class SecretResponse(BaseModel):
    """Context for the protected fragment."""

    username: str
