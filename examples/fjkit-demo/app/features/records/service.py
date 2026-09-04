"""In-memory store for the Records page.

Sorting, counting and slicing live here rather than in the router: a database
would answer them with `ORDER BY`, `COUNT(*)` and `LIMIT/OFFSET`, the same three
questions in the same order. The router asks; it does not compute.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from itertools import cycle, islice
from threading import Lock

from app.features.records.schemas import Record, Stage, parse_sort

#: Enough rows that the strip under the table has to elide something. Twelve to
#: a page over 137 rows is twelve pages, which is the case a five-page fixture
#: never reaches: an ellipsis on both sides at once.
_COUNT = 137

_NOUNS = ["orders", "sessions", "invoices", "events", "signups", "refunds", "shipments", "reviews"]
_QUALIFIERS = ["raw", "hourly", "daily", "rollup", "backfill", "staging", "archive"]
_OWNERS = ["livy", "mei", "kai", "unassigned"]
_STAGES = [Stage.INDEXED, Stage.DRAFT, Stage.INDEXED, Stage.ARCHIVED, Stage.INDEXED]


def _seed() -> list[Record]:
    """Build the fixture deterministically, so two runs sort identically.

    No `random`: a test asserting that page 3 descends by row count has to be
    able to say which rows page 3 holds.
    """
    epoch = date(2026, 8, 1)
    names = islice(zip(cycle(_NOUNS), cycle(_QUALIFIERS), strict=False), _COUNT)
    return [
        Record(
            id=i + 1,
            name=f"{noun}_{qualifier}_{i + 1:03d}",
            owner=_OWNERS[(i * 3) % len(_OWNERS)],
            stage=_STAGES[i % len(_STAGES)],
            rows=(i * 7919 % 900_000) + 1_200,
            updated=epoch - timedelta(days=(i * 5) % 180),
        )
        for i, (noun, qualifier) in enumerate(names)
    ]


class RecordService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[int, Record] = {r.id: r for r in _seed()}

    def count(self) -> int:
        return len(self._records)

    def page(self, sort: str | None, page: int, per_page: int) -> tuple[list[Record], int, int]:
        """Return one page of rows, the page number actually served, and the page count.

        The page number comes back out because it is clamped on the way in.
        `?page=900` is a stale bookmark, not an error worth a 404, and a page
        that answers it with an empty table shows a person nothing and explains
        nothing. Clamping lands them on the last page, where the rows are.
        """
        key, descending = parse_sort(sort)
        # `-id` breaks ties: two rows with the same owner must not swap places
        # between two renders of the same page, or paging drops rows silently.
        rows = sorted(self._records.values(), key=lambda r: (getattr(r, key), -r.id), reverse=descending)
        pages = max((len(rows) + per_page - 1) // per_page, 1)
        page = min(max(page, 1), pages)
        start = (page - 1) * per_page
        return rows[start : start + per_page], page, pages

    def archive(self, ids: Sequence[int]) -> int:
        """Move the named records to `archived`. Returns how many actually moved.

        Unknown ids are skipped rather than refused: the selection was made
        against a page that may since have been re-sorted, and failing the whole
        action over one stale id loses the other nine.
        """
        with self._lock:
            moved = 0
            for record_id in ids:
                record = self._records.get(record_id)
                if record is None or record.stage is Stage.ARCHIVED:
                    continue
                self._records[record_id] = record.model_copy(update={"stage": Stage.ARCHIVED})
                moved += 1
            return moved
