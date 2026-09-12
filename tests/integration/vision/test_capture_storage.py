"""Capture storage: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService

from tests.support.core.images import build_png_bytes
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession


class CaptureStorageTests(unittest.TestCase):
    """Proves capture storage."""

    def test_screenshot_service_persists_valid_png(self) -> None:
        """Captures a screenshot, validates it, and writes it to disk."""

        with tempfile.TemporaryDirectory() as temp_directory:
            service = ScreenshotService(artifact_store=ArtifactStore(root=Path(temp_directory)))
            screenshot = service.capture(
                _FakeScreenshotSession(build_png_bytes(size=(12, 14))),
                artifact_directory="k313_main_castle",
                label="home_scan",
            )

            self.assertTrue(screenshot.artifact.path.is_file())
            self.assertEqual(screenshot.image.size, (12, 14))
            self.assertEqual(screenshot.artifact.path.parent.name, "k313_main_castle")

    def test_repeated_capture_labels_preserve_every_screenshot(self) -> None:
        """Keeps prior evidence intact when captures share a label and timestamp."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            captured_at = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
            first_payload = build_png_bytes(size=(12, 14))
            second_payload = build_png_bytes(size=(20, 24))
            with patch("pnc_automation.core.infra.storage.artifact_store.datetime") as clock:
                clock.now.return_value = captured_at
                first = ScreenshotService(artifact_store=ArtifactStore(root=root)).capture(
                    _FakeScreenshotSession(first_payload),
                    artifact_directory="k313_main_castle",
                    label="home_scan",
                )
                second = ScreenshotService(artifact_store=ArtifactStore(root=root)).capture(
                    _FakeScreenshotSession(second_payload),
                    artifact_directory="k313_main_castle",
                    label="home_scan",
                )

            self.assertNotEqual(first.artifact_path, second.artifact_path)
            self.assertEqual(first.artifact_path.read_bytes(), first_payload)
            self.assertEqual(second.artifact_path.read_bytes(), second_payload)
