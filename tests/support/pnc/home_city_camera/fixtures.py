"""Shared home camera fixtures doubles and fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.vision.home_city_camera import (
    HOME_CITY_CAMERA_REFERENCE_SIZE,
    HomeCityCameraLocalizer,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT


_SCREEN_RECOGNITION = TEST_DATA_ROOT / "screen_recognition"


_CAMERA_FIXTURES = TEST_DATA_ROOT / "home_city_camera"


def _fixture(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _localizer() -> HomeCityCameraLocalizer:
    return HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())


def _frame_ref(label: str) -> FrameRef:
    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )


def _zoomed_fixture(image: Image.Image, zoom: float) -> Image.Image:
    """Re-renders a fixture's scene content at ``zoom`` around the viewport center.

    Scaling the content inside the same reference-size canvas mimics a game
    zoom change: scene positions become ``zoom * s + (1 - zoom) * center``
    while the matcher is exercised on genuinely resampled pixels.
    """

    base = image.resize(HOME_CITY_CAMERA_REFERENCE_SIZE, Image.Resampling.LANCZOS)
    scaled_size = (
        round(HOME_CITY_CAMERA_REFERENCE_SIZE[0] * zoom),
        round(HOME_CITY_CAMERA_REFERENCE_SIZE[1] * zoom),
    )
    scaled = base.resize(scaled_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", HOME_CITY_CAMERA_REFERENCE_SIZE, (0, 0, 0))
    canvas.paste(
        scaled,
        (
            (HOME_CITY_CAMERA_REFERENCE_SIZE[0] - scaled_size[0]) // 2,
            (HOME_CITY_CAMERA_REFERENCE_SIZE[1] - scaled_size[1]) // 2,
        ),
    )
    return canvas
