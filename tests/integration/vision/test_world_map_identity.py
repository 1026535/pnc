"""Loaded-World identity regressions for foreground-only HUD anchors.

The V19 live003 route reached a populated World frame whose second required
identity anchor (a lower-left patch over the translucent HUD-toggle background)
scored 0.8455/0.8255 under the unchanged 0.93 threshold. The world_map profile
now reuses the foreground-only masked HUD-arrow asset for that anchor.
The independently measured search magnifier remains optional. These tests
exercise the corrected contract through both production observation paths on the saved
native RGBA failure frame; they do not pre-convert captures to RGB.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import math
from pathlib import Path
import tempfile
import unittest

import cv2
from PIL import Image, ImageDraw

from pnc_automation.app.entrypoints.app import build_observation_builder
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
LOADED_WORLD = "world_map_loaded_20260923.png"

_REFERENCE_SIZE = (540, 960)
# Required identity anchors in catalog order: Home nav strip, then the
# foreground-masked arrows shared with PNC_WORLD_HUD_TOGGLE.
_IDENTITY_REGIONS = {
    "home_nav": (20, 928, 63, 29),
    "hud_toggle": (8, 798, 40, 38),
}
_SEARCH_REGION = (185, 81, 34, 32)


def _scaled_region(region: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Project a reference-space search region onto an arbitrary frame size."""

    sx, sy = size[0] / _REFERENCE_SIZE[0], size[1] / _REFERENCE_SIZE[1]
    x, y, w, h = region
    return (
        math.floor(x * sx),
        math.floor(y * sy),
        math.ceil((x + w) * sx) - math.floor(x * sx),
        math.ceil((y + h) * sy) - math.floor(y * sy),
    )


class WorldMapIdentityTests(unittest.TestCase):
    """Pin recognition, owned controls, provenance, and negatives on saved frames."""

    @classmethod
    def setUpClass(cls) -> None:
        # Saved-image template matching stays on one OpenCV thread to limit
        # shared host load; the runtime default is restored afterwards.
        cls._previous_threads = cv2.getNumThreads()
        cv2.setNumThreads(1)
        cls._builder = build_observation_builder(build_default_selector_registry())
        cls._perception = NavigationPerception(
            cls._builder.visual_recognizer,
            cls._builder.enricher,
            cls._builder.screen_classifier,
            cls._builder.create_ocr_context,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cv2.setNumThreads(cls._previous_threads)

    def _observations(
        self,
        name: str,
        *,
        store: ArtifactStore | None = None,
        frame_ref: FrameRef | None = None,
        mask_region: tuple[int, int, int, int] | None = None,
    ) -> dict[str, Observation]:
        """Observe one native-mode fixture through both production publishers."""

        with Image.open(FIXTURES / name) as source:
            image = source.copy()
        if mask_region is not None:
            draw = ImageDraw.Draw(image)
            x, y, w, h = mask_region
            draw.rectangle((x, y, x + w, y + h), fill=(0, 0, 0, 255))
        capture = CapturedScreenshot(
            None, image, "PNG", ephemeral_captured_at=datetime.now(UTC), frame_ref=frame_ref,
        )
        if store is not None:
            artifact = store.persist_bytes(
                artifact_directory="world_identity", label=Path(name).stem,
                extension="png", payload=(FIXTURES / name).read_bytes(),
            )
            capture = replace(capture, artifact=artifact)
        return {
            "builder": self._builder.build(capture),
            "perception": self._perception.build(capture),
        }

    def _assert_bounds_in_region(
        self, element_bounds: Bounds, region: tuple[int, int, int, int], size: tuple[int, int],
    ) -> None:
        """Require a published control's match to sit inside its scaled search region."""

        x, y, w, h = _scaled_region(region, size)
        self.assertGreaterEqual(element_bounds.x, x - 2)
        self.assertGreaterEqual(element_bounds.y, y - 2)
        self.assertLessEqual(element_bounds.x + element_bounds.width, x + w + 2)
        self.assertLessEqual(element_bounds.y + element_bounds.height, y + h + 2)

    def _assert_world_controls(self, observation: Observation) -> None:
        """Require both World-owned controls measured on this frame."""

        home_nav = observation.require(UiElementId.PNC_WORLD_HOME_NAV)
        search = observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON)
        for element in (home_nav, search):
            self.assertEqual(VisibleElementSourceKind.TEMPLATE, element.source_kind)
            self.assertFalse(element.identity_evidence)
        assert observation.image_size is not None
        self._assert_bounds_in_region(home_nav.bounds, _IDENTITY_REGIONS["home_nav"], observation.image_size)
        self._assert_bounds_in_region(search.bounds, _SEARCH_REGION, observation.image_size)

    def _assert_no_world(self, observation: Observation) -> None:
        """Require no actionable World identity or World-owned controls."""

        self.assertNotEqual(ScreenType.PNC_WORLD_MAP, observation.screen_type)
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_SEARCH_BUTTON))

    def test_loaded_world_recognizes_world_and_owned_controls(self) -> None:
        """The loaded native RGBA failure frame must own World identity and controls."""

        frame_ref = FrameRef("world-identity-003", 1, 1, 0, datetime.now(UTC))
        with tempfile.TemporaryDirectory() as temporary_directory:
            observations = self._observations(
                LOADED_WORLD, store=ArtifactStore(Path(temporary_directory)), frame_ref=frame_ref,
            )
            for publisher, observation in observations.items():
                with self.subTest(publisher=publisher):
                    self.assertEqual(ScreenType.PNC_WORLD_MAP, observation.screen_type)
                    self.assertTrue(observation.decision.action_eligible)
                    self._assert_world_controls(observation)
                    self.assertEqual(frame_ref, observation.frame_ref)
                    self.assertEqual((900, 1600), observation.image_size)
                    assert observation.artifact_path is not None
                    self.assertTrue(observation.artifact_path.name.endswith(".png"))

    def test_masking_either_identity_region_blocks_world_and_controls(self) -> None:
        """Destroying either required anchor region must remove World identity."""

        for region_name, region in _IDENTITY_REGIONS.items():
            for publisher, observation in self._observations(
                LOADED_WORLD, mask_region=_scaled_region(region, (900, 1600)),
            ).items():
                with self.subTest(region=region_name, publisher=publisher):
                    self._assert_no_world(observation)

    def test_home_and_foreground_modal_do_not_become_actionable_world(self) -> None:
        """Home keeps its own identity; the foreground modal never publishes World."""

        for publisher, observation in self._observations("home_city_core.png").items():
            with self.subTest(publisher=publisher, fixture="home_city_core"):
                self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
                self.assertTrue(observation.decision.action_eligible)
                self.assertFalse(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
                self.assertFalse(observation.has(UiElementId.PNC_WORLD_SEARCH_BUTTON))
        for publisher, observation in self._observations("alliance_invitation.png").items():
            with self.subTest(publisher=publisher, fixture="alliance_invitation"):
                self._assert_no_world(observation)

    def test_original_world_reference_still_matches(self) -> None:
        """The frozen 540x960 reference fixture must keep World identity."""

        for publisher, observation in self._observations("world_map_core.png").items():
            with self.subTest(publisher=publisher):
                self.assertEqual(ScreenType.PNC_WORLD_MAP, observation.screen_type)
                self.assertTrue(observation.decision.action_eligible)
                self._assert_world_controls(observation)


if __name__ == "__main__":
    unittest.main()
