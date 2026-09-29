"""Measured board and order geometry for Pet Workshop recognition.

This module owns reference-space transforms and pixel segmentation rules.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.template.template_matcher import PreparedFrame

from .constants import *  # noqa: F403 - measured constants are the data contract

@dataclass(frozen=True, slots=True)
class CardExtent:
    """Measured reference-space span of one order-strip card."""

    x0: int
    x1: int
    top: int
    bottom: int
    clipped: bool

_CardExtent = CardExtent

def _cell_region(row: int, column: int) -> Bounds:
    """Return one cell's reference bounds; row 1 is the bottom display row."""

    return Bounds(
        x=round(_CELL_X0 + (column - 1) * _CELL_W),
        y=round(_CELL_Y0 + (9 - row) * _CELL_H),
        width=71,
        height=71,
    )


def _cell_center_region(region: Bounds) -> Bounds:
    """Return the cell's center window, clear of corner selection brackets."""

    return Bounds(x=region.x + 20, y=region.y + 20, width=32, height=32)


def _inflate_region(region: Bounds, margin: int) -> Bounds:
    """Grow a search region, clamped to the reference frame."""

    clipped = _clipped(
        Bounds(
            x=region.x - margin,
            y=region.y - margin,
            width=region.width + margin * 2,
            height=region.height + margin * 2,
        )
    )
    return clipped if clipped is not None else region


def _clipped(region: Bounds) -> Bounds | None:
    """Clamp a region to the reference frame; ``None`` when fully outside."""

    x2 = min(region.x + region.width, _REFERENCE_SIZE[0])
    y2 = min(region.y + region.height, _REFERENCE_SIZE[1])
    x1 = max(region.x, 0)
    y1 = max(region.y, 0)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return Bounds(x=x1, y=y1, width=x2 - x1, height=y2 - y1)


def _fits(region: Bounds, template_size: tuple[int, int]) -> bool:
    """Check a search region can spatially hold one template."""

    return region.width >= template_size[0] and region.height >= template_size[1]


def _scaled_region(region: Bounds, image: Image.Image) -> Bounds:
    """Scale one fixed reference region into image coordinates."""

    scale_x = image.width / _REFERENCE_SIZE[0]
    scale_y = image.height / _REFERENCE_SIZE[1]
    return Bounds(
        x=round(region.x * scale_x),
        y=round(region.y * scale_y),
        width=round(region.width * scale_x),
        height=round(region.height * scale_y),
    )


def _intersects(first: Bounds, second: Bounds) -> bool:
    """Return whether two bounds rectangles overlap by at least one pixel."""

    return (
        first.x < second.x + second.width
        and second.x < first.x + first.width
        and first.y < second.y + second.height
        and second.y < first.y + first.height
    )


def _ref_region(bounds: Bounds, prepared: PreparedFrame) -> Bounds:
    """Convert image-space match bounds into reference coordinates."""

    scale_x = prepared.reference_size[0] / prepared.original_size[0]
    scale_y = prepared.reference_size[1] / prepared.original_size[1]
    return Bounds(
        x=round(bounds.x * scale_x),
        y=round(bounds.y * scale_y),
        width=max(1, round(bounds.width * scale_x)),
        height=max(1, round(bounds.height * scale_y)),
    )


def _channels(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split RGB pixels into int16 channels for mask arithmetic."""

    return (
        pixels[..., 0].astype(np.int16),
        pixels[..., 1].astype(np.int16),
        pixels[..., 2].astype(np.int16),
    )


def _panel_mask(pixels: np.ndarray) -> np.ndarray:
    """Cream card-panel pixels (the order card body fill)."""

    r, g, b = _channels(pixels)
    return (r >= 235) & (g >= 205) & (b >= 140) & (r > b + 30)


def _strip_bg_mask(pixels: np.ndarray) -> np.ndarray:
    """Strip background pixels: teal scene wash, foliage green and shadow."""

    r, g, b = _channels(pixels)
    teal = (r < 95) & (g > 55) & (g < 125) & (b > 60) & (b < 135) & (b >= g - 15)
    foliage = (g > r + 15) & (g > b + 20) & (g >= 90) & (g < 170) & (r < 140) & (b < 110)
    shadow = (r < 70) & (g < 70) & (b < 70)
    return teal | foliage | shadow


def _chrome_mask(pixels: np.ndarray) -> np.ndarray:
    """Warm wood-tone pixels along the strip's bottom chrome band."""

    r, g, b = _channels(pixels)
    return (r > g + 10) & (g > b) & (r >= 90) & (b < 140) & (r - b >= 40)


def _pedestal_mask(pixels: np.ndarray) -> np.ndarray:
    """Blue detail-modal pedestal pixels (saturated blue on navy modal)."""

    r, g, b = _channels(pixels)
    return (b > 105) & (b - r > 35) & (r < 135)


def _column_runs(mask: np.ndarray, min_width: int) -> list[tuple[int, int]]:
    """Contiguous True-column runs as inclusive ``(x0, x1)`` pairs."""

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, flag in enumerate(mask):
        if flag and start is None:
            start = x
        elif not flag and start is not None:
            if x - start >= min_width:
                runs.append((start, x - 1))
            start = None
    if start is not None and len(mask) - start >= min_width:
        runs.append((start, len(mask) - 1))
    return runs


def _detect_card_extents(pixels: np.ndarray) -> list[_CardExtent]:
    """Locate order-card panels from non-background columns on the strip.

    A horizontal run of mostly-content columns in the union band (reward row
    + tile row) is a card candidate; the left timer column is rejected by its
    missing reward-row panel fraction. Cards touching the frame edges or the
    timer column are marked clipped.
    """

    panel = _panel_mask(pixels)
    nonbg = ~_strip_bg_mask(pixels)
    y0, y1 = _CARD_UNION_BAND
    runs = _column_runs(nonbg[y0:y1].mean(axis=0) >= 0.5, _CARD_MIN_WIDTH)
    cards: list[_CardExtent] = []
    for x0, x1 in runs:
        if panel[_CARD_PANEL_BAND[0] : _CARD_PANEL_BAND[1], x0 : x1 + 1].mean() < 0.25:
            continue
        cards.append(
            _CardExtent(
                x0=x0,
                x1=x1 + 1,
                top=_card_top(nonbg, x0, x1 + 1),
                bottom=_card_bottom(panel, x0, x1 + 1),
                clipped=(
                    x1 - x0 + 1 < _CARD_FULL_MIN_WIDTH
                    or x1 + 1 >= _CARD_CLIP_RIGHT_X
                    or x0 <= _CARD_CLIP_LEFT_X
                ),
            )
        )
    return cards


def _card_top(nonbg: np.ndarray, x0: int, x1: int) -> int:
    """First row of three consecutive mostly-content rows within the card."""

    y0, y1 = _CARD_TOP_SCAN
    frac = nonbg[y0:y1, x0:x1].mean(axis=1)
    for i in range(len(frac) - 2):
        if frac[i] >= 0.5 and frac[i + 1] >= 0.5 and frac[i + 2] >= 0.5:
            return y0 + i
    return _CARD_PANEL_BAND[0]


def _card_bottom(panel: np.ndarray, x0: int, x1: int) -> int:
    """Row just past the card's last mostly-panel row; chrome top as fallback."""

    y0, y1 = _CARD_PANEL_TAIL_SCAN
    frac = panel[y0:y1, x0:x1].mean(axis=1)
    last = None
    for i, value in enumerate(frac):
        if value >= 0.4:
            last = y0 + i
    return (last + 1) if last is not None else _STRIP_CHROME_BAND[0]


def _order_strip_bounds(pixels: np.ndarray) -> Bounds | None:
    """Measure the order-strip surface from its continuous bottom chrome.

    The strip's wood chrome spans the widget horizontally; the top edge is
    the first row where that span reads mostly non-background content.
    ``None`` when no chrome run is measured.
    """

    chrome = _chrome_mask(pixels)
    y0, y1 = _STRIP_CHROME_BAND
    runs = _column_runs(chrome[y0:y1].mean(axis=0) >= 0.5, min_width=8)
    if not runs or max(b - a + 1 for a, b in runs) < 300:
        return None
    x0 = min(run[0] for run in runs)
    x1 = max(run[1] for run in runs) + 1
    nonbg = ~_strip_bg_mask(pixels)
    frac = nonbg[_STRIP_TOP_SCAN[0] : _STRIP_TOP_SCAN[1], x0:x1].mean(axis=1)
    top = None
    for i in range(len(frac) - 2):
        if frac[i] >= 0.45 and frac[i + 1] >= 0.45 and frac[i + 2] >= 0.45:
            top = _STRIP_TOP_SCAN[0] + i
            break
    if top is None:
        return None
    return Bounds(x=x0, y=top, width=x1 - x0, height=_STRIP_BOTTOM - top)


def _tile_runs(pixels: np.ndarray, card: _CardExtent) -> list[tuple[int, int]]:
    """Detect requirement tile columns inside one card's tile band."""

    x0 = card.x0 + 2
    x1 = min(card.x1 - 2, _REFERENCE_SIZE[0])
    if x1 - x0 <= 0:
        return []
    y0, height = _CARD_TILE_BAND
    nonpanel = ~_panel_mask(pixels)
    frac = nonpanel[y0 : y0 + height, x0:x1].mean(axis=0)
    return [(x0 + a, x0 + b) for a, b in _column_runs(frac >= 0.5, _TILE_RUN_MIN_WIDTH)]


def _reward_groups(pixels: np.ndarray, card: _CardExtent) -> list[tuple[int, int]]:
    """Measure reward foreground groups without depending on icon identity.

    On the qualified layout the cream row below the rewards spans their
    panel, including its unused space. Foreground columns above that row
    form icon/count groups; digit gaps are at most eight reference pixels,
    while the two-reward fixtures have larger inter-reward gaps. Ambiguous
    merged groups subsequently fail the one-icon-per-group coverage check.
    """

    panel = _panel_mask(pixels)
    spans = _column_runs(panel[_REWARD_PANEL_BASELINE, card.x0:card.x1], 30)
    if len(spans) != 1:
        return []
    x0, x1 = (card.x0 + value for value in spans[0])
    y0, y1 = _REWARD_INK_BAND
    ink = (~panel[y0:y1, x0:x1 + 1]).mean(axis=0) >= 0.15
    groups: list[tuple[int, int]] = []
    for left, right in _column_runs(ink, 2):
        left, right = x0 + left, x0 + right
        if groups and left - groups[-1][1] - 1 <= _REWARD_GROUP_GAP:
            groups[-1] = (groups[-1][0], right)
        else:
            groups.append((left, right))
    return groups


def _tile_coverage(
    runs: list[tuple[int, int]],
    icons: list[tuple[object, TemplateMatch]],
    prepared: PreparedFrame,
) -> bool:
    """Check tile runs and matched requirement icons agree one-for-one.

    Coverage holds when every run holds at least one icon center, every icon
    sits inside a run, and the run-width slot estimate equals the icon count.
    A card with no measured tiles is never covered.
    """

    if not runs:
        return False
    centers = [_ref_region(match.bounds, prepared).center() for _value, match in icons]
    if any(not any(a <= cx <= b for a, b in runs) for cx, _cy in centers):
        return False
    if any(not any(a <= cx <= b for cx, _cy in centers) for a, b in runs):
        return False
    slots = sum(
        max(1, round((b - a + 1) / _CARD_TILE_SLOT_PITCH)) for a, b in runs
    )
    return slots == len(icons)


def _pedestal_runs(
    pixels: np.ndarray, band: tuple[int, int], *, merge_gap: int = 0
) -> list[tuple[int, int]]:
    """Detect detail-modal pedestal columns from their blue lip rows.

    ``merge_gap`` rejoins lip runs split by icon art protruding through a
    small gap in one box's bottom edge; a wider gap stays two distinct
    pedestals.
    """

    ped = _pedestal_mask(pixels)
    y0, y1 = band
    frac = ped[y0:y1, 120:530].mean(axis=0)
    runs = _column_runs(frac >= 0.45, _OD_PEDESTAL_MIN_WIDTH)
    if merge_gap:
        merged: list[tuple[int, int]] = []
        for a, b in runs:
            if merged and a - merged[-1][1] - 1 <= merge_gap:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        runs = merged
    return [(a + 120, b + 120) for a, b in runs]


def _pedestals_covered(
    pedestals: list[tuple[int, int]],
    icons: list[tuple[object, TemplateMatch]],
    prepared: PreparedFrame,
) -> bool:
    """Check every pedestal holds a matched icon and every icon sits on one."""

    if not pedestals or len(pedestals) != len(icons):
        return False
    centers = [_ref_region(match.bounds, prepared).center() for _value, match in icons]
    spans = [
        (x0 - _OD_PEDESTAL_PAD_X, x1 + _OD_PEDESTAL_PAD_X) for x0, x1 in pedestals
    ]
    return all(any(a <= cx <= b for a, b in spans) for cx, _cy in centers) and all(
        any(a <= cx <= b for cx, _cy in centers) for a, b in spans
    )


def _bar_empty(pixels: np.ndarray) -> bool:
    """Measure whether the bottom selection bar carries no card/controls."""

    region = _SELECTION_BAR_REGION
    sub = pixels[
        region.y : region.y + region.height, region.x : region.x + region.width
    ].astype(np.float32)
    luminance = sub.mean(axis=2)
    edges = (
        (np.abs(np.diff(luminance, axis=1)) > 28).mean()
        + (np.abs(np.diff(luminance, axis=0)) > 28).mean()
    ) / 2
    return edges < _BAR_EMPTY_EDGE_MAX



def counted_icons(icons: list[tuple[object, TemplateMatch]]) -> dict[int, int]:
    """Count matched requirement icons by their typed item id."""

    counts: dict[int, int] = {}
    for value, _match in icons:
        counts[int(value)] = counts.get(int(value), 0) + 1
    return counts


cell_region = _cell_region
cell_center_region = _cell_center_region
inflate_region = _inflate_region
clipped = _clipped
fits = _fits
scaled_region = _scaled_region
detect_card_extents = _detect_card_extents
order_strip_bounds = _order_strip_bounds
tile_runs = _tile_runs
reward_groups = _reward_groups
tile_coverage = _tile_coverage
pedestal_runs = _pedestal_runs
pedestals_covered = _pedestals_covered
bar_empty = _bar_empty
ref_region = _ref_region
intersects = _intersects
