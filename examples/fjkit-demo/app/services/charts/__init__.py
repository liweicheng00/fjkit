"""The charts feature's public face: one builder per figure, and `build` for the page.

The individual builders are exported as well as `build`, because each takes the
rows it plots and a test asserts on one figure at a time.
"""

from __future__ import annotations

from app.services.charts.build import build
from app.services.charts.mix import owner_share, status_mix
from app.services.charts.oldest import oldest_open
from app.services.charts.trend import created_trend, intake
from app.services.charts.utils import TREND_DAYS
from app.services.charts.workload import workload

__all__ = [
    "TREND_DAYS",
    "build",
    "created_trend",
    "intake",
    "oldest_open",
    "owner_share",
    "status_mix",
    "workload",
]
