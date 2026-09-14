"""Measured modal overlays composed from a reviewed captured frame.

These helpers compose the reviewed panel pixels while deterministic OCR lines
remain supplied by each test. Foreground ownership and background-control
suppression therefore remain separate, explicit test contracts.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

from tests.support.paths import TEST_DATA_ROOT


_UPDATE_FIXTURE = TEST_DATA_ROOT / "screen_recognition" / "update_over_bag.png"
_REFERENCE_SIZE = (540, 960)

# The crop contains the complete foreground panel, including both side edges,
# top/bottom decorative edges, and the blue Confirm button.  Pixels outside
# this rectangle remain owned by the reviewed background fixture.
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


def update_modal_ocr_lines(image_size: tuple[int, int]) -> tuple[OcrLine, ...]:
    """Return exact update-message OCR lines scaled to ``image_size``."""

    return (
        OcrLine(
            "New version detected. Tap Confirm to update.",
            _scale_bounds(UPDATE_MESSAGE_BOUNDS, image_size),
            1.0,
        ),
        OcrLine("Confirm", _scale_bounds(UPDATE_CONFIRM_BOUNDS, image_size), 1.0),
    )


def compose_update_modal(background: Image.Image, *, source_path: Path = _UPDATE_FIXTURE) -> Image.Image:
    """Compose the reviewed update panel onto ``background`` at viewport scale.

    Only the measured modal panel is copied. Surrounding pixels remain from
    the supplied background; suppression tests must separately establish which
    background anchors and controls survive this occlusion.
    """

    with Image.open(source_path) as source:
        panel = source.convert("RGB").crop(
            (
                UPDATE_MODAL_PANEL_BOUNDS.x,
                UPDATE_MODAL_PANEL_BOUNDS.y,
                UPDATE_MODAL_PANEL_BOUNDS.x + UPDATE_MODAL_PANEL_BOUNDS.width,
                UPDATE_MODAL_PANEL_BOUNDS.y + UPDATE_MODAL_PANEL_BOUNDS.height,
            )
        )

    target_panel = _scale_bounds(UPDATE_MODAL_PANEL_BOUNDS, background.size)
    target_size = (target_panel.width, target_panel.height)
    if target_size != panel.size:
        panel = panel.resize(target_size, Image.Resampling.LANCZOS)
    composed = background.convert("RGB").copy()
    composed.paste(panel, (target_panel.x, target_panel.y))
    return composed


__all__ = [
    "UPDATE_CONFIRM_BOUNDS",
    "UPDATE_MESSAGE_BOUNDS",
    "UPDATE_MODAL_PANEL_BOUNDS",
    "compose_update_modal",
    "update_modal_ocr_lines",
]
