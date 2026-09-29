"""Measured Campaign marker geometry and row projection helpers."""

from __future__ import annotations

import cv2
import numpy as np

from pnc_automation.app.pnc.domain.observation import DetectedListEntry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import PreparedFrame

from .constants import (
    _BADGE_BLUE_INTERIOR_MIN, _BADGE_DARK_MIN, _BADGE_GOLD_BAND_MIN,
    _BADGE_WHITE_MIN, _HOUGH_PARAM1, _MAX_CIRCLE_CANDIDATES,
    _PLATE_GOLD_MIN, _PLATE_NAVY_DARK_MIN, _PLATE_NAVY_MIN, _LOCK_BLUE_INTERIOR_MIN, _LOCK_WHITE_MAX, _LOCK_GLYPH_MIN, _CircleCandidate,
)

def _circle_candidates(frame: PreparedFrame, params: tuple[int, int, int, int]) -> tuple[_CircleCandidate, ...]:
    """Bounded gray-frame Hough candidates; raw detections are not yet facts."""

    min_dist, param2, min_radius, max_radius = params
    gray = cv2.cvtColor(frame.pixels, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=min_dist,
        param1=_HOUGH_PARAM1,
        param2=param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return ()
    detected = np.round(circles[0], 1)
    return tuple(
        _CircleCandidate(cx=float(cx), cy=float(cy), radius=float(radius))
        for cx, cy, radius in detected[:_MAX_CIRCLE_CANDIDATES]
    )

def _to_reference_bounds(bounds: Bounds, frame: PreparedFrame) -> Bounds:
    """Project matcher output back into the frame's reference coordinate space."""

    original_width, original_height = frame.original_size
    reference_width, reference_height = frame.reference_size
    if (original_width, original_height) == (reference_width, reference_height):
        return bounds
    x = round(bounds.x * reference_width / original_width)
    y = round(bounds.y * reference_height / original_height)
    right = round((bounds.x + bounds.width) * reference_width / original_width)
    bottom = round((bounds.y + bounds.height) * reference_height / original_height)
    return Bounds(x=x, y=y, width=max(1, right - x), height=max(1, bottom - y))

def _disc_bounds(candidate: _CircleCandidate) -> Bounds:
    """Reference-space disc bounding box for one circle candidate."""

    diameter = int(round(candidate.radius * 2))
    return Bounds(
        x=int(round(candidate.cx - candidate.radius)),
        y=int(round(candidate.cy - candidate.radius)),
        width=max(1, diameter),
        height=max(1, diameter),
    )

def _edge_clipped(bounds: Bounds, size: tuple[int, int]) -> bool:
    """Whether a reference-space disc is cut by the frame edge."""

    return (
        bounds.x < 0
        or bounds.y < 0
        or bounds.x + bounds.width > size[0]
        or bounds.y + bounds.height > size[1]
    )

def _clip_bounds(bounds: Bounds, size: tuple[int, int]) -> Bounds | None:
    """Clamp reference-space bounds to the frame; ``None`` when nothing remains."""

    x = max(0, bounds.x)
    y = max(0, bounds.y)
    right = min(size[0], bounds.x + bounds.width)
    bottom = min(size[1], bounds.y + bounds.height)
    if right - x <= 0 or bottom - y <= 0:
        return None
    return Bounds(x=x, y=y, width=right - x, height=bottom - y)

def _node_features(pixels: np.ndarray, disc: Bounds) -> dict[str, float]:
    """Interior and rim-band color fractions for one circle candidate."""

    cx = disc.x + disc.width / 2.0
    cy = disc.y + disc.height / 2.0
    radius = min(disc.width, disc.height) / 2.0
    inner = _disc_mask(pixels.shape[:2], cx, cy, radius * 0.55)
    band = _disc_mask(pixels.shape[:2], cx, cy, radius) & ~_disc_mask(
        pixels.shape[:2], cx, cy, radius * 0.72
    )

    def _fraction(mask: np.ndarray, predicate) -> float:
        region = pixels[mask]
        if not np.any(mask):
            return 0.0
        return float(np.mean(predicate(region)))

    def _navy(region: np.ndarray) -> np.ndarray:
        blue = region[:, 2].astype(np.int16)
        return (blue - region[:, 0].astype(np.int16) > 30) & (blue > 80)

    return {
        "dark": _fraction(inner, lambda region: np.max(region, axis=1) < 80),
        "white": _fraction(inner, lambda region: np.min(region, axis=1) > 200),
        "blue": _fraction(inner, _navy),
        "grey": _fraction(
            inner,
            lambda region: (np.max(region, axis=1) - np.min(region, axis=1) < 40)
            & (region[:, 0] > 70)
            & (region[:, 0] < 200),
        ),
        "gold_band": _fraction(
            band,
            lambda region: (region[:, 0] > 140) & (region[:, 1] > 90) & (region[:, 2] < 110),
        ),
        "navy_band": _fraction(band, _navy),
    }

def _is_badge_core(features: dict[str, float]) -> bool:
    """A numbered badge: dark core, white numeral, gold rim or navy interior."""

    return (
        features["dark"] >= _BADGE_DARK_MIN
        and features["white"] >= _BADGE_WHITE_MIN
        and (
            features["gold_band"] >= _BADGE_GOLD_BAND_MIN
            or features["blue"] >= _BADGE_BLUE_INTERIOR_MIN
        )
    )

def _is_lock_core(features: dict[str, float]) -> bool:
    """A path lock circle: blue interior with a dark or grey padlock glyph."""

    return (
        features["blue"] >= _LOCK_BLUE_INTERIOR_MIN
        and features["white"] <= _LOCK_WHITE_MAX
        and features["grey"] + features["dark"] >= _LOCK_GLYPH_MIN
    )

def _disc_mask(shape: tuple[int, int], cx: float, cy: float, radius: float) -> np.ndarray:
    """Boolean mask for one circle inside a reference-space frame."""

    grid_y, grid_x = np.ogrid[: shape[0], : shape[1]]
    return (grid_x - cx) ** 2 + (grid_y - cy) ** 2 <= radius**2

def _nameplate_supported(pixels: np.ndarray, plate_ref: Bounds, *, gold: bool) -> bool:
    """Require the horizontal plate's measured trim color next to a badge disc."""

    clipped = _clip_bounds(plate_ref, (pixels.shape[1], pixels.shape[0]))
    if clipped is None:
        return False
    region = pixels[clipped.y : clipped.y + clipped.height, clipped.x : clipped.x + clipped.width]
    if region.size == 0:
        return False
    red, green, blue = region[..., 0], region[..., 1], region[..., 2]
    gold_fraction = np.mean((red > 140) & (green > 90) & (blue < 110))
    if gold:
        return bool(gold_fraction >= _PLATE_GOLD_MIN)
    blue_minus_red = blue.astype(np.int16) - red.astype(np.int16)
    navy = np.mean((blue_minus_red > 30) & (blue > 80))
    dark = np.mean(np.max(region, axis=2) < 80)
    return bool(navy >= _PLATE_NAVY_MIN and dark >= _PLATE_NAVY_DARK_MIN)

def _inset_bounds(bounds: Bounds, inset: int) -> Bounds:
    """Shrink bounds by ``inset`` reference units on each side."""

    return Bounds(
        x=bounds.x + inset,
        y=bounds.y + inset,
        width=max(1, bounds.width - 2 * inset),
        height=max(1, bounds.height - 2 * inset),
    )

def _union_bounds(left: Bounds, right: Bounds) -> Bounds:
    """Smallest rectangle covering two bounds."""

    x = min(left.x, right.x)
    y = min(left.y, right.y)
    return Bounds(
        x=x,
        y=y,
        width=max(left.x + left.width, right.x + right.width) - x,
        height=max(left.y + left.height, right.y + right.height) - y,
    )

def _bounds_overlap(left: Bounds, right: Bounds) -> bool:
    """Any-area overlap between two bounds."""

    return not (
        left.x + left.width <= right.x
        or right.x + right.width <= left.x
        or left.y + left.height <= right.y
        or right.y + right.height <= left.y
    )

def _deduplicate_marked(
    marked: list[tuple[Bounds, DetectedListEntry]],
) -> tuple[DetectedListEntry, ...]:
    """Drop a later row when its marker overlaps an earlier kept marker.

    Ownership is decided on the measured disc or glyph bounds, so an
    attached nameplate envelope overlapping a neighboring node cannot hide
    a distinct visible row.
    """

    kept_markers: list[Bounds] = []
    kept: list[DetectedListEntry] = []
    for marker, row in marked:
        if any(_bounds_overlap(marker, other) for other in kept_markers):
            continue
        kept_markers.append(marker)
        kept.append(row)
    return tuple(kept)
