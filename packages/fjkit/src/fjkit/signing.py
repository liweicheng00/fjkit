"""`<body>.<mac>` — the one cookie format the kit signs with.

Two plugins keep a value in a cookie the browser must not be able to write: a
flash message (otherwise a way to make a site display any text an attacker
likes) and the API console's credential. Neither value has to stay secret — one
is about to be printed on the page, the other is the caller's own token — so
this signs and does not encrypt.

One implementation rather than one per plugin: signing and verifying drifting
apart is the shape of bug that makes every cookie look valid.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac

__all__ = ["sign", "sign_text", "unsign", "unsign_text"]


def sign(secret: bytes, payload: bytes) -> str:
    """`payload`, base64url-encoded, with its MAC appended."""
    return sign_text(secret, base64.urlsafe_b64encode(payload).decode("ascii").rstrip("="))


def sign_text(secret: bytes, body: str) -> str:
    """Sign a body that is already ASCII-safe.

    Verification calls this too: `unsign` re-signs the body it was handed and
    compares, so one place decides what a signature is.
    """
    mac = hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(mac).decode('ascii').rstrip('=')}"


def unsign(secret: bytes, raw: str) -> bytes | None:
    """The payload `sign` was given, or `None` if this is not ours."""
    body = unsign_text(secret, raw)
    if body is None:
        return None
    try:
        return base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except (binascii.Error, ValueError):
        return None


def unsign_text(secret: bytes, raw: str) -> str | None:
    """The body half, verified but not decoded."""
    body, _, signature = raw.partition(".")
    if not signature:
        return None
    try:
        expected = sign_text(secret, body)
    except UnicodeEncodeError:
        # `sign_text` never produced a body with non-ASCII in it, so it cannot
        # verify. Refusing here keeps the failure a `None` like every other bad
        # cookie instead of an exception on the hot path.
        return None
    if not hmac.compare_digest(raw, expected):
        return None
    return body
