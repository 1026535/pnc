"""Popup close flow."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class PopupCloseFlowTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves popup close flow."""

    def test_close_blocking_popup_uses_vip_daily_reset_close_button(self) -> None:
        """Dismisses the VIP daily-reset screen through its observed Close button instead of falling back to Back."""

        planner = ScreenFlowPlanner()
        observation = make_observation(
            ScreenType.PNC_VIP_DAILY_RESET,
            visible_ids=(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,),
            blocking_popup=True,
        )

        actions = planner.close_blocking_popup(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON)

    def test_close_blocking_popup_prioritizes_required_update_confirm(self) -> None:
        """Confirms only the typed required-update popup before any generic dismissal path."""

        planner = ScreenFlowPlanner()
        observation = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(
                UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                UiElementId.PNC_POPUP_CLOSE_BUTTON,
            ),
            blocking_popup=True,
        )

        actions = planner.close_blocking_popup(observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_UPDATE_CONFIRM_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.full_runtime_default())
