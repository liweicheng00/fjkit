"""The list query: search, filters, order and one page of rows.

Every knob arrives from a query string somebody may have bookmarked, so an
unknown sort key, a page size outside the offered list and a page past the
end each fall back rather than raise. A 422 for a stale link loses the whole
page over a detail nobody chose; that is the rule the demo's Records page
follows, and an admin's lists are bookmarked more than most.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from fjkit_admin.introspect import ColumnInfo
from fjkit_admin.options import ModelAdmin

__all__ = ["ListParams", "ListResult", "coerce_filter", "parse_page_size", "parse_sort", "run_list"]

#: Query-string prefix for a filter on column `status`: `?f_status=done`.
FILTER_PREFIX = "f_"


@dataclass(frozen=True, slots=True)
class ListParams:
    """What the query string said, before any of it is trusted."""

    q: str = ""
    o: str | None = None
    page: int = 1
    per_page: int | None = None
    filters: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: Request, view: ModelAdmin) -> ListParams:
        params = request.query_params
        filters = {}
        for column in view.filter_columns():
            raw = params.get(FILTER_PREFIX + column.key, "")
            if raw != "":
                filters[column.key] = raw
        page = params.get("page", "1")
        per_page = params.get("per_page")
        return cls(
            q=params.get("q", "").strip(),
            o=params.get("o") or None,
            page=int(page) if page.isdigit() else 1,
            per_page=int(per_page) if per_page and per_page.isdigit() else None,
            filters=filters,
        )


@dataclass(frozen=True, slots=True)
class ListResult:
    rows: list[Any]
    total: int
    page: int
    pages: int
    per_page: int
    #: The order actually applied: column key and whether it descends.
    sort_key: str
    descending: bool


def parse_sort(view: ModelAdmin, value: str | None) -> tuple[str, bool]:
    """`-title` as `("title", True)`; anything not sortable falls back to the default order."""
    if value:
        key, descending = (value[1:], True) if value.startswith("-") else (value, False)
        if key in view.sortable_names() or key == view.info.pk.key:
            return key, descending
    first = view.default_ordering()[0]
    return (first[1:], True) if first.startswith("-") else (first, False)


def parse_page_size(view: ModelAdmin, value: int | None) -> int:
    return value if value in view.sizes() else view.list_per_page


def coerce_filter(column: ColumnInfo, raw: str) -> tuple[bool, Any]:
    """Turn the query-string text into a value the column compares to.

    Returns `(ok, value)`; a value the column cannot take is `(False, None)`
    and the filter is ignored, for the same reason an unknown sort key is.
    """
    if column.kind == "boolean":
        if raw in ("1", "true", "yes"):
            return True, True
        if raw in ("0", "false", "no"):
            return True, False
        return False, None
    if column.enum_class is not None:
        for member in column.enum_class:
            if str(member.value) == raw:
                return True, member
        return False, None
    py = column.python_type
    if py is None or py is str:
        return True, raw
    try:
        return True, py(raw)
    except (TypeError, ValueError):
        return False, None


def run_list(view: ModelAdmin, request: Request, session: Session, params: ListParams) -> ListResult:
    """Execute the list for one view and one page."""
    model = view.model
    info = view.info
    stmt = view.get_queryset(request, select(model))

    if params.q and view.search_fields:
        clauses = []
        for name in view.search_fields:
            column = info.column(view.column_key(name))
            if column is None:
                continue
            attr = getattr(model, column.key)
            clause = (
                attr.ilike(f"%{params.q}%")
                if column.kind in ("text", "textarea")
                else cast(attr, String).ilike(f"%{params.q}%")
            )
            clauses.append(clause)
        if clauses:
            stmt = stmt.where(or_(*clauses))

    for key, raw in params.filters.items():
        column = info.column(key)
        if column is None:
            continue
        ok, value = coerce_filter(column, raw)
        if ok:
            stmt = stmt.where(getattr(model, key) == value)

    for name in view.display_names():
        relation = info.relation(name)
        if relation is not None:
            stmt = stmt.options(selectinload(getattr(model, name)))

    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0

    sort_key, descending = parse_sort(view, params.o)
    order_attr = getattr(model, sort_key)
    stmt = stmt.order_by(order_attr.desc() if descending else order_attr.asc())
    if sort_key != info.pk.key:
        # A stable tiebreak, so two rows equal on the sort column keep one order
        # across pages instead of swapping places between page 2 and page 3.
        stmt = stmt.order_by(getattr(model, info.pk.key))

    per_page = parse_page_size(view, params.per_page)
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, params.page), pages)
    rows = list(session.scalars(stmt.limit(per_page).offset((page - 1) * per_page)).unique().all())

    return ListResult(
        rows=rows, total=total, page=page, pages=pages, per_page=per_page, sort_key=sort_key, descending=descending
    )
