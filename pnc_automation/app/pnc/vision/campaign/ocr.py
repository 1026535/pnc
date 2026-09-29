"""Bounded Campaign OCR readers and text parsing."""

from __future__ import annotations

from PIL import Image

from pnc_automation.app.pnc.domain.campaign import CampaignChapterIdentity
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_CHAPTER_TITLE_REGION,
    scale_campaign_bounds,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose

from .constants import (
    _CHAPTER_TITLE_PATTERN, _DISC_CORE_INSET_FRACTION, _LOCK_LABEL_PATTERN,
    _MAP_DISC_DIGIT_MARGIN, _NUMBER_PATTERN, _NUMERIC_CONFIDENCE_MIN,
)
from .geometry import _inset_bounds

def _chapter_identity(*, image: Image.Image, ocr_context: ObservationOcrContext) -> CampaignChapterIdentity | None:
    """The observed ``Ch.N`` title for the accepted chapter-path surface."""

    region = scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, image.size)
    result = ocr_context.read_result(
        image,
        region,
        purpose=OcrReadPurpose.CONTENT,
        detail="campaign_chapter_title",
        required_fact="campaign_chapter_identity",
    )
    lines = sorted(result.lines, key=lambda line: (line.bounds.y, line.bounds.x))
    joined = " ".join(line.text for line in lines).strip()
    match = _CHAPTER_TITLE_PATTERN.search(joined)
    if match is None:
        return None
    chapter_number = int(match.group(1))
    name = _CHAPTER_TITLE_PATTERN.sub("", joined, count=1).strip(" .-")
    if name.startswith(str(chapter_number)) and (
        len(name) == len(str(chapter_number)) or name[len(str(chapter_number))] in " .-"
    ):
        name = name[len(str(chapter_number)):].strip(" .-")
    return CampaignChapterIdentity(
        chapter_number=chapter_number,
        name=name or None,
    )

def _read_disc_number(
    *,
    image: Image.Image,
    disc_ref: Bounds,
    ocr_context: ObservationOcrContext,
    required_fact: str,
) -> int | None:
    """A badge numeral only when bounded reads prove exactly one positive value.

    The ordinary inset read runs first; the first credible singleton
    returns immediately, while conflicting values within one read abstain.
    One narrower inner-core retry runs only when the ordinary read resolves
    no credible numeral, because ring decoration can leak punctuation into
    the raw disc read.
    """

    candidates = _disc_number_candidates(
        image=image,
        ocr_context=ocr_context,
        required_fact=required_fact,
        detail="campaign_badge_number",
        region=_inset_bounds(disc_ref, _MAP_DISC_DIGIT_MARGIN),
    )
    if len(candidates) > 1:
        return None
    if not candidates:
        inset = max(
            1,
            round(min(disc_ref.width, disc_ref.height) * _DISC_CORE_INSET_FRACTION),
        )
        candidates = _disc_number_candidates(
            image=image,
            ocr_context=ocr_context,
            required_fact=required_fact,
            detail="campaign_badge_number_core",
            region=_inset_bounds(disc_ref, inset),
        )
    if len(candidates) != 1:
        return None
    return next(iter(candidates))

def _disc_number_candidates(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    required_fact: str,
    detail: str,
    region: Bounds,
) -> set[int]:
    """Credible positive numerals read inside one bounded disc region."""

    result = ocr_context.read_result(
        image,
        scale_campaign_bounds(region, image.size),
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
        required_fact=required_fact,
    )
    values: set[int] = set()
    for line in result.lines:
        match = _NUMBER_PATTERN.match(line.text.strip())
        if match is None or line.confidence < _NUMERIC_CONFIDENCE_MIN:
            continue
        value = int(match.group(1))
        if value > 0:
            values.add(value)
    return values

def _read_region_text(
    *,
    image: Image.Image,
    region: Bounds,
    ocr_context: ObservationOcrContext,
    detail: str,
) -> str | None:
    """One bounded text read; empty results stay ``None`` rather than guessed."""

    result = ocr_context.read_result(
        image,
        region,
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
    )
    text = " ".join(
        line.text.strip()
        for line in sorted(result.lines, key=lambda line: (line.bounds.y, line.bounds.x))
        if line.text.strip()
    )
    return text or None

def _parse_lock_label(text: str | None) -> tuple[int | None, str | None]:
    """``7 Mt. Blade`` or ``8Otto Icefield`` into an observed number and name."""

    if text is None:
        return None, None
    match = _LOCK_LABEL_PATTERN.match(text.strip())
    if match is None:
        return None, text.strip() or None
    return int(match.group(1)), (match.group(2) or None)
