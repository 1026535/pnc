"""Resource Bag semantics anchored to visual cards and blue single-Use buttons."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable

from PIL import Image

from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


_PACK_TITLE = re.compile(r"^(\d+(?:[.,]\d+)*)\s*([KM]?)\s*(FOOD|WOOD|IRON|GOLD)(\s*\(SAFE\))?$", re.I)
_OWNED = re.compile(r"^OWNED\s*:\s*([\d,]+)$", re.I)
_EXCLUDED_TITLE = re.compile(
    r"^(?:\d+(?:\.\d+)?[KM]?\s*Soulstones|24-hr\s*(?:Farm|Lumber|Iron|Gold)(?:\s*Mine)?\s*Output\s*Boost)$", re.I,
)


def parse_resource_inventory(
    *, image: Image.Image, lines: tuple[OcrLine, ...],
) -> tuple[DetectedListEntry, ...] | None:
    """Returns actionable owned-pack rows only on the selected Bag/Resource surface."""

    rgb = image.convert("RGB")
    header = {normalize_ocr_text(line.text) for line in lines if line.bounds.y < image.height * 0.17}
    if not {"BAG", "RESOURCE"}.issubset(header):
        return None
    if not all(
        _is_gold(rgb.getpixel((int(image.width * x), int(image.height * y))))
        for x, y in ((0.24, 0.09), (0.09, 0.145))
    ):
        return None
    entries: list[DetectedListEntry] = []
    for bounds in detect_resource_card_bounds(rgb):
        row_lines = tuple(
            line for line in lines
            if bounds.y <= line.bounds.y + line.bounds.height // 2 < bounds.y + bounds.height
        )
        title_matches = tuple(
            (line, _match_pack_title(line.text))
            for line in row_lines if image.width * 0.20 <= line.bounds.x < image.width * 0.70
        )
        titles = tuple((line, match) for line, match in title_matches if match is not None)
        counts = tuple(_OWNED.fullmatch(line.text.strip()) for line in row_lines)
        owned = tuple(match for match in counts if match is not None)
        exclusions = tuple(
            line for line in row_lines
            if image.width * 0.20 <= line.bounds.x < image.width * 0.70
            and _EXCLUDED_TITLE.fullmatch(line.text.strip())
        )
        if not titles and len(exclusions) == 1 and len(owned) == 1:
            entries.append(DetectedListEntry(
                kind=ListEntryKind.RESOURCE_INVENTORY_EXCLUSION,
                bounds=bounds, title_text=exclusions[0].text,
                metadata={"owned": int(owned[0].group(1).replace(",", ""))},
            ))
            continue
        if len(titles) != 1 or len(owned) != 1:
            continue
        buttons = _vertical_runs(
            rgb, x=int(image.width * 0.74), start=bounds.y, end=bounds.y + bounds.height,
            predicate=_is_blue_button, minimum=max(5, int(image.height * 0.015)),
        )
        if len(buttons) != 1:
            continue
        title, match = titles[0]
        raw_amount = match.group(1).replace(",", "")
        multiplier = {"": 1, "K": 1000, "M": 1000000}[match.group(2).upper()]
        amount = float(raw_amount) * multiplier
        if not amount.is_integer() or amount <= 0:
            continue
        crop = rgb.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height))
        top, bottom = buttons[0]
        resource = match.group(3).lower()
        safe = match.group(4) is not None
        entries.append(DetectedListEntry(
            kind=ListEntryKind.RESOURCE_ITEM,
            bounds=bounds,
            title_text=title.text,
            action_point=(int(image.width * 0.84), (top + bottom) // 2),
            metadata={
                "item_id": f"{resource}:{int(amount)}:{'safe' if safe else 'normal'}",
                "resource": resource,
                "amount": int(amount),
                "owned": int(owned[0].group(1).replace(",", "")),
                "observation_fingerprint": hashlib.sha256(crop.tobytes()).hexdigest(),
                "coordinate_provenance": "visual_geometry",
            },
        ))
    return tuple(entries)


def detect_resource_card_bounds(image: Image.Image) -> tuple[Bounds, ...]:
    """Finds inventory card bands without relying on text line coordinates."""

    rgb = image.convert("RGB")
    runs = _vertical_runs(
        rgb, x=max(1, int(image.width * 0.025)),
        start=int(image.height * 0.17), end=image.height,
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
    normalized = normalize_ocr_text(raw)
    corrected = normalized
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
        corrected = f"{corrected[:-4]} (SAFE)"
    return _PACK_TITLE.fullmatch(corrected)


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


def _is_gold(pixel: tuple[int, int, int]) -> bool:
    """Recognizes the selected tab's gold fill in reviewed normalized chrome."""

    red, green, blue = pixel
    return red > green and green > blue + 20 and red > 90


def _is_blue_button(pixel: tuple[int, int, int]) -> bool:
    """Separates blue single Use from orange bulk Use and dark blue cards."""

    red, green, blue = pixel
    return blue > 110 and green > 65 and blue > green + 20 and green > red + 10
