"""Resource list gestures require current tab identity and fresh stable completion."""

from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.navigation_core import NavigationCore
from pnc_automation.app.pnc.domain.action_requests import SwipeAction
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.support.pnc.observations import make_observation


class ResourceInventoryNavigationTests(unittest.TestCase):
    """Keep Resource scroll actions inside the reviewed list surface."""

    def setUp(self):
        self.source = make_observation(
            ScreenType.PNC_BAG, visible_ids=(UiElementId.PNC_BAG_SUBTAB_RESOURCE,),
        )
        self.actuator = Mock()
        self.actuator.execute_action.return_value = True
        self.navigation = NavigationCore(self.actuator, Mock(), ())

    def test_one_fine_scroll_uses_fresh_source_and_scanner_completion(self):
        after = replace(self.source, captured_at=self.source.captured_at + timedelta(seconds=1))
        completion = Mock(return_value=after)
        result = self.navigation.scroll_resource_inventory(
            upward=True, adjusted=False, fine=True,
            observe_content=Mock(return_value=self.source), confirm_scroll=completion,
        )
        action, observed = self.actuator.execute_action.call_args.args
        self.assertIsInstance(action, SwipeAction)
        self.assertEqual((0.46, 0.64), (action.start_y_ratio, action.end_y_ratio))
        self.assertIs(self.source, observed)
        self.assertIs(after, result)
        self.assertEqual(1, self.actuator.execute_action.call_count)
        completion.assert_called_once()

    def test_unselected_tab_prevents_swipe(self):
        completion = Mock()
        sources = (
            make_observation(ScreenType.PNC_BAG),
            replace(self.source, decision=replace(self.source.decision, guard=GuardVerdict.UNRESOLVED)),
        )
        for source in sources:
            with self.subTest(guard=source.decision.guard, selected=source.has(UiElementId.PNC_BAG_SUBTAB_RESOURCE)):
                with self.assertRaisesRegex(RuntimeError, "selected Resource tab"):
                    self.navigation.scroll_resource_inventory(
                        upward=False, adjusted=False,
                        observe_content=Mock(return_value=source), confirm_scroll=completion,
                    )
        self.actuator.execute_action.assert_not_called()
        completion.assert_not_called()

    def test_stale_completion_does_not_repeat_swipe(self):
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.navigation.scroll_resource_inventory(
                upward=False, adjusted=True,
                observe_content=Mock(return_value=self.source),
                confirm_scroll=Mock(return_value=self.source),
            )
        self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_failed_gesture_does_not_claim_completion(self):
        self.actuator.execute_action.return_value = False
        completion = Mock()
        with self.assertRaisesRegex(RuntimeError, "did not execute"):
            self.navigation.scroll_resource_inventory(
                upward=False, adjusted=False,
                observe_content=Mock(return_value=self.source), confirm_scroll=completion,
            )
        self.assertEqual(1, self.actuator.execute_action.call_count)
        completion.assert_not_called()
