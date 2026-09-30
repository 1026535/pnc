"""Bounded Campaign stage-detail fact readers.

Stage-detail facts come from reviewed bounded regions only: the ``[Ch-St]``
title bar, the ``power/maxPower`` action-point gauge, and the Challenge cost
numeral. A region the OCR backend cannot read stays ``None``; no mode,
availability, or destination is inferred from the Challenge control.
"""

from __future__ import annotations

import re
from PIL import Image

from pnc_automation.app.pnc.domain.campaign import CampaignStageDetail
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_REFERENCE_SIZE,
    CAMPAIGN_STAGE_ACTION_POINTS_REGION,
    CAMPAIGN_STAGE_CENTER_ACTION_POINTS_REGION,
    CAMPAIGN_STAGE_TITLE_REGION,
    campaign_stage_challenge_cost_bounds,
    scale_campaign_bounds,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
    OcrResult,
)

from .constants import _NUMERIC_CONFIDENCE_MIN

# Stage-detail title format rendered by the client as "[{chapterNo}-{passNo}]
# {chapterName}". The opening bracket may arrive as a bracket-like glyph.
_STAGE_TITLE_PATTERN = re.compile(r"[\[\(\{lI|]?\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*[\]\)\}]?\s*(.*)")
_STAGE_GAUGE_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
_DIGITS_PATTERN = re.compile(r"\d+")


def _stage_detail(
    *, image: Image.Image, ocr_context: ObservationOcrContext,
    challenge_bounds: Bounds | None,
) -> CampaignStageDetail | None:
    """Current-frame stage-detail facts read from reviewed bounded regions."""

    result = ocr_context.read_result(
        image,
        scale_campaign_bounds(CAMPAIGN_STAGE_TITLE_REGION, image.size),
        purpose=OcrReadPurpose.CONTENT,
        detail="campaign_stage_title",
        required_fact="campaign_stage_detail",
    )
    title = _stage_title_text(result)
    chapter_number, stage_number, name = _parse_stage_title(title or None)
    action_points, max_action_points = _stage_gauge_values(
        image=image,
        ocr_context=ocr_context,
    )
    challenge_cost = _stage_cost_value(
        image=image, ocr_context=ocr_context, challenge_bounds=challenge_bounds
    )
    if (
        chapter_number is None
        and stage_number is None
        and name is None
        and action_points is None
        and max_action_points is None
        and challenge_cost is None
    ):
        return None
    return CampaignStageDetail(
        chapter_number=chapter_number,
        stage_number=stage_number,
        name=name,
        action_points=action_points,
        max_action_points=max_action_points,
        challenge_cost=challenge_cost,
    )


def _stage_title_text(result: OcrResult) -> str:
    """Read each visual title row left to right despite OCR top-edge jitter."""

    lines = [
        line for line in result.lines
        if line.text.strip() and line.confidence >= _NUMERIC_CONFIDENCE_MIN
    ]
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda item: (item.bounds.y, item.bounds.x)):
        for row in rows:
            if any(
                2 * (min(line.bounds.y + line.bounds.height,
                         other.bounds.y + other.bounds.height)
                     - max(line.bounds.y, other.bounds.y))
                >= min(line.bounds.height, other.bounds.height)
                for other in row
            ):
                row.append(line)
                break
        else:
            rows.append([line])
    return " ".join(
        line.text.strip()
        for row in rows
        for line in sorted(row, key=lambda item: item.bounds.x)
    )


def _parse_stage_title(text: str | None) -> tuple[int | None, int | None, str | None]:
    """``[10-3] Grandia Ruins`` into observed ordinals plus the stage name."""

    if text is None:
        return None, None, None
    # Conflicting OCR candidates must not turn the second identity into a name.
    ordinals = set(re.findall(r"(\d{1,2})\s*[-–—]\s*(\d{1,2})", text))
    if len(ordinals) != 1:
        return None, None, None
    match = _STAGE_TITLE_PATTERN.match(text.strip())
    if match is None:
        return None, None, None
    chapter_number, stage_number = int(match.group(1)), int(match.group(2))
    if chapter_number <= 0 or stage_number <= 0:
        return None, None, None
    name = match.group(3).strip()
    return chapter_number, stage_number, name or None


def _stage_gauge_values(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
) -> tuple[int | None, int | None]:
    """The ``power/maxPower`` pair only when one credible read resolves."""

    # The stage footer has two observed layouts. Keep each read on its numeric
    # line; a broad union would include unrelated controls and break line OCR.
    for region in (
        CAMPAIGN_STAGE_ACTION_POINTS_REGION,
        CAMPAIGN_STAGE_CENTER_ACTION_POINTS_REGION,
    ):
        result = _read_stage_numeric_strip(
            image=image,
            ocr_context=ocr_context,
            region=scale_campaign_bounds(region, image.size),
            detail="campaign_stage_action_points",
        )
        pairs = {
            (int(match.group(1)), int(match.group(2)))
            for line in result.lines
            if line.confidence >= _NUMERIC_CONFIDENCE_MIN
            for match in _STAGE_GAUGE_PATTERN.finditer(line.text)
            if int(match.group(2)) > 0
        }
        if len(pairs) > 1:
            return None, None
        if pairs:
            return next(iter(pairs))
    return None, None


def _stage_cost_value(
    *, image: Image.Image, ocr_context: ObservationOcrContext,
    challenge_bounds: Bounds | None,
) -> int | None:
    """The Challenge cost only when bounded reads prove one positive numeral."""

    if challenge_bounds is None:
        return None
    result = _read_stage_numeric_strip(
        image=image,
        ocr_context=ocr_context,
        region=campaign_stage_challenge_cost_bounds(challenge_bounds),
        detail="campaign_stage_challenge_cost",
    )
    values = {
        value
        for line in result.lines
        if line.confidence >= _NUMERIC_CONFIDENCE_MIN
        for match in _DIGITS_PATTERN.finditer(line.text)
        if (value := int(match.group(0))) > 0
    }
    if len(values) != 1:
        return None
    return next(iter(values))


def _read_stage_numeric_strip(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    region: Bounds,
    detail: str,
) -> OcrResult:
    """Keep native-size numeric crops on the already qualified single-line OCR path.

    The native900x1600 gauge was split into overlapping ``126/`` and ``5/120``
    detections, while its Challenge cost produced no detection. Normalize only
    these larger crops; the reference-size reads already have captured proof.
    The canonical context preserves the original region and frame provenance.
    """
    if image.height <= CAMPAIGN_REFERENCE_SIZE[1]:
        return ocr_context.read_result(
            image, region, purpose=OcrReadPurpose.CONTENT, detail=detail,
            required_fact="campaign_stage_detail",
        )
    result = ocr_context.read_preprocessed_result(
        image, region, preprocessing_id="campaign_stage_numeric_line_28px_v1",
        prepare=_prepare_stage_numeric_strip, purpose=OcrReadPurpose.CONTENT,
        detail=detail, required_fact="campaign_stage_detail",
    )
    assert result is not None
    return result


def _prepare_stage_numeric_strip(image: Image.Image, region: Bounds) -> Image.Image:
    """Resize one bounded numeric line without including neighboring controls."""
    crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height))
    return crop.resize(
        (max(1, round(crop.width * 28 / crop.height)), 28), Image.Resampling.LANCZOS
    )
