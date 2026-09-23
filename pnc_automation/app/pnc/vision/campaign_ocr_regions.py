"""Reviewed OCR regions for Campaign screen content."""

from __future__ import annotations

from pnc_automation.core.vision.image.models import Bounds


CAMPAIGN_REFERENCE_SIZE: tuple[int, int] = (540, 960)
"""Reference viewport used to measure the reviewed Campaign regions."""

CAMPAIGN_CHAPTER_TITLE_REGION = Bounds(x=205, y=38, width=325, height=60)
"""Measured chapter title header region on the Campaign chapter screen."""

CAMPAIGN_STAGE_TITLE_REGION = Bounds(x=120, y=201, width=300, height=49)
"""Measured stage-detail title bar; matches the reviewed title anchor search region."""

CAMPAIGN_STAGE_ACTION_POINTS_REGION = Bounds(x=368, y=585, width=96, height=36)
"""Measured ``power/maxPower`` gauge, excluding the adjacent add-AP icon."""


def campaign_stage_challenge_cost_bounds(challenge: Bounds) -> Bounds:
    """Return the numeral strip inside the measured Challenge control.

    Captured stages place Challenge either centrally or to the left of Blitz.
    The strip follows the matched 184x54 control rather than a fixed screen point.
    """
    return Bounds(
        x=challenge.x + round(challenge.width * 60 / 184),
        y=challenge.y,
        width=max(1, round(challenge.width * 68 / 184)),
        height=max(1, round(challenge.height * 24 / 54)),
    )


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
