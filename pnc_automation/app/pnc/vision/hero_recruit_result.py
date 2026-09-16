"""Bounded content reads for independently qualified Hero Hall results."""

from dataclasses import dataclass
import re

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.hero_recruit_result import (
    HERO_RECRUIT_RESULT_LAYOUTS,
    HeroRecruitResult,
    HeroRecruitResultPhase,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose


def _native_bounds(image: Image.Image, region: Bounds) -> Bounds:
    """Project a measured 900x1600 source region to this capture."""

    return Bounds(
        round(region.x * image.width / 900), round(region.y * image.height / 1600),
        max(1, round(region.width * image.width / 900)),
        max(1, round(region.height * image.height / 1600)),
    )


def _read_text(
    image: Image.Image, context: ObservationOcrContext, region: Bounds, field: str,
) -> str | None:
    """Read only the current phase's measured field through shared OCR."""

    native_region = _native_bounds(image, region)
    lines = context.read_lines(
        image, native_region, purpose=OcrReadPurpose.CONTENT,
        detail=f"hero_recruit_{field}", required_fact=f"hero_recruit_{field}",
    )
    if not lines:
        result = context.read_preprocessed_result(
            image, native_region, preprocessing_id="hero_recruit_text_rgb_2x", prepare=_prepare_text,
            purpose=OcrReadPurpose.CONTENT, detail=f"hero_recruit_{field}_enlarged",
            required_fact=f"hero_recruit_{field}",
        )
        lines = () if result is None else result.lines
    return " ".join(line.text.strip() for line in sorted(
        lines, key=lambda line: line.bounds.x,
    ) if line.text.strip()) or None


def _prepare_text(image: Image.Image, region: Bounds) -> Image.Image:
    """Enlarge the result's small, single-line title and numeric fields."""

    crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height))
    return crop.convert("RGB").resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)


def _read_integer(
    image: Image.Image, context: ObservationOcrContext, region: Bounds, field: str,
) -> int | None:
    """Keep unreadable counters unknown instead of repairing OCR digits."""

    text = _read_text(image, context, region, field)
    return int(text) if text is not None and re.fullmatch(r"[0-9]+", text) else None


def _presentation_star_count(image: Image.Image) -> int | None:
    """Count separated gold stars in the observed presentation rating band."""

    reference = image.convert("RGB").resize((900, 1600), Image.Resampling.LANCZOS)
    pixels = np.asarray(reference.crop((330, 1130, 570, 1210)), dtype=np.int16)
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    gold = ((red > 170) & (green > 100) & (blue < 150) & (red > green * 1.05))
    _, _, stats, _ = cv2.connectedComponentsWithStats(gold.astype(np.uint8), connectivity=8)
    stars = [row for row in stats[1:] if 400 <= row[cv2.CC_STAT_AREA] <= 2200
             and 25 <= row[cv2.CC_STAT_WIDTH] <= 60 and 25 <= row[cv2.CC_STAT_HEIGHT] <= 60]
    return len(stars) or None


@dataclass(frozen=True, slots=True)
class HeroRecruitResultProducer:
    """Publish content only after a phase has independent visual identity."""

    def additions_for_screen(
        self, *, image: Image.Image, screen_type: ScreenType,
        ocr_context: ObservationOcrContext, layout_id: str | None,
    ) -> ObservationAdditions | None:
        """Keep result art distinct from menu attempts, Free, and paid controls."""

        phase = HERO_RECRUIT_RESULT_LAYOUTS.get(layout_id)
        if screen_type != ScreenType.PNC_HERO_RECRUIT_RESULT or phase is None:
            return None
        if phase == HeroRecruitResultPhase.HERO_PRESENTATION:
            result = HeroRecruitResult(
                phase=phase,
                title_text=_read_text(image, ocr_context, Bounds(260, 188, 380, 60), "hero_title"),
                star_count=_presentation_star_count(image),
            )
        else:
            result = HeroRecruitResult(
                phase=phase,
                title_text=_read_text(image, ocr_context, Bounds(335, 670, 235, 45), "item_title"),
                quantity=_read_integer(image, ocr_context, Bounds(478, 525, 48, 44), "quantity"),
                items_left=_read_integer(image, ocr_context, Bounds(700, 1380, 35, 50), "items_left"),
                recruit_cost=_read_integer(image, ocr_context, Bounds(686, 1440, 32, 30), "recruit_cost"),
            )
        return ObservationAdditions(hero_recruit_result=result)
