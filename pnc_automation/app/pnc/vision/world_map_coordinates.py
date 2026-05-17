"""Canonical world-map coordinate-bar OCR filtering and parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, SpatialViewport, SpatialViewportAddressingKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrService

_WORLD_X_COORDINATE_LABEL_PATTERN = re.compile(r"X\s*[:\uff1a]?", re.IGNORECASE)
_WORLD_Y_COORDINATE_LABEL_PATTERN = re.compile(r"Y\s*[:\uff1a]?", re.IGNORECASE)
_WORLD_COORDINATE_BAR_FILTER_SCALE = 3
_WORLD_COORDINATE_BAR_MIN_BLUE_PIXELS = 12
_WORLD_COORDINATE_BOUNDS = WorldMapCoordinateDomain.puzzles_and_conquest().bounds


@dataclass(frozen=True, slots=True)
class ParsedWorldViewport:
    """Carries the parsed world-map viewport plus the OCR region used to prove it."""

    viewport: SpatialViewport
    coordinate_bounds: Bounds
    coordinate_text: str


@dataclass(frozen=True, slots=True)
class _ParsedWorldCoordinatePair:
    """Carries one coherent X/Y coordinate pair plus the OCR lines that proved it."""

    x: int
    y: int
    lines: tuple[OcrLine, ...]


def parse_world_viewport(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ParsedWorldViewport | None:
    """Returns the strict world-map coordinate viewport when OCR proves one coherent X/Y pair."""

    candidate_lines = tuple(
        line
        for line in lines
        if line.bounds.y <= int(image.height * 0.18) and line.bounds.x <= int(image.width * 0.7)
    )
    if not candidate_lines:
        return None
    coordinate_pair = _extract_world_coordinate_pair(candidate_lines)
    if coordinate_pair is None:
        return None
    bounds_source = coordinate_pair.lines
    left = min(line.bounds.x for line in bounds_source)
    top = min(line.bounds.y for line in bounds_source)
    right = max(line.bounds.x + line.bounds.width for line in bounds_source)
    bottom = max(line.bounds.y + line.bounds.height for line in bounds_source)
    return _build_parsed_world_viewport(
        x=coordinate_pair.x,
        y=coordinate_pair.y,
        coordinate_bounds=Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top)),
    )


def read_world_coordinate_bar_viewport(
    *,
    image: Image.Image,
    bounds: object,
    ocr_service: OcrService,
) -> ParsedWorldViewport | None:
    """Returns the parsed coordinate-bar viewport from the canonical blue/cyan filtered selector crop."""

    text = read_world_coordinate_bar_text(image=image, bounds=bounds, ocr_service=ocr_service)
    pair = parse_world_coordinate_text(text)
    if pair is None:
        return None
    return _build_parsed_world_viewport(
        x=pair[0],
        y=pair[1],
        coordinate_bounds=Bounds(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height),
    )


def read_world_coordinate_bar_text(
    *,
    image: Image.Image,
    bounds: object,
    ocr_service: OcrService,
) -> str:
    """Returns OCR text from a blue-text-isolated coordinate-bar crop so background text cannot pollute recognition."""

    filtered = build_world_coordinate_bar_ocr_image(image=image, bounds=bounds)
    if filtered is None:
        return ""
    region_type = type(bounds)
    return ocr_service.read_text(
        filtered,
        region_type(x=0, y=0, width=filtered.width, height=filtered.height),
    )


def build_world_coordinate_bar_ocr_image(*, image: Image.Image, bounds: object) -> Image.Image | None:
    """Builds a scaled black-on-white OCR crop that keeps only the coordinate bar's blue/cyan glyphs."""

    crop = image.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height)).convert("RGB")
    filtered = Image.new("L", crop.size, 255)
    filtered_pixels = filtered.load()
    source_pixels = crop.load()
    blue_pixel_count = 0
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = source_pixels[x, y]
            if not is_world_map_blue_family_pixel(red=red, green=green, blue=blue):
                continue
            blue_pixel_count += 1
            filtered_pixels[x, y] = 0
            if x > 0:
                filtered_pixels[x - 1, y] = 0
            if x + 1 < crop.width:
                filtered_pixels[x + 1, y] = 0
    if blue_pixel_count < _WORLD_COORDINATE_BAR_MIN_BLUE_PIXELS:
        return None
    return filtered.resize(
        (max(1, filtered.width * _WORLD_COORDINATE_BAR_FILTER_SCALE), max(1, filtered.height * _WORLD_COORDINATE_BAR_FILTER_SCALE)),
        resample=Image.Resampling.NEAREST,
    )


def world_coordinate_text_matches(text: str) -> bool:
    """Returns whether raw OCR text contains one coherent world-coordinate X/Y pair."""

    return parse_world_coordinate_text(text) is not None


def parse_world_coordinate_text(text: str) -> tuple[int, int] | None:
    """Returns one coordinate pair from text-only OCR output when X appears before Y."""

    stripped = text.strip()
    x_match = _WORLD_X_COORDINATE_LABEL_PATTERN.search(stripped)
    y_match = _WORLD_Y_COORDINATE_LABEL_PATTERN.search(stripped)
    if x_match is None or y_match is None or x_match.start() > y_match.start():
        return None
    x_value = _parse_world_coordinate_component_fragment(
        fragment=stripped[x_match.end() : y_match.start()],
        max_value=_WORLD_COORDINATE_BOUNDS.max_x,
    )
    y_value = _parse_world_coordinate_component_fragment(
        fragment=stripped[y_match.end() :],
        max_value=_WORLD_COORDINATE_BOUNDS.max_y,
    )
    if x_value is None or y_value is None:
        return None
    return x_value, y_value


def parse_world_coordinate_dialog_field_text(*, selector_id: UiElementId, text: str | None) -> int | None:
    """Returns one committed coordinate-dialog field value from OCR text when it is parseable."""

    if text is None:
        return None
    stripped = text.strip()
    if stripped == "":
        return None
    match = re.search(r"\d+", stripped)
    if match is None:
        return None
    value = int(match.group(0))
    if selector_id == UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD and value <= 0:
        return None
    return value


def is_world_map_blue_family_pixel(*, red: int, green: int, blue: int) -> bool:
    """Returns whether one RGB pixel belongs to the live blue/cyan text family used by world-map chrome."""

    return blue >= 110 and blue >= red + 30 and blue >= green + 5


def _build_parsed_world_viewport(*, x: int, y: int, coordinate_bounds: Bounds) -> ParsedWorldViewport:
    """Builds one parsed world viewport from already-validated coordinate values and bounds."""

    return ParsedWorldViewport(
        viewport=SpatialViewport(
            addressing_kind=SpatialViewportAddressingKind.COORDINATE_BAR,
            x=x,
            y=y,
        ),
        coordinate_bounds=coordinate_bounds,
        coordinate_text=f"X:{x} Y:{y}",
    )


def _extract_world_coordinate_pair(lines: tuple[OcrLine, ...]) -> _ParsedWorldCoordinatePair | None:
    """Returns one coherent world-coordinate OCR pair without mixing unrelated top-HUD number rows."""

    ordered_lines = tuple(sorted(lines, key=lambda item: (item.bounds.y, item.bounds.x)))
    same_line_pair = _extract_same_line_world_coordinate_pair(ordered_lines)
    if same_line_pair is not None:
        return same_line_pair
    return _extract_split_line_world_coordinate_pair(ordered_lines)


def _extract_same_line_world_coordinate_pair(lines: tuple[OcrLine, ...]) -> _ParsedWorldCoordinatePair | None:
    """Returns a coordinate pair when one OCR line contains both X and Y evidence."""

    for line in lines:
        pair = parse_world_coordinate_text(line.text)
        if pair is None:
            continue
        return _ParsedWorldCoordinatePair(x=pair[0], y=pair[1], lines=(line,))
    return None


def _extract_split_line_world_coordinate_pair(lines: tuple[OcrLine, ...]) -> _ParsedWorldCoordinatePair | None:
    """Returns a nearby X/Y line pair from the coordinate bar while ignoring unrelated resource/status text."""

    best_pair: tuple[tuple[int, int, int], _ParsedWorldCoordinatePair] | None = None
    for x_line in lines:
        x_value = _parse_labeled_world_coordinate_component(
            text=x_line.text,
            label_pattern=_WORLD_X_COORDINATE_LABEL_PATTERN,
            max_value=_WORLD_COORDINATE_BOUNDS.max_x,
        )
        if x_value is None:
            continue
        for y_line in lines:
            if x_line is y_line:
                continue
            y_value = _parse_labeled_world_coordinate_component(
                text=y_line.text,
                label_pattern=_WORLD_Y_COORDINATE_LABEL_PATTERN,
                max_value=_WORLD_COORDINATE_BOUNDS.max_y,
            )
            if y_value is None:
                continue
            if not _world_coordinate_lines_are_pair(x_line=x_line, y_line=y_line):
                continue
            center_gap = abs(_line_center_y(x_line) - _line_center_y(y_line)) + abs(_line_center_x(x_line) - _line_center_x(y_line))
            score = (
                abs(_line_center_y(x_line) - _line_center_y(y_line)),
                center_gap,
                max(x_line.bounds.x, y_line.bounds.x),
            )
            pair = _ParsedWorldCoordinatePair(
                x=x_value,
                y=y_value,
                lines=(x_line, y_line),
            )
            if best_pair is None or score < best_pair[0]:
                best_pair = (score, pair)
    return None if best_pair is None else best_pair[1]


def _parse_labeled_world_coordinate_component(
    *,
    text: str,
    label_pattern: re.Pattern[str],
    max_value: int,
) -> int | None:
    """Returns one bounded coordinate component from a single labeled OCR line."""

    match = label_pattern.search(text.strip())
    if match is None:
        return None
    return _parse_world_coordinate_component_fragment(fragment=text[match.end() :], max_value=max_value)


def _parse_world_coordinate_component_fragment(*, fragment: str, max_value: int) -> int | None:
    """Returns one bounded coordinate value from a noisy OCR fragment after one axis label."""

    digit_matches = tuple(re.finditer(r"\d+", fragment))
    if not digit_matches:
        return None
    if len(digit_matches) == 1:
        return _parse_world_coordinate_component_value(raw_value=digit_matches[0].group(0), max_value=max_value)
    coalesced_value = _coalesce_world_coordinate_digit_runs(fragment=fragment, digit_matches=digit_matches)
    if coalesced_value is None:
        return None
    parsed_value = _parse_world_coordinate_component_value(raw_value=coalesced_value, max_value=max_value)
    if parsed_value is not None:
        return parsed_value
    return _recover_reviewed_whitespace_split_trailing_digit(
        coalesced_value=coalesced_value,
        digit_matches=digit_matches,
        max_value=max_value,
    )


def _coalesce_world_coordinate_digit_runs(
    *,
    fragment: str,
    digit_matches: tuple[re.Match[str], ...],
) -> str | None:
    """Returns one coalesced digit run when OCR only split a coordinate with whitespace gaps."""

    for previous, current in zip(digit_matches, digit_matches[1:], strict=False):
        separator = fragment[previous.end() : current.start()]
        if separator.strip() != "":
            return None
    return "".join(match.group(0) for match in digit_matches)


def _parse_world_coordinate_component_value(*, raw_value: str, max_value: int) -> int | None:
    """Returns one bounded coordinate value from one OCR digit run using only reviewed live recoveries."""

    value = int(raw_value)
    if value <= max_value:
        return value
    for recovery in (
        _recover_reviewed_prefixed_x_noise(raw_value=raw_value, max_value=max_value),
        _recover_reviewed_concatenated_y_triplets(raw_value=raw_value, max_value=max_value),
        _recover_reviewed_trailing_digit_noise(raw_value=raw_value, max_value=max_value),
    ):
        if recovery is not None:
            return recovery
    return None


def _recover_reviewed_prefixed_x_noise(*, raw_value: str, max_value: int) -> int | None:
    """Recovers the reviewed live X-bar defect where OCR prefixed ``99`` ahead of one valid three-digit X value."""

    if len(str(max_value)) != 3 or len(raw_value) != 5 or not raw_value.startswith("99"):
        return None
    candidate = int(raw_value[2:])
    return candidate if candidate <= max_value else None


def _recover_reviewed_concatenated_y_triplets(*, raw_value: str, max_value: int) -> int | None:
    """Recovers the reviewed live Y-bar defect where OCR concatenated two three-digit groups without separators."""

    if len(str(max_value)) != 4 or len(raw_value) != 6:
        return None
    candidate = int(raw_value[:3])
    trailing_group = int(raw_value[3:])
    if candidate > max_value or trailing_group > max_value:
        return None
    return candidate


def _recover_reviewed_trailing_digit_noise(*, raw_value: str, max_value: int) -> int | None:
    """Recovers one reviewed extra trailing digit only when the full overflow is far beyond the domain ceiling."""

    if len(raw_value) < 2:
        return None
    candidate = int(raw_value[:-1])
    if candidate > max_value or int(raw_value) <= max_value * 2:
        return None
    return candidate


def _recover_reviewed_whitespace_split_trailing_digit(
    *,
    coalesced_value: str,
    digit_matches: tuple[re.Match[str], ...],
    max_value: int,
) -> int | None:
    """Recovers the reviewed whitespace-split stray trailing digit seen in one live X-bar OCR variant."""

    if len(digit_matches) != 2 or len(digit_matches[1].group(0)) != 1:
        return None
    if len(coalesced_value) < 2:
        return None
    candidate = int(coalesced_value[:-1])
    return candidate if candidate <= max_value else None


def _world_coordinate_lines_are_pair(*, x_line: OcrLine, y_line: OcrLine) -> bool:
    """Returns whether separate X and Y OCR lines plausibly belong to the same coordinate bar."""

    height = max(x_line.bounds.height, y_line.bounds.height, 1)
    vertical_delta = abs(_line_center_y(x_line) - _line_center_y(y_line))
    if vertical_delta > height:
        return False
    horizontal_gap = y_line.bounds.x - (x_line.bounds.x + x_line.bounds.width)
    if horizontal_gap < -max(x_line.bounds.width, y_line.bounds.width) * 0.35:
        return False
    if horizontal_gap > max(48, (x_line.bounds.width + y_line.bounds.width) * 1.2):
        return False
    return True


def _line_center_x(line: OcrLine) -> int:
    """Returns the horizontal center for one OCR line."""

    return line.bounds.x + line.bounds.width // 2


def _line_center_y(line: OcrLine) -> int:
    """Returns the vertical center for one OCR line."""

    return line.bounds.y + line.bounds.height // 2
