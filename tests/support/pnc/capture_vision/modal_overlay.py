"""Measured modal overlays composed from a reviewed captured frame.

The popup guard accepts a required-update OCR message only when the current
image also contains the panel edges and blue Confirm surface. These helpers
keep that evidence in one test boundary while retaining the reviewed
background fixture around the modal.
"""

from __future__ import annotations

from PIL import Image

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

from tests.support.paths import TEST_DATA_ROOT


_UPDATE_FIXTURE = TEST_DATA_ROOT / "screen_recognition" / "update_over_bag.png"
_REFERENCE_SIZE = (540, 960)
# Keep the panel's side edges in the composite. The slightly wider measured
# crop is necessary because the guard samples both edges independently.
UPDATE_MODAL_PANEL_BOUNDS = Bounds(18, 286, 505, 314)
UPDATE_MESSAGE_BOUNDS = Bounds(58, 380, 420, 28)
UPDATE_CONFIRM_BOUNDS = Bounds(221, 531, 90, 27)


def _scale_bounds(bounds: Bounds, image_size: tuple[int, int]) -> Bounds:
    """Scale reference-capture coordinates to a reviewed viewport."""

    width, height = image_size
    return Bounds(
        round(bounds.x * width / _REFERENCE_SIZE[0]),
        round(bounds.y * height / _REFERENCE_SIZE[1]),
        round(bounds.width * width / _REFERENCE_SIZE[0]),
        round(bounds.height * height / _REFERENCE_SIZE[1]),
    )


def update_modal_lines(image_size: tuple[int, int]) -> tuple[OcrLine, ...]:
    """Return exact update-message OCR lines scaled to ``image_size``."""

    return (
        OcrLine(
            "New version detected. Tap Confirm to update.",
            _scale_bounds(UPDATE_MESSAGE_BOUNDS, image_size),
            1.0,
        ),
        OcrLine("Confirm", _scale_bounds(UPDATE_CONFIRM_BOUNDS, image_size), 1.0),
    )


def with_update_modal(background: Image.Image) -> Image.Image:
    """Compose the reviewed update panel onto ``background`` at viewport scale.

    The copied rectangle is the reviewed panel surface from the actual
    ``update_over_bag`` frame. Surrounding pixels remain from the supplied
    background so tests continue to prove that its controls and rows are
    suppressed by foreground ownership.
    """

    with Image.open(_UPDATE_FIXTURE) as source:
        overlay = source.convert("RGB").resize(background.size, Image.Resampling.LANCZOS)
    panel_bounds = _scale_bounds(UPDATE_MODAL_PANEL_BOUNDS, background.size)
    panel_box = (
        panel_bounds.x,
        panel_bounds.y,
        panel_bounds.x + panel_bounds.width,
        panel_bounds.y + panel_bounds.height,
    )
    composed = background.convert("RGB").copy()
    composed.paste(overlay.crop(panel_box), panel_box)
    return composed


__all__ = [
    "UPDATE_CONFIRM_BOUNDS",
    "UPDATE_MESSAGE_BOUNDS",
    "UPDATE_MODAL_PANEL_BOUNDS",
    "update_modal_lines",
    "with_update_modal",
]
