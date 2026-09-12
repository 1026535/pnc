"""Visual row geometry and OCR-semantic parsing for the Daily Quest screen."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from PIL import Image

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestRowState
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog, DailyQuestDefinition
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.resource_inventory import (
    detect_button_runs,
    is_blue_button_pixel,
    is_gold_button_pixel,
)
from pnc_automation.app.pnc.vision.numeric_parsing import parse_grouped_integer
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


_PROGRESS_PATTERN = re.compile(r"\(\s*(?P<current>[^()/]*)\s*/\s*(?P<required>[^()/]*)\s*\)")
_IGNORED_ROW_TEXT = frozenset({"GO", "CLAIM", "CLAIMED", "COMPLETED"})
_QUEST_BODY_TOP_RATIO = 0.36


@dataclass(frozen=True, slots=True)
class DailyQuestVisionResult:
    """Carries the selected Quest tab and visually detected Daily rows."""

    selected_tab: str | None
    rows: tuple[DetectedListEntry, ...]


@dataclass(frozen=True, slots=True)
class QuestActionRecoveryCandidate:
    """One row eligible for a bounded same-frame action-label reread."""

    row_index: int
    row_bounds: Bounds
    action_bounds: Bounds
    ocr_bounds: Bounds


def find_missing_quest_action_candidates(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    result: DailyQuestVisionResult,
) -> tuple[QuestActionRecoveryCandidate, ...]:
    """Find rows whose proved geometry is missing only its action label.

    Candidate admission is deliberately stricter than row parsing: title,
    progress, non-clipped geometry, and a unique quest identity must already
    be proved, and the original row must contain no recognized action token.
    This keeps a crop reread from resolving contradictions or inventing row
    identity. At most eight controls are eligible per captured frame.
    """

    if result.selected_tab != "daily":
        return ()
    duplicate_ids = _duplicate_quest_ids(result.rows)
    candidates: list[QuestActionRecoveryCandidate] = []
    for row_index, row in enumerate(result.rows):
        if row.row_status != RowRecognitionStatus.NO_ACTION:
            continue
        if row.metadata.get("row_state") != DailyQuestRowState.UNKNOWN_ACTION.value:
            continue
        quest_id = row.metadata.get("quest_id")
        if (
            row.title_text is None
            or quest_id is None
            or quest_id in duplicate_ids
            or not isinstance(row.metadata.get("progress_current"), int)
            or not isinstance(row.metadata.get("progress_required"), int)
            or int(row.metadata["progress_required"]) <= 0
            or row.action_bounds is None
            or _row_is_clipped(row.bounds, image, body_top=daily_quest_body_bounds(image).y)
            or not row.bounds.contains_bounds(row.action_bounds)
            or not Bounds(0, 0, image.width, image.height).contains_bounds(row.action_bounds)
        ):
            continue
        row_lines = tuple(line for line in lines if _line_contained(row.bounds, line))
        if _recognized_action_tokens(row_lines, image_width=image.width):
            continue
        candidates.append(
            QuestActionRecoveryCandidate(
                row_index=row_index,
                row_bounds=row.bounds,
                action_bounds=row.action_bounds,
                ocr_bounds=_expanded_action_ocr_bounds(
                    image=image,
                    row_bounds=row.bounds,
                    action_bounds=row.action_bounds,
                ),
            )
        )
        if len(candidates) == 8:
            break
    return tuple(candidates)


def parse_daily_quest_screen(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    catalog: DailyQuestCatalog | None = None,
    proved_screen: ScreenType | None = None,
) -> DailyQuestVisionResult | None:
    """Parse Quest rows from visually bounded cards and independently found controls."""

    if proved_screen is not None and not isinstance(proved_screen, ScreenType):
        raise TypeError("proved_screen must be a ScreenType or None")
    proved = proved_screen
    if proved not in {None, ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}:
        return None
    if proved is None and not _has_quest_chrome(image=image, lines=lines):
        return None
    selected_tab = detect_selected_quest_tab(image)
    if selected_tab is None:
        return None
    if proved == ScreenType.PNC_QUEST_MAIN and selected_tab != "main":
        return None
    if proved == ScreenType.PNC_QUEST_DAILY and selected_tab != "daily":
        return None
    if selected_tab != "daily":
        return DailyQuestVisionResult(selected_tab=selected_tab, rows=())
    active_catalog = catalog or DailyQuestCatalog()
    row_bounds = detect_daily_row_bounds(image)
    rows = tuple(
        _build_row_entry(image=image, lines=lines, bounds=bounds, catalog=active_catalog)
        for bounds in row_bounds
    )
    return DailyQuestVisionResult(
        selected_tab=selected_tab,
        rows=_mark_duplicate_quest_ids(rows),
    )


def detect_daily_row_bounds(image: Image.Image) -> tuple[Bounds, ...]:
    """Detects the full-width blue row cards from pixels at a stable visual probe."""

    rgb_image = image.convert("RGB")
    width, height = rgb_image.size
    probe_x = min(width - 1, max(1, int(width * 0.037)))
    start_y = daily_quest_body_bounds(image).y
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


def quest_screen_chrome_proven(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> bool:
    """Return whether the shared Quest header and tab OCR prove the family."""

    return _has_quest_chrome(image=image, lines=lines)


def detect_selected_quest_tab(image: Image.Image) -> str | None:
    """Return the selected Quest tab from the reviewed gold-fill predicate."""

    return _detect_selected_tab(image)


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

    row_lines = tuple(line for line in lines if _line_contained(bounds, line))
    definition, title_text, title_status = _resolve_title(
        row_lines=row_lines,
        image_width=image.width,
        catalog=catalog,
    )
    action_control = _detect_quest_action_bounds(image=image, bounds=bounds, lines=row_lines)
    action_bounds = None if action_control is None else action_control[0]
    action_kind = None if action_control is None else action_control[1]
    state, state_status = _resolve_row_state(
        row_lines,
        action_bounds=action_bounds,
        action_kind=action_kind,
        image_width=image.width,
    )
    progress = _resolve_progress(row_lines)
    clipped = _row_is_clipped(bounds, image, body_top=daily_quest_body_bounds(image).y)
    row_status = RowRecognitionStatus.COMPLETE
    reason: str | None = None
    if clipped:
        row_status = RowRecognitionStatus.CLIPPED
        reason = "clipped_row"
    elif title_status == RowRecognitionStatus.AMBIGUOUS:
        row_status = RowRecognitionStatus.AMBIGUOUS
        reason = "multiple_valid_titles"
    elif definition is None or title_text is None or progress is None:
        row_status = RowRecognitionStatus.UNREADABLE
        reason = "missing_or_ambiguous_title_or_progress"
    elif state == DailyQuestRowState.CLAIM and progress[0] < progress[1]:
        row_status = RowRecognitionStatus.AMBIGUOUS
        reason = "claim_progress_incomplete"
    elif state_status != RowRecognitionStatus.COMPLETE:
        row_status = state_status
        reason = "missing_or_incompatible_action_control"
    action_point = None
    if row_status == RowRecognitionStatus.COMPLETE and action_bounds is not None:
        action_point = (
            action_bounds.x + action_bounds.width // 2,
            action_bounds.y + action_bounds.height // 2,
        )
    metadata: dict[str, str | int | None] = {
        "quest_id": None if definition is None else definition.quest_id.value,
        "row_state": state.value,
        "coordinate_provenance": "visual_geometry",
        "observation_fingerprint": _row_fingerprint(image=image, bounds=bounds),
        "progress_current": None if progress is None else progress[0],
        "progress_required": None if progress is None else progress[1],
    }
    if reason is not None:
        metadata["unresolved_reason"] = reason
    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=bounds,
        title_text=title_text,
        action_point=action_point,
        action_bounds=action_bounds,
        row_status=row_status,
        metadata=metadata,
    )


def _resolve_title(
    *,
    row_lines: tuple[OcrLine, ...],
    image_width: int,
    catalog: DailyQuestCatalog,
) -> tuple[DailyQuestDefinition | None, str | None, RowRecognitionStatus | None]:
    """Returns one exact catalog match or the strongest unknown title candidate."""

    candidates = tuple(
        line
        for line in row_lines
        if int(image_width * 0.25) <= line.bounds.x <= int(image_width * 0.72)
        and normalize_ocr_text(line.text) not in _IGNORED_ROW_TEXT
        and _PROGRESS_PATTERN.search(line.text) is None
        and any(character.isalpha() for character in line.text)
    )
    matches = tuple(
        (line, definition)
        for line in candidates
        if (definition := catalog.resolve_title(line.text)) is not None
    )
    distinct_ids = {definition.quest_id for _, definition in matches}
    if len(distinct_ids) > 1:
        strongest = max(matches, key=lambda item: (item[0].confidence, item[0].bounds.width))
        return None, strongest[0].text, RowRecognitionStatus.AMBIGUOUS
    if matches:
        strongest = max(matches, key=lambda item: (item[0].confidence, item[0].bounds.width))
        return strongest[1], strongest[0].text, None
    if not candidates:
        return None, None, None
    strongest = max(candidates, key=lambda item: (item.confidence, item.bounds.width))
    return None, strongest.text, None


def _resolve_row_state(
    row_lines: tuple[OcrLine, ...],
    *,
    action_bounds: Bounds | None,
    action_kind: str | None,
    image_width: int,
) -> tuple[DailyQuestRowState, RowRecognitionStatus]:
    """Classify every right-strip state before requiring one compatible control label."""

    state_lines = _recognized_action_tokens(row_lines, image_width=image_width)

    if len(state_lines) > 1 or any(len(lines) > 1 for lines in state_lines.values()):
        return DailyQuestRowState.UNKNOWN_ACTION, RowRecognitionStatus.AMBIGUOUS
    if not state_lines:
        return DailyQuestRowState.UNKNOWN_ACTION, RowRecognitionStatus.NO_ACTION

    token, labels = next(iter(state_lines.items()))
    label_inside_control = action_bounds is not None and _line_contained(action_bounds, labels[0])
    if token == "CLAIM":
        if action_kind != "claim" or not label_inside_control:
            return DailyQuestRowState.UNKNOWN_ACTION, RowRecognitionStatus.NO_ACTION
        return DailyQuestRowState.CLAIM, RowRecognitionStatus.COMPLETE
    if token == "GO":
        if action_kind != "go" or not label_inside_control:
            return DailyQuestRowState.UNKNOWN_ACTION, RowRecognitionStatus.NO_ACTION
        return DailyQuestRowState.GO, RowRecognitionStatus.COMPLETE
    if token in {"CLAIMED", "COMPLETED"}:
        return DailyQuestRowState.COMPLETED, RowRecognitionStatus.NO_ACTION
    if token == "REQUIRED":
        return DailyQuestRowState.REQUIREMENT, RowRecognitionStatus.NO_ACTION
    return DailyQuestRowState.UNKNOWN_ACTION, RowRecognitionStatus.NO_ACTION


def _recognized_action_tokens(
    row_lines: tuple[OcrLine, ...],
    *,
    image_width: int,
) -> dict[str, list[OcrLine]]:
    """Collect all recognized right-strip state tokens, including outside controls."""

    state_lines: dict[str, list[OcrLine]] = {}
    for line in row_lines:
        if not (
            line.bounds.x >= int(image_width * 0.72)
            and line.bounds.x + line.bounds.width <= int(image_width * 0.98)
        ):
            continue
        token = _action_state_token(line.text)
        if token is not None:
            state_lines.setdefault(token, []).append(line)
    return state_lines


def _action_state_token(text: str) -> str | None:
    """Normalize one OCR label using the canonical Quest action vocabulary."""

    normalized = normalize_ocr_text(text)
    if normalized == "CLAIM":
        return "CLAIM"
    if normalized == "GO":
        return "GO"
    if normalized == "CLAIMED":
        return "CLAIMED"
    if normalized == "COMPLETED":
        return "COMPLETED"
    if "REQUIRED" in normalized:
        return "REQUIRED"
    return None


def _looks_like_blue_go_button(*, image: Image.Image, row_bounds: Bounds) -> bool:
    """Recognizes a wide blue action button only inside the row's right action region."""

    left = max(row_bounds.x, int(image.width * 0.70))
    right = min(row_bounds.x + row_bounds.width, int(image.width * 0.976))
    top = row_bounds.y + int(row_bounds.height * 0.18)
    bottom = row_bounds.y + int(row_bounds.height * 0.82)
    if right <= left or bottom <= top:
        return False

    width = right - left
    height = bottom - top
    blue_pixels = 0
    blue_columns = [0] * width
    blue_rows = [0] * height
    rgb_image = image.convert("RGB")
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue = rgb_image.getpixel((x, y))
            if blue < 100 or blue < red + 20 or blue < green - 20:
                continue
            blue_pixels += 1
            blue_columns[x - left] += 1
            blue_rows[y - top] += 1

    region_area = width * height
    if blue_pixels / region_area < 0.45:
        return False
    wide_columns = sum(count >= height * 0.40 for count in blue_columns)
    filled_rows = sum(count >= width * 0.40 for count in blue_rows)
    return wide_columns / width >= 0.60 and filled_rows / height >= 0.50


def _resolve_progress(row_lines: tuple[OcrLine, ...]) -> tuple[int, int] | None:
    """Parses every explicit current/required count without accepting malformed grouping."""

    matches: list[tuple[int, int]] = []
    for line in row_lines:
        for match in _PROGRESS_PATTERN.finditer(line.text):
            current = parse_grouped_integer(match.group("current"))
            required = parse_grouped_integer(match.group("required"))
            if current is None or required is None:
                return None
            matches.append((current, required))
    if len(set(matches)) != 1:
        return None
    if not matches or matches[0][1] <= 0:
        return None
    return matches[0]


def _line_contained(bounds: Bounds, line: OcrLine) -> bool:
    """Keep only OCR lines wholly contained by a detected row/control."""

    return bounds.contains_bounds(line.bounds)


def _row_is_clipped(bounds: Bounds, image: Image.Image, *, body_top: int) -> bool:
    """Reject any row card that touches the screenshot edge."""

    return (
        bounds.x <= 0
        or bounds.y <= body_top
        or bounds.x + bounds.width >= image.width
        or bounds.y + bounds.height >= image.height
    )


def daily_quest_body_bounds(image: Image.Image) -> Bounds:
    """Return the reviewed OCR body region shared by row detection and planning."""

    return daily_quest_body_bounds_for_size(image.size)


def daily_quest_body_bounds_for_size(image_size: tuple[int, int]) -> Bounds:
    """Return the shared Quest body region for a decoded image size."""

    width, height = image_size
    top = int(height * _QUEST_BODY_TOP_RATIO)
    return Bounds(x=0, y=top, width=width, height=max(1, height - top))


def _detect_quest_action_bounds(
    *,
    image: Image.Image,
    bounds: Bounds,
    lines: tuple[OcrLine, ...],
) -> tuple[Bounds, str] | None:
    """Find one blue Go or gold Claim control in the right strip."""

    del lines
    rgb_image = image.convert("RGB")
    x_start = max(bounds.x, int(image.width * 0.72))
    x_end = min(bounds.x + bounds.width, int(image.width * 0.98))
    blue = detect_button_runs(
        rgb_image,
        bounds=bounds,
        x_start=x_start,
        x_end=x_end,
        predicate=is_blue_button_pixel,
        minimum_height=max(5, int(image.height * 0.015)),
    )
    gold = detect_button_runs(
        rgb_image,
        bounds=bounds,
        x_start=x_start,
        x_end=x_end,
        predicate=is_gold_button_pixel,
        minimum_height=max(5, int(image.height * 0.015)),
    )
    controls = [(control, "go") for control in blue] + [(control, "claim") for control in gold]
    if len(controls) != 1:
        return None
    return controls[0]


def _expanded_action_ocr_bounds(
    *,
    image: Image.Image,
    row_bounds: Bounds,
    action_bounds: Bounds,
) -> Bounds:
    """Expand action OCR slightly while retaining the row and image ownership bounds."""

    padding = max(1, round(image.width * 8 / 900))
    left = max(row_bounds.x, action_bounds.x - padding, 0)
    top = max(row_bounds.y, action_bounds.y - padding, 0)
    right = min(
        row_bounds.x + row_bounds.width,
        image.width,
        action_bounds.x + action_bounds.width + padding,
    )
    bottom = min(
        row_bounds.y + row_bounds.height,
        image.height,
        action_bounds.y + action_bounds.height + padding,
    )
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _mark_duplicate_quest_ids(
    rows: tuple[DetectedListEntry, ...],
) -> tuple[DetectedListEntry, ...]:
    """Mark duplicate semantic Quest IDs ambiguous without suppressing either row."""

    duplicates = _duplicate_quest_ids(rows)
    if not duplicates:
        return rows
    return tuple(
        row
        if (
            row.metadata.get("quest_id") not in duplicates
            or row.row_status != RowRecognitionStatus.COMPLETE
        )
        else replace(
            row,
            action_point=None,
            metadata={**row.metadata, "unresolved_reason": "duplicate_quest_id"},
            row_status=RowRecognitionStatus.AMBIGUOUS,
        )
        for row in rows
    )


def _duplicate_quest_ids(rows: tuple[DetectedListEntry, ...]) -> frozenset[object]:
    """Return semantic Quest IDs that occur more than once in one parse."""

    ids = tuple(row.metadata.get("quest_id") for row in rows)
    return frozenset(
        quest_id
        for quest_id in ids
        if quest_id is not None and ids.count(quest_id) > 1
    )


def _row_fingerprint(*, image: Image.Image, bounds: Bounds) -> str:
    """Returns a stable hash of the visual row crop used to reject stale geometry."""

    crop = image.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height)).convert("RGB")
    return hashlib.sha256(crop.tobytes()).hexdigest()
