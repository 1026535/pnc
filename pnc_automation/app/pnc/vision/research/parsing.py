"""Pure Research OCR grouping, level, detail and queue parsing helpers."""

from __future__ import annotations

import re

from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import (
    RESEARCH_CATEGORY_DEFINITIONS,
    ResearchQueueRow,
    ResearchQueueState,
)
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from PIL import Image

_LEVEL_PATTERN = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_DETAIL_TITLE_PATTERN = re.compile(r"^(?P<title>.+?)\s*\((?P<cur>\d+)\s*/\s*(?P<max>\d+)\s*\)\s*$")
_DETAIL_TIME_PATTERN = re.compile(r"^\d{1,3}:\d{2}:\d{2}$")
_DETAIL_COST_PATTERN = re.compile(r"^(\d{1,3}(?:,\d{3})*|\d+)\s*/\s*(\d{1,3}(?:,\d{3})*|\d+)$")
_DETAIL_GEM_COST_PATTERN = re.compile(r"^\d{1,4}$")
_QUEUE_ROW_TITLE_PATTERN = re.compile(r"^\d+(?:ST|ND|RD|TH)RESEARCHQUEUE$")
_QUEUE_TIMER_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_QUEUE_TIMER_SEARCH = re.compile(r"\d{1,2}:\d{2}:\d{2}")
_RESEARCH_CATEGORY_BY_HEADER = {
    normalize_ocr_text(item.title): item.category
    for item in RESEARCH_CATEGORY_DEFINITIONS
}
_DECORATION_LABEL_PREFIXES = ("MASTERRESEARCHER",)


def header_category(lines: tuple[OcrLine, ...], *, image: Image.Image) -> ResearchCategory | None:
    """Resolve the proved tree category from its bounded header read."""

    header_bottom = image.height * (0.065 + 0.02)
    for line in lines:
        if line.bounds.y > header_bottom:
            continue
        normalized = normalize_ocr_text(line.text)
        for text, category in _RESEARCH_CATEGORY_BY_HEADER.items():
            if normalized == text or normalized.endswith(text):
                return category
    return None


def join_label_text(lines: tuple[OcrLine, ...]) -> str:
    """Join a tile's OCR lines by vertical row and then left-to-right."""

    if not lines:
        return ""
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda item: (item.bounds.y, item.bounds.x)):
        for row in rows:
            anchor = row[0].bounds
            overlap = min(anchor.y + anchor.height, line.bounds.y + line.bounds.height) - max(anchor.y, line.bounds.y)
            if overlap * 2 >= min(anchor.height, line.bounds.height):
                row.append(line)
                break
        else:
            rows.append([line])
    ordered = [line for row in rows for line in sorted(row, key=lambda item: item.bounds.x)]
    merged = ordered[0]
    for line in ordered[1:]:
        merged = merge_ocr_lines(merged, line)
    return merged.text


def node_level_readings(lines: tuple[OcrLine, ...]) -> set[tuple[int | None, int | None, bool]]:
    """Keep complete n/m and MAX readings distinct; join only split counters."""

    readings: set[tuple[int | None, int | None, bool]] = set()
    for line in lines:
        match = _LEVEL_PATTERN.match(line.text.strip())
        if match is not None:
            current, maximum = int(match.group(1)), int(match.group(2))
            if current <= maximum:
                readings.add((current, maximum, current == maximum))
        elif normalize_ocr_text(line.text) == "MAX":
            readings.add((None, None, True))
    if readings:
        return readings
    joined = "".join(line.text.strip() for line in sorted(lines, key=lambda line: line.bounds.x))
    match = _LEVEL_PATTERN.match(joined)
    if match is not None:
        current, maximum = int(match.group(1)), int(match.group(2))
        if current <= maximum:
            readings.add((current, maximum, current == maximum))
    return readings


def queue_row(*, image: Image.Image, title_line: OcrLine, row_lines: tuple[OcrLine, ...]) -> ResearchQueueRow:
    """Build one measured queue row with explicit idle/active/unknown state."""

    top = max(0, title_line.bounds.y - 6)
    bottom = min(image.height, max(line.bounds.y + line.bounds.height for line in row_lines) + 8)
    state = ResearchQueueState.UNKNOWN
    timer_text: str | None = None
    for line in row_lines:
        normalized = normalize_ocr_text(line.text)
        if normalized == "IDLE":
            state = ResearchQueueState.IDLE
        elif _QUEUE_TIMER_PATTERN.match(line.text.strip()) is not None:
            state = ResearchQueueState.ACTIVE
            timer_text = line.text.strip()
        elif normalized == "SPEEDUP":
            state = ResearchQueueState.ACTIVE
    return ResearchQueueRow(
        bounds=Bounds(0, top, image.width, max(1, bottom - top)),
        title_text=title_line.text.strip(),
        state=state,
        timer_text=timer_text,
    )


def time_below(label: OcrLine | None, time_lines: list[OcrLine]) -> str | None:
    """Return the first measured time value under one label column."""

    if label is None:
        return None
    candidates = [
        line for line in time_lines
        if line.bounds.y >= label.bounds.y + label.bounds.height
        and abs(line.bounds.x - label.bounds.x) <= label.bounds.width
    ]
    candidates.sort(key=lambda line: (line.bounds.y, line.bounds.x))
    return candidates[0].text.strip() if candidates else None


def queue_timer_after(anchor: OcrLine | None, time_lines: list[OcrLine]) -> str | None:
    """Return the timer shown with one queue-status anchor."""

    if anchor is None:
        return None
    embedded = _QUEUE_TIMER_SEARCH.search(anchor.text)
    if embedded is not None:
        return embedded.group(0)
    candidates = [line for line in time_lines if abs(line.bounds.y - anchor.bounds.y) <= anchor.bounds.height * 2]
    candidates.sort(key=lambda line: (abs(line.bounds.y - anchor.bounds.y), line.bounds.x))
    return candidates[0].text.strip() if candidates else None
