"""Build queue observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class BuildQueueObservationTests(unittest.TestCase):
    """Proves build queue observation."""

    def test_observation_builder_classifies_build_queue_and_extracts_active_entry(self) -> None:
        """Recognizes the build queue overlay and exposes its active upgrading row for task verification."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_build_queue",
                label="build_queue",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build Queue", x=315, y=64, width=256, height=36),
                            _ocr_line("Upgrading: Wall", x=115, y=250, width=250, height=34),
                            _ocr_line("00:48:16", x=262, y=303, width=128, height=28),
                            _ocr_line("Speedup", x=673, y=244, width=154, height=40),
                            _ocr_line("2nd Build Queue", x=101, y=420, width=278, height=32),
                            _ocr_line("Idle", x=113, y=470, width=68, height=26),
                            _ocr_line("Go", x=754, y=468, width=52, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILD_QUEUE)
            active_entries = observation.entries(ListEntryKind.BUILDING)
            self.assertEqual(len(active_entries), 1)
            self.assertEqual(active_entries[0].title_text, "Wall")
            self.assertEqual(active_entries[0].timer_text, "00:48:16")
            self.assertEqual(active_entries[0].metadata["queue_state"], "upgrading")

    def test_observation_builder_classifies_centered_idle_build_queue(self) -> None:
        """Recognizes the live centered queue overlay when its first queue is idle and second queue inactive."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="testing_build_queue",
                label="centered_idle_build_queue",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build Queue", x=327, y=428, width=249, height=44),
                            _ocr_line("1st Build Queue", x=212, y=541, width=216, height=32),
                            _ocr_line("Idle", x=209, y=596, width=57, height=33),
                            _ocr_line("2nd Build Queue", x=213, y=703, width=225, height=30),
                            _ocr_line("Activate", x=662, y=734, width=125, height=31),
                            _ocr_line("Inactive", x=211, y=758, width=110, height=30),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILD_QUEUE)
            self.assertEqual(observation.entries(ListEntryKind.BUILDING), ())
