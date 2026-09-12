"""Offline regressions for shared canary identity recovery."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.canary_runtime import verify_canary_identity
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_entry, make_observation


class CanaryIdentityRecoveryTests(unittest.TestCase):
    """Protects named canaries from stopping on known startup interruptions."""

    def test_vip_daily_reset_is_closed_before_castle_identity_navigation(self) -> None:
        """Uses the typed VIP Close selector before proceeding to Manage Char."""

        target = DailyMaintenanceTargetConfig(
            account_id="account_a",
            castle_ref="npc_2",
            castle=CastleIdentity("K157", "NPC 2", 22),
            capabilities=(),
        )
        vip_reset = make_observation(
            ScreenType.PNC_VIP_DAILY_RESET,
            visible_ids=(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,),
            blocking_popup=True,
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        castle_selection = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="NPC 2",
                    metadata={"kingdom": "K157", "castle_level": 22},
                    selected=True,
                ),
            ),
        )

        observer = Mock()
        observer.observe.return_value = vip_reset
        actions = Mock()
        actions.recover_interruption_if_required.return_value = None
        actions.execute_actions.side_effect = (
            SimpleNamespace(observation=home),
            SimpleNamespace(observation=castle_selection),
        )
        planner = Mock()
        planner.close_blocking_popup.return_value = [
            TapAction(selector_id=UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON),
        ]
        planner.open_castle_selection.return_value = [
            TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE),
        ]
        runtime = Mock()
        runtime.observation_service = observer
        runtime.require_observed_action_executor.return_value = actions
        connected = SimpleNamespace(
            runtime=runtime,
            runner=SimpleNamespace(flow_planner=planner),
        )
        script_runner = Mock()
        script_runner.config.require_account.return_value = Mock()
        script_runner.config.defaults = Mock()
        script_runner.logger = Mock()

        result = verify_canary_identity(
            script_runner=script_runner,
            connected=connected,
            target=target,
        )

        self.assertEqual(castle_selection, result.observation)
        self.assertEqual(
            UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
            actions.execute_actions.call_args_list[0].args[0][0].selector_id,
        )
        planner.close_blocking_popup.assert_called_once_with(vip_reset)

    def test_world_map_returns_home_before_castle_identity_navigation(self) -> None:
        """Uses the typed World Map Home control instead of rejecting a safe starting surface."""

        target = DailyMaintenanceTargetConfig(
            account_id="account_a",
            castle_ref="npc_2",
            castle=CastleIdentity("K157", "NPC 2", 22),
            capabilities=(),
        )
        world_map = make_observation(
            ScreenType.PNC_WORLD_MAP,
            visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        castle_selection = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="NPC 2",
                    metadata={"kingdom": "K157", "castle_level": 22},
                    selected=True,
                ),
            ),
        )

        observer = Mock()
        observer.observe.return_value = world_map
        actions = Mock()
        actions.recover_interruption_if_required.return_value = None
        actions.execute_actions.side_effect = (
            SimpleNamespace(observation=home),
            SimpleNamespace(observation=castle_selection),
        )
        planner = Mock()
        planner.ensure_home_city.return_value = [
            TapAction(selector_id=UiElementId.PNC_WORLD_HOME_NAV),
        ]
        planner.open_castle_selection.return_value = [
            TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE),
        ]
        runtime = Mock()
        runtime.observation_service = observer
        runtime.require_observed_action_executor.return_value = actions
        connected = SimpleNamespace(
            runtime=runtime,
            runner=SimpleNamespace(flow_planner=planner),
        )
        script_runner = Mock()
        script_runner.config.require_account.return_value = Mock()
        script_runner.config.defaults = Mock()
        script_runner.logger = Mock()

        result = verify_canary_identity(
            script_runner=script_runner,
            connected=connected,
            target=target,
        )

        self.assertEqual(castle_selection, result.observation)
        self.assertEqual(
            UiElementId.PNC_WORLD_HOME_NAV,
            actions.execute_actions.call_args_list[0].args[0][0].selector_id,
        )
        planner.ensure_home_city.assert_called_once_with(world_map)


if __name__ == "__main__":
    unittest.main()
