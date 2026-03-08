"""P&C-specific OCR enrichment for dynamic screens without template anchors."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image

from pnc_automation.pnc.observation import Bounds, DetectedListEntry, ListEntryKind, VisibleElement
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import ObservationAdditions
from pnc_automation.vision.ocr_service import OcrLine, OcrService

_KINGDOM_PATTERN = re.compile(r"\bK\s*(\d{2,4})\b", re.IGNORECASE)
_CASTLE_LEVEL_PATTERN = re.compile(r"castle\s*level\s*[:.]?\s*(\d+)", re.IGNORECASE)
_HOME_NAV_BY_LABEL = {
    "HOME": UiElementId.PNC_BOTTOM_NAV_HOME,
    "HERO": UiElementId.PNC_BOTTOM_NAV_HERO,
    "QUEST": UiElementId.PNC_BOTTOM_NAV_QUEST,
    "BAG": UiElementId.PNC_BOTTOM_NAV_BAG,
    "MAIL": UiElementId.PNC_BOTTOM_NAV_MAIL,
    "ALLIANCE": UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
    "MORE": UiElementId.PNC_BOTTOM_NAV_MORE,
}


@dataclass(slots=True)
class PncObservationEnricher:
    """Derives P&C screen facts that are more reliable via OCR than selectors."""

    ocr_service: OcrService

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
    ) -> ObservationAdditions:
        """Recognizes and parses the Manage Char castle-selection screen."""

        del visible_elements
        if screen_type not in {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION}:
            return ObservationAdditions()

        lines = tuple(sorted(self.ocr_service.read_lines(image), key=lambda line: (line.bounds.y, line.bounds.x)))
        building_detail = _build_building_detail_additions(image, lines)
        if building_detail is not None:
            return building_detail
        home_city = _build_home_city_additions(image, lines)
        if home_city is not None:
            return home_city
        entries = _extract_castle_entries(image, lines)
        if not _looks_like_castle_selection(lines, entries):
            return ObservationAdditions()

        current_castle_name = next((entry.title_text for entry in entries if entry.selected), None)
        return ObservationAdditions(
            screen_type_override=ScreenType.PNC_CASTLE_SELECTION,
            list_entries=entries,
            current_castle_name=current_castle_name,
        )


def _build_building_detail_additions(
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns derived selectors when OCR matches a building-detail screen."""

    upgrade_line = next(
        (
            line
            for line in lines
            if _normalize_text(line.text) == "UPGRADE"
            and line.bounds.x >= int(image.width * 0.55)
            and line.bounds.y <= int(image.height * 0.42)
        ),
        None,
    )
    if upgrade_line is None:
        return None
    title_line = next(
        (
            line
            for line in lines
            if line.bounds.y <= int(image.height * 0.09)
            and _normalize_text(line.text) not in {"UPGRADE", ""}
            and "MANAGECHAR" not in _normalize_text(line.text)
        ),
        None,
    )
    if title_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT: _make_visible(
                selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                x=0,
                y=0,
                width=max(1, int(image.width * 0.12)),
                height=max(1, int(image.height * 0.08)),
            ),
            UiElementId.PNC_BUILDING_UPGRADE_BUTTON: _make_visible(
                selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                x=max(0, upgrade_line.bounds.x - max(12, upgrade_line.bounds.width // 2)),
                y=max(0, upgrade_line.bounds.y - max(10, upgrade_line.bounds.height)),
                width=min(
                    image.width,
                    upgrade_line.bounds.width + max(40, upgrade_line.bounds.width),
                ),
                height=min(
                    image.height,
                    upgrade_line.bounds.height + max(20, upgrade_line.bounds.height),
                ),
            ),
        },
        screen_type_override=ScreenType.PNC_BUILDING_DETAILS,
    )


def _build_home_city_additions(
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns home-city classification when bottom navigation OCR is visible."""

    nav_lines = [line for line in lines if line.bounds.y >= int(image.height * 0.86)]
    visible_nav_elements: dict[UiElementId, VisibleElement] = {}
    for line in nav_lines:
        normalized = _normalize_text(line.text)
        selector_id = _HOME_NAV_BY_LABEL.get(normalized)
        if selector_id is None or selector_id in visible_nav_elements:
            continue
        visible_nav_elements[selector_id] = _make_visible(
            selector_id=selector_id,
            x=line.bounds.x,
            y=line.bounds.y,
            width=line.bounds.width,
            height=line.bounds.height,
            extracted_text=line.text.strip(),
        )
    if len(visible_nav_elements) < 2:
        return None
    if UiElementId.PNC_BOTTOM_NAV_MORE not in visible_nav_elements and UiElementId.PNC_BOTTOM_NAV_ALLIANCE not in visible_nav_elements:
        return None
    return ObservationAdditions(
        visible_elements=visible_nav_elements,
        screen_type_override=ScreenType.PNC_HOME_CITY,
    )


def _looks_like_castle_selection(
    lines: tuple[OcrLine, ...],
    entries: tuple[DetectedListEntry, ...],
) -> bool:
    """Returns whether OCR output matches the Manage Char screen structure."""

    if any("MANAGECHAR" in _normalize_text(line.text) for line in lines):
        return True
    if len(entries) < 2:
        return False
    leveled_entries = sum(1 for entry in entries if entry.metadata.get("castle_level") is not None)
    return leveled_entries >= 2


def _extract_castle_entries(image: Image.Image, lines: tuple[OcrLine, ...]) -> tuple[DetectedListEntry, ...]:
    """Extracts typed castle rows from OCR lines on the Manage Char screen."""

    kingdom_line_indexes = [index for index, line in enumerate(lines) if _parse_kingdom(line.text) is not None]
    entries: list[DetectedListEntry] = []
    for index, start in enumerate(kingdom_line_indexes):
        end = kingdom_line_indexes[index + 1] if index + 1 < len(kingdom_line_indexes) else len(lines)
        entry = _build_castle_entry(
            image=image,
            row_lines=lines[start:end],
            next_row_top=None if end >= len(lines) else lines[end].bounds.y,
        )
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def _build_castle_entry(
    *,
    image: Image.Image,
    row_lines: tuple[OcrLine, ...],
    next_row_top: int | None,
) -> DetectedListEntry | None:
    """Builds one detected castle entry from the OCR lines belonging to a row."""

    if not row_lines:
        return None
    kingdom = _parse_kingdom(row_lines[0].text)
    if kingdom is None:
        return None

    level_line = next((line for line in row_lines if _parse_castle_level(line.text) is not None), None)
    castle_name_line = _find_castle_name_line(row_lines, level_line=level_line)
    if castle_name_line is None:
        return None

    row_top = max(0, row_lines[0].bounds.y - 8)
    row_bottom = _resolve_row_bottom(row_lines, level_line=level_line, next_row_top=next_row_top, image_height=image.height)
    row_height = max(1, row_bottom - row_top)
    selected = _has_selected_checkmark(image, row_top=row_top, row_bottom=row_bottom)
    castle_level = _parse_castle_level(level_line.text) if level_line is not None else None
    return DetectedListEntry(
        kind=ListEntryKind.CASTLE,
        bounds=Bounds(x=0, y=row_top, width=image.width, height=row_height),
        title_text=castle_name_line.text.strip(),
        subtitle_text=row_lines[0].text.strip(),
        selected=selected,
        action_point=(image.width // 2, row_top + row_height // 2),
        metadata={
            "kingdom": kingdom,
            "castle_level": castle_level,
        },
    )


def _find_castle_name_line(row_lines: tuple[OcrLine, ...], *, level_line: OcrLine | None) -> OcrLine | None:
    """Returns the OCR line that most likely contains the castle name."""

    for line in row_lines[1:]:
        if _parse_kingdom(line.text) is not None:
            continue
        if _parse_castle_level(line.text) is not None:
            continue
        if level_line is not None and line.bounds.y > level_line.bounds.y:
            continue
        if _normalize_text(line.text) == "":
            continue
        return line
    return None


def _resolve_row_bottom(
    row_lines: tuple[OcrLine, ...],
    *,
    level_line: OcrLine | None,
    next_row_top: int | None,
    image_height: int,
) -> int:
    """Resolves a stable vertical tap target for one castle row."""

    content_bottom = row_lines[0].bounds.y + row_lines[0].bounds.height + 48
    if level_line is not None:
        content_bottom = level_line.bounds.y + level_line.bounds.height + 12
    if next_row_top is not None:
        return min(image_height, max(content_bottom, next_row_top - 8))
    return min(image_height, max(content_bottom, row_lines[0].bounds.y + 88))


def _has_selected_checkmark(image: Image.Image, *, row_top: int, row_bottom: int) -> bool:
    """Returns whether the castle row contains the green selection checkmark."""

    check_left = int(image.width * 0.82)
    crop = image.crop((check_left, row_top, image.width, row_bottom)).convert("RGB")
    green_pixels = 0
    threshold = max(24, (crop.width * crop.height) // 150)
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = pixels[x, y]
            if green >= 140 and green >= red + 35 and green >= blue + 35:
                green_pixels += 1
                if green_pixels >= threshold:
                    return True
    return False


def _parse_kingdom(text: str) -> str | None:
    """Extracts the normalized kingdom identifier from one OCR line."""

    match = _KINGDOM_PATTERN.search(text)
    if match is None:
        return None
    return f"K{match.group(1)}"


def _parse_castle_level(text: str) -> int | None:
    """Extracts the displayed castle level from one OCR line when present."""

    match = _CASTLE_LEVEL_PATTERN.search(text)
    if match is None:
        return None
    return int(match.group(1))


def _normalize_text(text: str) -> str:
    """Normalizes OCR text for tolerant header matching."""

    return "".join(character for character in text.upper() if character.isalnum())


def _make_visible(
    *,
    selector_id: UiElementId,
    x: int,
    y: int,
    width: int,
    height: int,
    extracted_text: str | None = None,
) -> VisibleElement:
    """Builds one derived visible element from OCR or anchored geometry."""

    return VisibleElement(
        selector_id=selector_id,
        bounds=Bounds(x=x, y=y, width=max(1, width), height=max(1, height)),
        confidence=1.0,
        extracted_text=extracted_text,
    )
