"""Reviewed OCR regions for Campaign screen content."""

from __future__ import annotations

from pnc_automation.core.vision.image.models import Bounds


CAMPAIGN_REFERENCE_SIZE: tuple[int, int] = (540, 960)
"""Reference viewport used to measure the reviewed Campaign regions."""

CAMPAIGN_CHAPTER_TITLE_REGION = Bounds(x=205, y=38, width=325, height=60)
"""Measured chapter title header region on the Campaign chapter screen."""


def scale_campaign_bounds(bounds: Bounds, image_size: tuple[int, int]) -> Bounds:
    """Scale reviewed Campaign geometry from the reference viewport."""

    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Campaign OCR region scaling requires positive image dimensions.")
    reference_width, reference_height = CAMPAIGN_REFERENCE_SIZE
    return Bounds(
        x=round(bounds.x * image_width / reference_width),
        y=round(bounds.y * image_height / reference_height),
        width=max(1, round(bounds.width * image_width / reference_width)),
        height=max(1, round(bounds.height * image_height / reference_height)),
    )
