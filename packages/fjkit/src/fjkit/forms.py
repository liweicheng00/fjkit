"""Naming a validation failure the way a form names its fields.

    errors = field_errors(exc, request_scoped=True)
    errors.title          # "Field required", or None

`fjkit.errors` renders the navigation error page from this and reads
`.messages()` for a toast. `static/js/errors.js` does the same `loc`-to-name
derivation in the browser; `field_name` here and `fieldName` there must agree.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

__all__ = [
    "NO_ERRORS",
    "FieldErrors",
    "field_errors",
    "field_name",
    "label",
]

#: Where FastAPI puts a form or JSON body field. Stripped from `loc` so that a
#: field is named the way the form names it — `title`, not `body.title`. The
#: others are kept: a failure in the query string or a path segment is not a
#: field on this form, and flattening it to a bare name would let it light up
#: an unrelated input.
_BODY = "body"

#: Pydantic's word for "this body was not JSON at all", and the one failure
#: whose `loc` does not name a field: it reads `("body", <offset>)`, a position
#: in the text. `field_name` cannot be the one to notice, because `("body", 0)`
#: is also exactly what a body that *is* a list reports about its first item —
#: the two shapes are identical and only the type tells them apart. Left to it,
#: an unreadable body becomes a field called `1` and a toast reading
#: "2: JSON decode error", which names a byte to a person who typed characters.
#:
#: Only JSON gets here. A urlencoded body has no parse step that can fail this
#: way: what is not a pair is simply not a field.
_UNPARSABLE = frozenset({"json_invalid"})


class _ByField(Mapping[str, str]):
    """A mapping readable as `errors.title`; an absent name answers `None`."""

    __slots__ = ("_by_field",)

    def __init__(self, by_field: Mapping[str, str]) -> None:
        self._by_field = dict(by_field)

    def __getattr__(self, name: str) -> str | None:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._by_field.get(name)

    def __getitem__(self, key: str) -> str:
        return self._by_field[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._by_field)

    def __len__(self) -> int:
        return len(self._by_field)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._by_field!r})"


class FieldErrors(_ByField):
    """Field name -> the first message for it."""

    __slots__ = ("_general",)

    def __init__(self, by_field: Mapping[str, str], general: Sequence[str] = ()) -> None:
        super().__init__(by_field)
        self._general = tuple(general)

    @property
    def general(self) -> tuple[str, ...]:
        """Messages with no field: a model-level rule, a malformed body, a `loc`
        outside the body.
        """
        return self._general

    def __repr__(self) -> str:
        return f"FieldErrors({self._by_field!r}, general={self._general!r})"

    def messages(self) -> tuple[str, ...]:
        """Every message, field ones first and prefixed with `label(name)`."""
        return (*(f"{label(name)}: {text}" for name, text in self._by_field.items()), *self._general)


def field_errors(exc: Any, *, request_scoped: bool) -> FieldErrors:
    """Read `exc.errors()` into `FieldErrors`.

    `request_scoped=True` for FastAPI's `RequestValidationError`, whose `loc`
    starts with where the value came from (`("body", "title")`); `False` for a
    pydantic `ValidationError`, whose `loc` is `("title",)`. An unparsable
    body (`_UNPARSABLE`) goes to `general`.
    """
    by_field: dict[str, str] = {}
    general: list[str] = []
    for detail in getattr(exc, "errors", lambda: ())():
        message = str(detail.get("msg", "Invalid value"))
        if detail.get("type") in _UNPARSABLE:
            general.append(message)
            continue
        name = field_name(detail.get("loc", ()), request_scoped=request_scoped)
        if name is None:
            general.append(message)
        elif name not in by_field:
            by_field[name] = message
    return FieldErrors(by_field, general)


def field_name(loc: Sequence[Any], *, request_scoped: bool) -> str | None:
    """The form field a `loc` refers to, or `None`.

    Request-scoped: `("body", "title")` -> `"title"`; anything not under
    `body` -> `None`. Model-scoped: `("title",)` -> `"title"`; empty -> `None`.
    Nested paths are joined with dots: `("body", "items", 0, "title")` ->
    `"items.0.title"`.
    """
    parts = tuple(loc)
    if request_scoped:
        if not parts or parts[0] != _BODY:
            return None
        parts = parts[1:]
    if not parts:
        return None
    return ".".join(str(part) for part in parts)


def label(name: str) -> str:
    """`owner_name` -> `Owner name`, `items.0.title` -> `Items 1 title`.
    Indexes are shown one-based.
    """
    parts = []
    for part in name.split("."):
        parts.append(str(int(part) + 1) if part.isdigit() else part.replace("_", " "))
    return " ".join(parts).strip().capitalize()


NO_ERRORS = FieldErrors({})
