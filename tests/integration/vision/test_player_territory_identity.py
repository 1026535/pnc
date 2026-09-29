"""Player Territory identity regressions for the measured remote detail profile.

The final007 live005 Castle tap opened the named remote Player Territory, but no
PNC_PLAYER_TERRITORY visual profile existed, so strict family-gated OCR never ran
and the generic popup guard dismissed the task-owned panel. The
remote_player_territory profile owns identity through the title and static
Coordinates label; the Player Info control is independently measured and optional. These
tests exercise that contract through both production observation paths on the
saved native RGBA detail frame under the canonical Castle detail follow-up
request; they do not pre-convert captures to RGB.
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
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
REMOTE_TERRITORY = "player_territory_20260923.png"

_REFERENCE_SIZE = (540, 960)
# Catalog search regions in reference space; coordinates values are excluded.
_TITLE_REGION = (165, 111, 214, 50)
_COORDINATES_LABEL_REGION = (116, 256, 120, 40)
_PLAYER_INFO_REGION = (15, 705, 100, 82)


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


class PlayerTerritoryIdentityTests(unittest.TestCase):
    """Pin Territory identity, optional Info action, provenance, and negatives."""

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
        cls._request = ObservationRequest.world_yolo_castle_detail_follow_up()

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
                artifact_directory="player_territory_identity", label=Path(name).stem,
                extension="png", payload=(FIXTURES / name).read_bytes(),
            )
            capture = replace(capture, artifact=artifact)
        return {
            "builder": self._builder.build(capture, request=self._request),
            "perception": self._perception.build(
                capture, include_content=True, request=self._request,
            ),
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

    def _assert_no_territory(self, observation: Observation) -> None:
        """Require no actionable Territory identity or Territory-owned controls."""

        self.assertNotEqual(ScreenType.PNC_PLAYER_TERRITORY, observation.screen_type)
        self.assertFalse(observation.has(UiElementId.PNC_PLAYER_TERRITORY_HEADER))
        self.assertFalse(observation.has(UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON))

    def test_remote_territory_recognizes_screen_and_measured_player_info(self) -> None:
        """The saved detail frame must own Territory identity and the Info action."""

        frame_ref = FrameRef("territory-identity-006", 1, 1, 0, datetime.now(UTC))
        with tempfile.TemporaryDirectory() as temporary_directory:
            observations = self._observations(
                REMOTE_TERRITORY, store=ArtifactStore(Path(temporary_directory)), frame_ref=frame_ref,
            )
            for publisher, observation in observations.items():
                with self.subTest(publisher=publisher):
                    self.assertEqual(ScreenType.PNC_PLAYER_TERRITORY, observation.screen_type)
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertTrue(observation.decision.action_eligible)
                    player_info = observation.require(
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON
                    )
                    header = observation.require(UiElementId.PNC_PLAYER_TERRITORY_HEADER)
                    self.assertFalse(player_info.identity_evidence)
                    assert observation.image_size is not None
                    self._assert_bounds_in_region(
                        player_info.bounds, _PLAYER_INFO_REGION, observation.image_size
                    )
                    self._assert_bounds_in_region(
                        header.bounds, _TITLE_REGION, observation.image_size
                    )
                    action_x, action_y = player_info.action_point
                    self.assertTrue(
                        player_info.bounds.x <= action_x <= player_info.bounds.x + player_info.bounds.width
                    )
                    self.assertTrue(
                        player_info.bounds.y <= action_y <= player_info.bounds.y + player_info.bounds.height
                    )
                    self.assertEqual(frame_ref, observation.frame_ref)
                    self.assertEqual((900, 1600), observation.image_size)
                    assert observation.artifact_path is not None
                    self.assertTrue(observation.artifact_path.name.endswith(".png"))

    def test_erased_title_never_qualifies_territory(self) -> None:
        """Destroying the title anchor must remove Territory identity."""

        for publisher, observation in self._observations(
            REMOTE_TERRITORY, mask_region=_scaled_region(_TITLE_REGION, (900, 1600)),
        ).items():
            with self.subTest(publisher=publisher):
                self._assert_no_territory(observation)

    def test_erased_coordinates_label_never_qualifies_territory(self) -> None:
        """A generic title-strip match alone cannot own the detail panel."""

        for publisher, observation in self._observations(
            REMOTE_TERRITORY,
            mask_region=_scaled_region(_COORDINATES_LABEL_REGION, (900, 1600)),
        ).items():
            with self.subTest(publisher=publisher):
                self._assert_no_territory(observation)

    def test_erased_player_info_retains_territory_without_the_action(self) -> None:
        """Identity must not depend on the optional Player Info action."""

        for publisher, observation in self._observations(
            REMOTE_TERRITORY, mask_region=_scaled_region(_PLAYER_INFO_REGION, (900, 1600)),
        ).items():
            with self.subTest(publisher=publisher):
                self.assertEqual(ScreenType.PNC_PLAYER_TERRITORY, observation.screen_type)
                self.assertTrue(observation.decision.action_eligible)
                self.assertTrue(observation.has(UiElementId.PNC_PLAYER_TERRITORY_HEADER))
                self.assertFalse(
                    observation.has(UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON)
                )

    def test_genuine_popup_remains_blocked_and_never_becomes_territory(self) -> None:
        """The existing modal guard still owns a real invitation popup."""

        for publisher, observation in self._observations("alliance_invitation.png").items():
            with self.subTest(publisher=publisher):
                self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
                self.assertEqual(GuardVerdict.BLOCKED, observation.decision.guard)
                self.assertFalse(
                    observation.has(UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON)
                )
                self.assertFalse(observation.has(UiElementId.PNC_PLAYER_TERRITORY_HEADER))


if __name__ == "__main__":
    unittest.main()
