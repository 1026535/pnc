"""Flow-planner and task unit tests."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.automation.engine.task import TaskId, TaskResult, TaskStatus
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.app.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.app.automation.tasks.gathering_task import GatheringTask
from pnc_automation.app.automation.tasks.login_task import LoginTask
from pnc_automation.app.automation.tasks.open_building_task import OpenBuildingTask
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.automation.tasks.active_castle_resolution import remember_active_castle_identity
from pnc_automation.app.automation.tasks.send_chat_message_task import (
    ChatMessageTaskParams,
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CastleIdentity,
    CastleRosterOrdering,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)
from pnc_automation.core.errors import ScriptValidationError, SelectorResolutionError, TaskVerificationError
from pnc_automation.app.pnc.domain.action_requests import (
    ActionTimingProfile,
    InputTextAction,
    KeyEventAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapPointAction,
    TapListEntryAction,
    TapSpatialObjectAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityMapCoordinate, HomeCityObjectId, build_home_city_object_metadata
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
    resolve_unambiguous_castle_identity,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import WorldCoordinate
from pnc_automation.app.pnc.domain.policy_models import BuildingPriority, BuildingUpgradePolicy, GatheringPolicy, OpenBuildingPolicy
from pnc_automation.app.pnc.navigation.screen_flows import ChatChannel, ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from tests.test_support import (
    build_logger,
    make_entry,
    make_observation,
    make_spatial_object,
    make_spatial_surface,
)


class FlowAndTaskTests(unittest.TestCase):
    """Validates reusable flows and direct task behavior."""

    def setUp(self) -> None:
        """Builds shared task context inputs."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.flows = ScreenFlowPlanner()
        self.logger = build_logger()

    def _make_context(
        self,
        *,
        params: object,
        task_id: TaskId = TaskId.ENSURE_GAME_RUNNING,
        target_castle: CastleIdentity | None = None,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None = None,
        castle_roster_store: CastleRosterStore | None = None,
    ) -> TaskContext:
        """Builds one task context with the shared test account and flow planner."""

        return TaskContext(
            account=self.account,
            castle_roster_provider=(lambda: None) if castle_roster_provider is None else castle_roster_provider,
            defaults=self.defaults,
            step=ScriptStep(task=task_id),
            params=params,
            flows=self.flows,
            logger=self.logger,
            target_castle=target_castle,
            castle_roster_store=castle_roster_store,
        )

    def _make_castle_selection_observation(self, castles: tuple[CastleIdentity, ...]) -> Observation:
        """Builds one Manage Char observation from an ordered tuple of castle identities."""

        return make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=tuple(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={
                        "kingdom": castle.kingdom,
                        "castle_level": castle.castle_level,
                    },
                )
                for castle in castles
            ),
        )

    def _run_refresh_scan(
        self,
        *,
        store: CastleRosterStore,
        windows: tuple[tuple[CastleIdentity, ...], ...],
    ) -> tuple[TaskResult, CastleRosterStore, TaskContext]:
        """Runs one synthetic refresh scan across the provided ordered Manage Char windows."""

        task = RefreshCastleRosterTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.REFRESH_CASTLE_ROSTER,
            castle_roster_provider=lambda: store.get(self.account.pnc_account_id),
            castle_roster_store=store,
        )
        current_window = self._make_castle_selection_observation(windows[0])
        task.verify(context, current_window, current_window)
        for next_window in windows[1:]:
            next_observation = self._make_castle_selection_observation(next_window)
            task.verify(context, current_window, next_observation)
            current_window = next_observation
        result = task.verify(context, current_window, current_window)
        return result, store, context

    def test_ensure_home_city_from_world_map_uses_world_home_nav(self) -> None:
        """Ensures the reusable flow maps world map back to city with one canonical selector."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV, UiElementId.PNC_WORLD_SEARCH_BUTTON),
        )

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_HOME_NAV)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.home_city_follow_up(ScreenType.PNC_WORLD_MAP))

    def test_ensure_home_city_from_alliance_join_uses_back_navigation(self) -> None:
        """Treats the join-alliance landing as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_ALLIANCE_JOIN)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.home_city_follow_up(ScreenType.PNC_ALLIANCE_JOIN))

    def test_ensure_home_city_from_castle_selection_uses_back_navigation(self) -> None:
        """Treats the Manage Char roster as a back-navigable root-adjacent screen."""

        observation = make_observation(ScreenType.PNC_CASTLE_SELECTION)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_from_daily_to_do_uses_back_navigation(self) -> None:
        """Treats the Daily To-Do overlay as a dismissible back-navigable screen."""

        observation = make_observation(ScreenType.PNC_DAILY_TO_DO)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_ensure_home_city_from_build_queue_uses_back_navigation(self) -> None:
        """Treats the build queue overlay as a dismissible home-adjacent screen."""

        observation = make_observation(ScreenType.PNC_BUILD_QUEUE)

        actions = self.flows.ensure_home_city(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")

    def test_open_chat_from_world_map_uses_shared_shortcut(self) -> None:
        """Uses the shared chat shortcut instead of forcing a return to home city first."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.open_chat(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)

    def test_ensure_chat_channel_reuses_open_chat_until_chat_is_visible(self) -> None:
        """Uses the shared open-chat flow before attempting any channel-specific chat action."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.ensure_chat_channel(observation, ChatChannel.WORLD)

        self.assertEqual(actions, self.flows.open_chat(observation))

    def test_ensure_chat_channel_selects_requested_tab_from_shared_chat_overlay(self) -> None:
        """Uses one canonical channel-selection action once the shared chat overlay is already open."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            active_chat_channel=ChatChannel.ALLIANCE,
        )

        actions = self.flows.ensure_chat_channel(observation, ChatChannel.WORLD)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SelectChatChannelAction)
        self.assertEqual(actions[0].channel, ChatChannel.WORLD)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT))

    def test_open_institute_uses_home_city_spatial_building_when_fixed_button_is_missing(self) -> None:
        """Falls back to the home-city spatial surface instead of a legacy academy selector."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Academy",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                ),
            ),
        )

        actions = self.flows.open_institute(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.kind, SpatialObjectKind.HOME_BUILDING)
        self.assertEqual(actions[0].query.metadata_key, "home_city_object_id")
        self.assertEqual(actions[0].query.metadata_value, "institute")
        self.assertEqual(actions[0].target_point, (50, 50))

    def test_focus_home_city_object_uses_extended_fixed_map_tour_before_exhaustion(self) -> None:
        """Keeps home-city search alive across the full canonical fixed-map tour before failing fast."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="wall",
        )

        first_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        second_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        third_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        fourth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        fifth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
        sixth_actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)

        for actions in (
            first_actions,
            second_actions,
            third_actions,
            fourth_actions,
            fifth_actions,
            sixth_actions,
        ):
            self.assertEqual(len(actions), 1)
            self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(first_actions[0].direction, "left")
        self.assertEqual(first_actions[0].reason, "scan_home_city_upper_right_to_left_1")
        self.assertEqual(second_actions[0].direction, "left")
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_2")
        self.assertEqual(third_actions[0].direction, "down")
        self.assertEqual(third_actions[0].reason, "scan_home_city_shift_to_lower_view")
        self.assertEqual(fourth_actions[0].direction, "right")
        self.assertEqual(fourth_actions[0].reason, "scan_home_city_lower_left_to_right_1")
        self.assertEqual(fifth_actions[0].direction, "right")
        self.assertEqual(fifth_actions[0].reason, "scan_home_city_lower_left_to_right_2")
        self.assertEqual(sixth_actions[0].direction, "up")
        self.assertEqual(sixth_actions[0].reason, "scan_home_city_reset_to_upper_view")

        remaining_steps = self.flows.home_city_navigator.focus_step_budget() - 6
        for _ in range(remaining_steps):
            actions = self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)
            self.assertEqual(len(actions), 1)
            self.assertIsInstance(actions[0], SwipeAction)
        with self.assertRaises(SelectorResolutionError):
            self.flows.focus_home_city_object(observation, query, runtime_state=runtime_state)

    def test_open_home_city_object_uses_atlas_tap_when_target_should_already_be_visible(self) -> None:
        """Uses the static home-city atlas to click the target even when OCR only recognized the anchor building."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="infantry_barracks",
            ),
            reason="open_infantry_barracks",
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_infantry_barracks_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual((actions[1].x, actions[1].y), (150, 699))
        self.assertEqual(actions[1].reason, "open_infantry_barracks_from_home_city_atlas")

    def test_build_home_city_object_metadata_exposes_static_atlas_coordinate(self) -> None:
        """Keeps the atlas coordinate on canonical building metadata so runtime inference only consumes static data."""

        metadata = build_home_city_object_metadata(HomeCityObjectId.ALLIANCE_HALL)

        self.assertEqual(metadata["home_city_map_coordinate"], (1881, 1538))

    def test_open_home_city_object_uses_atlas_swipe_when_target_is_offscreen(self) -> None:
        """Uses the static home-city atlas to move toward an offscreen target before any generic sweep starts."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="alliance_hall",
            ),
            reason="open_alliance_hall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertFalse(actions[0].observe_after)
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_alliance_hall_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertFalse(actions[1].observe_after)
        self.assertEqual(actions[1].direction, "up")
        self.assertEqual(actions[1].reason, "focus_alliance_hall_from_home_city_atlas_y")
        self.assertIsInstance(actions[2], TapPointAction)
        self.assertEqual((actions[2].x, actions[2].y), (810, 1085))
        self.assertTrue(actions[2].observe_after)
        self.assertEqual(actions[2].reason, "open_alliance_hall_from_home_city_atlas")

    def test_open_home_city_object_ignores_repeatable_small_buildings_as_atlas_anchors(self) -> None:
        """Refuses to infer the atlas center from repeatable small-building labels whose slots are not uniquely fixed."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Farm",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.FARM),
                        viewport_offset_ratio=(0.1, -0.2),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="castle",
            ),
            reason="open_castle",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "scan_home_city_upper_right_to_left_1")

    def test_open_home_city_object_can_use_remembered_atlas_center_when_current_view_has_no_unique_anchor(self) -> None:
        """Keeps using the last planned viewport center when the latest screenshot is visually ambiguous after blind motion."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1521, 1000),
            }
        }

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="castle",
            ),
            reason="open_castle",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_castle_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual(actions[1].reason, "open_castle_from_home_city_atlas")

    def test_open_home_city_object_repositions_before_tapping_when_the_current_view_would_put_the_target_under_hud(self) -> None:
        """Refuses blind taps that would land inside the persistent home-city HUD and nudges the camera first."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1394, 851),
            }
        }

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[0].start_x_ratio, 0.55)
        self.assertIsNotNone(actions[0].start_y_ratio)
        self.assertEqual(actions[0].end_x_ratio, 0.55)
        self.assertIsNotNone(actions[0].end_y_ratio)
        self.assertIsInstance(actions[1], TapPointAction)
        self.assertEqual((actions[1].x, actions[1].y), (351, 1085))
        self.assertEqual(actions[1].reason, "open_trap_workshop_from_home_city_atlas")

    def test_open_home_city_object_routes_exactly_to_the_safe_band_for_final_taps(self) -> None:
        """Uses exact atlas routing for open actions so the final blind tap never stops just outside the safe band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {
            "home_city_navigation": {
                "known_viewport_center": (1774, 704),
            }
        }

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertEqual(actions[1].direction, "right")
        self.assertEqual(actions[1].reason, "focus_trap_workshop_from_home_city_atlas_x")
        self.assertIsInstance(actions[2], TapPointAction)
        self.assertEqual((actions[2].x, actions[2].y), (150, 1085))
        self.assertEqual(actions[2].reason, "open_trap_workshop_from_home_city_atlas")

    def test_open_home_city_object_prioritizes_the_x_axis_before_vertical_motion_in_the_sauroi_band(self) -> None:
        """Keeps blind routes through the Sauroi/Campaign skyline deterministic by shifting horizontally before vertical motion."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                        viewport_offset_ratio=(0.005555555555555556, 0.03875),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Arena",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.ARENA),
                        viewport_offset_ratio=(0.37777777777777777, 0.223125),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertGreaterEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "right")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_x")
        self.assertIsInstance(actions[1], SwipeAction)
        self.assertEqual(actions[1].direction, "up")
        self.assertEqual(actions[1].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[1].start_x_ratio, 0.55)
        self.assertEqual(actions[1].end_x_ratio, 0.55)

    def test_open_home_city_object_uses_the_castle_utility_vertical_swipe_lane_for_trap_workshop(self) -> None:
        """Routes y-first trap-workshop pans through the reviewed right-side lane when the castle utility band is visible."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                        viewport_offset_ratio=(55 / 900, 460 / 1600),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertGreaterEqual(len(actions), 2)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "focus_trap_workshop_from_home_city_atlas_y")
        self.assertEqual(actions[0].start_x_ratio, 0.69)
        self.assertEqual(actions[0].end_x_ratio, 0.69)

    def test_open_home_city_object_guides_trap_workshop_into_the_blacksmith_lower_band(self) -> None:
        """Uses a deterministic short upward pan once the blacksmith-only skyline proves the lower-band trap view is nearby."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                        viewport_offset_ratio=(0.18333333333333332, 0.009375),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")
        self.assertEqual(actions[0].reason, "guide_trap_workshop_lower_band_from_blacksmith")

    def test_open_home_city_object_uses_blacksmith_lower_band_direct_tap_for_trap_workshop(self) -> None:
        """Treats the calibrated blacksmith-plus-farm lower band as a trusted direct-tap view for trap workshop."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                        viewport_offset_ratio=(0.18444444444444444, -0.22875),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Farm",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.FARM),
                        viewport_offset_ratio=(0.31666666666666665, 0.1775),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_trap_workshop_from_blacksmith_lower_band")
        self.assertEqual((actions[0].x, actions[0].y), (667, 875))

    def test_focus_home_city_coordinate_uses_inferred_atlas_center(self) -> None:
        """Moves the home-city camera toward one requested atlas coordinate from the inferred current center."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
        )

        actions = self.flows.focus_home_city_coordinate(
            observation,
            HomeCityMapCoordinate(x=1500, y=1000),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_home_city_atlas_x")

    def test_focus_home_city_coordinate_precomputes_full_swipe_series_before_observing(self) -> None:
        """Plans the whole atlas route up front and only observes after the last swipe in the series."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        viewport_offset_ratio=(-9 / 900, -375 / 1600),
                    ),
                ),
            ),
        )

        actions = self.flows.focus_home_city_coordinate(
            observation,
            HomeCityMapCoordinate(x=2350, y=1000),
        )

        self.assertEqual(len(actions), 2)
        self.assertTrue(all(isinstance(action, SwipeAction) for action in actions))
        self.assertEqual(actions[0].direction, "left")
        self.assertEqual(actions[0].reason, "focus_home_city_atlas_x")
        self.assertFalse(actions[0].observe_after)
        self.assertEqual(actions[1].direction, "left")
        self.assertEqual(actions[1].reason, "focus_home_city_atlas_x")
        self.assertTrue(actions[1].observe_after)
        self.assertEqual(actions[1].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
        self.assertIsNotNone(actions[1].start_x_ratio)
        self.assertEqual(actions[1].start_y_ratio, 0.56)
        self.assertIsNotNone(actions[1].end_x_ratio)
        self.assertEqual(actions[1].end_y_ratio, 0.56)

    def test_open_home_city_object_guides_wall_search_from_castle_before_generic_scan(self) -> None:
        """Uses the reviewed Castle-to-Blacksmith shift before the generic wall raster begins."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            ),
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_wall_search_from_castle")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_wall_search_from_blacksmith_before_generic_scan(self) -> None:
        """Uses the reviewed Blacksmith-to-Wall shift before the generic wall raster begins."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            ),
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_wall_search_from_blacksmith")
        self.assertEqual(actions[0].direction, "left")

    def test_open_home_city_object_does_not_repeat_wall_guidance_from_same_anchor_view(self) -> None:
        """Falls back to the generic raster after the current Castle-guided wall move was already spent."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                ),
            ),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="wall",
        )

        first_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_wall",
            runtime_state=runtime_state,
        )
        second_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_wall",
            runtime_state=runtime_state,
        )

        self.assertEqual(first_actions[0].reason, "guide_wall_search_from_castle")
        self.assertEqual(len(second_actions), 1)
        self.assertIsInstance(second_actions[0], SwipeAction)
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_1")

    def test_open_home_city_object_uses_research_shortcut_for_institute(self) -> None:
        """Uses the fixed home-city research shortcut instead of moving the camera for Institute."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_RESEARCH_BUTTON,),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="institute",
            ),
            reason="open_institute",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_RESEARCH_BUTTON)
        self.assertEqual(actions[0].reason, "open_institute")

    def test_open_home_city_object_uses_root_view_direct_tap_for_institute_when_label_is_missing(self) -> None:
        """Uses the canonical fixed root-view tap when Institute is off the OCR surface but its anchor buildings prove the view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="institute",
            ),
            reason="open_institute",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_institute_from_root_view")
        self.assertEqual((actions[0].x, actions[0].y), (722, 912))

    def test_open_home_city_object_uses_root_view_direct_tap_for_castle_when_label_is_missing(self) -> None:
        """Uses the canonical root-view tap for Castle when the barracks pair proves the framing despite OCR drift on Castle itself."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="castle",
            ),
            reason="open_castle",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_castle_from_root_view")
        self.assertEqual((actions[0].x, actions[0].y), (441, 425))

    def test_open_home_city_object_uses_utility_view_direct_tap_for_warehouse_when_label_is_missing(self) -> None:
        """Uses the canonical utility-view tap when Warehouse OCR is missing but the right-side anchor view is known."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Watch Tower",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WATCHTOWER),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="warehouse",
            ),
            reason="open_warehouse",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_warehouse_from_utility_view")
        self.assertEqual((actions[0].x, actions[0].y), (395, 841))

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_alliance_hall(self) -> None:
        """Uses the known lower-right quadrant tap for Alliance Hall when the surrounding fixed buildings prove the view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="alliance_hall",
            ),
            reason="open_alliance_hall",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_alliance_hall_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (827, 666))

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_blacksmith(self) -> None:
        """Uses the known lower-left quadrant tap for Blacksmith when the surrounding fixed buildings prove the view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Alliance Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.ALLIANCE_HALL),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="blacksmith",
            ),
            reason="open_blacksmith",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_blacksmith_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (190, 924))

    def test_open_home_city_object_uses_institute_wall_quadrant_direct_tap_for_trap_workshop(self) -> None:
        """Uses the fixed lower-left support-slot tap for Trap Workshop when the institute-wall framing is proven."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Blacksmith",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.BLACKSMITH),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="trap_workshop",
            ),
            reason="open_trap_workshop",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].reason, "open_trap_workshop_from_institute_wall_quadrant")
        self.assertEqual((actions[0].x, actions[0].y), (241, 1365))

    def test_open_home_city_object_does_not_repeat_direct_tap_from_same_anchor_view(self) -> None:
        """Spends one trusted fixed-view tap attempt once before falling back to the remaining fixed-map navigation budget."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
            image_size=(900, 1600),
        )
        runtime_state: dict[str, object] = {}
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value="institute",
        )

        first_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_institute",
            runtime_state=runtime_state,
        )
        second_actions = self.flows.open_home_city_object(
            observation,
            query,
            reason="open_institute",
            runtime_state=runtime_state,
        )

        self.assertEqual(len(first_actions), 1)
        self.assertIsInstance(first_actions[0], TapPointAction)
        self.assertEqual(first_actions[0].reason, "open_institute_from_root_view")
        self.assertEqual(len(second_actions), 1)
        self.assertIsInstance(second_actions[0], SwipeAction)
        self.assertEqual(second_actions[0].reason, "scan_home_city_upper_right_to_left_1")

    def test_open_home_city_object_guides_utility_view_from_root_before_generic_scan(self) -> None:
        """Uses the deterministic root-to-utility transition before falling back to raster movement for right-side fixed buildings."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="alliance_hall",
            ),
            reason="open_alliance_hall",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_utility_view_from_root_view")
        self.assertEqual(actions[0].direction, "left")

    def test_open_home_city_object_guides_institute_wall_quadrant_from_utility_view(self) -> None:
        """Uses the deterministic utility-to-support-quadrant transition before generic scan for alliance buildings and wall-side structures."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Watch Tower",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WATCHTOWER),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="blacksmith",
            ),
            reason="open_blacksmith",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_institute_wall_quadrant_from_utility_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_root_view_from_utility_for_infantry_barracks(self) -> None:
        """Uses the deterministic utility-to-root transition before generic scan for root-view barracks targets."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Watch Tower",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WATCHTOWER),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sauroi Lair",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SAUROI_LAIR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="infantry_barracks",
            ),
            reason="open_infantry_barracks",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_root_view_from_utility_view")
        self.assertEqual(actions[0].direction, "right")

    def test_open_home_city_object_guides_hero_war_view_from_root(self) -> None:
        """Uses the deterministic root-to-hero-war transition before generic scan for the upper support band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Infantry Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Ranged Barracks",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RANGED_BARRACKS),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="hero_hall",
            ),
            reason="open_hero_hall",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_hero_war_view_from_root_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_sacred_tree_band_from_hero_war_view(self) -> None:
        """Uses the deterministic hero-war-to-sacred-tree transition before generic scan for the lower-left support band."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="sacred_tree",
            ),
            reason="open_sacred_tree",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_sacred_tree_band_from_hero_war_view")
        self.assertEqual(actions[0].direction, "up")

    def test_open_home_city_object_guides_warehouse_search_from_hall_of_war_and_recruiting_center_band(self) -> None:
        """Uses the fixed-map downward warehouse route from the Hall of War / Sacred Tree / Recruiting Center view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Sacred Tree",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.SACRED_TREE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Recruiting Center",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.RECRUITING_CENTER),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="warehouse",
            ),
            reason="open_warehouse",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_warehouse_search_from_hall_of_war_and_recruiting_center_band")
        self.assertEqual(actions[0].direction, "down")

    def test_open_home_city_object_guides_warehouse_search_from_hall_of_war_and_hero_hall(self) -> None:
        """Uses the fixed-map warehouse route once Hall of War and Hero Hall prove the correct intermediate view."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hall of War",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HALL_OF_WAR),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                    ),
                ),
            ),
        )

        actions = self.flows.open_home_city_object(
            observation,
            SpatialObjectQuery(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="warehouse",
            ),
            reason="open_warehouse",
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "guide_warehouse_search_from_hall_of_war_and_hero_hall")
        self.assertEqual(actions[0].direction, "left")

    def test_focus_world_coordinate_plans_one_coordinate_driven_swipe(self) -> None:
        """Uses the shared world-map navigator instead of task-local swipe heuristics."""

        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=100,
                y=120,
            ),
        )

        actions = self.flows.focus_world_coordinate(
            observation,
            WorldCoordinate(x=150, y=120),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "left")
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

    def test_recover_unknown_game_screen_uses_back_without_relaunching(self) -> None:
        """Uses one in-game back increment for unknown endpoint states instead of restarting the app."""

        actions = self.flows.recover_unknown_game_screen(
            make_observation(ScreenType.UNKNOWN),
            reason="recover_unknown_endpoint",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].reason, "recover_unknown_endpoint")

    def test_ensure_game_running_waits_on_unknown_once_launch_is_in_progress(self) -> None:
        """Keeps waiting on the launch splash instead of bouncing back through Android home."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)
        context.runtime_state["ensure_game_running_launch_started"] = True
        observation = make_observation(ScreenType.UNKNOWN)

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].reason, "wait_for_pnc_launch")

    def test_ensure_game_running_replans_when_launch_lands_on_unknown_splash(self) -> None:
        """Treats an unknown post-launch splash as in-progress foregrounding instead of immediate failure."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)

        result = task.verify(
            context,
            make_observation(ScreenType.ANDROID_HOME),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertTrue(context.runtime_state["ensure_game_running_launch_started"])

    def test_ensure_game_running_keeps_waiting_after_four_unknown_launch_observations(self) -> None:
        """Allows slower live launch/login handoffs instead of hard-failing after only a few splash observations."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)
        context.runtime_state["ensure_game_running_launch_started"] = True
        context.runtime_state["ensure_game_running_launch_wait_attempts"] = 4

        result = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)

    def test_send_chat_message_from_home_city_opens_chat_selects_channel_and_sends(self) -> None:
        """Uses one chat-opening increment from home so the chat origin is observed before sending."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)
        self.assertTrue(actions[0].observe_after)

    def test_send_chat_message_maps_world_channel_to_kingdom_tab(self) -> None:
        """Maps the public world-channel enum to the in-game Kingdom chat tab."""

        observation = make_observation(ScreenType.PNC_CHAT)

        actions = self.flows.send_chat_message(
            observation,
            message="ping",
            channel=ChatChannel.WORLD,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SelectChatChannelAction)
        self.assertEqual(actions[0].channel, ChatChannel.WORLD)
        self.assertTrue(actions[0].observe_after)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT))

    def test_send_chat_message_uses_narrow_chat_open_follow_up_request(self) -> None:
        """Uses the shared chat-specific navigation follow-up instead of a broad default observation."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.navigation_follow_up((self.flows._chat_navigation_outcome(),)),
        )

    def test_send_chat_message_preserves_runtime_channel_skip_when_chat_is_already_active(self) -> None:
        """Skips channel selection once chat is already on the requested tab and goes straight to send actions."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            active_chat_channel=ChatChannel.ALLIANCE,
            chat_draft_empty=True,
        )

        actions = self.flows.send_chat_message(
            observation,
            message="hello",
            channel=ChatChannel.ALLIANCE,
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_INPUT_FIELD)
        self.assertEqual(actions[0].text, "hello")
        self.assertTrue(actions[0].replace_existing)
        self.assertEqual(actions[0].timing_profile, ActionTimingProfile.CHAT)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_CHAT_SEND_BUTTON)
        self.assertEqual(actions[1].follow_up_request, ObservationRequest.chat_send_follow_up())
        self.assertEqual(actions[1].timing_profile, ActionTimingProfile.CHAT)

    def test_send_alliance_chat_message_task_parses_one_required_message(self) -> None:
        """Accepts only the single script-facing message parameter for alliance chat sends."""

        task = SendAllianceChatMessageTask()

        params = task.parse_params({"message": "bot shall invade"})

        self.assertEqual(params, ChatMessageTaskParams(message="bot shall invade"))
        with self.assertRaises(ScriptValidationError):
            task.parse_params({})
        with self.assertRaises(ScriptValidationError):
            task.parse_params({"message": " ", "channel": "alliance"})

    def test_send_alliance_chat_message_task_delegates_to_the_canonical_chat_flow(self) -> None:
        """Plans the existing alliance chat flow without reimplementing any chat actions."""

        task = SendAllianceChatMessageTask()
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )
        context = self._make_context(params=ChatMessageTaskParams(message="hello alliance"))

        actions = task.plan(context, observation)

        self.assertEqual(
            actions,
            self.flows.send_chat_message(
                observation,
                message="hello alliance",
                channel=ChatChannel.ALLIANCE,
            ),
        )

    def test_send_world_chat_message_task_returns_one_recovery_increment_until_chat_ready(self) -> None:
        """Uses the canonical root-return flow before attempting the fixed world-chat send."""

        task = SendWorldChatMessageTask()
        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS, UiElementId.PNC_BOTTOM_NAV_MORE),
        )
        context = self._make_context(params=ChatMessageTaskParams(message="hello world"))

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.ensure_home_city(observation))

    def test_send_world_chat_message_task_waits_through_loading(self) -> None:
        """Waits for loading to settle before attempting the reusable chat workflow."""

        task = SendWorldChatMessageTask()
        context = self._make_context(params=ChatMessageTaskParams(message="hello world"))

        actions = task.plan(context, make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_send_alliance_chat_message_task_uses_shared_unknown_recovery_increment(self) -> None:
        """Recovers unknown in-game states with the shared back action before chat navigation resumes."""

        task = SendAllianceChatMessageTask()
        context = self._make_context(params=ChatMessageTaskParams(message="hello alliance"))

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))

        self.assertEqual(
            actions,
            self.flows.recover_unknown_game_screen(
                make_observation(ScreenType.UNKNOWN),
                reason="recover_unknown_alliance_chat_screen",
            ),
        )

    def test_send_alliance_chat_message_task_verifies_a_successful_send(self) -> None:
        """Succeeds only when the final observation proves the expected alliance chat state."""

        task = SendAllianceChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello alliance")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=False,
                chat_draft_text="hello alliance",
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
        )

        self.assertTrue(result.succeeded)

    def test_send_world_chat_message_task_replans_while_returning_to_a_chat_ready_screen(self) -> None:
        """Replans between recovery increments instead of trying to send from unsupported screens."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(ScreenType.PNC_VIP),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status.value, "replan")

    def test_send_world_chat_message_task_replans_after_reaching_the_requested_channel(self) -> None:
        """Keeps replanning after channel selection because reaching the right chat tab is not the same as sending."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertIn("can now send", result.message)

    def test_send_world_chat_message_task_does_not_report_success_during_recovery(self) -> None:
        """Keeps replanning when recovery lands on an already-open chat instead of claiming the message was sent."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(ScreenType.PNC_DAILY_TO_DO),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
            ),
        )

        self.assertEqual(result.status.value, "replan")

    def test_send_world_chat_message_task_fails_when_the_final_chat_state_is_not_cleared(self) -> None:
        """Fails fast when the reusable send flow does not leave the shared chat draft empty."""

        task = SendWorldChatMessageTask()
        result = task.verify(
            self._make_context(params=ChatMessageTaskParams(message="hello world")),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="hello world",
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=False,
                chat_draft_text="hello world",
            ),
        )

        self.assertFalse(result.succeeded)
        self.assertTrue(result.retryable)

    def test_login_task_plans_username_and_password_entry(self) -> None:
        """Builds the expected credential-entry actions on the login screen."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_LOGIN,
            visible_ids=(
                UiElementId.PNC_LOGIN_USERNAME_FIELD,
                UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].text, "user@example.com")
        self.assertEqual(actions[1].text, "secret")

    def test_login_task_uses_change_account_when_switch_screen_shows_wrong_account(self) -> None:
        """Forces a clean relogin when account-switch OCR exposes a different remembered account."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_ACCOUNT_SWITCH,
            visible_ids=(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON,),
            current_pnc_account_id="other@example.com",
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON)

    def test_login_task_waits_when_loading_screen_has_no_reconnect_action(self) -> None:
        """Uses one canonical observed wait when bootstrap is still loading."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        actions = task.plan(context, make_observation(ScreenType.PNC_LOADING))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_login_task_opens_castle_selection_when_home_city_is_unverified_but_roster_exists(self) -> None:
        """Uses the trusted roster cache to verify already-in-game sessions instead of silently succeeding."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.LOGIN,
            castle_roster_provider=lambda: roster,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_login_task_opens_lord_info_when_home_city_is_unverified_and_no_roster_exists(self) -> None:
        """Uses the faster Lord Info shortcut when no trusted roster snapshot is available."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)

    def test_login_task_uses_manage_char_from_more_menu_when_verifying_in_game_account(self) -> None:
        """Continues the verification path from the More menu into Manage Char."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.LOGIN,
            castle_roster_provider=lambda: roster,
        )
        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_login_task_does_not_interrupt_an_already_open_world_map_session(self) -> None:
        """Avoids redundant root navigation when login is invoked from another active in-game screen."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(actions, [])

    def test_login_task_does_not_interrupt_an_open_building_screen(self) -> None:
        """Treats an in-progress building screen as an already-open session instead of relogging through root."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        actions = task.plan(
            context,
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
        )

        self.assertEqual(actions, [])

    def test_login_task_verifies_castle_selection_against_pre_observation_roster_snapshot(self) -> None:
        """Accepts a castle-selection state only when the trusted pre-observation snapshot matches."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                self.target_castle,
                CastleIdentity(kingdom="K229", castle_name="Farm", castle_level=4),
            ),
        )
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        before = make_observation(ScreenType.PNC_HOME_CITY)
        after = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(ListEntryKind.CASTLE, title="Main", metadata={"kingdom": "K230", "castle_level": 8}),
                make_entry(ListEntryKind.CASTLE, title="Farm", metadata={"kingdom": "K229", "castle_level": 4}),
            ),
            castle_roster_snapshot=roster,
        )

        result = task.verify(context, before, after)

        self.assertTrue(result.succeeded)
        self.assertIn("trusted cached castle roster", result.message)

    def test_login_task_verifies_lord_info_without_trusted_roster_snapshot(self) -> None:
        """Accepts Lord Info as usable session proof when no cached roster is available."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="Main"),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Lord Info", result.message)

    def test_login_task_verifies_manage_char_without_trusted_roster_snapshot(self) -> None:
        """Accepts Manage Char as usable session proof even when the roster cache is missing or stale."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_MORE_MENU),
            make_observation(
                ScreenType.PNC_CASTLE_SELECTION,
                list_entries=(make_entry(ListEntryKind.CASTLE, title="Main", metadata={"kingdom": "K230"}),),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Manage Char", result.message)

    def test_login_task_falls_back_to_manage_char_when_snapshot_membership_is_stale(self) -> None:
        """Accepts Manage Char session proof even when a trusted snapshot no longer matches exactly."""

        task = LoginTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(CastleIdentity(kingdom="K230", castle_name="Main"),),
        )
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_MORE_MENU),
            make_observation(
                ScreenType.PNC_CASTLE_SELECTION,
                list_entries=(make_entry(ListEntryKind.CASTLE, title="Renamed Main", metadata={"kingdom": "K230"}),),
                castle_roster_snapshot=roster,
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertIn("Manage Char", result.message)

    def test_login_task_replans_wrong_account_on_recoverable_login_states(self) -> None:
        """Keeps wrong-account login and account-switch states on the task's replan path."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)

        for screen_type in (ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH):
            with self.subTest(screen_type=screen_type):
                result = task.verify(
                    context,
                    make_observation(screen_type),
                    make_observation(screen_type, current_pnc_account_id="other@example.com"),
                )

                self.assertEqual(result.status.value, "replan")

    def test_open_castle_selection_uses_more_then_settings_then_manage_char(self) -> None:
        """Uses the live More-overlay path through Settings before entering Manage Char."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
        )
        settings_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
        )

        home_actions = self.flows.open_castle_selection(home_observation)
        more_actions = self.flows.open_castle_selection(more_observation)
        settings_actions = self.flows.open_castle_selection(settings_observation)

        self.assertEqual(len(home_actions), 3)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(home_actions[1], TapAction)
        self.assertEqual(home_actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(home_actions[2], TapAction)
        self.assertEqual(home_actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)
        self.assertEqual(len(settings_actions), 1)
        self.assertIsInstance(settings_actions[0], TapAction)
        self.assertEqual(settings_actions[0].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_open_lord_info_uses_home_shortcut_after_closing_more_overlay(self) -> None:
        """Uses the direct home shortcut and only closes overlays when the task starts from More."""

        home_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )
        more_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )
        settings_observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_MORE_SETTINGS,
                UiElementId.PNC_MORE_MANAGE_CHAR,
            ),
        )

        home_actions = self.flows.open_lord_info(home_observation)
        more_actions = self.flows.open_lord_info(more_observation)
        settings_actions = self.flows.open_lord_info(settings_observation)

        self.assertEqual(len(home_actions), 1)
        self.assertIsInstance(home_actions[0], TapAction)
        self.assertEqual(home_actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(more_actions), 2)
        self.assertIsInstance(more_actions[0], TapAction)
        self.assertEqual(more_actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(more_actions[1], TapAction)
        self.assertEqual(more_actions[1].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertEqual(len(settings_actions), 1)
        self.assertIsInstance(settings_actions[0], TapAction)
        self.assertEqual(settings_actions[0].selector_id, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)

    def test_select_castle_opens_manage_char_directly_when_current_castle_is_unknown(self) -> None:
        """Uses the explicit Manage Char switch path directly instead of chaining Lord Info first."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_select_castle_switches_from_lord_info_when_origin_castle_is_wrong(self) -> None:
        """Leaves Lord Info and continues straight into Manage Char when the origin castle is not the target."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Wrong",
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 4)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[3], TapAction)
        self.assertEqual(actions[3].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_select_castle_returns_to_home_from_a_building_screen_before_opening_manage_char(self) -> None:
        """Uses the explicit castle-switch step to leave in-progress screens before Manage Char navigation."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(ScreenType.PNC_INFANTRY_BARRACKS)

        actions = task.plan(context, observation)
        result = task.verify(context, observation, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(actions, self.flows.ensure_home_city(observation))
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("root-adjacent", result.message)

    def test_select_castle_taps_visible_target_despite_spacing_only_ocr_drift(self) -> None:
        """Treats spacing-only OCR drift as the same visible target castle on Manage Char."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="please bgentle",
                    metadata={"kingdom": "K226", "castle_level": 12},
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertEqual(actions[0].title_text, "please b gentle")
        self.assertEqual(actions[0].metadata_key, "kingdom")
        self.assertEqual(actions[0].metadata_value, "K226")
        self.assertIsInstance(actions[1], WaitAction)

    def test_resolve_unambiguous_castle_identity_prefers_the_exact_requested_name_variant(self) -> None:
        """Returns the exact preferred castle spelling even when an equivalent variant appears first."""

        first_variant = CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12)
        exact_variant = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)

        resolved = resolve_unambiguous_castle_identity(
            (first_variant, exact_variant),
            preferred_name="please b gentle",
        )

        self.assertEqual(resolved, exact_variant)

    def test_select_castle_fails_fast_without_an_explicit_target(self) -> None:
        """Rejects direct select-castle execution when the step omitted its runtime castle target."""

        task = SelectCastleTask()

        with self.assertRaises(TaskVerificationError):
            task.plan(
                self._make_context(params=None, task_id=TaskId.SELECT_CASTLE),
                make_observation(ScreenType.PNC_HOME_CITY),
            )

    def test_return_to_safe_root_screen_closes_more_overlay_without_triggering_exit_popup(self) -> None:
        """Closes the live More overlay with its own toggle instead of using Android back."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_closes_more_settings_submenu_with_toggle(self) -> None:
        """Uses the More toggle to exit the live submenu state that back turns into a popup loop."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS, UiElementId.PNC_MORE_MANAGE_CHAR),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)

    def test_return_to_safe_root_screen_uses_top_left_back_for_fullscreen_more_settings(self) -> None:
        """Uses the visible top-left back target when the full-screen Settings page hides the More toggle."""

        observation = make_observation(
            ScreenType.PNC_MORE_MENU,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_MORE_MANAGE_CHAR),
        )

        actions = self.flows.return_to_safe_root_screen(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)

    def test_select_castle_succeeds_on_lord_info_confirmation_for_target(self) -> None:
        """Treats the post-switch Lord Info confirmation as a terminal success condition."""

        task = SelectCastleTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(self.target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Main",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_for_live_target_name(self) -> None:
        """Keeps the terminal Lord Info success path working for the live pine cobaye target."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="pine cobaye 1",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_after_returning_home_from_selected_manage_char_without_roster(self) -> None:
        """Treats exact Manage Char selection as sufficient once home city inherits the validated target."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
        )
        selected_manage_char = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=target_castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )
        returned_home = make_observation(
            ScreenType.PNC_HOME_CITY,
            current_castle=target_castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )

        actions = task.plan(context, selected_manage_char)
        result = task.verify(context, selected_manage_char, returned_home)

        self.assertEqual(len(actions), 1)
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_despite_spacing_only_ocr_drift(self) -> None:
        """Treats spacing-only Lord Info OCR drift as the same configured target castle."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(target_castle,),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="please bgentle",
        )

        actions = task.plan(context, matching_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertEqual(actions, [])
        self.assertTrue(result.succeeded)

    def test_select_castle_succeeds_on_lord_info_confirmation_with_duplicate_semantic_roster_variants(self) -> None:
        """Does not treat OCR-variant duplicate roster rows as ambiguous Lord Info evidence."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                target_castle,
                CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12),
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
            castle_roster_provider=lambda: roster,
        )
        matching_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="please b gentle",
        )

        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), matching_lord_info)

        self.assertTrue(result.succeeded)

    def test_remember_active_castle_identity_prefers_the_exact_lord_info_name_variant(self) -> None:
        """Preserves the exact Lord Info spelling when semantically equivalent roster entries coexist."""

        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        exact_variant = CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                target_castle,
                exact_variant,
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            castle_roster_provider=lambda: roster,
        )

        resolved = remember_active_castle_identity(
            context,
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="please bgentle"),
        )

        self.assertEqual(resolved, exact_variant)

    def test_select_castle_replans_when_lord_info_name_is_ambiguous_across_kingdoms(self) -> None:
        """Does not accept Lord Info name-only evidence when the cached roster contains duplicate castle names."""

        task = SelectCastleTask()
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                self.target_castle,
                CastleIdentity(kingdom="K999", castle_name="Main", castle_level=9),
            ),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
            castle_roster_provider=lambda: roster,
        )
        ambiguous_lord_info = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Main",
        )

        actions = task.plan(context, ambiguous_lord_info)
        result = task.verify(context, make_observation(ScreenType.PNC_HOME_CITY), ambiguous_lord_info)

        self.assertTrue(actions)
        self.assertEqual(result.status.value, "replan")
        self.assertIn("ambiguous", result.message)

    def test_select_castle_waits_on_unknown_transition_after_switch(self) -> None:
        """Keeps unknown splash frames on the recoverable settle path after a castle switch."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))
        result = task.verify(context, make_observation(ScreenType.PNC_LOADING), make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(result.status.value, "replan")

    def test_select_castle_replans_popup_after_switch_for_runner_recovery(self) -> None:
        """Hands post-switch popups back to the runner instead of failing the step outright."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_LOADING),
            make_observation(ScreenType.PNC_POPUP, blocking_popup=True),
        )

        self.assertEqual(result.status.value, "replan")

    def test_refresh_castle_roster_replaces_stale_cache_membership_with_observed_full_scan(self) -> None:
        """Drops obsolete cached castles instead of upgrading stale membership to `full_scan`."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        stale = CastleIdentity(kingdom="K228", castle_name="Stale", castle_level=2)
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (self.target_castle, stale, alpha, bravo),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            result, store, context = self._run_refresh_scan(
                store=store,
                windows=(
                    (alpha, bravo),
                    (bravo, self.target_castle),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertEqual(result.status.value, "replan")
            self.assertEqual(context.runtime_state["refresh_phase"], "return_home")
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))
            self.assertEqual(roster.ordering, CastleRosterOrdering.FULL_SCAN)

    def test_refresh_castle_roster_replaces_wrong_partial_order_with_scanned_order(self) -> None:
        """Persists the ordered windows observed during the refresh instead of reusing stale cache order."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (self.target_castle, alpha, bravo),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            self._run_refresh_scan(
                store=store,
                windows=(
                    (alpha, bravo),
                    (bravo, self.target_castle),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))

    def test_refresh_castle_roster_persists_exact_scanned_windows_and_backfills_missing_levels(self) -> None:
        """Builds the final full scan from the observed windows while using the pre-refresh cache only for missing levels."""

        alpha = CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3)
        bravo = CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4)
        observed_alpha = CastleIdentity(kingdom="K226", castle_name="Alpha")
        observed_bravo = CastleIdentity(kingdom="K227", castle_name="Bravo")
        observed_main = CastleIdentity(kingdom="K230", castle_name="Main")
        with tempfile.TemporaryDirectory() as temp_directory:
            store = CastleRosterStore(path=Path(temp_directory) / "castles.yaml")
            store.sync(
                self.account.pnc_account_id,
                (alpha, bravo, self.target_castle),
                ordering=CastleRosterOrdering.UNKNOWN,
            )

            self._run_refresh_scan(
                store=store,
                windows=(
                    (observed_alpha, observed_bravo),
                    (observed_bravo, observed_main),
                ),
            )

            roster = store.get(self.account.pnc_account_id)
            self.assertIsNotNone(roster)
            self.assertEqual(roster.castles, (alpha, bravo, self.target_castle))
            self.assertEqual(roster.ordering, CastleRosterOrdering.FULL_SCAN)

    def test_refresh_castle_roster_fails_when_scan_repeats_a_previous_window(self) -> None:
        """Fails fast instead of silently looping when full-scan page progression becomes inconsistent."""

        task = RefreshCastleRosterTask()
        context = self._make_context(params=None, task_id=TaskId.REFRESH_CASTLE_ROSTER)
        top_window = self._make_castle_selection_observation(
            (
                CastleIdentity(kingdom="K226", castle_name="Alpha"),
                CastleIdentity(kingdom="K227", castle_name="Bravo"),
            )
        )
        before = self._make_castle_selection_observation((CastleIdentity(kingdom="K230", castle_name="Main"),))
        task.verify(context, top_window, top_window)
        after = top_window

        result = task.verify(context, before, after)

        self.assertEqual(result.status.value, "failed")
        self.assertIn("repeated", result.message)

    def test_ensure_correct_castle_selected_scrolls_toward_target_using_cached_roster_order(self) -> None:
        """Plans a deterministic swipe when the target castle is outside the visible roster window."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                CastleIdentity(kingdom="K227", castle_name="Bravo", castle_level=4),
                self.target_castle,
            ),
            ordering=CastleRosterOrdering.FULL_SCAN,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(ListEntryKind.CASTLE, title="Alpha", metadata={"kingdom": "K226", "castle_level": 3}),
                make_entry(ListEntryKind.CASTLE, title="Bravo", metadata={"kingdom": "K227", "castle_level": 4}),
            ),
        )

        actions = self.flows.ensure_correct_castle_selected(observation, self.target_castle, roster)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].direction, "up")

    def test_ensure_correct_castle_selected_rejects_untrusted_cached_roster_order(self) -> None:
        """Fails fast instead of guessing a scroll direction from a partial cached roster."""

        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(
                CastleIdentity(kingdom="K226", castle_name="Alpha", castle_level=3),
                self.target_castle,
            ),
            ordering=CastleRosterOrdering.UNKNOWN,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(make_entry(ListEntryKind.CASTLE, title="Alpha", metadata={"kingdom": "K226", "castle_level": 3}),),
        )

        with self.assertRaises(SelectorResolutionError):
            self.flows.ensure_correct_castle_selected(observation, self.target_castle, roster)

    def test_ensure_correct_castle_selected_waits_after_tapping_visible_target(self) -> None:
        """Plans a post-tap stabilization wait so live castle switching can pass through loading safely."""

        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="Main",
                    metadata={"kingdom": "K230", "castle_level": 8},
                ),
            ),
        )

        actions = self.flows.ensure_correct_castle_selected(observation, self.target_castle, None)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertIsInstance(actions[1], WaitAction)
        self.assertTrue(actions[1].observe_after)

    def test_open_building_task_parse_params_accepts_sanctum(self) -> None:
        """Allows direct open-building scripts to target non-upgrade sanctum navigation explicitly."""

        params = OpenBuildingTask().parse_params({"building": "sanctum"})

        self.assertEqual(params, OpenBuildingPolicy(building=HomeCityObjectId.SANCTUM))

    def test_open_building_task_opens_visible_requested_building(self) -> None:
        """Taps the visible requested home-city building instead of sweeping when it is already on-screen."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.INFANTRY_BARRACKS),
            task_id=TaskId.OPEN_BUILDING,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Infantry Barracks",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].reason, "open_requested_building")

    def test_open_building_task_replans_after_camera_focus_when_target_is_offscreen(self) -> None:
        """Keeps the dedicated open-building task alive while the shared home-city search adjusts the camera."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.WALL),
            task_id=TaskId.OPEN_BUILDING,
        )
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )

        actions = task.plan(context, before)
        result = task.verify(context, before, make_observation(ScreenType.PNC_HOME_CITY, spatial_surface=before.spatial_surface))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("searching", result.message)

    def test_open_building_task_succeeds_when_requested_building_screen_opens(self) -> None:
        """Finishes once the exact requested building-owned screen becomes visible."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.INFANTRY_BARRACKS),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Infantry Barracks", result.message)

    def test_open_building_task_accepts_sanctum_icons_as_success(self) -> None:
        """Accepts Sanctum's artifact-plus-relic controls as an open-screen proof even when classification lags."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.SANCTUM),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(
                ScreenType.UNKNOWN,
                visible_ids=(UiElementId.PNC_SANCTUM_ARTIFACT_BUTTON, UiElementId.PNC_SANCTUM_RELIC_BUTTON),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Sanctum", result.message)

    def test_open_building_task_accepts_matching_build_menu_for_unbuilt_target(self) -> None:
        """Accepts the exact build-menu option as success when the requested building slot is not built yet."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.MARKET),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(
                ScreenType.PNC_BUILD_MENU_LARGE_SLOT,
                visible_ids=(UiElementId.PNC_BUILD_MARKET_OPTION,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Market", result.message)

    def test_open_building_task_accepts_generic_building_details_for_unmodeled_screen_owner(self) -> None:
        """Accepts generic building details when the requested building has no dedicated screen enum yet."""

        task = OpenBuildingTask()
        context = self._make_context(
            params=OpenBuildingPolicy(building=HomeCityObjectId.BANK),
            task_id=TaskId.OPEN_BUILDING,
        )

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Bank", result.message)

    def test_building_upgrade_task_parse_params_accepts_priority_file(self) -> None:
        """Loads one ordered building list from a text file so scripts do not need one YAML per target sequence."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "priorities.txt"
            priority_file.write_text("institute\nwarehouse\n", encoding="utf-8")

            params = BuildingUpgradeTask().parse_params({"priority_file": str(priority_file), "allow_speedups": False})

        self.assertEqual(params.priority, (BuildingPriority.INSTITUTE, BuildingPriority.WAREHOUSE))
        self.assertFalse(params.allow_speedups)

    def test_building_upgrade_task_parse_params_rejects_priority_and_priority_file_together(self) -> None:
        """Fails fast when scripts try to mix direct building priorities with one priority-file source."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "priorities.txt"
            priority_file.write_text("institute\n", encoding="utf-8")

            with self.assertRaises(ScriptValidationError):
                BuildingUpgradeTask().parse_params(
                    {
                        "priority": ["warehouse"],
                        "priority_file": str(priority_file),
                        "allow_speedups": False,
                    }
                )

    def test_building_upgrade_task_chooses_highest_priority_candidate(self) -> None:
        """Selects the configured highest-priority building candidate for inspection before claiming eligibility."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(
                UiElementId.PNC_HOME_WORLD_SWITCH,
                UiElementId.PNC_HOME_CHARACTER_PANEL,
                UiElementId.PNC_HOME_BUILD_BUTTON,
            ),
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(70, 60),
                    ),
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.name_text, "Castle")
        self.assertEqual(actions[0].target_point, (70, 60))

    def test_building_upgrade_task_replans_after_camera_focus_when_target_priority_is_offscreen(self) -> None:
        """Treats a home-city search swipe as progress even when other upgradeable buildings were already visible."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Institute",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.INSTITUTE),
                    ),
                ),
            ),
        )

        actions = task.plan(context, before)
        result = task.verify(context, before, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("searching for the requested building", result.message)

    def test_building_upgrade_task_replans_when_details_confirm_upgrade_button(self) -> None:
        """Treats the details screen as the canonical proof that a building is actually upgradeable."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                            action_point=(70, 60),
                        ),
                    ),
                ),
            ),
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("upgrade button is available", result.message)

    def test_building_upgrade_task_replans_when_details_show_no_upgrade_button(self) -> None:
        """Does not report success when the inspected building lacks a visible upgrade action."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(70, 60),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            before,
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("not upgradeable", result.message)
        self.assertIn((BuildingPriority.CASTLE, "Castle", (70, 60)), context.runtime_state["building_upgrade_ineligible_targets"])
        self.assertIn(BuildingPriority.CASTLE, context.runtime_state["building_upgrade_ineligible_object_ids"])

    def test_building_upgrade_task_accepts_exact_building_screen_as_verified_upgrade_context(self) -> None:
        """Treats exact building-owned screens as equivalent to the legacy generic detail screen."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                            action_point=(70, 60),
                        ),
                    ),
                ),
            ),
            make_observation(
                ScreenType.PNC_CASTLE,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("upgrade button is available", result.message)

    def test_building_upgrade_task_taps_upgrade_only_from_verified_details_screen(self) -> None:
        """Starts the upgrade only after the task is already on a details screen with the upgrade button."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_BUILDING_DETAILS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        self.assertIsInstance(actions[1], WaitAction)
        self.assertTrue(actions[1].observe_after)

    def test_building_upgrade_task_waits_for_unknown_screen_to_settle(self) -> None:
        """Allows the task to recover from a transient unknown frame instead of failing applicability."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_requests_visible_active_build_help_before_searching(self) -> None:
        """Treats a visible home-city `Help` button as an already-active build that should be helped opportunistically."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_BUILD_BUTTON)
        self.assertEqual(actions[0].reason, "request_active_build_help")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_skips_when_another_build_is_already_active_after_help_request(self) -> None:
        """Stops cleanly once a visible active build proves the construction queue is already occupied."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("already active", result.message)

    def test_building_upgrade_task_skips_when_active_timer_is_visible_without_help(self) -> None:
        """Uses the shared home-city active-timer signal to skip when the builder is busy outside an alliance."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("already active", result.message)

    def test_building_upgrade_task_replans_once_when_upgrade_opens_final_confirmation(self) -> None:
        """Allows one extra confirmation pass when the first verified upgrade click opens the shared confirmation layout."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("final `Upgrade` click", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_confirmation_pending"])

    def test_building_upgrade_task_replans_when_upgrade_opens_unmet_requirement_panel(self) -> None:
        """Marks the requested building ineligible when the verified upgrade click reveals a prerequisite gate."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
                visible_texts={
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7",
                },
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("Recruiting Center : Lv.7", result.message)
        self.assertIn(BuildingPriority.INFANTRY_BARRACKS, context.runtime_state["building_upgrade_ineligible_object_ids"])

    def test_building_upgrade_task_backs_out_of_unmet_requirement_panel(self) -> None:
        """Leaves the requirement-gated building screen instead of treating it as another confirmation click."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].reason, "leave_building_requirement_panel")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_replans_when_upgrade_click_lands_on_unknown_transition(self) -> None:
        """Keeps the task alive when a verified upgrade click lands on a transient unknown frame."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("still settling", result.message)

    def test_building_upgrade_task_replans_for_help_when_upgrade_returns_home_city_with_help_visible(self) -> None:
        """Requests optional alliance help after the upgrade starts when the home-city help affordance is available."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("alliance help", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_post_start_help_pending"])

    def test_building_upgrade_task_replans_for_build_queue_when_home_city_has_no_timer_or_level_change(self) -> None:
        """Falls through to the second ordered success proof when the home-city observation cannot yet prove the start."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        level=3,
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=3,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("build queue", result.message)
        self.assertEqual(context.runtime_state["building_upgrade_success_verification_stage"], "open_build_queue")

    def test_building_upgrade_task_checks_build_queue_before_accepting_level_change(self) -> None:
        """Preserves the requested timer-first verification order when the level already changed quickly."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Wall",
                        level=3,
                        metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                    ),
                ),
            ),
        )
        task.plan(context, before)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=4,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("build queue", result.message)
        self.assertEqual(context.runtime_state["building_upgrade_success_verification_stage"], "open_build_queue")

    def test_building_upgrade_task_extends_replan_budget_for_home_city_search(self) -> None:
        """Uses a task-local replan budget sized to the shared home-city sweep plus verification overhead."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.WALL,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )

        budget = task.max_replans_per_step(context)

        self.assertIsNotNone(budget)
        assert budget is not None
        self.assertEqual(
            budget,
            self.flows.home_city_navigator.focus_step_budget() + 10,
        )
        self.assertGreater(budget, 5)

    def test_building_upgrade_task_opens_build_queue_for_verification(self) -> None:
        """Uses the shared left-rail build control for the second ordered success proof."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_success_verification_stage"] = "open_build_queue"

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_BUILD_BUTTON)
        self.assertEqual(actions[0].reason, "open_build_queue_for_upgrade_verification")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.build_queue_follow_up())

    def test_building_upgrade_task_succeeds_when_build_queue_shows_timer(self) -> None:
        """Accepts the second ordered success proof when the build queue exposes an active timer row."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_success_verification_stage"] = "open_build_queue"

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Build"},
            ),
            make_observation(
                ScreenType.PNC_BUILD_QUEUE,
                list_entries=(
                    make_entry(
                        ListEntryKind.BUILDING,
                        title="Wall",
                        timer_text="00:48:16",
                        metadata={"queue_state": "upgrading"},
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("build queue", result.message)

    def test_building_upgrade_task_succeeds_when_level_increases_after_build_queue_fallback(self) -> None:
        """Uses the final ordered level-change proof when neither timer-based observation stayed visible."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=3,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )
        context.runtime_state["building_upgrade_success_verification_stage"] = "return_home_for_level"

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_BUILD_QUEUE),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Wall",
                            level=4,
                            metadata=build_home_city_object_metadata(HomeCityObjectId.WALL),
                        ),
                    ),
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Lv.3 to Lv.4", result.message)

    def test_building_upgrade_task_taps_upgrade_button_again_when_confirmation_is_pending(self) -> None:
        """Uses the shared blue `Upgrade` control as the final confirmation click on the exact screen."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        self.assertEqual(actions[0].reason, "confirm_building_upgrade")

    def test_building_upgrade_task_replans_when_upgrade_confirmation_layout_appears(self) -> None:
        """Treats the shared exact-screen confirmation layout as a real confirmation step instead of a failed click."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(
                    UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
                    UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
                ),
            ),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("final `Upgrade` click", result.message)
        self.assertTrue(context.runtime_state["building_upgrade_confirmation_pending"])

    def test_building_upgrade_task_succeeds_when_speedup_replaces_upgrade_button(self) -> None:
        """Treats the shared `Speedup` control as a direct upgrade-start success proof."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_WALL,
                visible_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)
        self.assertIn("Speedup", result.message)

    def test_building_upgrade_task_taps_post_upgrade_help_when_pending(self) -> None:
        """Uses the shared home-city build-slot control to request help after a successful upgrade start."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_post_start_help_pending"] = True

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_BUILD_BUTTON)
        self.assertEqual(actions[0].reason, "request_post_upgrade_help")
        self.assertTrue(actions[0].observe_after)

    def test_building_upgrade_task_succeeds_when_confirmation_click_returns_home_city(self) -> None:
        """Treats the second verified click as success once the final confirmation is consumed."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_confirmation_pending", context.runtime_state)

    def test_building_upgrade_task_succeeds_after_post_upgrade_help_tap_returns_home_city(self) -> None:
        """Treats the help tap as best-effort and still finishes once the task settles back at home city."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_post_start_help_pending"] = True

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
                visible_texts={UiElementId.PNC_HOME_BUILD_BUTTON: "Help"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_post_start_help_pending", context.runtime_state)

    def test_building_upgrade_task_succeeds_when_unknown_settle_returns_home_after_confirmation(self) -> None:
        """Accepts the post-confirm settle path once the transient unknown frame resolves to home city."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_confirmation_pending"] = True

        result = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    metadata={"active_build_timer_text": "00:48:33"},
                ),
            ),
        )

        self.assertTrue(result.succeeded)
        self.assertNotIn("building_upgrade_confirmation_pending", context.runtime_state)

    def test_building_upgrade_task_fails_after_returning_home_with_no_remaining_requested_priorities(self) -> None:
        """Returns one known terminal failure once the explicit requested target is blocked by an unsupported prerequisite."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        context.runtime_state["building_upgrade_ineligible_object_ids"] = {BuildingPriority.INFANTRY_BARRACKS}
        context.runtime_state["building_upgrade_last_unmet_requirement"] = "Recruiting Center : Lv.7"

        result = task.verify(
            context,
            make_observation(
                ScreenType.PNC_INFANTRY_BARRACKS,
                visible_ids=(
                    UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                    UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                    UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
                ),
                visible_texts={UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL: "Recruiting Center : Lv.7"},
            ),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertFalse(result.retryable)
        self.assertIn("Recruiting Center : Lv.7", result.message)
        self.assertIn("not supported yet", result.message)

    def test_building_upgrade_task_skips_after_returning_home_with_no_remaining_requested_priorities_and_no_requirement(self) -> None:
        """Keeps generic no-candidate exhaustion as a skip when no unsupported prerequisite was observed."""

        task = BuildingUpgradeTask()
        context = self._make_context(
            params=BuildingUpgradePolicy(priority=(BuildingPriority.INFANTRY_BARRACKS,)),
            task_id=TaskId.BUILDING_UPGRADE,
        )
        context.runtime_state["building_upgrade_ineligible_object_ids"] = {BuildingPriority.INFANTRY_BARRACKS}

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_INFANTRY_BARRACKS),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("currently eligible", result.message)

    def test_research_task_uses_highest_priority_visible_institute_button(self) -> None:
        """Uses the exact institute category buttons instead of a generic academy badge."""

        task = ResearchTask()
        context = self._make_context(task_id=TaskId.RESEARCH, params=task.parse_params({"priority": ["economy", "development"]}))

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_INSTITUTE,
                visible_ids=(
                    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                    UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON)

    def test_gathering_task_chooses_highest_priority_visible_resource_node(self) -> None:
        """Chooses visible world-map resource nodes from the spatial surface instead of list entries."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Wood Lot",
                        metadata={"resource_type": "wood"},
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(68, 52),
                    ),
                ),
            ),
            available_march_slots=2,
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.kind, SpatialObjectKind.RESOURCE_NODE)
        self.assertEqual(actions[0].query.metadata_key, "resource_type")
        self.assertEqual(actions[0].query.metadata_value, "food")
        self.assertEqual(actions[0].target_point, (68, 52))

    def test_open_visible_world_object_preserves_selected_duplicate_resource_identity(self) -> None:
        """Keeps the chosen world-map duplicate target instead of retargeting by a broad semantic query."""

        first = make_spatial_object(
            SpatialObjectKind.RESOURCE_NODE,
            name_text="Food Farm",
            metadata={"resource_type": "food"},
            action_point=(41, 51),
        )
        second = make_spatial_object(
            SpatialObjectKind.RESOURCE_NODE,
            name_text="Food Farm",
            metadata={"resource_type": "food"},
            action_point=(88, 99),
        )
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(first, second),
            ),
        )

        actions = self.flows.open_visible_world_object(observation, second, reason="open_duplicate_food")

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].target_point, (88, 99))

    def test_open_visible_home_city_object_preserves_selected_duplicate_building_identity(self) -> None:
        """Keeps the chosen home-city duplicate target instead of collapsing repeated buildings into one query match."""

        first = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Infantry Barracks",
            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
            action_point=(61, 71),
        )
        second = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Infantry Barracks",
            metadata=build_home_city_object_metadata(HomeCityObjectId.INFANTRY_BARRACKS),
            action_point=(133, 144),
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(first, second),
            ),
        )

        actions = self.flows.open_visible_home_city_object(observation, second, reason="open_duplicate_infantry_barracks")

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].target_point, (133, 144))

    def test_gathering_task_skips_when_no_march_slots_remain(self) -> None:
        """Treats zero available march slots as a safe no-op."""

        task = GatheringTask()
        context = self._make_context(params=GatheringPolicy(), task_id=TaskId.GATHERING)
        before = make_observation(ScreenType.PNC_WORLD_MAP, available_march_slots=0)
        after = before

        result = task.verify(context, before, after)

        self.assertTrue(result.succeeded)
        self.assertIn("No march slots", result.message)


if __name__ == "__main__":
    unittest.main()

