"""Player Profile name regression for the measured remote gear layout.

Incident INC-20260923-v19-a89fb729-157farm-final008-001: final008 live006
reached the correct remote Profile, but the title OCR split into two same-row
fragments ("another" / "NPC") and the single-fragment title reader abstained
with missing_or_ambiguous_name. The remote_player_profile_gear title reader now
joins same-row fragments in reading order. This saved-frame case exercises the
whole production observation path on the native RGBA profile frame under the
canonical player_profile_follow_up request; it does not pre-convert captures.

Authored during the profile007 package while saved-frame OCR/OpenCV capacity
was reserved for the V44 live worker; its first run is deferred to the lead's
combined gate. The lead probe already proved the same frame through both
production publishers (probe evidence under
.local-data/lead-v19/profile-name007-20260923/probe.json).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

import cv2
from PIL import Image

from pnc_automation.app.entrypoints.app import build_observation_builder
from pnc_automation.app.pnc.domain.castles import (
    castle_names_match,
    normalize_castle_display_name,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore

from tests.support.paths import TEST_DATA_ROOT


REMOTE_PROFILE = "player_profile_variants/remote_player_profile_gear_20260923.png"
# Tagged World label recorded by the live006 source observation on this castle.
WORLD_LABEL = "[NGF]another NPC"
EXPECTED_PROFILE_NAME = "another NPC"


class PlayerProfileIdentityTests(unittest.TestCase):
    """Pin the fragmented-title name read through both production publishers."""

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
        cls._request = ObservationRequest.player_profile_follow_up()

    @classmethod
    def tearDownClass(cls) -> None:
        cv2.setNumThreads(cls._previous_threads)

    def _observations(
        self,
        *,
        store: ArtifactStore,
        frame_ref: FrameRef,
    ) -> dict[str, Observation]:
        """Observe the native-mode fixture through both production publishers."""

        fixture = TEST_DATA_ROOT / "screen_recognition" / REMOTE_PROFILE
        with Image.open(fixture) as source:
            image = source.copy()
        capture = CapturedScreenshot(
            None, image, "PNG", ephemeral_captured_at=datetime.now(UTC), frame_ref=frame_ref,
        )
        artifact = store.persist_bytes(
            artifact_directory="player_profile_identity", label=fixture.stem,
            extension="png", payload=fixture.read_bytes(),
        )
        capture = replace(capture, artifact=artifact)
        return {
            "builder": self._builder.build(capture, request=self._request),
            "perception": self._perception.build(
                capture, include_content=True, request=self._request,
            ),
        }

    def test_remote_profile_reads_fragmented_title_as_player_name(self) -> None:
        """The saved profile frame must publish the assembled remote name."""

        frame_ref = FrameRef("profile-name-007", 1, 1, 0, datetime.now(UTC))
        with tempfile.TemporaryDirectory() as temporary_directory:
            observations = self._observations(
                store=ArtifactStore(Path(temporary_directory)), frame_ref=frame_ref,
            )
            for publisher, observation in observations.items():
                with self.subTest(publisher=publisher):
                    self.assertEqual(ScreenType.PNC_PLAYER_PROFILE, observation.screen_type)
                    self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                    self.assertTrue(observation.decision.action_eligible)
                    self.assertEqual(EXPECTED_PROFILE_NAME, observation.profile_player_name)
                    self.assertTrue(
                        castle_names_match(
                            normalize_castle_display_name(WORLD_LABEL),
                            observation.profile_player_name,
                        )
                    )
                    self.assertEqual(frame_ref, observation.frame_ref)
                    self.assertEqual((900, 1600), observation.image_size)
                    assert observation.artifact_path is not None
                    self.assertTrue(observation.artifact_path.name.endswith(".png"))


if __name__ == "__main__":
    unittest.main()
