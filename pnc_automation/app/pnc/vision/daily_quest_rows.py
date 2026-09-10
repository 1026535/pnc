"""Visual row geometry and OCR-semantic parsing for the Daily Quest screen."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from PIL import Image

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestRowState
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog, DailyQuestDefinition
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


_PROGRESS_PATTERN = re.compile(r"\(\s*(?P<current>[\d,]+)\s*/\s*(?P<required>[\d,]+)\s*\)")
_IGNORED_ROW_TEXT = frozenset({"GO", "CLAIM", "CLAIMED", "COMPLETED"})


@dataclass(frozen=True, slots=True)
class DailyQuestVisionResult:
    """Carries the selected Quest tab and visually detected Daily rows."""

    selected_tab: str | None
    rows: tuple[DetectedListEntry, ...]


def parse_daily_quest_screen(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    catalog: DailyQuestCatalog | None = None,
) -> DailyQuestVisionResult | None:
    """Parses Quest chrome and rows while keeping OCR out of click geometry."""

    if not _has_quest_chrome(image=image, lines=lines):
        return None
    selected_tab = _detect_selected_tab(image)
    if selected_tab != "daily":
        return DailyQuestVisionResult(selected_tab=selected_tab, rows=())
    active_catalog = catalog or DailyQuestCatalog()
    row_bounds = detect_daily_row_bounds(image)
    return DailyQuestVisionResult(
        selected_tab=selected_tab,
        rows=tuple(
            _build_row_entry(image=image, lines=lines, bounds=bounds, catalog=active_catalog)
            for bounds in row_bounds
        ),
    )


def detect_daily_row_bounds(image: Image.Image) -> tuple[Bounds, ...]:
    """Detects the full-width blue row cards from pixels at a stable visual probe."""

    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    probe_x = min(width - 1, max(1, int(width * 0.037)))
    start_y = int(height * 0.36)
    minimum_height = max(20, int(height * 0.06))
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for y in range(start_y, height):
        red, green, blue = rgb_image.getpixel((probe_x, y))
        inside_card = red + green + blue >= 130 and blue >= red + 20
        if inside_card and run_start is None:
            run_start = y
        elif not inside_card and run_start is not None:
            if y - run_start >= minimum_height:
                runs.append((run_start, y - 1))
            run_start = None
    if run_start is not None and height - run_start >= minimum_height:
        runs.append((run_start, height - 1))
    left = int(width * 0.018)
    right = int(width * 0.976)
    return tuple(Bounds(x=left, y=top, width=max(1, right - left), height=bottom - top + 1) for top, bottom in runs)


def _has_quest_chrome(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> bool:
    """Returns whether OCR proves the shared Quest header and three-tab layout."""

    normalized = {normalize_ocr_text(line.text) for line in lines if line.bounds.y <= int(image.height * 0.16)}
    has_quest = "QUEST" in normalized
    has_main = "MAINQUEST" in normalized
    has_daily = "DAILYQUEST" in normalized
    has_alliance = "ALLIANCEACTIVITY" in normalized or {"ALLIANCE", "ACTIVITY"}.issubset(normalized)
    return has_quest and has_main and has_daily and has_alliance


def _detect_selected_tab(image: Image.Image) -> str | None:
    """Classifies the selected tab from its gold visual fill rather than OCR position."""

    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    sample_y = min(height - 1, int(height * 0.085))
    samples = {
        "main": rgb_image.getpixel((int(width * 0.17), sample_y)),
        "daily": rgb_image.getpixel((int(width * 0.50), sample_y)),
        "alliance": rgb_image.getpixel((int(width * 0.84), sample_y)),
    }
    warmth = {name: red + green - blue for name, (red, green, blue) in samples.items()}
    selected = max(warmth, key=warmth.get)
    ordered = sorted(warmth.values(), reverse=True)
    if len(ordered) < 2 or ordered[0] - ordered[1] < 25:
        return None
    return selected


def _build_row_entry(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    bounds: Bounds,
    catalog: DailyQuestCatalog,
) -> DetectedListEntry:
    """Combines visual card geometry with OCR-only title, progress, and action semantics."""

    row_lines = tuple(
        line
        for line in lines
        if bounds.y <= line.bounds.y + line.bounds.height // 2 <= bounds.y + bounds.height
    )
    definition, title_text = _resolve_title(row_lines=row_lines, image_width=image.width, catalog=catalog)
    state = _resolve_row_state(row_lines)
    progress = _resolve_progress(row_lines)
    action_x = int(image.width * 0.84)
    action_y = bounds.y + bounds.height // 2
    metadata: dict[str, str | int | None] = {
        "quest_id": None if definition is None else definition.quest_id.value,
        "row_state": state.value,
        "coordinate_provenance": "visual_geometry",
        "observation_fingerprint": _row_fingerprint(image=image, bounds=bounds),
        "progress_current": None if progress is None else progress[0],
        "progress_required": None if progress is None else progress[1],
    }
    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=bounds,
        title_text=title_text,
        action_point=(action_x, action_y),
        metadata=metadata,
    )


def _resolve_title(
    *,
    row_lines: tuple[OcrLine, ...],
    image_width: int,
    catalog: DailyQuestCatalog,
) -> tuple[DailyQuestDefinition | None, str | None]:
    """Returns one exact catalog match or the strongest unknown title candidate."""

    candidates = tuple(
        line
        for line in row_lines
        if int(image_width * 0.25) <= line.bounds.x <= int(image_width * 0.72)
        and normalize_ocr_text(line.text) not in _IGNORED_ROW_TEXT
        and _PROGRESS_PATTERN.search(line.text) is None
        and any(character.isalpha() for character in line.text)
    )
    for line in candidates:
        definition = catalog.resolve_title(line.text)
        if definition is not None:
            return definition, line.text
    if not candidates:
        return None, None
    strongest = max(candidates, key=lambda item: (item.confidence, item.bounds.width))
    return None, strongest.text


def _resolve_row_state(row_lines: tuple[OcrLine, ...]) -> DailyQuestRowState:
    """Classifies action semantics without allowing OCR bounds to drive a tap."""

    normalized = {normalize_ocr_text(line.text) for line in row_lines}
    if "CLAIM" in normalized:
        return DailyQuestRowState.CLAIM
    if "GO" in normalized:
        return DailyQuestRowState.GO
    if "CLAIMED" in normalized:
        return DailyQuestRowState.COMPLETED
    if any("REQUIRED" in item or item == "COMPLETED" for item in normalized):
        return DailyQuestRowState.REQUIREMENT
    return DailyQuestRowState.UNKNOWN_ACTION


def _resolve_progress(row_lines: tuple[OcrLine, ...]) -> tuple[int, int] | None:
    """Parses the first explicit current/required count from row OCR text."""

    for line in row_lines:
        match = _PROGRESS_PATTERN.search(line.text)
        if match is None:
            continue
        return (
            int(match.group("current").replace(",", "")),
            int(match.group("required").replace(",", "")),
        )
    return None


def _row_fingerprint(*, image: Image.Image, bounds: Bounds) -> str:
    """Returns a stable hash of the visual row crop used to reject stale geometry."""

    crop = image.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height)).convert("RGB")
    return hashlib.sha256(crop.tobytes()).hexdigest()
