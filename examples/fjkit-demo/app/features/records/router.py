"""The Records page — 0.4's three additions on one table.

Sortable headers, a page strip and a batch-selection column, all as htmx swaps
into `#records`, and all of them still working with JavaScript off. That second
half is not decoration: an order and a page number are the two things about a
list that people bookmark and send to each other, so both live in the URL and
both are reachable by a plain GET.

One route serves the page and the swap. `@render(partial=…)` returns the shell
for a browser and `records/_table.html` for htmx, so the sort links and the
page links each need one address, not two, and the two cannot drift.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fjkit import messages, render

from app.features.records.schemas import (
    PAGE_SIZES,
    RecordsResponse,
    columns,
    page_url,
    parse_page_size,
    parse_sort,
)
from app.features.records.service import RecordService

router = APIRouter(tags=["records"])

#: Rows to a page when nothing asks for another size. Small enough that 137
#: records need twelve pages.
PER_PAGE = PAGE_SIZES[0]


def get_service(request: Request) -> RecordService:
    return request.app.state.records


ServiceDep = Annotated[RecordService, Depends(get_service)]


def _view(
    request: Request,
    service: RecordService,
    sort: str | None,
    page: int,
    per_page: int | None = None,
) -> RecordsResponse:
    """Build the table's context for one view and one page."""
    # `.path`, not the absolute URL Starlette returns: every href the kit
    # renders is root-relative, and a mixed page breaks a reverse proxy.
    base = request.url_for("records_page").path
    size = parse_page_size(per_page)
    records, page, pages = service.page(sort, page, size)
    key, descending = parse_sort(sort)
    return RecordsResponse(
        records=records,
        columns=columns(base, sort, size),
        page=page,
        pages=pages,
        total=service.count(),
        per_page=size,
        offset=(page - 1) * size,
        page_sizes=PAGE_SIZES,
        base_url=base,
        # The order survives a page-size change; the page number does not,
        # because it names a position and the change moves every position.
        keep={"o": f"{'-' if descending else ''}{key}"},
        page_url=page_url(base, sort, size),
        # The bulk action returns the person to the rows they were looking at,
        # so it has to carry every part of where that was.
        action_url=(
            f"{request.url_for('records_archive').path}"
            f"?o={sort or ''}&page={page}&per_page={size}"
        ),
    )


@router.get("/records", name="records_page")
@render("records/page.html", partial="records/_table.html")
def records_page(
    request: Request,
    service: ServiceDep,
    o: str | None = None,
    page: int = 1,
    per_page: int | None = None,
) -> RecordsResponse:
    """Render the Records page, or just the table for an htmx request.

    All three are plain query parameters with lenient handling behind them: an
    unknown sort key falls back to the default order, a page size outside the
    offered list falls back to the default size, and an out-of-range page
    clamps to the last one. Every one of them arrives from a link somebody
    kept, and a 422 for a stale link loses the page over a detail nobody chose.
    """
    return _view(request, service, o, page, per_page)


@router.post("/records/archive", name="records_archive")
@render("records/_table.html")
def archive_records(
    request: Request,
    service: ServiceDep,
    selected: Annotated[list[int] | None, Form()] = None,
    o: str | None = None,
    page: int = 1,
    per_page: int | None = None,
) -> RecordsResponse:
    """Archive the ticked rows and answer with the table they were ticked in.

    `selected` arrives as the repeated field a checkbox column has always
    posted — `selected=3&selected=7` — because `select_cell` writes an ordinary
    checkbox with an ordinary name. The button opposite it carries
    `hx-include="[data-fjkit-select]"`, and htmx omits an unticked box the way
    a form does, so nothing here has to filter.

    An empty selection is not an error. The button is reachable with nothing
    ticked, and saying so in a toast is more use than a 422 that swaps the
    table away.
    """
    selected = selected or []
    moved = service.archive(selected)
    if not selected:
        messages.add(request, "Nothing was selected", "Tick a row first.", category="warning")
    else:
        messages.add(
            request,
            f"Archived {moved} of {len(selected)}",
            "Rows already archived were left alone." if moved < len(selected) else None,
            category="success",
        )
    return _view(request, service, o, page, per_page)
