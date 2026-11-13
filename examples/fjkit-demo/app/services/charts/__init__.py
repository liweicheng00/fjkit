"""The charts feature's public face: one builder per figure, and `build` for the page.

The individual builders are exported as well as `build`, because each takes the
rows it plots and a test asserts on one figure at a time.
"""

from __future__ import annotations

from app.services.charts.age import age_spread
from app.services.charts.build import build, gallery
from app.services.charts.density import size_against_age, size_against_age_contour, stage_over_time
from app.services.charts.mix import owner_share, status_mix
from app.services.charts.oldest import oldest_open
from app.services.charts.raster import board_raster
from app.services.charts.shapes import age_histogram, age_shape, owner_mix, owner_status_grid
from app.services.charts.trend import created_trend, intake
from app.services.charts.utils import TREND_DAYS
from app.services.charts.workload import workload

__all__ = [
    "TREND_DAYS",
    "age_histogram",
    "age_shape",
    "age_spread",
    "board_raster",
    "build",
    "created_trend",
    "gallery",
    "intake",
    "oldest_open",
    "owner_mix",
    "owner_share",
    "owner_status_grid",
    "size_against_age",
    "size_against_age_contour",
    "stage_over_time",
    "status_mix",
    "workload",
]
