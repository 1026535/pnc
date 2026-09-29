"""Measured Campaign geometry, thresholds, and OCR patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAP_HOUGH = (32, 18, 14, 25)
_PATH_HOUGH = (38, 25, 18, 33)
_HOUGH_PARAM1 = 100
_MAX_CIRCLE_CANDIDATES = 48

_MAP_PADLOCK_TEMPLATES = (
    "screen_anchors/campaign_map_padlock.png",
    "screen_anchors/campaign_map_padlock_alt.png",
)
_MAP_PADLOCK_THRESHOLD = 0.85
_MAP_PADLOCK_SEARCH = (0, 0, 540, 800)
_MAP_MAX_PADLOCKS = 8

_MAP_LOCK_LABEL_OFFSET = (-60, 6, 120, 42)
_MAP_PLATE_OFFSET = (12, -24, 150, 48)
_MAP_DISC_DIGIT_MARGIN = 2
_NUMERIC_CONFIDENCE_MIN = 0.80
_DISC_CORE_INSET_FRACTION = 0.10
_MAP_PADLOCK_CLUSTER_RADIUS = 45.0

_BADGE_DARK_MIN = 0.30
_BADGE_WHITE_MIN = 0.08
_BADGE_GOLD_BAND_MIN = 0.15
_BADGE_BLUE_INTERIOR_MIN = 0.12
_LOCK_BLUE_INTERIOR_MIN = 0.50
_LOCK_WHITE_MAX = 0.08
_LOCK_GLYPH_MIN = 0.18
_PLATE_GOLD_MIN = 0.30
_PLATE_NAVY_MIN = 0.10
_PLATE_NAVY_DARK_MIN = 0.20

_CHAPTER_TITLE_PATTERN = re.compile(r"ch\.?\s*(\d{1,2})", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"^(\d{1,2})$")
_LOCK_LABEL_PATTERN = re.compile(r"^(\d{1,2})\s*([A-Za-z].*)?$")


@dataclass(frozen=True, slots=True)
class _CircleCandidate:
    """One bounded Hough circle in reference coordinates."""

    cx: float
    cy: float
    radius: float
