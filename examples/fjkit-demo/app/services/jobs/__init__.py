"""The jobs feature's public face. One module: the store is all there is."""

from __future__ import annotations

from app.services.jobs.store import JobService

__all__ = ["JobService"]
