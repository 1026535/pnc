"""Shared Bag shell geometry: body bounds, card bands and selected-subtab measurement."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.bag import BAG_TAB_ORDER, BagTab
from pnc_automation.core.vision.image.models import Bounds


_BAG_BODY_TOP_RATIO = 0.17
_CARD_BAND_FLOOR = 20
_INTERIOR_CARD_MINIMUM_RATIO = 0.075
_CARD_TOP_EDGE_INSET_RATIO = 0.005
_CARD_BOTTOM_EDGE_INSET_RATIO = 0.0025

# The main Bag panel keeps its own gold proof independent of subtab contents.
_MAIN_BAG_SELECTED_POINT = (0.24, 0.09)
# The five subtab slots share one band; selection is exactly one gold container.
_SUBTAB_BAND_TOP_RATIO = 0.128
_SUBTAB_BAND_BOTTOM_RATIO = 0.167
_SUBTAB_CONTAINER_MIN_WIDTH_RATIO = 0.14
_SUBTAB_CONTAINER_MIN_HEIGHT_RATIO = 0.5
_SUBTAB_SLOT_X_TOLERANCE_RATIO = 0.10
_SUBTAB_SLOT_WIDTH_TOLERANCE_RATIO = 0.25


@dataclass(frozen=True, slots=True)
class BagCardGeometry:
    """One measured Bag card band and its viewport-clipping state."""

    bounds: Bounds
    clipped: bool


def bag_body_bounds(image: Image.Image) -> Bounds:
    """Return the reviewed shared Bag card body region for one decoded frame."""

    return bag_body_bounds_for_size(image.size)


def bag_body_bounds_for_size(image_size: tuple[int, int]) -> Bounds:
    """Return the shared Bag body region for a decoded image size."""

    width, height = image_size
    top = int(height * _BAG_BODY_TOP_RATIO)
    return Bounds(x=0, y=top, width=width, height=max(1, height - top))


def detect_bag_card_geometry(image: Image.Image) -> tuple[BagCardGeometry, ...]:
    """Find card bands shared by every Bag subtab without relying on text lines.

    Interior cards keep the ordinary height minimum; shorter bands are retained
    only when they intersect a supported viewport edge, and every retained edge
    band reports ``clipped`` so consumers can refuse its contents.
    """

    rgb = image.convert("RGB")
    body_top = bag_body_bounds(image).y
    interior_minimum = max(_CARD_BAND_FLOOR, int(image.height * _INTERIOR_CARD_MINIMUM_RATIO))
    runs = _vertical_runs(
        rgb,
        x=max(1, int(image.width * 0.025)),
        start=body_top,
        end=image.height,
        predicate=_is_card_band_pixel,
        minimum=_CARD_BAND_FLOOR,
    )
    geometry: list[BagCardGeometry] = []
    for top, bottom in runs:
        bounds = Bounds(int(image.width * 0.01), top, int(image.width * 0.98), bottom - top)
        clipped = _card_is_clipped(bounds, image, body_top=body_top)
        if bottom - top >= interior_minimum or clipped:
            geometry.append(BagCardGeometry(bounds=bounds, clipped=clipped))
    return tuple(geometry)


def detect_selected_bag_tab(image: Image.Image) -> BagTab | None:
    """Measure the uniquely gold-filled Bag subtab; absence or ambiguity is unknown.

    The selected main Bag panel must keep its gold proof, and exactly one
    substantial gold container must occupy a supported five-slot position in the
    subtab band. Multiple or absent candidates fail closed.
    """

    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    height, width = rgb.shape[:2]
    main_x = min(width - 1, int(width * _MAIN_BAG_SELECTED_POINT[0]))
    main_y = min(height - 1, int(height * _MAIN_BAG_SELECTED_POINT[1]))
    if not is_gold_button_pixel(tuple(int(channel) for channel in rgb[main_y, main_x])):
        return None
    top = round(height * _SUBTAB_BAND_TOP_RATIO)
    bottom = round(height * _SUBTAB_BAND_BOTTOM_RATIO)
    if bottom - top < 4:
        return None
    band = rgb[top:bottom]
    gold = (
        (band[:, :, 0] > band[:, :, 1])
        & (band[:, :, 1] > band[:, :, 2] + 20)
        & (band[:, :, 0] > 90)
    ).astype(np.uint8) * 255
    gold = cv2.morphologyEx(
        gold,
        cv2.MORPH_CLOSE,
        np.ones((3, max(3, round(width * 0.01))), np.uint8),
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(gold)
    containers = tuple(
        (int(x), int(component_width), int(component_height))
        for x, _y, component_width, component_height, _area in stats[1:]
        if component_width >= width * _SUBTAB_CONTAINER_MIN_WIDTH_RATIO
        and component_height >= (bottom - top) * _SUBTAB_CONTAINER_MIN_HEIGHT_RATIO
    )
    if len(containers) != 1:
        return None
    x, container_width, _container_height = containers[0]
    slot_width = width / len(BAG_TAB_ORDER)
    index = int((x + container_width / 2) // slot_width)
    if not 0 <= index < len(BAG_TAB_ORDER):
        return None
    if abs(x - index * slot_width) > slot_width * _SUBTAB_SLOT_X_TOLERANCE_RATIO:
        return None
    if abs(container_width - slot_width) > slot_width * _SUBTAB_SLOT_WIDTH_TOLERANCE_RATIO:
        return None
    return BAG_TAB_ORDER[index]


def is_gold_button_pixel(pixel: tuple[int, int, int]) -> bool:
    """Recognizes the selected gold chrome fill in reviewed normalized regions."""

    red, green, blue = pixel
    return red > green and green > blue + 20 and red > 90


def _is_card_band_pixel(pixel: tuple[int, int, int]) -> bool:
    """Recognizes the dark blue card band shared by Bag item rows."""

    return sum(pixel) >= 125 and pixel[2] >= pixel[0] + 20


def _card_is_clipped(bounds: Bounds, image: Image.Image, *, body_top: int) -> bool:
    """Classify cards touching a supported viewport edge as clipped evidence."""

    return (
        bounds.x <= 0
        or bounds.x + bounds.width >= image.width
        or _band_touches_viewable_edge(
            bounds.y,
            bounds.y + bounds.height,
            body_top=body_top,
            image_height=image.height,
        )
    )


def _band_touches_viewable_edge(top: int, bottom: int, *, body_top: int, image_height: int) -> bool:
    """Share one normalized viewport-edge rule between band retention and clipping."""

    return (
        top <= body_top + int(image_height * _CARD_TOP_EDGE_INSET_RATIO)
        or bottom >= image_height - int(image_height * _CARD_BOTTOM_EDGE_INSET_RATIO)
    )


def _vertical_runs(
    image: Image.Image,
    *,
    x: int,
    start: int,
    end: int,
    predicate: Callable[[tuple[int, int, int]], bool],
    minimum: int,
) -> tuple[tuple[int, int], ...]:
    """Extracts contiguous pixel bands for the card-band detector."""

    runs: list[tuple[int, int]] = []
    begin: int | None = None
    for y in range(start, min(end, image.height)):
        matches = predicate(image.getpixel((x, y)))
        if matches and begin is None:
            begin = y
        if not matches and begin is not None:
            if y - begin >= minimum:
                runs.append((begin, y))
            begin = None
    if begin is not None and min(end, image.height) - begin >= minimum:
        runs.append((begin, min(end, image.height)))
    return tuple(runs)
