"""Shared OCR text-anchor detection used by P&C screen parsers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.vision.ocr_service import OcrLine
from pnc_automation.vision.selectors import Region


class TextAnchorId(StrEnum):
    """Canonical OCR labels consumed by screen-specific parsers."""

    LABEL_ALLIANCE = "label_alliance"
    LABEL_BAG = "label_bag"
    LABEL_BUILD = "label_build"
    LABEL_CAMPAIGN = "label_campaign"
    LABEL_ENHANCE = "label_enhance"
    LABEL_EVOLVE = "label_evolve"
    LABEL_HERO = "label_hero"
    LABEL_HERO_SKILL = "label_hero_skill"
    LABEL_HOME = "label_home"
    LABEL_MAIL = "label_mail"
    LABEL_MANAGE_CHAR = "label_manage_char"
    LABEL_MORE = "label_more"
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


@dataclass(slots=True)
class TextAnchorDetector:
    """Normalizes OCR lines into shared typed anchors."""

    def detect(self, lines: Iterable[OcrLine]) -> tuple[DetectedTextAnchor, ...]:
        """Returns every OCR line that matches one canonical text anchor."""

        anchors: list[DetectedTextAnchor] = []
        for line in lines:
            normalized_text = normalize_ocr_text(line.text)
            anchor_id = _ANCHOR_IDS_BY_NORMALIZED_TEXT.get(normalized_text)
            if anchor_id is None:
                continue
            anchors.append(
                DetectedTextAnchor(
                    id=anchor_id,
                    text=line.text.strip(),
                    normalized_text=normalized_text,
                    bounds=line.bounds,
                    confidence=line.confidence,
                )
            )
        return tuple(anchors)


def normalize_ocr_text(text: str) -> str:
    """Normalizes OCR text for tolerant anchor matching."""

    return "".join(character for character in text.upper() if character.isalnum())


_ANCHOR_IDS_BY_NORMALIZED_TEXT: dict[str, TextAnchorId] = {
    "ALLIANCE": TextAnchorId.LABEL_ALLIANCE,
    "BAG": TextAnchorId.LABEL_BAG,
    "BUILD": TextAnchorId.LABEL_BUILD,
    "CAMPAIGN": TextAnchorId.LABEL_CAMPAIGN,
    "ENHANCE": TextAnchorId.LABEL_ENHANCE,
    "EVOLVE": TextAnchorId.LABEL_EVOLVE,
    "HERO": TextAnchorId.LABEL_HERO,
    "HEROSKILL": TextAnchorId.LABEL_HERO_SKILL,
    "HOME": TextAnchorId.LABEL_HOME,
    "MAIL": TextAnchorId.LABEL_MAIL,
    "MANAGECHAR": TextAnchorId.LABEL_MANAGE_CHAR,
    "MORE": TextAnchorId.LABEL_MORE,
    "QUEST": TextAnchorId.LABEL_QUEST,
    "RESEARCH": TextAnchorId.LABEL_RESEARCH,
    "TROOPSKILL": TextAnchorId.LABEL_TROOP_SKILL,
    "UPGRADE": TextAnchorId.LABEL_UPGRADE,
}
