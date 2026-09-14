"""Captured Alliance member row geometry and bounded semantic OCR."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.resource_inventory import (
    detect_button_runs,
    is_blue_button_pixel,
)
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
)


_MANAGE_LAYOUT_ID = "alliance_remaining_member_list"
_REINFORCE_LAYOUT_ID = "alliance_remaining_member_reinforce"
_REFERENCE_SIZE = (900, 1600)
_CARD_LEFT = 17
_CARD_WIDTH = 866
_CARD_HEIGHT = 200
_BLUE_SCAN_LEFT_RATIO = 0.68
_BLUE_SCAN_RIGHT_RATIO = 0.985
_NAME_LEFT_RATIO = 0.22
_NAME_RIGHT_RATIO = 0.70
_NAME_TOP_OFFSET = 16
_NAME_HEIGHT = 80
_ACTION_OCR_PADDING = 8
_ACTION_LABELS = frozenset({"MANAGE", "REINFORCE"})
_SEPARATOR_SEARCH_RADIUS = 4
_TOP_SEPARATOR_DELTA = 8
_BOTTOM_SEPARATOR_DELTA = 8
_MIN_SEPARATOR_PROBES = 3


@dataclass(frozen=True, slots=True)
class _AllianceMemberLayout:
    """Defines the measured row slots for one captured member-list layout."""

    screen_type: ScreenType
    action: str
    row_tops: tuple[int, ...]


_LAYOUTS = {
    (_MANAGE_LAYOUT_ID, ScreenType.PNC_ALLIANCE_MEMBER_LIST): _AllianceMemberLayout(
        screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
        action="manage",
        row_tops=(560, 861, 1079, 1297, 1515),
    ),
    (_REINFORCE_LAYOUT_ID, ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE): _AllianceMemberLayout(
        screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
        action="reinforce",
        row_tops=(185, 488, 706, 924, 1142, 1360),
    ),
}


def parse_alliance_member_rows(
    *,
    image: Image.Image,
    screen_type: ScreenType,
    layout_id: str,
    ocr_context: ObservationOcrContext,
) -> tuple[DetectedListEntry, ...]:
    """Parse the currently captured Alliance member layout from bounded rows.

    The screen and layout pair must be independently proved by the caller. A
    card is admitted from its captured card geometry, then its name and action
    are read from separate semantic crops. An action point is emitted only
    when the measured blue control and the mode-specific OCR label agree.
    """

    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image.")
    if not isinstance(screen_type, ScreenType):
        raise TypeError("screen_type must be a ScreenType value.")
    if not isinstance(layout_id, str) or not layout_id.strip():
        raise TypeError("layout_id must be a non-empty string.")
    if not hasattr(ocr_context, "read_result"):
        raise TypeError("ocr_context must provide bounded read_result().")

    layout = _LAYOUTS.get((layout_id, screen_type))
    if layout is None:
        return ()
    rows = detect_alliance_member_row_bounds(
        image=image,
        screen_type=screen_type,
        layout_id=layout_id,
    )
    entries: list[DetectedListEntry] = []
    for row_index, row_bounds in enumerate(rows):
        action_bounds = _detect_row_action_bounds(image=image, row_bounds=row_bounds)
        action_ocr_bounds = (
            None
            if action_bounds is None
            else _expanded_bounds(
                action_bounds,
                padding=_ACTION_OCR_PADDING,
                container=row_bounds,
            )
        )
        name_bounds = _name_region(image=image, row_bounds=row_bounds)
        name_lines = _read_region_lines(
            image=image,
            ocr_context=ocr_context,
            region=name_bounds,
            detail=f"alliance_member:{layout.action}:row_{row_index}:name",
            required_fact=f"alliance_member.{layout.action}.{row_index}.name",
        )
        action_lines = (
            ()
            if action_ocr_bounds is None
            else _read_region_lines(
                image=image,
                ocr_context=ocr_context,
                region=action_ocr_bounds,
                detail=f"alliance_member:{layout.action}:row_{row_index}:action",
                required_fact=f"alliance_member.{layout.action}.{row_index}.action",
            )
        )
        title_text, name_status = _resolve_name(name_lines)
        action_status = _resolve_action(
            action_lines,
            expected_action=layout.action,
            action_bounds=action_bounds,
        )
        status = _row_status(
            name_status=name_status,
            action_status=action_status,
            action_bounds=action_bounds,
        )
        action_point = (
            None
            if status != RowRecognitionStatus.COMPLETE or action_bounds is None
            else action_bounds.center()
        )
        metadata: dict[str, Any] = {
            "action": layout.action,
            "action_label": layout.action.title(),
            "row_index": row_index,
            "name_region_bounds": name_bounds,
            "action_ocr_region_bounds": action_ocr_bounds,
            "source_region_bounds": {
                "row": row_bounds,
                "name": name_bounds,
                "action": action_ocr_bounds,
            },
            "coordinate_provenance": "visual_geometry",
            "observation_fingerprint": _row_fingerprint(image=image, bounds=row_bounds),
        }
        reason = _unresolved_reason(
            name_status=name_status,
            action_status=action_status,
            action_bounds=action_bounds,
        )
        if reason is not None:
            metadata["unresolved_reason"] = reason
        entries.append(
            DetectedListEntry(
                kind=ListEntryKind.ALLIANCE_MEMBER,
                bounds=row_bounds,
                title_text=title_text,
                action_point=action_point,
                action_bounds=action_bounds,
                row_status=status,
                metadata=metadata,
                frame_ref=getattr(ocr_context, "frame_ref", None),
                source_screen=screen_type,
                source_layout_id=layout_id,
            )
        )
    return tuple(entries)


def detect_alliance_member_row_bounds(
    *,
    image: Image.Image,
    screen_type: ScreenType,
    layout_id: str,
) -> tuple[Bounds, ...]:
    """Return complete captured member cards with native image-space bounds."""

    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image.")
    if not isinstance(screen_type, ScreenType):
        raise TypeError("screen_type must be a ScreenType value.")
    if not isinstance(layout_id, str) or not layout_id.strip():
        raise TypeError("layout_id must be a non-empty string.")
    layout = _LAYOUTS.get((layout_id, screen_type))
    if layout is None:
        return ()
    rows: list[Bounds] = []
    for reference_top in layout.row_tops:
        nominal_row = _scaled_card_bounds(reference_top=reference_top, image_size=image.size)
        if _row_is_clipped(nominal_row, image_size=image.size):
            continue
        row = _measure_card_bounds(image=image, nominal_bounds=nominal_row)
        if row is not None and _card_surface_present(image=image, bounds=row):
            rows.append(row)
    return tuple(rows)


def _scaled_card_bounds(*, reference_top: int, image_size: tuple[int, int]) -> Bounds:
    """Scale one reviewed 900x1600 card rectangle into native coordinates."""

    width, height = image_size
    return Bounds(
        x=round(_CARD_LEFT * width / _REFERENCE_SIZE[0]),
        y=round(reference_top * height / _REFERENCE_SIZE[1]),
        width=max(1, round(_CARD_WIDTH * width / _REFERENCE_SIZE[0])),
        height=max(1, round(_CARD_HEIGHT * height / _REFERENCE_SIZE[1])),
    )


def _row_is_clipped(bounds: Bounds, *, image_size: tuple[int, int]) -> bool:
    """Return whether a candidate card touches the captured viewport edge."""

    return bounds.y < 0 or bounds.y + bounds.height > image_size[1]


def _measure_card_bounds(*, image: Image.Image, nominal_bounds: Bounds) -> Bounds | None:
    """Measure and validate the card's current-frame top and bottom borders.

    The slot positions are only search anchors from the reviewed captures. A
    row shifted outside the narrow separator windows is rejected, even when
    its remaining area happens to resemble a generic blue card background.
    """

    rgb = image.convert("RGB")
    top = _find_horizontal_separator(
        rgb,
        nominal_bounds=nominal_bounds,
        edge="top",
    )
    bottom = _find_horizontal_separator(
        rgb,
        nominal_bounds=nominal_bounds,
        edge="bottom",
    )
    if top is None or bottom is None or bottom < top:
        return None
    measured_height = bottom - top + 1
    height_tolerance = max(4, round(nominal_bounds.height * 0.06))
    if abs(measured_height - nominal_bounds.height) > height_tolerance:
        return None
    return Bounds(
        x=nominal_bounds.x,
        y=top,
        width=nominal_bounds.width,
        height=measured_height,
    )


def _find_horizontal_separator(
    image: Image.Image,
    *,
    nominal_bounds: Bounds,
    edge: str,
) -> int | None:
    """Find one measured card edge from stable side probes near its slot."""

    if edge not in {"top", "bottom"}:
        raise ValueError("edge must be 'top' or 'bottom'.")
    probes = (
        nominal_bounds.x + 2,
        nominal_bounds.x + 10,
        nominal_bounds.x + nominal_bounds.width - 11,
        nominal_bounds.x + nominal_bounds.width - 2,
    )
    if edge == "top":
        start = max(1, nominal_bounds.y - _SEPARATOR_SEARCH_RADIUS)
        stop = min(image.height - 1, nominal_bounds.y + _SEPARATOR_SEARCH_RADIUS)
        direction = -1
        threshold = _TOP_SEPARATOR_DELTA
    else:
        start = max(0, nominal_bounds.y + nominal_bounds.height - 1 - _SEPARATOR_SEARCH_RADIUS)
        stop = min(image.height - 2, nominal_bounds.y + nominal_bounds.height - 1 + _SEPARATOR_SEARCH_RADIUS)
        direction = 1
        threshold = _BOTTOM_SEPARATOR_DELTA
    candidates: list[tuple[int, int, int]] = []
    for y in range(start, stop + 1):
        deltas = []
        for x in probes:
            current = sum(image.getpixel((x, y)))
            neighbor = sum(image.getpixel((x, y + direction)))
            delta = current - neighbor
            deltas.append(delta)
        matched = sum(delta >= threshold for delta in deltas)
        if matched >= _MIN_SEPARATOR_PROBES:
            candidates.append((matched, sum(max(0, delta) for delta in deltas), y))
    if not candidates:
        return None
    anchor = nominal_bounds.y if edge == "top" else nominal_bounds.y + nominal_bounds.height - 1
    return min(
        candidates,
        key=lambda candidate: (
            abs(candidate[2] - anchor),
            -candidate[0],
            -candidate[1],
        ),
    )[2]


def _card_surface_present(*, image: Image.Image, bounds: Bounds) -> bool:
    """Check stable blue card surface probes without reading text or tiling."""

    rgb = image.convert("RGB")
    probes = (
        (bounds.x + max(1, bounds.width // 20), bounds.y + 10),
        (bounds.x + bounds.width // 2, bounds.y + 10),
        (bounds.x + bounds.width - max(2, bounds.width // 20), bounds.y + 10),
        (bounds.x + max(1, bounds.width // 20), bounds.y + bounds.height // 2),
        (bounds.x + bounds.width - max(2, bounds.width // 20), bounds.y + bounds.height // 2),
        (bounds.x + bounds.width // 2, bounds.y + bounds.height - 10),
    )
    present = 0
    for x, y in probes:
        red, green, blue = rgb.getpixel((x, y))
        if red + green + blue >= 90 and blue >= red + 18:
            present += 1
    return present >= 4


def _detect_row_action_bounds(*, image: Image.Image, row_bounds: Bounds) -> Bounds | None:
    """Detect one blue button inside one card, retaining the measured box."""

    runs = detect_button_runs(
        image.convert("RGB"),
        bounds=row_bounds,
        x_start=max(row_bounds.x, int(image.width * _BLUE_SCAN_LEFT_RATIO)),
        x_end=min(row_bounds.x + row_bounds.width, int(image.width * _BLUE_SCAN_RIGHT_RATIO)),
        predicate=is_blue_button_pixel,
        minimum_height=max(5, round(image.height * 0.02)),
    )
    return runs[0] if len(runs) == 1 else None


def _name_region(*, image: Image.Image, row_bounds: Bounds) -> Bounds:
    """Return the bounded name field aligned to one card."""

    left = max(row_bounds.x, round(image.width * _NAME_LEFT_RATIO))
    right = min(row_bounds.x + row_bounds.width, round(image.width * _NAME_RIGHT_RATIO))
    top = row_bounds.y + round(_NAME_TOP_OFFSET * image.height / _REFERENCE_SIZE[1])
    bottom = min(row_bounds.y + row_bounds.height, top + round(_NAME_HEIGHT * image.height / _REFERENCE_SIZE[1]))
    return Bounds(left, top, max(1, right - left), max(1, bottom - top))


def _expanded_bounds(bounds: Bounds, *, padding: int, container: Bounds) -> Bounds:
    """Expand a semantic action crop while retaining row ownership."""

    left = max(container.x, bounds.x - padding)
    top = max(container.y, bounds.y - padding)
    right = min(container.x + container.width, bounds.x + bounds.width + padding)
    bottom = min(container.y + container.height, bounds.y + bounds.height + padding)
    return Bounds(left, top, max(1, right - left), max(1, bottom - top))


def _read_region_lines(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    region: Bounds,
    detail: str,
    required_fact: str,
) -> tuple[OcrLine, ...]:
    """Read one named semantic region from the frame-bound OCR context."""

    result = ocr_context.read_result(
        image,
        region,
        reuse_full_frame=False,
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
        required_fact=required_fact,
    )
    return tuple(sorted(result.lines, key=lambda line: (line.bounds.y, line.bounds.x)))


def _resolve_name(lines: tuple[OcrLine, ...]) -> tuple[str | None, str]:
    """Resolve one exact name line, keeping OCR spelling unchanged."""

    candidates = tuple(
        line
        for line in lines
        if normalize_ocr_text(line.text)
        and len(normalize_ocr_text(line.text)) >= 2
        and any(character.isalpha() for character in line.text)
    )
    if len(candidates) != 1:
        return None, "ambiguous_name" if candidates else "missing_name"
    return candidates[0].text.strip(), "complete"


def _resolve_action(
    lines: tuple[OcrLine, ...],
    *,
    expected_action: str,
    action_bounds: Bounds | None,
) -> str:
    """Require exactly one mode-correct label inside the measured blue box."""

    if action_bounds is None:
        return "missing_button"
    labels = tuple(
        line
        for line in lines
        if normalize_ocr_text(line.text) in _ACTION_LABELS
    )
    if len(labels) != 1:
        return "missing_or_ambiguous_action"
    label = labels[0]
    if normalize_ocr_text(label.text) != expected_action.upper():
        return "wrong_action"
    if not action_bounds.contains_bounds(label.bounds):
        return "action_label_outside_button"
    return "complete"


def _row_status(*, name_status: str, action_status: str, action_bounds: Bounds | None) -> RowRecognitionStatus:
    """Project independent name and action outcomes into the row contract."""

    if name_status != "complete":
        return (
            RowRecognitionStatus.AMBIGUOUS
            if name_status == "ambiguous_name"
            else RowRecognitionStatus.UNREADABLE
        )
    if action_status != "complete" or action_bounds is None:
        return RowRecognitionStatus.NO_ACTION
    return RowRecognitionStatus.COMPLETE


def _unresolved_reason(*, name_status: str, action_status: str, action_bounds: Bounds | None) -> str | None:
    """Return one concise reason for a non-actionable row."""

    if name_status != "complete":
        return name_status
    if action_status != "complete":
        return action_status
    if action_bounds is None:
        return "missing_button"
    return None


def _row_fingerprint(*, image: Image.Image, bounds: Bounds) -> str:
    """Hash the native card crop for same-frame diagnostics and correlation."""

    crop = image.convert("RGB").crop(
        (bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height)
    )
    return hashlib.sha256(crop.tobytes()).hexdigest()


__all__ = [
    "detect_alliance_member_row_bounds",
    "parse_alliance_member_rows",
]
