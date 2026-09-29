"""Measured Bag card and preview coordinate geometry."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root
from pnc_automation.core.vision.image.models import Bounds

REFERENCE_SIZE = (900, 1600)
PREVIEW_REFERENCE_SIZE = (540, 960)
MAGNIFIER_TEMPLATE = default_selector_asset_root() / "screen_anchors" / "bag_item_magnifier.png"
MAGNIFIER_THRESHOLD = 0.85
MAGNIFIER_SEARCH = Bounds(x=130, y=-5, width=90, height=115)
CARD_TEXT_REGION = Bounds(x=28, y=5, width=597, height=195)
TEXT_COLUMN_MIN_X = 190
NAME_MAX_Y = 70
CARD_NAME_REGION = Bounds(x=190, y=0, width=435, height=75)


def native_offset_region(region: Bounds, card_bounds: Bounds, image: Image.Image) -> Bounds:
    """Translate a reference-space card-relative region to native pixels."""

    scale_x = image.width / REFERENCE_SIZE[0]
    scale_y = image.height / REFERENCE_SIZE[1]
    left = max(0, card_bounds.x + round(region.x * scale_x))
    top = max(0, card_bounds.y + round(region.y * scale_y))
    right = min(card_bounds.x + round((region.x + region.width) * scale_x), image.width)
    bottom = min(card_bounds.y + round((region.y + region.height) * scale_y), image.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def reference_offset_region(region: Bounds, card_bounds: Bounds, image: Image.Image) -> Bounds:
    """Translate a card-relative region into prepared reference space."""

    scale_x = REFERENCE_SIZE[0] / image.width
    scale_y = REFERENCE_SIZE[1] / image.height
    card_x = round(card_bounds.x * scale_x)
    card_y = round(card_bounds.y * scale_y)
    left = max(0, card_x + region.x)
    top = max(0, card_y + region.y)
    right = min(left + region.width, REFERENCE_SIZE[0])
    bottom = min(top + region.height, REFERENCE_SIZE[1])
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def scaled_region(region: Bounds, image: Image.Image, *, reference: tuple[int, int]) -> Bounds:
    """Project reference-coordinate bounds into the current image space."""

    scale_x = image.width / reference[0]
    scale_y = image.height / reference[1]
    left = round(region.x * scale_x)
    top = round(region.y * scale_y)
    right = min(round((region.x + region.width) * scale_x), image.width)
    bottom = min(round((region.y + region.height) * scale_y), image.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def clamp_bounds(bounds: Bounds, container: Bounds) -> Bounds:
    """Clamp one measured rectangle inside its owning card bounds."""

    left = max(bounds.x, container.x)
    top = max(bounds.y, container.y)
    right = min(bounds.x + bounds.width, container.x + container.width)
    bottom = min(bounds.y + bounds.height, container.y + container.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))
