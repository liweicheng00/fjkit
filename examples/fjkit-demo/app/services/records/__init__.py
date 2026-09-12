"""The records feature's public face. Other layers import from here."""

from __future__ import annotations

from app.services.records.queries import page
from app.services.records.store import RecordService

__all__ = ["RecordService", "page"]
