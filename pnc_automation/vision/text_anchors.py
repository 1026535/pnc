"""Shared OCR text-anchor detection used by P&C screen parsers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.text_normalization import normalize_ocr_text
from pnc_automation.vision.ocr_service import OcrLine, OcrResult, OcrWord
from pnc_automation.vision.selectors import Region


class TextAnchorId(StrEnum):
    """Canonical OCR labels consumed by screen-specific parsers."""

    CASTLE_LEVEL = "castle_level"
    LABEL_CANCEL = "label_cancel"
    KINGDOM = "kingdom"
    LABEL_ALLIANCE = "label_alliance"
    LABEL_BAG = "label_bag"
    LABEL_BUILD = "label_build"
    LABEL_CAMPAIGN = "label_campaign"
    LABEL_CONFIRM = "label_confirm"
    LABEL_ENHANCE = "label_enhance"
    LABEL_EVOLVE = "label_evolve"
    LABEL_HERO = "label_hero"
    LABEL_HELP = "label_help"
    LABEL_HERO_SKILL = "label_hero_skill"
    LABEL_HOME = "label_home"
    LABEL_JOIN_APPLY = "label_join_apply"
    LABEL_MAIL = "label_mail"
    LABEL_MANAGE_CHAR = "label_manage_char"
    LABEL_MORE = "label_more"
    LABEL_NEXT = "label_next"
    LABEL_QUEST = "label_quest"
    LABEL_RESEARCH = "label_research"
    LABEL_TROOP_SKILL = "label_troop_skill"
    LABEL_UPGRADE = "label_upgrade"


@dataclass(frozen=True, slots=True)
class DetectedTextAnchor:
    """Represents one known OCR label localized to screenshot coordinates."""

    id: TextAnchorId
    text: str
    normalized_text: str
    bounds: Region
    confidence: float
    metadata: tuple[tuple[str, str | int], ...] = ()

    def metadata_value(self, key: str) -> str | int | None:
        """Returns one metadata value when present."""

        for metadata_key, value in self.metadata:
            if metadata_key == key:
                return value
        return None


@dataclass(slots=True)
class TextAnchorDetector:
    """Normalizes OCR lines into shared typed anchors."""

    def detect(self, ocr: OcrResult | Iterable[OcrLine]) -> tuple[DetectedTextAnchor, ...]:
        """Returns every OCR phrase that matches one canonical text anchor."""

        lines = ocr.lines if isinstance(ocr, OcrResult) else tuple(ocr)
        anchors: list[DetectedTextAnchor] = []
        seen: set[tuple[TextAnchorId, int, int, int, int]] = set()
        for line in lines:
            _append_anchor_matches(anchors, seen, text=line.text, bounds=line.bounds, confidence=line.confidence)
            if not line.words:
                continue
            _append_word_span_matches(anchors, seen, line.words, max_words=3)
        return tuple(anchors)

_ANCHOR_IDS_BY_NORMALIZED_TEXT: dict[str, TextAnchorId] = {
    "ALLIANCE": TextAnchorId.LABEL_ALLIANCE,
    "BAG": TextAnchorId.LABEL_BAG,
    "BUILD": TextAnchorId.LABEL_BUILD,
    "CANCEL": TextAnchorId.LABEL_CANCEL,
    "CAMPAIGN": TextAnchorId.LABEL_CAMPAIGN,
    "CONFIRM": TextAnchorId.LABEL_CONFIRM,
    "ENHANCE": TextAnchorId.LABEL_ENHANCE,
    "EVOLVE": TextAnchorId.LABEL_EVOLVE,
    "HERO": TextAnchorId.LABEL_HERO,
    "HELP": TextAnchorId.LABEL_HELP,
    "HEROSKILL": TextAnchorId.LABEL_HERO_SKILL,
    "HOME": TextAnchorId.LABEL_HOME,
    "JOINAPPLY": TextAnchorId.LABEL_JOIN_APPLY,
    "MAIL": TextAnchorId.LABEL_MAIL,
    "MANAGECHAR": TextAnchorId.LABEL_MANAGE_CHAR,
    "MORE": TextAnchorId.LABEL_MORE,
    "NEXT": TextAnchorId.LABEL_NEXT,
    "QUEST": TextAnchorId.LABEL_QUEST,
    "RESEARCH": TextAnchorId.LABEL_RESEARCH,
    "TROOPSKILL": TextAnchorId.LABEL_TROOP_SKILL,
    "UPGRADE": TextAnchorId.LABEL_UPGRADE,
}

_STRUCTURED_ANCHOR_PATTERNS: tuple[tuple[re.Pattern[str], TextAnchorId, str], ...] = (
    (re.compile(r"\bK\s*(\d{2,4})(?:\s*KINGDOM\b|\b)", re.IGNORECASE), TextAnchorId.KINGDOM, "kingdom"),
    (re.compile(r"castle\s*level\s*[:.]?\s*(\d+)", re.IGNORECASE), TextAnchorId.CASTLE_LEVEL, "castle_level"),
)


def _append_anchor_matches(
    anchors: list[DetectedTextAnchor],
    seen: set[tuple[TextAnchorId, int, int, int, int]],
    *,
    text: str,
    bounds: Region,
    confidence: float,
) -> None:
    """Appends every anchor match found in one OCR text span."""

    normalized_text = normalize_ocr_text(text)
    if normalized_text == "":
        return

    anchor_id = _ANCHOR_IDS_BY_NORMALIZED_TEXT.get(normalized_text)
    if anchor_id is not None:
        _append_anchor(
            anchors,
            seen,
            DetectedTextAnchor(
                id=anchor_id,
                text=text.strip(),
                normalized_text=normalized_text,
                bounds=bounds,
                confidence=confidence,
            ),
        )

    for pattern, structured_anchor_id, metadata_key in _STRUCTURED_ANCHOR_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        raw_value = match.group(1)
        metadata_value: str | int = f"K{raw_value}" if structured_anchor_id == TextAnchorId.KINGDOM else int(raw_value)
        _append_anchor(
            anchors,
            seen,
            DetectedTextAnchor(
                id=structured_anchor_id,
                text=text.strip(),
                normalized_text=normalized_text,
                bounds=bounds,
                confidence=confidence,
                metadata=((metadata_key, metadata_value),),
            ),
        )


def _append_word_span_matches(
    anchors: list[DetectedTextAnchor],
    seen: set[tuple[TextAnchorId, int, int, int, int]],
    words: tuple[OcrWord, ...],
    *,
    max_words: int,
) -> None:
    """Evaluates short OCR word spans so split labels still map to one anchor."""

    for start in range(len(words)):
        span_words: list[OcrWord] = []
        for end in range(start, min(len(words), start + max_words)):
            span_words.append(words[end])
            span_text = " ".join(word.text for word in span_words)
            span_bounds = _merge_bounds(tuple(span_words))
            span_confidence = min(word.confidence for word in span_words)
            _append_anchor_matches(
                anchors,
                seen,
                text=span_text,
                bounds=span_bounds,
                confidence=span_confidence,
            )


def _append_anchor(
    anchors: list[DetectedTextAnchor],
    seen: set[tuple[TextAnchorId, int, int, int, int]],
    anchor: DetectedTextAnchor,
) -> None:
    """Appends one anchor while suppressing duplicate span/id matches."""

    dedupe_key = (
        anchor.id,
        anchor.bounds.x,
        anchor.bounds.y,
        anchor.bounds.width,
        anchor.bounds.height,
    )
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    anchors.append(anchor)


def _merge_bounds(words: tuple[OcrWord, ...]) -> Region:
    """Merges one or more OCR word bounds into a single region."""

    left = min(word.bounds.x for word in words)
    top = min(word.bounds.y for word in words)
    right = max(word.bounds.x + word.bounds.width for word in words)
    bottom = max(word.bounds.y + word.bounds.height for word in words)
    return Region(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))
