"""Menu observation: semantic parsers under explicit screen decisions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationAdditions,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.bag_items import BagItemContentProducer
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_alliance_join_additions,
    _build_bag_additions,
    _build_daily_to_do_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import (
    _FakeScreenshotSession,
    make_captured_frame,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


def _build_bag_semantics(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
    """Run the Bag parser with a frame-bound fake OCR context."""

    ocr_context = ObservationOcrContext(
        image,
        _FakeOcrService(lines=lines),
        make_captured_frame(b"").frame_ref,
        "menu-observation-test",
    )
    ocr_context.require_bounded_regions()
    additions = _build_bag_additions(
        image=image,
        ocr_context=ocr_context,
        selector_registry=build_default_selector_registry(),
        bag_item_producer=BagItemContentProducer(),
    )
    return additions or ObservationAdditions()


class MenuObservationTests(unittest.TestCase):
    """Proves menu semantic parsing and classifier abstention."""

    def test_explicit_screen_decision_publishes_bag_chrome(self) -> None:
        """Publishes Bag identity from the accepted chrome while withholding an unproved Use control."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Bag", x=177, y=16, width=100, height=64),
                _ocr_line("Bag", x=184, y=123, width=82, height=52),
                _ocr_line("Diamond Shop", x=545, y=125, width=259, height=44),
                _ocr_line("Resource", x=22, y=220, width=139, height=35),
                _ocr_line("Use", x=725, y=327, width=64, height=37),
            ),
            accepted_screen=ScreenType.PNC_BAG,
            semantic_parser=_build_bag_semantics,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_BAG)
        self.assertTrue(observation.has(UiElementId.PNC_BAG_MAIN_TAB_BAG))
        self.assertFalse(observation.has(UiElementId.PNC_BAG_USE_BUTTON))

    def test_explicit_screen_decision_publishes_alliance_join_landing(self) -> None:
        """Publishes the accepted join-alliance landing semantics."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Join Alliance", x=300, y=627, width=305, height=49),
                _ocr_line("Join", x=642, y=1198, width=78, height=39),
                _ocr_line("Create Alliance", x=131, y=1218, width=259, height=36),
            ),
            accepted_screen=ScreenType.PNC_ALLIANCE_JOIN,
            semantic_parser=lambda image, lines: _build_alliance_join_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_JOIN)

    def test_explicit_screen_decision_publishes_daily_to_do_chrome(self) -> None:
        """Publishes the accepted Daily To-Do overlay and its canonical header."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Daily To-Do", x=110, y=112, width=160, height=28),
                _ocr_line("Camp", x=17, y=180, width=55, height=21),
                _ocr_line("Daily Quest", x=21, y=463, width=95, height=22),
                _ocr_line("Go", x=339, y=215, width=37, height=20),
                _ocr_line("Go", x=339, y=293, width=37, height=20),
                _ocr_line("Tap to close", x=131, y=859, width=112, height=22),
            ),
            accepted_screen=ScreenType.PNC_DAILY_TO_DO,
            image_size=(540, 960),
            semantic_parser=lambda image, lines: _build_daily_to_do_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_DAILY_TO_DO)
        self.assertTrue(observation.has(UiElementId.PNC_DAILY_TO_DO_HEADER))

    def test_screen_classifier_does_not_read_bag_body_without_resource_chrome(self) -> None:
        """Bag identity without the Resource subtab must not authorize body parsing."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="bag_missing_resource_chrome",
                label="bag_missing_resource_chrome",
            )
            ocr_service = _RecordingOcrService(
                lines=(_ocr_line("Bag", x=177, y=16, width=100, height=64),)
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=ocr_service,
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertEqual(0, ocr_service.read_text_calls)
            self.assertFalse(observation.list_entries)


if __name__ == "__main__":
    unittest.main()
