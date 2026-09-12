from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from tools.prototype_yolo import _has_visual_content, wait_for_live_visual_state


class PrototypeYoloTests(unittest.TestCase):
    def test_visual_content_rejects_blank_launch_frame(self) -> None:
        blank = Image.new("RGB", (900, 1600), (245, 245, 245))
        patterned = blank.copy()
        for x in range(100, 800):
            for y in range(300, 1200):
                patterned.putpixel((x, y), ((x + y) % 256, x % 256, y % 256))

        self.assertFalse(_has_visual_content(blank))
        self.assertTrue(_has_visual_content(patterned))

    def test_startup_wait_keeps_unknown_visual_frame_as_bounded_fallback(self) -> None:
        blank = self._capture(Image.new("RGB", (90, 160), (245, 245, 245)), ScreenType.UNKNOWN)
        visual = self._capture(self._patterned_image(), ScreenType.UNKNOWN)
        observer = _FakeObserver([blank, visual])
        times = iter((0.0, 0.0, 2.0))

        capture, readiness, attempts = wait_for_live_visual_state(
            observer,
            run_id="test",
            timeout_seconds=2.0,
            clock=lambda: next(times),
            wait=lambda _: None,
        )

        self.assertIs(capture, visual)
        self.assertEqual(readiness, "visual_content_only")
        self.assertEqual(attempts, 2)

    def test_startup_wait_returns_known_screen_without_an_extra_capture(self) -> None:
        known = self._capture(self._patterned_image(), ScreenType.PNC_HOME_CITY)
        observer = _FakeObserver([known])

        capture, readiness, attempts = wait_for_live_visual_state(
            observer,
            run_id="test",
            timeout_seconds=30.0,
        )

        self.assertIs(capture, known)
        self.assertEqual(readiness, "known_screen")
        self.assertEqual(attempts, 1)

    @staticmethod
    def _patterned_image() -> Image.Image:
        image = Image.new("RGB", (90, 160), (245, 245, 245))
        for x in range(10, 80):
            for y in range(30, 120):
                image.putpixel((x, y), ((x + y) % 256, x % 256, y % 256))
        return image

    @staticmethod
    def _capture(image: Image.Image, screen_type: ScreenType) -> CapturedObservation:
        screenshot = CapturedScreenshot(
            None,
            image,
            "PNG",
            ephemeral_captured_at=datetime.now(UTC),
        )
        observation = Observation(
            screen_type=screen_type,
            visible_elements={},
            image_size=image.size,
            frame_fingerprint=hashlib.sha256(image.tobytes()).hexdigest(),
        )
        return CapturedObservation(screenshot=screenshot, observation=observation)


class _FakeObserver:
    def __init__(self, captures: list[CapturedObservation]) -> None:
        self._captures = iter(captures)

    def capture_observation(self, _label: str) -> CapturedObservation:
        return next(self._captures)


if __name__ == "__main__":
    unittest.main()
