"""`ModelAdmin` — what an app says about one model, in Django's vocabulary.

    class TaskAdmin(ModelAdmin, model=Task):
        list_display = ("title", "status", "project", "due")
        search_fields = ("title", "notes")
        list_filter = ("status", "project")
        ordering = ("-created",)

Every option has a default derived from the mapper, so `class TaskAdmin(
ModelAdmin, model=Task): pass` is already a working list and form. The class
attributes are declarations; the `get_*` and `has_*` methods are the hooks a
subclass overrides when the answer depends on the request.

Names are Django's on purpose. An admin is a thing people already know how to
configure, and a second vocabulary for the same twelve knobs would be a cost
with nothing bought.
"""

from __future__ import annotations

import datetime as dt
import enum
import re
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from fastapi import Request
from sqlalchemy import Select
from sqlalchemy.orm import Session

from fjkit_admin.introspect import ColumnInfo, ModelInfo, RelationInfo, inspect_model, label

if TYPE_CHECKING:
    from fjkit_admin.plugin import AdminPlugin

__all__ = ["ModelAdmin", "action", "display"]

#: The widget names `widgets = {...}` and `Column.info["admin"]["widget"]` accept.
WIDGETS = frozenset(
    {"text", "textarea", "number", "boolean", "date", "datetime", "time", "enum", "select", "email", "url", "password"}
)


def action(
    description: str,
    *,
    variant: str = "secondary",
    confirm: str | None = None,
    permission: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a `ModelAdmin` method as a bulk action.

        @action("Mark done", confirm="Mark the selected tasks done?")
        def mark_done(self, request, session, objs) -> str | None:
            for task in objs:
                task.done = True
            return f"{len(objs)} marked done"

    The method receives the open session and the selected instances, and
    returns the toast text or `None` for the default one. `variant` is the
    button's, from fjkit's closed list. `permission` names a `has_*_permission`
    method that must answer True before the button renders or the action runs;
    `delete_selected` uses `"delete"`.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.__admin_action__ = {  # type: ignore[attr-defined]
            "description": description,
            "variant": variant,
            "confirm": confirm,
            "permission": permission,
        }
        return fn

    return decorate


def display(description: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Name the column a `list_display` method renders as.

        @display("Tasks")
        def task_count(self, project) -> int:
            return len(project.tasks)

    Without it the header is the method name spelled out, `Task count`. It
    sets the same `short_description` attribute Django's `@admin.display`
    does, so a method written for Django reads the same here.
    """

    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn.short_description = description  # type: ignore[attr-defined]
        return fn

    return decorate


def _words(name: str) -> str:
    """`ProjectMember` as `project member`."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


class ModelAdmin:
    """The options for one model. Subclass with `model=`; never instantiate by hand."""

    model: ClassVar[type]
    info: ClassVar[ModelInfo]
    #: The URL segment: `/admin/<key>/`. The lower-cased class name by default.
    key: ClassVar[str]
    verbose_name: ClassVar[str]
    verbose_name_plural: ClassVar[str]
    #: A Lucide icon name for the sidebar entry.
    icon: ClassVar[str] = "table"

    # ------------------------------------------------------------ list page
    #: Column keys, relationship keys, or names of methods on this class.
    #: Empty means every column, with foreign keys shown as their relation.
    list_display: ClassVar[Sequence[str]] = ()
    #: Which of `list_display` link to the change form. Empty means the first.
    list_display_links: ClassVar[Sequence[str]] = ()
    #: Text columns the search box matches, with `ILIKE %term%`. Empty hides the box.
    search_fields: ClassVar[Sequence[str]] = ()
    #: Enum, boolean or foreign-key columns that get a filter select.
    list_filter: ClassVar[Sequence[str]] = ()
    #: `("-created", "title")`. Empty means the primary key.
    ordering: ClassVar[Sequence[str]] = ()
    #: Which columns may be sorted by clicking their header. `None` means every
    #: plain column in `list_display`.
    sortable_by: ClassVar[Sequence[str] | None] = None
    list_per_page: ClassVar[int] = 25
    #: What the rows-per-page control offers. `list_per_page` is added if absent.
    page_sizes: ClassVar[Sequence[int]] = (25, 50, 100)
    #: What a `None` cell prints.
    empty_value_display: ClassVar[str] = "—"

    # ------------------------------------------------------------ change form
    #: Column keys in form order. A relationship key stands for its foreign-key
    #: column. Empty means every column but the primary key.
    fields: ClassVar[Sequence[str]] = ()
    exclude: ClassVar[Sequence[str]] = ()
    #: Shown on the form, never posted.
    readonly_fields: ClassVar[Sequence[str]] = ()
    labels: ClassVar[dict[str, str]] = {}
    help_texts: ClassVar[dict[str, str]] = {}
    #: Field name -> one of `WIDGETS`. Overrides what the column type implies.
    widgets: ClassVar[dict[str, str]] = {}
    #: How many rows a foreign-key select offers before it is too many for one.
    fk_limit: ClassVar[int] = 200

    # ------------------------------------------------------------ actions
    #: Method names decorated with `@action`, in button order.
    actions: ClassVar[Sequence[str]] = ("delete_selected",)

    def __init_subclass__(cls, model: type | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if model is None:
            if not hasattr(cls, "model"):
                raise TypeError(f"{cls.__name__} needs `model=`: class {cls.__name__}(ModelAdmin, model=Thing)")
            model = cls.model
        cls.model = model
        cls.info = inspect_model(model)
        if "key" not in cls.__dict__:
            cls.key = model.__name__.lower()
        if "verbose_name" not in cls.__dict__:
            cls.verbose_name = _words(model.__name__)
        if "verbose_name_plural" not in cls.__dict__:
            cls.verbose_name_plural = cls.verbose_name + "s"
        cls._validate_options()

    def __init__(self, admin: AdminPlugin) -> None:
        from fjkit_admin.schema import build_form_model

        self.admin = admin
        fields = self.form_fields()
        #: The body model the create and update routes declare. Built once per
        #: registration, from the same option values the form renders from.
        self.form_model = build_form_model(
            self.info, fields, {key: self.widget_for(key) for key in fields}, f"{self.info.name}Form"
        )

    # ---------------------------------------------------------------- hooks

    def get_queryset(self, request: Request, stmt: Select) -> Select:
        """The base `select(Model)`; narrow it here for per-request scoping."""
        return stmt

    def has_view_permission(self, request: Request, obj: Any | None = None) -> bool:
        return True

    def has_add_permission(self, request: Request) -> bool:
        return True

    def has_change_permission(self, request: Request, obj: Any | None = None) -> bool:
        return True

    def has_delete_permission(self, request: Request, obj: Any | None = None) -> bool:
        return True

    def save_model(self, request: Request, session: Session, obj: Any, data: dict[str, Any], change: bool) -> None:
        """Persist `obj`. `data` is the validated payload already applied to it."""
        session.add(obj)

    def delete_model(self, request: Request, session: Session, obj: Any) -> None:
        session.delete(obj)

    def label_for(self, obj: Any) -> str:
        """How an instance is named in a link, a select option and a toast.

        `str(obj)` when the class defines `__str__`; otherwise the verbose name
        and the key, because `<Task object at 0x…>` is not a label.
        """
        if type(obj).__str__ is not object.__str__:
            return str(obj)
        return f"{self.verbose_name} {self.info.identity(obj)}"

    # ------------------------------------------------------------- resolved

    @classmethod
    def _validate_options(cls) -> None:
        info = cls.info
        known = set(info.columns) | set(info.relations)
        for option in ("list_display", "search_fields", "list_filter", "fields", "exclude", "readonly_fields"):
            for name in getattr(cls, option):
                if name in known or (option == "list_display" and callable(getattr(cls, name, None))):
                    continue
                raise TypeError(
                    f"{cls.__name__}.{option} names {name!r}, which is not a column, relationship or method "
                    f"of {info.name}."
                )
        for name in cls.ordering:
            if name.lstrip("-") not in info.columns:
                raise TypeError(f"{cls.__name__}.ordering names {name!r}, which is not a column of {info.name}.")
        for name, widget in cls.widgets.items():
            if widget not in WIDGETS:
                raise TypeError(f"{cls.__name__}.widgets[{name!r}] = {widget!r}; choose from {sorted(WIDGETS)}.")
        for name in cls.actions:
            fn = getattr(cls, name, None)
            if fn is None or not hasattr(fn, "__admin_action__"):
                raise TypeError(f"{cls.__name__}.actions names {name!r}, which is not a method decorated with @action.")

    def column_key(self, name: str) -> str:
        """`project` and `project_id` both name the foreign-key column."""
        relation = self.info.relation(name)
        if relation is not None and relation.direction == "MANYTOONE" and len(relation.local_columns) == 1:
            return relation.local_columns[0]
        return name

    def form_fields(self) -> list[str]:
        """Column keys the form edits, in order, with the primary key and `exclude` left out."""
        if self.fields:
            names = [self.column_key(n) for n in self.fields]
        else:
            names = [key for key in self.info.columns if not self.info.columns[key].primary_key]
        excluded = {self.column_key(n) for n in self.exclude}
        readonly = {self.column_key(n) for n in self.readonly_fields}
        seen: set[str] = set()
        ordered: list[str] = []
        for name in names:
            if name in excluded or name in seen or name not in self.info.columns or name in readonly:
                continue
            seen.add(name)
            ordered.append(name)
        return ordered

    def readonly_columns(self) -> list[str]:
        return [self.column_key(n) for n in self.readonly_fields if self.column_key(n) in self.info.columns]

    def display_names(self) -> list[str]:
        """`list_display` resolved: every column by default, foreign keys as their relation."""
        if self.list_display:
            return list(self.list_display)
        names: list[str] = []
        for key, column in self.info.columns.items():
            relation = self.info.relation_for_column(key) if column.foreign_key else None
            names.append(relation.key if relation is not None else key)
        return names

    def link_names(self) -> set[str]:
        names = self.display_names()
        if self.list_display_links:
            return set(self.list_display_links)
        return {names[0]} if names else set()

    def sortable_names(self) -> set[str]:
        if self.sortable_by is not None:
            return {n for n in self.sortable_by if n in self.info.columns}
        return {n for n in self.display_names() if n in self.info.columns}

    def default_ordering(self) -> tuple[str, ...]:
        return tuple(self.ordering) or (self.info.pk.key,)

    def sizes(self) -> tuple[int, ...]:
        sizes = tuple(sorted({*self.page_sizes, self.list_per_page}))
        return sizes

    def field_label(self, name: str) -> str:
        if name in self.labels:
            return self.labels[name]
        relation = self.info.relation_for_column(name) if name in self.info.columns else self.info.relation(name)
        if relation is not None and (name not in self.info.columns or self.info.columns[name].foreign_key):
            return relation.label
        column = self.info.column(name)
        if column is not None:
            return column.label
        fn = getattr(self, name, None)
        described = getattr(fn, "short_description", None)
        return str(described) if described else label(name)

    def field_help(self, name: str) -> str | None:
        if name in self.help_texts:
            return self.help_texts[name]
        column = self.info.column(name)
        if column is None:
            return None
        return column.admin_info.get("help") or column.column.comment or None

    def widget_for(self, name: str) -> str:
        """The widget a form field renders as, from the override, the column's `info`, then its type."""
        if name in self.widgets:
            return self.widgets[name]
        column = self.info.column(name)
        if column is None:
            return "text"
        if column.foreign_key and self.info.relation_for_column(name) is not None:
            return "select"
        hinted = column.admin_info.get("widget")
        if hinted in WIDGETS:
            return str(hinted)
        return column.kind

    def filter_columns(self) -> list[ColumnInfo]:
        """`list_filter` as columns: enum, boolean or foreign-key, anything else is skipped."""
        result: list[ColumnInfo] = []
        for name in self.list_filter:
            column = self.info.column(self.column_key(name))
            if column is None:
                continue
            if column.kind in ("enum", "boolean") or column.foreign_key:
                result.append(column)
        return result

    def action_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for name in self.actions:
            meta = dict(getattr(self, name).__admin_action__)
            meta["name"] = name
            specs.append(meta)
        return specs

    def allowed_actions(self, request: Request) -> list[dict[str, Any]]:
        allowed: list[dict[str, Any]] = []
        for spec in self.action_specs():
            permission = spec.get("permission")
            if permission and not getattr(self, f"has_{permission}_permission")(request):
                continue
            allowed.append(spec)
        return allowed

    # --------------------------------------------------------------- values

    def display_value(self, obj: Any, name: str) -> str:
        """One cell's text, for a column, a relationship or a method of this class."""
        if name in self.info.relations:
            related = getattr(obj, name)
            if related is None:
                return self.empty_value_display
            if self.info.relations[name].uselist:
                return f"{len(related)}"
            return self.admin.label_for_instance(related)
        column = self.info.column(name)
        if column is not None:
            return self.format_value(getattr(obj, name), column)
        fn = getattr(self, name, None)
        if callable(fn):
            value = fn(obj)
            return self.empty_value_display if value is None else str(value)
        return self.empty_value_display

    def format_value(self, value: Any, column: ColumnInfo) -> str:
        if value is None:
            return self.empty_value_display
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, enum.Enum):
            return label(str(value.value))
        if isinstance(value, dt.datetime):
            return value.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, (dt.date, dt.time)):
            return value.isoformat()
        if column.foreign_key:
            relation = self.info.relation_for_column(column.key)
            if relation is not None:
                return str(value)
        return str(value)

    # -------------------------------------------------------------- actions

    @action(
        "Delete selected",
        variant="destructive",
        confirm="Delete the selected rows? This cannot be undone.",
        permission="delete",
    )
    def delete_selected(self, request: Request, session: Session, objs: Iterable[Any]) -> str:
        count = 0
        for obj in objs:
            self.delete_model(request, session, obj)
            count += 1
        return f"Deleted {count} {self.verbose_name if count == 1 else self.verbose_name_plural}"


def relation_options_query(relation: RelationInfo) -> Select:
    """`select(Target)` for a foreign-key select, ordered by its key so the list is stable."""
    from sqlalchemy import select

    target_info = inspect_model(relation.target)
    return select(relation.target).order_by(getattr(relation.target, target_info.pk.key))
