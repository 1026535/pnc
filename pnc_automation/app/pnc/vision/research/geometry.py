"""Measured Research image geometry and bounded pixel projections."""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root
from pnc_automation.app.pnc.domain.policy_models import ResourceType
from pnc_automation.core.vision.image.models import Bounds

_LABEL_BLUE_MIN_BLUE = 70
_LABEL_BLUE_MIN_RED_DELTA = 25
_LABEL_BLUE_MIN_GREEN_DELTA = 15
_HEADER_HEIGHT_RATIO = 0.065
_EXPECTED_LABEL_HEIGHT_RATIO = 55 / 1600
_PARTIAL_LABEL_HEIGHT_RATIO = 0.75
_ICON_WIDTH_RATIO = 0.82
_ICON_HEIGHT_RATIO = 0.80
_ICON_GAP_RATIO = 0.15
_LEVEL_REGION_WIDTH_RATIO = 0.62
_LEVEL_REGION_HEIGHT_RATIO = 0.30
_LEVEL_TEXT_HEIGHT_RATIO = 0.21
_ICON_FRAME_BORDER_RATIO = 0.07
_ICON_FRAME_MIN_BLUE_FRACTION = 0.20
_GLYPH_REFERENCE_SIZE = (540, 960)
_GLYPH_MATCH_THRESHOLD = 0.82
_PREMIUM_SEARCH_REGION_RATIO = (0.10, 0.43, 0.48, 0.12)
_PREMIUM_GOLD_MIN_RED = 130
_PREMIUM_GOLD_MIN_GREEN = 90
_PREMIUM_GOLD_RED_DELTA = 40
_PREMIUM_GOLD_GREEN_DELTA = 20
_PREMIUM_BUTTON_MIN_AREA_RATIO = 0.003
_COST_ICON_SLOT_RATIO = (0.10, 0.13)

_DATA_DIR = default_selector_asset_root() / "screen_anchors"
_PADLOCK_TEMPLATE = _DATA_DIR / "research_node_padlock.png"
_COST_ICON_TEMPLATES = (
    (ResourceType.FOOD, _DATA_DIR / "research_cost_food.png"),
    (ResourceType.WOOD, _DATA_DIR / "research_cost_wood.png"),
)


def prepare_research_text_2x(image: Image.Image, region: Bounds) -> Image.Image:
    """Enlarge one bounded text region; OCR context restores native bounds."""

    crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height))
    return crop.convert("RGB").resize((crop.width * 2, crop.height * 2), Image.Resampling.BICUBIC)


def discover_label_components(array: np.ndarray) -> tuple[Bounds, ...]:
    """Measure blue node-label rectangles without consulting OCR text."""

    height, width = array.shape[:2]
    mask = (
        (array[:, :, 2] >= _LABEL_BLUE_MIN_BLUE)
        & (array[:, :, 2] >= array[:, :, 0] + _LABEL_BLUE_MIN_RED_DELTA)
        & (array[:, :, 2] >= array[:, :, 1] + _LABEL_BLUE_MIN_GREEN_DELTA)
    ).astype(np.uint8) * 255
    mask[: round(height * _HEADER_HEIGHT_RATIO)] = 0
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, max(3, round(width * 0.025))), np.uint8))
    opened = cv2.morphologyEx(
        closed,
        cv2.MORPH_OPEN,
        np.ones((max(3, round(height * 0.0075)), max(3, round(width * 0.08))), np.uint8),
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(opened)
    return tuple(
        Bounds(int(stat[0]), int(stat[1]), int(stat[2]), int(stat[3]))
        for stat in stats[1:]
        if width * 0.19 <= stat[2] <= width * 0.27 and height * 0.008 <= stat[3] <= height * 0.07
    )


def component_is_partial(component: Bounds, *, image: Image.Image) -> bool:
    """Keep honest boundary fragments clipped instead of repairing them."""

    expected_height = image.height * _EXPECTED_LABEL_HEIGHT_RATIO
    return (
        component.height < expected_height * _PARTIAL_LABEL_HEIGHT_RATIO
        or component.x <= 0
        or component.y <= 0
        or component.x + component.width >= image.width
        or component.y + component.height >= image.height
    )


def scroll_viewport(image: Image.Image) -> Bounds:
    """Return the measured node scroll viewport below the fixed header."""

    top = round(image.height * _HEADER_HEIGHT_RATIO)
    return Bounds(0, top, image.width, image.height - top)


def derive_icon_bounds(label_bounds: Bounds) -> Bounds:
    """Derive the selectable icon square above a measured label rectangle."""

    icon_width = max(1, round(label_bounds.width * _ICON_WIDTH_RATIO))
    icon_height = max(1, round(label_bounds.width * _ICON_HEIGHT_RATIO))
    gap = max(1, round(label_bounds.width * _ICON_GAP_RATIO))
    return Bounds(
        x=label_bounds.x + (label_bounds.width - icon_width) // 2,
        y=label_bounds.y - gap - icon_height,
        width=icon_width,
        height=icon_height,
    )


def icon_has_visible_frame(*, rgb: np.ndarray, icon_bounds: Bounds) -> bool:
    """Confirm the derived icon region shows the blue square frame/body pixels."""

    border = max(2, round(icon_bounds.width * _ICON_FRAME_BORDER_RATIO))
    x0, y0 = icon_bounds.x, icon_bounds.y
    x1, y1 = x0 + icon_bounds.width, y0 + icon_bounds.height
    strips = (
        rgb[y0:y0 + border, x0:x1],
        rgb[y1 - border:y1, x0:x1],
        rgb[y0:y1, x0:x0 + border],
        rgb[y0:y1, x1 - border:x1],
    )
    fractions = []
    for strip in strips:
        if strip.size == 0:
            continue
        blue = (
            (strip[:, :, 2] >= _LABEL_BLUE_MIN_BLUE)
            & (strip[:, :, 2] >= strip[:, :, 0] + _LABEL_BLUE_MIN_RED_DELTA)
            & (strip[:, :, 2] >= strip[:, :, 1] + _LABEL_BLUE_MIN_GREEN_DELTA)
        )
        fractions.append(float(blue.mean()))
    return bool(fractions) and sum(fractions) / len(fractions) >= _ICON_FRAME_MIN_BLUE_FRACTION


def inset_bounds(bounds: Bounds, *, padding: int, image: Image.Image) -> Bounds:
    """Pad (or shrink, for negative padding) bounds inside the image."""

    return clip_bounds(
        Bounds(bounds.x - padding, bounds.y - padding, bounds.width + 2 * padding, bounds.height + 2 * padding),
        Bounds(0, 0, image.width, image.height),
    )


def clip_bounds(bounds: Bounds, viewport: Bounds) -> Bounds:
    """Clip bounds to a viewport rectangle."""

    left = max(bounds.x, viewport.x)
    top = max(bounds.y, viewport.y)
    right = min(bounds.x + bounds.width, viewport.x + viewport.width)
    bottom = min(bounds.y + bounds.height, viewport.y + viewport.height)
    return Bounds(left, top, max(1, right - left), max(1, bottom - top))


def union_bounds(left: Bounds, right: Bounds) -> Bounds:
    """Return the smallest rectangle containing two bounds."""

    x0 = min(left.x, right.x)
    y0 = min(left.y, right.y)
    x1 = max(left.x + left.width, right.x + right.width)
    y1 = max(left.y + left.height, right.y + right.height)
    return Bounds(x0, y0, x1 - x0, y1 - y0)


def project_bounds_to_reference(
    bounds: Bounds,
    *,
    original_size: tuple[int, int],
    reference_size: tuple[int, int],
) -> Bounds:
    """Project image-space bounds into a prepared frame's reference space."""

    if original_size == reference_size:
        return bounds
    scale_x = reference_size[0] / original_size[0]
    scale_y = reference_size[1] / original_size[1]
    return Bounds(
        round(bounds.x * scale_x),
        round(bounds.y * scale_y),
        max(1, round(bounds.width * scale_x)),
        max(1, round(bounds.height * scale_y)),
    )
