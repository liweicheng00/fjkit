"""The Records store: the rows, and the one action that changes them."""

from __future__ import annotations

from collections.abc import Sequence
from threading import Lock

from app.schemas.records import Record, Stage
from app.services.records.seed import seed_records


class RecordService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[int, Record] = {r.id: r for r in seed_records()}

    def count(self) -> int:
        return len(self._records)

    def all(self) -> list[Record]:
        """Every row, unordered. `queries.page` decides the order."""
        return list(self._records.values())

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
