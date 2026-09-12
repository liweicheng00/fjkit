"""The Records fixture, built deterministically so two runs sort identically.

No `random`: a test asserting that page 3 descends by row count has to be able
to say which rows page 3 holds.
"""

from __future__ import annotations

from datetime import date, timedelta
from itertools import cycle, islice

from app.schemas.records import Record, Stage

#: Enough rows that the strip under the table has to elide something. Twelve to
#: a page over 137 rows is twelve pages, which is the case a five-page fixture
#: never reaches: an ellipsis on both sides at once.
_COUNT = 137

_NOUNS = ["orders", "sessions", "invoices", "events", "signups", "refunds", "shipments", "reviews"]
_QUALIFIERS = ["raw", "hourly", "daily", "rollup", "backfill", "staging", "archive"]
_OWNERS = ["livy", "mei", "kai", "unassigned"]
_STAGES = [Stage.INDEXED, Stage.DRAFT, Stage.INDEXED, Stage.ARCHIVED, Stage.INDEXED]


def seed_records() -> list[Record]:
    """Build the 137 rows the page opens on."""
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
