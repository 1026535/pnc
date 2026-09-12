"""Observation castle continuity: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ObservationService

from tests.support.pnc.observations import make_observation
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.sequenced_observation_builder import (
    _SequencedObservationBuilder,
)
from tests.support.pnc.capture_vision.encode_png import _encode_png


class ObservationCastleContinuityTests(unittest.TestCase):
    """Proves observation castle continuity."""

    def test_observation_service_carries_lord_info_castle_name_back_to_home_adjacent_screens(self) -> None:
        """Keeps the last validated current castle on home-adjacent screens across Lord Info and Manage Char."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="K304554ca2797"),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                        make_observation(
                            ScreenType.PNC_MORE_MENU,
                            visible_ids=(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR,),
                        ),
                        make_observation(
                            ScreenType.PNC_CASTLE_SELECTION,
                            current_castle=CastleIdentity(kingdom="K313", castle_name="K313alpha"),
                        ),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                    ]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="k304_validation",
            )

            lord_info = service.observe("lord_info")
            home_city = service.observe("home_city")
            more_menu = service.observe("more_menu")
            castle_selection = service.observe("castle_selection")
            post_switch_home = service.observe("post_switch_home")

            self.assertEqual(lord_info.current_castle_name, "K304554ca2797")
            self.assertEqual(home_city.current_castle_name, "K304554ca2797")
            self.assertEqual(more_menu.current_castle_name, "K304554ca2797")
            self.assertEqual(castle_selection.current_castle_name, "K313alpha")
            self.assertEqual(post_switch_home.current_castle_name, "K313alpha")

    def test_observation_service_carries_selected_manage_char_castle_back_to_home_adjacent_screens(self) -> None:
        """Keeps exact Manage Char castle selection on home-adjacent screens until a new switch flow starts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            selected_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_CASTLE_SELECTION, current_castle=selected_castle),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                        make_observation(
                            ScreenType.PNC_MORE_MENU,
                            visible_ids=(UiElementId.PNC_MORE_OVERLAY_MANAGE_CHAR,),
                        ),
                        make_observation(ScreenType.PNC_WORLD_MAP),
                    ]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="k287_manage_char_validation",
            )

            castle_selection = service.observe("castle_selection")
            home_city = service.observe("home_city")
            more_menu = service.observe("more_menu")
            world_map = service.observe("world_map")

            self.assertEqual(castle_selection.current_castle, selected_castle)
            self.assertEqual(home_city.current_castle, selected_castle)
            self.assertEqual(more_menu.current_castle, selected_castle)
            self.assertIsNone(world_map.current_castle)

    def test_observation_service_carries_selected_castle_through_switch_loading_states(self) -> None:
        """Preserves exact Manage Char selection through loading, unknown, and startup popup frames."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            selected_castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_CASTLE_SELECTION, current_castle=selected_castle),
                        make_observation(ScreenType.PNC_LOADING),
                        make_observation(ScreenType.UNKNOWN),
                        make_observation(ScreenType.PNC_POPUP, blocking_popup=True),
                        make_observation(ScreenType.PNC_HOME_CITY),
                    ]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="k157_npc_2_switch_validation",
            )

            observations = tuple(
                service.observe(label)
                for label in ("selected", "loading", "unknown", "popup", "home")
            )

            self.assertEqual(observations[0].current_castle, selected_castle)
            self.assertEqual(tuple(item.current_castle for item in observations[1:4]), (None, None, None))
            self.assertEqual(observations[4].current_castle, selected_castle)
