"""The form's pydantic model, built from the mapper.

A change form posts JSON — `form(encoding="json")` — to a route that declares
its body as a model, and that is the whole of the validation story: FastAPI
rejects a bad body with its own 422, fjkit's `errors.js` writes each message
under the control whose `name` matches the field, and nothing here renders an
error. The model only has to exist, with the right field names and types.

It is built with `pydantic.create_model` from `ColumnInfo`, one field per
editable column:

    nullable=True             ->  T | None = None
    has_default, not nullable ->  T | None = None, and `apply()` leaves the
                                  attribute alone when it arrives as None so
                                  the column default fires
    otherwise                 ->  T, required

Every field takes a `""` as `None` first. A browser posts an emptied text box
as an empty string, and "" is not a date, an int or a foreign key — it is the
absence of one, which is what the nullable rule above is about.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import BaseModel, ConfigDict, StringConstraints, create_model, field_validator

from fjkit_admin.introspect import ColumnInfo, ModelInfo

__all__ = ["apply", "build_form_model", "sqlmodel_errors"]


def _annotation(column: ColumnInfo, widget: str) -> Any:
    """The Python type a field validates to, from the widget then the column."""
    if column.foreign_key and widget == "select":
        return column.python_type or int
    if widget == "boolean":
        return bool
    if widget == "enum":
        if column.enum_class is not None:
            return column.enum_class
        enums = getattr(column.column.type, "enums", None)
        if enums:
            return Literal[tuple(enums)]  # type: ignore[valid-type]
        return str
    if widget == "date":
        return dt.date
    if widget == "datetime":
        return dt.datetime
    if widget == "time":
        return dt.time
    if widget == "number":
        py = column.python_type
        if py in (int, float, decimal.Decimal):
            return py
        return float
    if column.length:
        return Annotated[str, StringConstraints(max_length=column.length)]
    return str


def build_form_model(info: ModelInfo, fields: list[str], widgets: dict[str, str], name: str) -> type[BaseModel]:
    """One pydantic model for `fields`, named after the mapped class."""
    definitions: dict[str, Any] = {}
    #: Fields where an emptied control means "no value". A required text
    #: field is not one of them: there "" is a value that is too short, and
    #: "String should have at least 1 character" is the message to draw.
    blankable: list[str] = []
    for key in fields:
        column = info.columns[key]
        widget = widgets.get(key, column.kind)
        annotation = _annotation(column, widget)
        if widget == "boolean":
            # An unticked checkbox is absent from the payload, not false, so the
            # default is what makes "unticked" mean "no".
            definitions[key] = (bool, False)
        elif column.nullable or column.has_default:
            definitions[key] = (annotation | None, None)
            blankable.append(key)
        elif annotation is str or (get_origin(annotation) is Annotated and get_args(annotation)[0] is str):
            definitions[key] = (
                Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=column.length)],
                ...,
            )
        else:
            definitions[key] = (annotation, ...)
            blankable.append(key)

    def empty_to_none(cls: type, value: Any) -> Any:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    validators = {}
    if blankable:
        validators["_empty_to_none"] = field_validator(*blankable, mode="before")(classmethod(empty_to_none))  # type: ignore[arg-type]

    return create_model(  # type: ignore[call-overload]
        name,
        __config__=ConfigDict(extra="ignore", str_strip_whitespace=True),
        __validators__=validators,
        **definitions,
    )


def apply(info: ModelInfo, obj: Any, data: dict[str, Any], fields: list[str]) -> None:
    """Copy the validated payload onto the instance.

    A `None` for a column that is not nullable but has a default is left
    untouched rather than written: writing it would send NULL to a NOT NULL
    column, and the person left the box empty because they wanted the default.
    """
    for key in fields:
        if key not in data:
            continue
        value = data[key]
        column = info.columns[key]
        if value is None and not column.nullable and column.has_default:
            continue
        setattr(obj, key, value)


def is_sqlmodel_table(model: type) -> bool:
    """True for a SQLModel `table=True` class, without importing SQLModel.

    Duck-typed on the two attributes SQLModel adds to every model plus the one
    it sets only for table models. A plain SQLAlchemy class has none of them.
    """
    return bool(
        getattr(model, "__table__", None) is not None
        and hasattr(model, "model_validate")
        and getattr(model, "model_config", {}).get("table", False)
    )


def sqlmodel_errors(model: type, obj: Any | None, data: dict[str, Any], info: ModelInfo) -> list[dict[str, Any]]:
    """Run a SQLModel table class's own validators over the would-be row.

    A table model does not validate on construction — `Hero(age="x")` keeps
    the string — so the admin's pydantic model has already done the type
    checks. What remains are the validators the app wrote on the class
    (`@field_validator`, `@model_validator`), which only `model_validate` runs.

    The payload is completed with the current values of the row on an update,
    because `model_validate` wants every required field and a change form
    posts only the editable ones.

    Returns pydantic's error list with `loc` rooted at `body`, the shape
    FastAPI's own 422 uses, so `errors.js` draws these under the fields too.
    """
    if not is_sqlmodel_table(model):
        return []
    from pydantic import ValidationError

    values: dict[str, Any] = {}
    if obj is not None:
        for key in info.columns:
            values[key] = getattr(obj, key)
    values.update(data)
    try:
        model.model_validate(values)  # type: ignore[attr-defined]
    except ValidationError as exc:
        return [{**error, "loc": ("body", *error["loc"])} for error in exc.errors(include_url=False)]
    return []


def enum_options(column: ColumnInfo) -> list[tuple[str, str]]:
    """`(value, label)` pairs for an enum column, from the class or the bare strings."""
    if column.enum_class is not None:
        return [(str(member.value), _enum_label(member)) for member in column.enum_class]
    enums = getattr(column.column.type, "enums", None) or ()
    return [(str(value), str(value).replace("_", " ").capitalize()) for value in enums]


def _enum_label(member: enum.Enum) -> str:
    return str(member.value).replace("_", " ").capitalize()
