"""Resource Bag semantics anchored to visual cards and blue single-Use buttons."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.app.pnc.vision.numeric_parsing import (
    AMOUNT_TOKEN_PATTERN,
    parse_amount,
    parse_grouped_integer,
)


_PACK_TITLE = re.compile(
    rf"^(?P<amount>{AMOUNT_TOKEN_PATTERN.pattern[1:-1]})\s*"
    r"(?P<multiplier>[KM]?)\s*(?P<resource>FOOD|WOOD|IRON|GOLD)"
    r"(?P<safe>\s*\(SAFE\))?$",
    re.I,
)
_OWNED = re.compile(r"^OWNED\s*:\s*(?P<owned>.*)$", re.I)
_EXCLUDED_TITLE = re.compile(
    r"^(?:\d+(?:\.\d+)?[KM]?\s*Soulstones|24-hr\s*(?:Farm|Lumber|Iron|Gold)(?:\s*Mine)?\s*Output\s*Boost)$", re.I,
)
_RESOURCE_BODY_TOP_RATIO = 0.17


def parse_resource_inventory(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    proved_screen: ScreenType | None = None,
) -> tuple[DetectedListEntry, ...] | None:
    """Return visually bounded Bag rows, preserving unresolved visible cards."""

    rgb = image.convert("RGB")
    if proved_screen is not None and not isinstance(proved_screen, ScreenType):
        raise TypeError("proved_screen must be a ScreenType or None")
    proved = proved_screen
    if proved not in {None, ScreenType.PNC_BAG}:
        return None
    # A caller-proved Bag may intentionally supply body-only OCR; the builder
    # owns the separate chrome proof before invoking this semantic parser.
    if proved is None and not resource_inventory_chrome_proven(image=image, lines=lines):
        return None
    if not resource_inventory_tab_is_selected(rgb):
        return None
    entries: list[DetectedListEntry] = []
    card_bounds = detect_resource_card_bounds(rgb)
    if not card_bounds:
        return (_unresolved_inventory_entry(image, reason="inventory_cards_unreadable"),)
    for bounds in card_bounds:
        if _row_is_clipped(bounds, image, body_top=resource_inventory_body_bounds(image).y):
            entries.append(_unresolved_inventory_entry(
                image,
                bounds=bounds,
                reason="clipped_card",
                row_status=RowRecognitionStatus.CLIPPED,
            ))
            continue
        row_lines = tuple(
            line for line in lines
            if _line_contained(bounds, line)
        )
        title_matches = tuple(
            (line, _match_pack_title(line.text))
            for line in row_lines if image.width * 0.20 <= line.bounds.x < image.width * 0.70
        )
        titles = tuple((line, match) for line, match in title_matches if match is not None)
        counts = tuple(
            (line, _OWNED.fullmatch(line.text.strip()))
            for line in row_lines
        )
        owned = tuple(
            (line, parse_grouped_integer(match.group("owned")))
            for line, match in counts
            if match is not None
        )
        exclusions = tuple(
            line for line in row_lines
            if image.width * 0.20 <= line.bounds.x < image.width * 0.70
            and _EXCLUDED_TITLE.fullmatch(line.text.strip())
        )
        if not titles and len(exclusions) == 1 and len(owned) == 1 and owned[0][1] is not None:
            entries.append(DetectedListEntry(
                kind=ListEntryKind.RESOURCE_INVENTORY_EXCLUSION,
                bounds=bounds, title_text=exclusions[0].text,
                metadata={"owned": owned[0][1]},
                row_status=RowRecognitionStatus.NO_ACTION,
            ))
            continue
        if len(titles) != 1 or len(owned) != 1 or owned[0][1] is None:
            entries.append(_unresolved_inventory_entry(image, bounds=bounds, reason="missing_or_ambiguous_title_or_count"))
            continue
        action_bounds = _detect_blue_action_bounds(rgb, bounds, row_lines)
        if action_bounds is None:
            entries.append(_unresolved_inventory_entry(image, bounds=bounds, reason="missing_or_ambiguous_single_use_button"))
            continue
        title, match = titles[0]
        raw_amount = match.group("amount")
        multiplier = {"": 1, "K": 1000, "M": 1000000}[match.group("multiplier").upper()]
        parsed_amount = parse_amount(raw_amount)
        amount = None if parsed_amount is None else parsed_amount * Decimal(multiplier)
        if amount is None or amount != amount.to_integral_value() or amount <= 0:
            entries.append(_unresolved_inventory_entry(
                image,
                bounds=bounds,
                title_text=title.text,
                reason="invalid_pack_amount",
            ))
            continue
        crop = rgb.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height))
        resource = match.group("resource").lower()
        safe = match.group("safe") is not None
        action_point = (
            action_bounds.x + action_bounds.width // 2,
            action_bounds.y + action_bounds.height // 2,
        )
        entries.append(DetectedListEntry(
            kind=ListEntryKind.RESOURCE_ITEM,
            bounds=bounds,
            title_text=title.text,
            action_point=action_point,
            action_bounds=action_bounds,
            row_status=RowRecognitionStatus.COMPLETE,
            metadata={
                "item_id": f"{resource}:{int(amount)}:{'safe' if safe else 'normal'}",
                "resource": resource,
                "amount": int(amount),
                "owned": owned[0][1],
                "observation_fingerprint": hashlib.sha256(crop.tobytes()).hexdigest(),
                "coordinate_provenance": "visual_geometry",
            },
        ))
    return _mark_duplicate_resource_ids(tuple(entries))


def detect_resource_card_bounds(image: Image.Image) -> tuple[Bounds, ...]:
    """Finds inventory card bands without relying on text line coordinates."""

    rgb = image.convert("RGB")
    runs = _vertical_runs(
        rgb, x=max(1, int(image.width * 0.025)),
        start=resource_inventory_body_bounds(image).y, end=image.height,
        predicate=lambda pixel: sum(pixel) >= 125 and pixel[2] >= pixel[0] + 20,
        minimum=max(20, int(image.height * 0.075)),
    )
    return tuple(
        Bounds(int(image.width * 0.01), top, int(image.width * 0.98), bottom - top)
        for top, bottom in runs
    )


def _match_pack_title(text: str) -> re.Match[str] | None:
    """Matches canonical pack titles and bounded OCR glyph confusions in the resource word."""

    raw = text.strip()
    direct = _PACK_TITLE.fullmatch(raw)
    if direct is not None:
        return direct
    corrected = re.sub(r"\s+", "", raw.upper())
    for noisy, canonical in {
        "F00D": "FOOD",
        "F0OD": "FOOD",
        "FO0D": "FOOD",
        "W00D": "WOOD",
        "W0OD": "WOOD",
        "WO0D": "WOOD",
        "IR0N": "IRON",
        "LRON": "IRON",
        "G0LD": "GOLD",
    }.items():
        corrected = corrected.replace(noisy, canonical)
    if corrected.endswith("SAFE"):
        corrected = f"{corrected[:-4]}(SAFE)"
    return _PACK_TITLE.fullmatch(corrected)


def resource_inventory_tab_is_selected(image: Image.Image) -> bool:
    """Require the reviewed Bag and Resource tab pixels even with proved header context."""

    rgb = image.convert("RGB")
    return all(
        is_gold_button_pixel(rgb.getpixel((int(rgb.width * x), int(rgb.height * y))))
        for x, y in ((0.24, 0.09), (0.09, 0.145))
    )


def _line_contained(bounds: Bounds, line: OcrLine) -> bool:
    """Keep only OCR lines wholly contained by the visual card."""

    return bounds.contains_bounds(line.bounds)


def _row_is_clipped(bounds: Bounds, image: Image.Image, *, body_top: int) -> bool:
    """Reject cards touching the screenshot edge as incomplete evidence."""

    return (
        bounds.x <= 0
        or bounds.y <= body_top
        or bounds.x + bounds.width >= image.width
        or bounds.y + bounds.height >= image.height
    )


def resource_inventory_chrome_proven(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> bool:
    """Require the OCR-owned Bag and Resource chrome before reading body rows."""

    body_top = resource_inventory_body_bounds(image).y
    header = {
        normalize_ocr_text(line.text)
        for line in lines
        if line.bounds.y < body_top
    }
    return {"BAG", "RESOURCE"}.issubset(header)


def resource_inventory_body_bounds(image: Image.Image) -> Bounds:
    """Return the reviewed OCR body region shared by Bag detection and planning."""

    return resource_inventory_body_bounds_for_size(image.size)


def resource_inventory_body_bounds_for_size(image_size: tuple[int, int]) -> Bounds:
    """Return the shared Bag body region for a decoded image size."""

    width, height = image_size
    top = int(height * _RESOURCE_BODY_TOP_RATIO)
    return Bounds(x=0, y=top, width=width, height=max(1, height - top))


def _detect_blue_action_bounds(
    image: Image.Image,
    bounds: Bounds,
    lines: tuple[OcrLine, ...],
) -> Bounds | None:
    """Find one actual blue single-Use button, retaining its per-card Y."""

    runs = detect_button_runs(
        image,
        bounds=bounds,
        x_start=max(bounds.x, int(image.width * 0.72)),
        x_end=min(bounds.x + bounds.width, int(image.width * 0.98)),
        predicate=is_blue_button_pixel,
        minimum_height=max(5, int(image.height * 0.015)),
    )
    if len(runs) != 1:
        return None
    action_bounds = runs[0]
    labels = {
        normalize_ocr_text(line.text)
        for line in lines
        if _line_contained(action_bounds, line)
    }
    if labels and labels != {"USE"}:
        return None
    return action_bounds


def detect_button_runs(
    image: Image.Image,
    *,
    bounds: Bounds,
    x_start: int,
    x_end: int,
    predicate: Callable[[tuple[int, int, int]], bool],
    minimum_height: int,
) -> tuple[Bounds, ...]:
    """Detect solid button rectangles from pixels in one bounded row."""

    y_runs: list[tuple[int, int]] = []
    start: int | None = None
    for y in range(bounds.y, min(bounds.y + bounds.height, image.height)):
        matched = sum(predicate(image.getpixel((x, y))) for x in range(x_start, x_end))
        present = matched >= max(5, int((x_end - x_start) * 0.35))
        if present and start is None:
            start = y
        elif not present and start is not None:
            if y - start >= minimum_height:
                y_runs.append((start, y))
            start = None
    if start is not None and min(bounds.y + bounds.height, image.height) - start >= minimum_height:
        y_runs.append((start, min(bounds.y + bounds.height, image.height)))
    result: list[Bounds] = []
    for top, bottom in y_runs:
        segments: list[tuple[int, int]] = []
        segment_start: int | None = None
        for x in range(x_start, x_end):
            matched = sum(predicate(image.getpixel((x, y))) for y in range(top, bottom))
            present = matched >= max(3, int((bottom - top) * 0.35))
            if present and segment_start is None:
                segment_start = x
            elif not present and segment_start is not None:
                if x - segment_start >= 5:
                    segments.append((segment_start, x))
                segment_start = None
        if segment_start is not None and x_end - segment_start >= 5:
            segments.append((segment_start, x_end))
        if len(segments) == 1:
            left, right = segments[0]
            result.append(Bounds(left, top, right - left, bottom - top))
    return tuple(result)


def _unresolved_inventory_entry(
    image: Image.Image,
    *,
    bounds: Bounds | None = None,
    title_text: str | None = None,
    reason: str,
    row_status: RowRecognitionStatus = RowRecognitionStatus.UNREADABLE,
) -> DetectedListEntry:
    """Represent visible but unresolved inventory evidence explicitly."""

    resolved_bounds = bounds or resource_inventory_body_bounds(image)
    return DetectedListEntry(
        kind=ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED,
        bounds=resolved_bounds,
        title_text=title_text,
        row_status=row_status,
        metadata={"unresolved_reason": reason, "coordinate_provenance": "visual_geometry"},
    )


def _mark_duplicate_resource_ids(
    entries: tuple[DetectedListEntry, ...],
) -> tuple[DetectedListEntry, ...]:
    """Mark repeated semantic item identities ambiguous instead of selecting one."""

    ids = [entry.metadata.get("item_id") for entry in entries if entry.kind == ListEntryKind.RESOURCE_ITEM]
    duplicates = {item_id for item_id in ids if item_id is not None and ids.count(item_id) > 1}
    if not duplicates:
        return entries
    return tuple(
        entry
        if entry.metadata.get("item_id") not in duplicates
        else replace(
            entry,
            action_point=None,
            metadata={**entry.metadata, "unresolved_reason": "duplicate_item_id"},
            row_status=RowRecognitionStatus.AMBIGUOUS,
        )
        for entry in entries
    )


def _vertical_runs(
    image: Image.Image, *, x: int, start: int, end: int,
    predicate: Callable[[tuple[int, int, int]], bool], minimum: int,
) -> tuple[tuple[int, int], ...]:
    """Extracts contiguous pixel bands for this inventory detector."""

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


def is_gold_button_pixel(pixel: tuple[int, int, int]) -> bool:
    """Recognizes the selected tab's gold fill in reviewed normalized chrome."""

    red, green, blue = pixel
    return red > green and green > blue + 20 and red > 90


def is_blue_button_pixel(pixel: tuple[int, int, int]) -> bool:
    """Separates blue single Use from orange bulk Use and dark blue cards."""

    red, green, blue = pixel
    return blue > 110 and green > 65 and blue > green + 20 and green > red + 10
