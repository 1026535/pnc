"""Observation artifact emission: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ObservationDebugArtifactCollector,
    ObservationService,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.observations import make_observation
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.sequenced_observation_builder import (
    _SequencedObservationBuilder,
)
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ObservationArtifactEmissionTests(unittest.TestCase):
    """Proves observation artifact emission."""

    def test_observation_service_skips_routine_artifact_persistence_in_light_mode(self) -> None:
        """Leaves routine observations ephemeral in light mode so idle scheduler runs do not flood artifacts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[make_observation(ScreenType.PNC_HOME_CITY)]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="light_mode_test",
                mode=ObservationMode.LIGHT,
            )

            observation = service.observe("light_scan")

            self.assertIsNone(observation.artifact_path)
            self.assertFalse(any((root / "artifacts").rglob("*.png")))

    def test_observation_service_honors_explicit_artifact_requests_in_light_mode(self) -> None:
        """Still persists explicitly requested archive-grade captures while the runtime stays in light mode."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[make_observation(ScreenType.PNC_MAIL_THREAD)]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="light_mode_test",
                mode=ObservationMode.LIGHT,
            )

            capture = service.capture_observation("mail_thread_scan", request=ObservationRequest.mail_thread_observation())

            self.assertIsNotNone(capture.screenshot.artifact_path)
            self.assertTrue(any((root / "artifacts").rglob("*.png")))

    def test_observation_service_persists_unidentified_ocr_sidecars_only_in_debug_mode(self) -> None:
        """Writes a debug-only OCR sidecar for unmatched lines without changing normal light-mode behavior."""

        for mode, persist_request, expect_artifact, expect_sidecar in (
            (ObservationMode.DEBUG, None, True, True),
            (ObservationMode.LIGHT, None, False, False),
            (ObservationMode.LIGHT, ObservationRequest.mail_thread_observation(), True, False),
        ):
            with self.subTest(mode=mode, explicit_request=persist_request is not None):
                root = Path.cwd() / ".tmp_test_artifacts" / f"debug_sidecar_{mode.value}_{persist_request is not None}"
                if root.exists():
                    shutil.rmtree(root)
                root.mkdir(parents=True, exist_ok=True)
                try:
                    screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                    payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
                    registry = build_default_selector_registry()
                    ocr_service = _FakeOcrService(
                        lines=(
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                            _ocr_line("My Territory", x=210, y=505, width=180, height=24),
                            _ocr_line("Mystery Badge", x=640, y=820, width=140, height=24),
                            _ocr_line("Home", x=50, y=1564, width=90, height=24),
                            _ocr_line("Hero", x=215, y=1564, width=90, height=24),
                            _ocr_line("Quest", x=330, y=1569, width=90, height=24),
                            _ocr_line("Mail", x=570, y=1568, width=90, height=24),
                            _ocr_line("Alliance", x=665, y=1566, width=120, height=24),
                            _ocr_line("More", x=794, y=1567, width=90, height=24),
                        )
                    )
                    builder = ObservationBuilder(
                        selector_registry=registry,
                        selector_engine=ImageSelectorEngine(
                            template_matcher=OpenCvTemplateMatcher(),

                        ),
                        screen_classifier=ScreenClassifier(),
                        enricher=PncObservationEnricher(

                            selector_registry=registry,
                        ),
                        debug_artifact_collector=ObservationDebugArtifactCollector(),
            ocr_service=ocr_service)
                    service = ObservationService(
                        screenshot_service=screenshot_service,
                        observation_builder=builder,
                        session=_FakeScreenshotSession(payload),
                        artifact_directory="debug_sidecar_test",
                        mode=mode,
                    )

                    capture = service.capture_observation("world_scan", request=persist_request)

                    expected_screen_type = ScreenType.PNC_WORLD_MAP
                    self.assertEqual(capture.observation.screen_type, expected_screen_type)
                    if expect_artifact:
                        self.assertIsNotNone(capture.screenshot.artifact_path)
                    else:
                        self.assertIsNone(capture.screenshot.artifact_path)
                    artifact_files = tuple((root / "artifacts").rglob("*.png"))
                    self.assertEqual(bool(artifact_files), expect_artifact)
                    sidecar_files = tuple((root / "artifacts").rglob("*_unidentified_ocr.json"))
                    self.assertEqual(bool(sidecar_files), expect_sidecar)
                    if not expect_sidecar:
                        continue
                    document = json.loads(sidecar_files[0].read_text(encoding="utf-8"))
                    unidentified_texts = [entry["text"] for entry in document["unidentified_ocr_lines"]]
                    self.assertIn("Mystery Badge", unidentified_texts)
                    self.assertNotIn("My Territory", unidentified_texts)
                finally:
                    if root.exists():
                        shutil.rmtree(root)

    def test_chat_transcript_observation_uses_the_shared_artifact_mode_policy(self) -> None:
        """Keeps transcript captures ephemeral in light mode while preserving them in debug mode through the shared policy."""

        for mode, expect_artifact in (
            (ObservationMode.LIGHT, False),
            (ObservationMode.DEBUG, True),
        ):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory)
                    screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                    payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
                    service = ObservationService(
                        screenshot_service=screenshot_service,
                        observation_builder=_SequencedObservationBuilder(
                            observations=[make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD)]
                        ),
                        session=_FakeScreenshotSession(payload),
                        artifact_directory="chat_transcript_mode_test",
                        mode=mode,
                    )

                    capture = service.capture_observation(
                        "chat_transcript_scan",
                        request=ObservationRequest.chat_transcript_observation(),
                    )

                    self.assertEqual(capture.observation.screen_type, ScreenType.PNC_CHAT)
                    if expect_artifact:
                        self.assertIsNotNone(capture.screenshot.artifact_path)
                        self.assertTrue(any((root / "artifacts").rglob("*.png")))
                    else:
                        self.assertIsNone(capture.screenshot.artifact_path)
                        self.assertFalse(any((root / "artifacts").rglob("*.png")))
