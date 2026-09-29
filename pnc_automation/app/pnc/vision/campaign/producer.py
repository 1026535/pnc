"""Supported Campaign producer composition root."""

from __future__ import annotations

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.campaign_ocr_regions import CAMPAIGN_REFERENCE_SIZE
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from .board import _map_rows
from .chapters import _chapter_rows
from .stage import _stage_detail


def build_campaign_additions(
    *, image: Image.Image, screen_type: ScreenType, ocr_context: ObservationOcrContext,
    template_matcher: OpenCvTemplateMatcher | None,
    challenge_bounds: Bounds | None = None,
) -> ObservationAdditions:
    """Publish typed Campaign rows and surface facts for an accepted screen."""

    if screen_type == ScreenType.PNC_CAMPAIGN_STAGE:
        return ObservationAdditions(
            campaign_stage=_stage_detail(
                image=image, ocr_context=ocr_context, challenge_bounds=challenge_bounds
            )
        )
    if screen_type not in {ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER}:
        return ObservationAdditions()
    if template_matcher is None:
        return ObservationAdditions()
    frame = template_matcher.prepare_frame(image, reference_size=CAMPAIGN_REFERENCE_SIZE)
    if frame is None:
        return ObservationAdditions()
    if screen_type == ScreenType.PNC_CAMPAIGN_MAP:
        rows = _map_rows(image=image, frame=frame, ocr_context=ocr_context, matcher=template_matcher)
        return ObservationAdditions(list_entries=rows)
    rows, chapter = _chapter_rows(image=image, frame=frame, ocr_context=ocr_context)
    return ObservationAdditions(list_entries=rows, campaign_chapter=chapter)
