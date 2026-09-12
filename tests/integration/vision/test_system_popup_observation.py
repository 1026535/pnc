"""System popup observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_popup_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class SystemPopupObservationTests(unittest.TestCase):
    """Proves system popup observation."""

    def test_observation_builder_classifies_bluestacks_android_home_from_pnc_label(self) -> None:
        """Replays BlueStacks home when template matching misses but OCR proves the P&C launcher label."""

        fixture_path = require_local_fixture_artifact(
            "bluestacks_android_home_pnc_label_live_20260617",
            default_repo_relative_path="tests/data/world_map/bluestacks_android_home_pnc_label_live_20260617.png",
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_android_home",
                label="bluestacks_android_home",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Search for games & apps", x=125, y=56, width=113, height=16),
                            _ocr_line("Store", x=86, y=215, width=44, height=20),
                            _ocr_line("System apps", x=221, y=216, width=98, height=20),
                            _ocr_line("Puzzles & Conquest", x=359, y=217, width=146, height=17),
                        )
                    )
                )

            observation = builder.build(screenshot, request=ObservationRequest.full_runtime_default())

            self.assertEqual(observation.screen_type, ScreenType.ANDROID_HOME)
            launcher = observation.require(UiElementId.ANDROID_HOME_PNC_ICON)
            self.assertEqual(launcher.extracted_text, "Puzzles & Conquest")

    def test_observation_builder_classifies_research_queue_overlay_as_blocking_popup(self) -> None:
        """Recognizes the in-game research queue overlay as a popup so bootstrap stays inside the game."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_research_queue_popup",
                label="research_queue_popup",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Research Queue", x=288, y=427, width=328, height=45),
                            _ocr_line("1st Research Queue", x=213, y=544, width=265, height=30),
                            _ocr_line("Go", x=700, y=573, width=50, height=35),
                            _ocr_line("Idle", x=208, y=596, width=58, height=33),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)

    def test_observation_builder_classifies_google_play_games_profile_prompt_as_blocking_popup(self) -> None:
        """Treats the external Google Play Games profile prompt as a recoverable popup instead of bootstrap unknown."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_google_play_games_popup",
                label="google_play_games_popup",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Google Play Games", x=369, y=440, width=214, height=27),
                            _ocr_line("Create a Play Games profile", x=233, y=960, width=424, height=30),
                            _ocr_line("No profile", x=154, y=1097, width=109, height=30),
                            _ocr_line("Cancel", x=59, y=1529, width=78, height=24),
                            _ocr_line("Next", x=782, y=1530, width=56, height=22),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_alliance_invitation_fixture_requires_alliance_body_before_exposing_cancel(self) -> None:
        """The tracked invitation artifact authorizes Cancel only with its body/title evidence."""

        fixture = Path("tests/data/screen_recognition/alliance_invitation.png")
        with Image.open(fixture) as image:
            alliance_lines = (
                _ocr_line("Join our alliance and get strong together!", x=194, y=390, width=310, height=28),
                _ocr_line("(ATN) FarmerPhilly", x=325, y=470, width=180, height=24),
                _ocr_line("Cancel", x=197, y=526, width=130, height=40),
                _ocr_line("Join/Apply", x=352, y=526, width=130, height=40),
            )
            alliance_additions = _build_popup_additions(
                image=image,
                lines=alliance_lines,
                anchors=TextAnchorDetector().detect(alliance_lines),
            )
            self.assertIsNotNone(alliance_additions)
            self.assertEqual(alliance_additions.popup_overlay.layout_id, "alliance_invitation_footer")
            self.assertEqual(alliance_additions.popup_overlay.candidates[0].control_kind, PopupControlKind.CANCEL)

            non_alliance_lines = (
                _ocr_line("Optional feature available", x=194, y=390, width=310, height=28),
                _ocr_line("Cancel", x=197, y=526, width=130, height=40),
                _ocr_line("Join/Apply", x=352, y=526, width=130, height=40),
            )
            generic_additions = _build_popup_additions(
                image=image,
                lines=non_alliance_lines,
                anchors=TextAnchorDetector().detect(non_alliance_lines),
            )
            self.assertIsNone(generic_additions)

            task_owned_additions = _build_popup_additions(
                image=image,
                lines=alliance_lines,
                anchors=TextAnchorDetector().detect(alliance_lines),
                task_owned=True,
            )
            self.assertIsNone(task_owned_additions)
