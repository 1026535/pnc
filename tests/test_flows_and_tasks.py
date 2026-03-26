"""Flow-planner and task unit tests."""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from pnc_automation.scripts.models import ScriptStep
from pnc_automation.automation.task import TaskId, TaskResult, TaskStatus
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.automation.tasks.gathering_task import GatheringTask
from pnc_automation.automation.tasks.login_task import LoginTask
from pnc_automation.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.automation.tasks.active_castle_resolution import remember_active_castle_identity
from pnc_automation.automation.tasks.send_chat_message_task import (
    ChatMessageTaskParams,
    SendAllianceChatMessageTask,
    SendWorldChatMessageTask,
)
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import (
    AccountConfig,
    CastleIdentity,
    CastleRosterOrdering,
    CredentialSource,
    DefaultsConfig,
    PncAccountCastleRosterConfig,
    ResolvedCredentials,
)
from pnc_automation.errors import ScriptValidationError, SelectorResolutionError, TaskVerificationError
from pnc_automation.pnc.action_requests import (
    ActionTimingProfile,
    InputTextAction,
    KeyEventAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    TapSpatialObjectAction,
    WaitAction,
)
from pnc_automation.pnc.observation import (
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.pnc.spatial_navigation import WorldCoordinate
from pnc_automation.pnc.policy_models import BuildingPriority, BuildingUpgradePolicy, GatheringPolicy
from pnc_automation.pnc.screen_flows import ChatChannel, ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest
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

    def test_open_academy_uses_home_city_spatial_building_when_fixed_button_is_missing(self) -> None:
        """Falls back to the home-city spatial surface instead of a legacy academy selector."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Academy",
                        metadata={"category": "academy"},
                    ),
                ),
            ),
        )

        actions = self.flows.open_academy(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.kind, SpatialObjectKind.HOME_BUILDING)
        self.assertEqual(actions[0].query.metadata_key, "category")
        self.assertEqual(actions[0].query.metadata_value, "academy")
        self.assertEqual(actions[0].target_point, (50, 50))

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

    def test_login_task_returns_home_city_when_started_from_world_map(self) -> None:
        """Supports already-logged sessions from other in-game screens by routing back to home city first."""

        task = LoginTask()
        context = self._make_context(params=None, task_id=TaskId.LOGIN)
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_WORLD_HOME_NAV)

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

    def test_select_castle_opens_lord_info_before_switch_when_current_castle_is_unknown(self) -> None:
        """Validates the origin castle from Lord Info before entering Manage Char."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)

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

    def test_remember_active_castle_identity_tolerates_spacing_only_lord_info_drift(self) -> None:
        """Resolves Lord Info castle names through the shared OCR-tolerant castle-name matcher."""

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
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            castle_roster_provider=lambda: roster,
        )

        resolved = remember_active_castle_identity(
            context,
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="please bgentle"),
        )

        self.assertEqual(resolved, target_castle)

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
                        name_text="Academy",
                        metadata={"category": "academy"},
                    ),
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata={"category": "castle"},
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
                            metadata={"category": "castle"},
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
        context.runtime_state["building_upgrade_pending_target"] = (BuildingPriority.CASTLE, "Castle", (70, 60))

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
                            metadata={"category": "castle"},
                            action_point=(70, 60),
                        ),
                    ),
                ),
            ),
            make_observation(ScreenType.PNC_BUILDING_DETAILS),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("not upgradeable", result.message)
        self.assertIn((BuildingPriority.CASTLE, "Castle", (70, 60)), context.runtime_state["building_upgrade_ineligible_targets"])

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

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BUILDING_UPGRADE_BUTTON)

    def test_building_upgrade_task_skips_after_all_visible_candidates_prove_ineligible(self) -> None:
        """Stops cleanly once every visible supported building has already been inspected and rejected."""

        task = BuildingUpgradeTask()
        context = self._make_context(params=BuildingUpgradePolicy(), task_id=TaskId.BUILDING_UPGRADE)
        context.runtime_state["building_upgrade_ineligible_targets"] = {(BuildingPriority.CASTLE, "Castle", (70, 60))}
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata={"category": "castle"},
                        action_point=(70, 60),
                    ),
                ),
            ),
        )

        result = task.verify(context, before, before)

        self.assertEqual(result.status, TaskStatus.SKIPPED)
        self.assertIn("No eligible building upgrades", result.message)

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
            name_text="Barracks",
            metadata={"category": "barracks"},
            action_point=(61, 71),
        )
        second = make_spatial_object(
            SpatialObjectKind.HOME_BUILDING,
            name_text="Barracks",
            metadata={"category": "barracks"},
            action_point=(133, 144),
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(first, second),
            ),
        )

        actions = self.flows.open_visible_home_city_object(observation, second, reason="open_duplicate_barracks")

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

