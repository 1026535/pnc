"""Capture storage: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
