"""What the mapper says about a model, read once and kept.

Everything else in this package — the list columns, the form fields, the
search clause, the label on a foreign-key select — is derived from the
`Mapper` that SQLAlchemy already built for the class. Nothing is declared
twice: a column that gains `nullable=False` in the model becomes required in
the admin form without anyone touching the admin.

A SQLModel `table=True` class produces the same `Mapper`, so it goes through
this module unchanged. Whether the class also carries a pydantic schema is a
question `schema.py` asks later.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, Integer, Numeric, String, Text, Time
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import ColumnProperty, Mapper, RelationshipProperty

__all__ = ["ColumnInfo", "ModelInfo", "RelationInfo", "inspect_model", "label"]


def label(name: str) -> str:
    """`owner_name` as `Owner name`, the way fjkit's `forms.label` spells it."""
    return name.replace("_", " ").strip().capitalize()


def _python_type(column: Column) -> type | None:
    """The Python type a column's values take, or `None` when the type has none.

    `TypeEngine.python_type` raises rather than guessing for a type that has
    no single Python counterpart. A `TypeDecorator` usually knows through its
    `impl`, so that is tried second; after that the answer is honestly unknown
    and the caller falls back to text.
    """
    try:
        return column.type.python_type
    except NotImplementedError:
        impl = getattr(column.type, "impl", None)
        if impl is not None:
            try:
                return impl.python_type
            except NotImplementedError:
                return None
        return None


@dataclass(frozen=True, slots=True)
class ColumnInfo:
    """One mapped column, as the admin needs to know it."""

    key: str
    column: Column
    python_type: type | None
    nullable: bool
    primary_key: bool
    #: True when SQLAlchemy or the database supplies a value the form may omit.
    has_default: bool
    foreign_key: bool
    #: `Enum` columns backed by a Python enum class carry it here; every other
    #: column, and an `Enum` of bare strings, leaves it `None`.
    enum_class: type[enum.Enum] | None
    #: The declared `String(80)` length, when there is one.
    length: int | None
    #: `Column.info`, the sanctioned place for per-column hints. The admin
    #: reads the `"admin"` entry: `{"label": …, "help": …, "widget": …}`.
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """The widget family this column wants, as a closed name.

        text | textarea | number | boolean | date | datetime | time | enum

        Decided from the SQLAlchemy type first, because that is what the
        column declared, and from the Python type only when the SQLAlchemy
        type is one this module has no rule for.
        """
        sa_type = self.column.type
        if self.enum_class is not None or isinstance(sa_type, Enum):
            return "enum"
        if isinstance(sa_type, Boolean):
            return "boolean"
        if isinstance(sa_type, Text):
            return "textarea"
        if isinstance(sa_type, DateTime):
            return "datetime"
        if isinstance(sa_type, Date):
            return "date"
        if isinstance(sa_type, Time):
            return "time"
        if isinstance(sa_type, (Integer, Numeric, Float)):
            return "number"
        if isinstance(sa_type, String):
            return "text"
        py = self.python_type
        if py is bool:
            return "boolean"
        if py in (int, float):
            return "number"
        return "text"

    @property
    def admin_info(self) -> dict[str, Any]:
        value = self.info.get("admin", {})
        return value if isinstance(value, dict) else {}

    @property
    def label(self) -> str:
        return str(self.admin_info.get("label") or label(self.key))


@dataclass(frozen=True, slots=True)
class RelationInfo:
    """One relationship, reduced to the three facts a form and a list need."""

    key: str
    #: MANYTOONE | ONETOMANY | MANYTOMANY | ONETOONE
    direction: str
    target: type
    uselist: bool
    #: The local foreign-key column keys behind a many-to-one, so a form can
    #: render the relationship as a select over the target and post the key.
    local_columns: tuple[str, ...]

    @property
    def label(self) -> str:
        return label(self.key)


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """The mapper, read into plain fields."""

    model: type
    mapper: Mapper
    pk: ColumnInfo
    columns: dict[str, ColumnInfo]
    relations: dict[str, RelationInfo]

    @property
    def name(self) -> str:
        return self.model.__name__

    def column(self, key: str) -> ColumnInfo | None:
        return self.columns.get(key)

    def relation(self, key: str) -> RelationInfo | None:
        return self.relations.get(key)

    def relation_for_column(self, key: str) -> RelationInfo | None:
        """The many-to-one whose foreign key is `key`, if there is one."""
        for relation in self.relations.values():
            if relation.direction == "MANYTOONE" and key in relation.local_columns:
                return relation
        return None

    def identity(self, obj: Any) -> Any:
        """The primary-key value of an instance, from the instance state."""
        state = sa_inspect(obj)
        identity = state.identity
        if identity is None:
            return getattr(obj, self.pk.key)
        return identity[0] if len(identity) == 1 else identity


def inspect_model(model: type) -> ModelInfo:
    """Read a mapped class. Raises `TypeError` for anything SQLAlchemy cannot map."""
    try:
        mapper: Mapper = sa_inspect(model)
    except NoInspectionAvailable as exc:
        raise TypeError(
            f"{model!r} is not a SQLAlchemy mapped class; the admin can only register mapped classes."
        ) from exc

    if len(mapper.primary_key) != 1:
        raise TypeError(
            f"{model.__name__} has a composite primary key ({[c.key for c in mapper.primary_key]}); "
            "fjkit-admin 0.1 addresses a row by one key."
        )

    columns: dict[str, ColumnInfo] = {}
    for attr in mapper.column_attrs:
        if not isinstance(attr, ColumnProperty) or len(attr.columns) != 1:
            continue
        column = attr.columns[0]
        if not isinstance(column, Column):
            # A column_property over an expression: readable, never editable,
            # and not something a generic form has a widget for.
            continue
        sa_type = column.type
        enum_class = getattr(sa_type, "enum_class", None) if isinstance(sa_type, Enum) else None
        columns[attr.key] = ColumnInfo(
            key=attr.key,
            column=column,
            python_type=_python_type(column),
            nullable=bool(column.nullable),
            primary_key=bool(column.primary_key),
            has_default=column.default is not None
            or column.server_default is not None
            or bool(column.autoincrement is True and column.primary_key),
            foreign_key=bool(column.foreign_keys),
            enum_class=enum_class if isinstance(enum_class, type) and issubclass(enum_class, enum.Enum) else None,
            # `impl` first: SQLModel's `AutoString` is a `TypeDecorator` over
            # `String`, and its length lives on the decorator itself.
            length=getattr(sa_type, "length", None) if isinstance(getattr(sa_type, "impl", sa_type), String) else None,
            info=dict(column.info or {}),
        )

    relations: dict[str, RelationInfo] = {}
    for rel in mapper.relationships:
        if not isinstance(rel, RelationshipProperty):
            continue
        direction = rel.direction.name
        if direction == "ONETOMANY" and not rel.uselist:
            direction = "ONETOONE"
        relations[rel.key] = RelationInfo(
            key=rel.key,
            direction=direction,
            target=rel.mapper.class_,
            uselist=bool(rel.uselist),
            local_columns=tuple(c.key for c in rel.local_columns if c.table is mapper.local_table),
        )

    pk_column = mapper.primary_key[0]
    pk = next((c for c in columns.values() if c.column is pk_column), None)
    if pk is None:
        raise TypeError(f"{model.__name__}: the primary key is not a plain mapped column.")

    return ModelInfo(model=model, mapper=mapper, pk=pk, columns=columns, relations=relations)
