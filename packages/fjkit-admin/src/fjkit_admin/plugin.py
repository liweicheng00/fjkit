"""`AdminPlugin` — the routes, and the context each template is handed.

    admin = AdminPlugin(SessionLocal, views=(TaskAdmin, ProjectAdmin), base_template="base.html")
    mount_fjkit(app, FjkitConfig(template_dir=…, plugins=(auth, admin)))

Shaped like `fjkit.apidocs.ApiDocsPlugin`: it owns a URL prefix, ships its
templates under its own `admin/` namespace so an app can shadow any one of
them, renders inside whatever `base_template` names, and gates every route
through `dependencies`. What it adds is a data layer — a `sessionmaker` and
the SQLAlchemy models the views register — which is exactly the thing fjkit
itself must not carry (CHARTER §1), and why this is a second distribution.

One region, `#admin-main`, is the target of every swap: a sort, a page, a
search, a saved form and a bulk action all replace it. The list partial and
the form partial both render into that id, so a saved form comes back as the
list without a second target anywhere.

Handlers that render are `def`, so Starlette runs them in the threadpool.
The one `async def` reads a request body htmx posted from a checkbox column
and does it with `parse_qs`, which keeps `python-multipart` off the
dependency list.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from fjkit import htmx, messages
from fjkit.plugins import AppSetup, EnvSetup
from fjkit.templating import get_templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fjkit_admin.introspect import ColumnInfo, inspect_model
from fjkit_admin.options import ModelAdmin, relation_options_query
from fjkit_admin.queries import FILTER_PREFIX, ListParams, run_list
from fjkit_admin.schema import apply, enum_options, sqlmodel_errors

__all__ = ["REGION", "TEMPLATE_DIR", "AdminPlugin"]

#: This plugin's own templates, handed to the loader by `extend`. The inner
#: `admin/` keeps the names `admin/page.html`, so an app shadows one by
#: writing `templates/admin/page.html`.
TEMPLATE_DIR = Path(__file__).parent / "templates"

#: The id every swap targets.
REGION = "admin-main"


class AdminPlugin:
    """A Django-style admin over SQLAlchemy models, rendered with fjkit.

    :param session_factory: a `sessionmaker` (or any callable returning a
        `Session` usable as a context manager). One session per request.
        An `async_sessionmaker` is refused with a message; 0.1 is sync only.
    :param views: `ModelAdmin` subclasses to register, in sidebar order.
    :param url: where the admin lives. Absolute, not `/`.
    :param title: the name in the sidebar and the tab.
    :param base_template: what the page extends — the kit's shell by default,
        or the app's `base.html` so the admin sits inside the app's chrome.
        The admin fills the shell's `sidebar` block with its model list, so a
        base that fills it too loses its own navigation here; `home_url` is
        the way back.
    :param dependencies: FastAPI dependencies on every route, typically
        `(Depends(auth.required),)`.
    """

    name = "admin"

    def __init__(
        self,
        session_factory: Callable[[], Session],
        views: Iterable[type[ModelAdmin]] = (),
        *,
        url: str = "/admin",
        title: str = "Admin",
        base_template: str = "ui/shell.html",
        dependencies: Sequence[Any] = (),
        home_url: str = "",
        home_label: str = "Back to the app",
        route_name: str = "fjkit_admin",
    ) -> None:
        if not url.startswith("/") or url == "/":
            raise ValueError(f"AdminPlugin(url={url!r}) must be an absolute path such as '/admin'.")
        if type(session_factory).__name__ == "async_sessionmaker":
            raise TypeError(
                "AdminPlugin needs a synchronous sessionmaker. fjkit-admin 0.1 renders in the threadpool and "
                "opens one Session per request; pass sessionmaker(engine), not async_sessionmaker."
            )
        self.session_factory = session_factory
        self.url = url.rstrip("/")
        self.title = title
        self.base_template = base_template
        self.dependencies = list(dependencies)
        self.home_url = home_url
        self.home_label = home_label
        self.route_name = route_name
        self.views: dict[str, ModelAdmin] = {}
        self._by_model: dict[type, ModelAdmin] = {}
        for view in views:
            self.register(view)

    # ------------------------------------------------------------- registry

    def register(self, view_cls: type[ModelAdmin]) -> ModelAdmin:
        """Add a view. Raises on a duplicate `key` or a duplicate model."""
        if not (isinstance(view_cls, type) and issubclass(view_cls, ModelAdmin)):
            raise TypeError(f"AdminPlugin.register() takes a ModelAdmin subclass, not {view_cls!r}.")
        if view_cls.key in self.views:
            raise ValueError(
                f"Two views share key={view_cls.key!r}: "
                f"{type(self.views[view_cls.key]).__name__} and {view_cls.__name__}."
            )
        if view_cls.model in self._by_model:
            raise ValueError(
                f"{view_cls.model.__name__} is already registered by {type(self._by_model[view_cls.model]).__name__}."
            )
        view = view_cls(self)
        self.views[view.key] = view
        self._by_model[view.model] = view
        return view

    def view_for(self, model: type) -> ModelAdmin | None:
        return self._by_model.get(model)

    def label_for_instance(self, obj: Any) -> str:
        """Name a row of any model — through its view when one is registered."""
        view = self._by_model.get(type(obj))
        if view is not None:
            return view.label_for(obj)
        if type(obj).__str__ is not object.__str__:
            return str(obj)
        info = inspect_model(type(obj))
        return f"{type(obj).__name__} {info.identity(obj)}"

    # --------------------------------------------------------------- plugin

    def mount(self, setup: AppSetup) -> None:
        taken = next((r for r in setup.app.routes if getattr(r, "path", None) == self.url), None)
        if taken is not None:
            setup.warn(
                f"{self.url} is already routed by {getattr(taken, 'name', taken)!r}. Starlette matches the "
                "first route that fits, so the admin index will never render. Pass a different `url=`."
            )
        setup.include_router(self._router())

    def extend(self, setup: EnvSetup) -> None:
        """Add `templates/` to the loader. Nothing else: every value a template
        needs is per-page and comes from the route."""
        setup.add_template_dir(TEMPLATE_DIR)

    # --------------------------------------------------------------- routes

    def _route(self, view: ModelAdmin | None, suffix: str) -> str:
        return f"{self.route_name}_{view.key}_{suffix}" if view else f"{self.route_name}_{suffix}"

    def list_url(self, view: ModelAdmin) -> str:
        return f"{self.url}/{view.key}"

    def _router(self) -> APIRouter:
        router = APIRouter(prefix=self.url, include_in_schema=False, dependencies=self.dependencies)

        def add(path: str, handler: Callable[..., Any], method: str, name: str) -> None:
            # Every GET page answers with and without a trailing slash, so the
            # admin never issues a redirect for one. Django's admin lives at
            # `/admin/` and redirects the other spelling with a permanent 301,
            # which browsers cache per host and port; a Django project that ran
            # on this port earlier leaves that 301 behind, and an admin that
            # redirected `/admin/` back to `/admin` would loop with it forever.
            router.add_api_route(path, handler, methods=[method], name=name)
            if method == "GET":
                router.add_api_route(path + "/", handler, methods=[method], name=f"{name}_slash")

        add("", self._index, "GET", self._route(None, "index"))
        for key, view in self.views.items():
            add(f"/{key}", self._list_handler(view), "GET", self._route(view, "list"))
            add(f"/{key}", self._create_handler(view), "POST", self._route(view, "create"))
            # `/new` before `/{pk}`: Starlette takes the first route that fits.
            add(f"/{key}/new", self._add_handler(view), "GET", self._route(view, "add"))
            add(f"/{key}/action/{{action}}", self._action_handler(view), "POST", self._route(view, "action"))
            add(f"/{key}/{{pk}}", self._change_handler(view), "GET", self._route(view, "change"))
            add(f"/{key}/{{pk}}", self._update_handler(view), "POST", self._route(view, "update"))
            add(f"/{key}/{{pk}}", self._delete_handler(view), "DELETE", self._route(view, "delete"))
        return router

    def _index(self, request: Request) -> HTMLResponse:
        models = []
        with self.session_factory() as session:
            for view in self.views.values():
                if not view.has_view_permission(request):
                    continue
                count = session.scalar(select(func.count()).select_from(view.model)) or 0
                models.append(
                    {
                        "label": view.verbose_name_plural,
                        "count_label": f"{count} {view.verbose_name if count == 1 else view.verbose_name_plural}",
                        "url": self.list_url(view),
                        "add_url": f"{self.list_url(view)}/new",
                        "can_add": view.has_add_permission(request),
                        "icon": view.icon,
                    }
                )
        context = {
            "title": self.title,
            "index_description": f"{len(models)} model{'' if len(models) == 1 else 's'}",
            "models": models,
        }
        return self._render(request, "admin/_index.html", context)

    def _list_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        def list_rows(request: Request) -> HTMLResponse:
            self._require(view.has_view_permission(request))
            params = ListParams.from_request(request, view)
            with self.session_factory() as session:
                context = self._list_context(request, session, view, params)
            return self._render(request, "admin/_list.html", context)

        return list_rows

    def _add_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        def add(request: Request) -> HTMLResponse:
            self._require(view.has_add_permission(request))
            with self.session_factory() as session:
                context = self._form_context(request, session, view, None)
            return self._render(request, "admin/_form.html", context)

        return add

    def _change_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        def change(request: Request, pk: str) -> HTMLResponse:
            with self.session_factory() as session:
                obj = self._load(session, view, pk)
                self._require(view.has_view_permission(request, obj))
                context = self._form_context(request, session, view, obj)
            return self._render(request, "admin/_form.html", context)

        return change

    def _create_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        payload_model = view.form_model

        def create(request: Request, payload: Any) -> HTMLResponse:
            self._require(view.has_add_permission(request))
            data = payload.model_dump()
            with self.session_factory() as session:
                errors = sqlmodel_errors(view.model, None, data, view.info)
                if errors:
                    raise RequestValidationError(errors)
                obj = view.model()
                apply(view.info, obj, data, view.form_fields())
                view.save_model(request, session, obj, data, change=False)
                session.commit()
                messages.add(
                    request, f"{view.verbose_name.capitalize()} added", view.label_for(obj), category="success"
                )
                context = self._list_context(request, session, view, ListParams())
            return self._render(request, "admin/_list.html", context, headers={"HX-Push-Url": self.list_url(view)})

        # The body's type is this view's generated model. Set after the `def`
        # so FastAPI reads the class, not a name it cannot resolve.
        create.__annotations__["payload"] = payload_model
        return create

    def _update_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        payload_model = view.form_model

        def update(request: Request, pk: str, payload: Any) -> HTMLResponse:
            data = payload.model_dump()
            with self.session_factory() as session:
                obj = self._load(session, view, pk)
                self._require(view.has_change_permission(request, obj))
                errors = sqlmodel_errors(view.model, obj, data, view.info)
                if errors:
                    raise RequestValidationError(errors)
                apply(view.info, obj, data, view.form_fields())
                view.save_model(request, session, obj, data, change=True)
                session.commit()
                messages.add(
                    request, f"{view.verbose_name.capitalize()} saved", view.label_for(obj), category="success"
                )
                context = self._list_context(request, session, view, ListParams())
            return self._render(request, "admin/_list.html", context, headers={"HX-Push-Url": self.list_url(view)})

        update.__annotations__["payload"] = payload_model
        return update

    def _delete_handler(self, view: ModelAdmin) -> Callable[..., HTMLResponse]:
        def delete(request: Request, pk: str) -> HTMLResponse:
            params = ListParams.from_request(request, view)
            with self.session_factory() as session:
                obj = self._load(session, view, pk)
                self._require(view.has_delete_permission(request, obj))
                label = view.label_for(obj)
                view.delete_model(request, session, obj)
                session.commit()
                messages.add(request, f"{view.verbose_name.capitalize()} deleted", label, category="success")
                context = self._list_context(request, session, view, params)
            # The list is what shows next whichever page the delete came from,
            # so the address bar says so.
            return self._render(request, "admin/_list.html", context, headers={"HX-Push-Url": context["page_url"]})

        return delete

    def _action_handler(self, view: ModelAdmin) -> Callable[..., Any]:
        async def run_action(request: Request, action: str) -> HTMLResponse:
            spec = next((s for s in view.allowed_actions(request) if s["name"] == action), None)
            if spec is None:
                raise HTTPException(status_code=404, detail=f"No action {action!r}.")
            # `hx-include="[data-fjkit-select]"` posts the ticked boxes as a
            # urlencoded body: `selected=3&selected=7`.
            body = (await request.body()).decode()
            raw = parse_qs(body).get("selected", [])
            params = ListParams.from_request(request, view)
            with self.session_factory() as session:
                objs = [
                    obj
                    for obj in (self._load(session, view, value, missing_ok=True) for value in raw)
                    if obj is not None
                ]
                if not objs:
                    messages.add(request, "Nothing was selected", "Tick a row first.", category="warning")
                else:
                    text = getattr(view, action)(request, session, objs)
                    session.commit()
                    messages.add(request, text or f"{len(objs)} updated", category="success")
                context = self._list_context(request, session, view, params)
            return self._render(request, "admin/_list.html", context)

        return run_action

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _require(allowed: bool) -> None:
        if not allowed:
            raise HTTPException(status_code=403, detail="Not allowed.")

    def _load(self, session: Session, view: ModelAdmin, raw: str, *, missing_ok: bool = False) -> Any:
        py = view.info.pk.python_type or str
        try:
            pk = py(raw)
        except (TypeError, ValueError):
            pk = None
        obj = session.get(view.model, pk) if pk is not None else None
        if obj is None and not missing_ok:
            raise HTTPException(status_code=404, detail=f"No {view.verbose_name} {raw!r}.")
        return obj

    def _render(
        self,
        request: Request,
        partial: str,
        context: Mapping[str, Any],
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> HTMLResponse:
        swap = htmx.is_swap(request)
        # `swap` reaches the partial so it can carry a `<title>`: htmx applies
        # one found in a fragment, and a saved form that becomes the list
        # should stop calling the tab "Add task".
        merged = {**self._base_context(request), **context, "partial": partial, "swap": swap}
        reply: dict[str, str] = {"vary": "HX-Request", **(headers or {})}
        if swap:
            # A full render shows the queue through the shell's toaster; a swap
            # has no shell, so the messages travel as `HX-Trigger`.
            trigger = messages.trigger_header(request, reply.get("HX-Trigger"))
            if trigger:
                reply["HX-Trigger"] = trigger
        return get_templates(request).page(
            request, partial if swap else "admin/page.html", merged, status_code=status_code, headers=reply
        )

    def _base_context(self, request: Request) -> dict[str, Any]:
        return {
            "base_template": self.base_template,
            "admin_title": self.title,
            "index_url": self.url,
            "home_url": self.home_url,
            "home_label": self.home_label,
            "region": REGION,
            "nav": [
                {"route": self._route(view, "list"), "label": view.verbose_name_plural.capitalize(), "icon": view.icon}
                for view in self.views.values()
                if view.has_view_permission(request)
            ],
        }

    # --------------------------------------------------------- list context

    def _list_context(self, request: Request, session: Session, view: ModelAdmin, params: ListParams) -> dict[str, Any]:
        result = run_list(view, request, session, params)
        base = self.list_url(view)
        sort_token = f"{'-' if result.descending else ''}{result.sort_key}"
        # Every link starts from this: the view settings, never the page number.
        common: dict[str, str] = {}
        if params.q:
            common["q"] = params.q
        for key, raw in params.filters.items():
            common[FILTER_PREFIX + key] = raw
        common["o"] = sort_token
        common["per_page"] = str(result.per_page)

        can_change = view.has_change_permission(request)
        links = view.link_names()
        sortable = view.sortable_names()
        actions = view.allowed_actions(request)

        columns: list[dict[str, Any]] = [{"select": True}] if actions else []
        for name in view.display_names():
            column = view.info.column(name)
            active = name == result.sort_key
            spec: dict[str, Any] = {
                "label": view.field_label(name),
                "align": "end" if column is not None and column.kind == "number" else None,
            }
            if name in sortable:
                spec["sort"] = ("desc" if result.descending else "asc") if active else None
                spec["sort_url"] = (
                    f"{base}?{urlencode({**common, 'o': ('-' if active and not result.descending else '') + name})}"
                )
            columns.append(spec)

        rows = []
        for obj in result.rows:
            pk = view.info.identity(obj)
            change_url = f"{base}/{pk}"
            cells = []
            for name in view.display_names():
                column = view.info.column(name)
                text = view.display_value(obj, name)
                cells.append(
                    {
                        "text": text,
                        "href": change_url if name in links and can_change else None,
                        "numeric": column is not None and column.kind == "number",
                        "align": "end" if column is not None and column.kind == "number" else None,
                        "tone": "muted" if text == view.empty_value_display else None,
                    }
                )
            rows.append({"pk": pk, "label": view.label_for(obj), "cells": cells})

        filters = []
        for column in view.filter_columns():
            filters.append(
                {
                    "name": FILTER_PREFIX + column.key,
                    "label": view.field_label(column.key),
                    "options": self._filter_options(session, view, column),
                    "selected": params.filters.get(column.key, ""),
                    "blank": "All",
                }
            )

        return {
            "title": view.verbose_name_plural.capitalize(),
            "view": {"verbose_name": view.verbose_name, "verbose_name_plural": view.verbose_name_plural},
            "urls": {"list": base, "add": f"{base}/new"},
            "can_add": view.has_add_permission(request),
            "search": {
                "enabled": bool(view.search_fields),
                "q": params.q,
                "placeholder": "Search " + ", ".join(view.field_label(n).lower() for n in view.search_fields),
            },
            "filters": filters,
            "hidden": [("o", sort_token), ("per_page", str(result.per_page))],
            "actions": [
                {**spec, "url": f"{base}/action/{spec['name']}?{urlencode({**common, 'page': result.page})}"}
                for spec in actions
            ],
            "select": bool(actions),
            "columns": columns,
            "rows": rows,
            "total": result.total,
            "page": result.page,
            "pages": result.pages,
            "per_page": result.per_page,
            "page_sizes": view.sizes(),
            "keep": {k: v for k, v in common.items() if k != "per_page"},
            "page_url": f"{base}?{urlencode(common)}",
            "empty_description": "Nothing matches this search."
            if params.q or params.filters
            else f"No {view.verbose_name} has been added yet.",
        }

    def _filter_options(self, session: Session, view: ModelAdmin, column: ColumnInfo) -> list[tuple[str, str]]:
        if column.kind == "boolean":
            return [("1", "Yes"), ("0", "No")]
        if column.kind == "enum":
            return enum_options(column)
        relation = view.info.relation_for_column(column.key)
        if relation is None:
            return []
        return self._relation_options(session, view, relation.target, relation)

    def _relation_options(
        self, session: Session, view: ModelAdmin, target: type, relation: Any
    ) -> list[tuple[str, str]]:
        target_info = inspect_model(target)
        rows = session.scalars(relation_options_query(relation).limit(view.fk_limit)).all()
        return [(str(target_info.identity(row)), self.label_for_instance(row)) for row in rows]

    # --------------------------------------------------------- form context

    def _form_context(self, request: Request, session: Session, view: ModelAdmin, obj: Any | None) -> dict[str, Any]:
        base = self.list_url(view)
        is_change = obj is not None
        fields = []
        for key in view.form_fields():
            column = view.info.columns[key]
            widget = view.widget_for(key)
            value = getattr(obj, key) if obj is not None else _scalar_default(column)
            spec: dict[str, Any] = {
                "name": key,
                "label": view.field_label(key),
                "widget": widget,
                "hint": view.field_help(key),
                "required": widget != "boolean" and not column.nullable and not column.has_default,
                "readonly": False,
                "value": _input_value(value),
                "checked": bool(value),
                "options": [],
                "selected": None if value is None else _input_value(value),
                "blank": None,
                "maxlength": column.length,
                "step": "any" if column.python_type in (float, decimal.Decimal) else None,
            }
            if widget == "enum":
                spec["options"] = enum_options(column)
            elif widget == "select":
                relation = view.info.relation_for_column(key)
                spec["options"] = self._relation_options(session, view, relation.target, relation) if relation else []
            if widget in ("enum", "select"):
                spec["blank"] = "—" if not spec["required"] or value is None else None
            fields.append(spec)
        # Read-only columns are shown on the change form only. On the add form
        # there is no row yet, and an empty disabled box says nothing.
        for key in view.readonly_columns() if obj is not None else ():
            column = view.info.columns[key]
            value = getattr(obj, key)
            fields.append(
                {
                    "name": key,
                    "label": view.field_label(key),
                    "widget": "text",
                    "hint": view.field_help(key),
                    "required": False,
                    "readonly": True,
                    "value": view.format_value(value, column) if value is not None else "",
                    "checked": False,
                    "options": [],
                    "selected": None,
                    "blank": None,
                    "maxlength": None,
                    "step": None,
                }
            )

        pk = view.info.identity(obj) if obj is not None else None
        return {
            "title": f"{'Change' if is_change else 'Add'} {view.verbose_name}",
            "form_title": f"{'Change' if is_change else 'Add'} {view.verbose_name}",
            "is_change": is_change,
            "obj_label": view.label_for(obj) if obj is not None else None,
            "can_delete": is_change and view.has_delete_permission(request, obj),
            "delete_confirm": f"Delete this {view.verbose_name}? This cannot be undone.",
            "urls": {
                "list": base,
                "submit": f"{base}/{pk}" if is_change else base,
                "delete": f"{base}/{pk}" if is_change else None,
            },
            "fields": fields,
        }


def _scalar_default(column: ColumnInfo) -> Any:
    """The column's Python-side default when it is a plain value, else `None`."""
    default = column.column.default
    if default is not None and getattr(default, "is_scalar", False):
        return default.arg
    return None


def _input_value(value: Any) -> str:
    """What goes in `value=`: the string an `<input>` of that type reads back."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "on" if value else ""
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)
