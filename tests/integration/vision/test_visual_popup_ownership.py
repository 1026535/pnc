"""Visual popup ownership: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _bright_popup_close_pixels,
    _build_popup_additions,
    _is_bright_popup_close_pixel,
    _vertical_surface_edge_contrast,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class VisualPopupOwnershipTests(unittest.TestCase):
    """Proves visual popup ownership."""

    def test_vectorized_bright_mask_preserves_predicate_and_global_coordinates(self) -> None:
        """Keeps the bright white/gold predicate and maps cropped pixels globally."""

        image = Image.new("RGB", (20, 20), (0, 0, 0))
        pixels = {
            (7, 8): (255, 255, 255),
            (6, 9): (190, 160, 130),
            (5, 7): (190, 160, 129),
            (15, 15): (255, 255, 255),
        }
        for point, pixel in pixels.items():
            image.putpixel(point, pixel)

        expected = {
            point
            for point, pixel in pixels.items()
            if 5 <= point[0] < 15 and 4 <= point[1] < 14 and _is_bright_popup_close_pixel(pixel)
        }
        self.assertEqual(
            _bright_popup_close_pixels(rgb_image=image, left=5, top=4, right=15, bottom=14),
            expected,
        )

    def test_vectorized_surface_edge_contrast_preserves_mean_difference(self) -> None:
        """Preserves the RGB-sum edge arithmetic for both scan directions."""

        image = Image.new("RGB", (20, 12), (0, 0, 0))
        for y in range(2, 10):
            image.putpixel((5, y), (10, 10, 10))
            image.putpixel((8, y), (10, 10, 10))

        self.assertEqual(
            _vertical_surface_edge_contrast(
                rgb_image=image,
                start=5,
                end=8,
                top=2,
                bottom=10,
                direction=1,
            ),
            10.0,
        )
        self.assertEqual(
            _vertical_surface_edge_contrast(
                rgb_image=image,
                start=8,
                end=11,
                top=2,
                bottom=10,
                direction=-1,
            ),
            10.0,
        )

    def test_observation_builder_classifies_generic_upper_right_popup_x_without_popup_ocr(self) -> None:
        """Recognizes the shared bright popup X when the one global OCR pass has no popup lines."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.rectangle((25, 250, 860, 1000), fill=(25, 33, 50), outline=(65, 82, 110), width=4)
            drawing.line((794, 302, 832, 340), fill=(255, 247, 218), width=8)
            drawing.line((832, 302, 794, 340), fill=(255, 247, 218), width=8)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="generic_visual_popup",
                label="upper_right_close_x",
            )
            ocr_service = _RecordingOcrService(lines=())
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
            ocr_service=ocr_service,
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
            self.assertEqual(ocr_service.read_result_calls, 1)

    def test_observation_builder_accepts_shifted_x_owned_by_modal_text_cluster(self) -> None:
        """Finds a measured X after a compact message and primary action prove modal ownership."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            drawing = ImageDraw.Draw(image)
            drawing.line((700, 302, 738, 340), fill=(255, 247, 218), width=8)
            drawing.line((738, 302, 700, 340), fill=(255, 247, 218), width=8)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="generic_visual_popup",
                label="owned_shifted_close_x",
            )
            ocr_service = _FakeOcrService(
                lines=(
                    _ocr_line("Special opportunity", x=300, y=420, width=280, height=34),
                    _ocr_line("Claim", x=500, y=900, width=150, height=38),
                )
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=ocr_service,
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertEqual(observation.popup_overlay.layout_id, "generic_modal_close_x")
            close_button = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            self.assertEqual(close_button.action_point, (720, 321))

    def test_observation_builder_rejects_x_outside_proven_modal_edges(self) -> None:
        """A bright cross outside the OCR-owned modal is not a dismiss control."""

        image = Image.new("RGB", (900, 1600), (15, 28, 68))
        drawing = ImageDraw.Draw(image)
        drawing.line((54, 302, 92, 340), fill=(255, 247, 218), width=8)
        drawing.line((92, 302, 54, 340), fill=(255, 247, 218), width=8)
        additions = _build_popup_additions(
            image=image,
            lines=(
                _ocr_line("Special opportunity", x=250, y=420, width=300, height=34),
                _ocr_line("Claim", x=360, y=900, width=150, height=38),
            ),
            anchors=(),
        )
        self.assertIsNone(additions)
