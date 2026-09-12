"""Reading the Records list: order, count, slice.

A database would answer all three with `ORDER BY`, `COUNT(*)` and
`LIMIT/OFFSET`, in that order. The router asks; it does not compute.
"""

from __future__ import annotations

from app.schemas.records import Record, parse_sort


def page(records: list[Record], sort: str | None, page: int, per_page: int) -> tuple[list[Record], int, int]:
    """Return one page of rows, the page number actually served, and the page count.

    The page number comes back out because it is clamped on the way in.
    `?page=900` is a stale bookmark, not an error worth a 404, and a page that
    answers it with an empty table shows a person nothing and explains nothing.
    Clamping lands them on the last page, where the rows are.
    """
    key, descending = parse_sort(sort)
    # `-id` breaks ties: two rows with the same owner must not swap places
    # between two renders of the same page, or paging drops rows silently.
    rows = sorted(records, key=lambda r: (getattr(r, key), -r.id), reverse=descending)
    pages = max((len(rows) + per_page - 1) // per_page, 1)
    page = min(max(page, 1), pages)
    start = (page - 1) * per_page
    return rows[start : start + per_page], page, pages
