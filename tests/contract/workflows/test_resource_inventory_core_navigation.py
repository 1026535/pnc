"""Resource list gestures require current tab identity and fresh stable completion."""

from dataclasses import replace
from datetime import timedelta
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapAction
from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.support.pnc.observations import make_observation


class ResourceInventoryNavigationTests(unittest.TestCase):
    """Keep Resource scroll actions inside the reviewed list surface."""

    def setUp(self):
        self.source = make_observation(
            ScreenType.PNC_BAG, visible_ids=(UiElementId.PNC_BAG_SUBTAB_RESOURCE,),
            active_bag_tab=BagTab.RESOURCE,
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
            make_observation(
                ScreenType.PNC_BAG,
                visible_ids=(UiElementId.PNC_BAG_SUBTAB_RESOURCE,),
                active_bag_tab=BagTab.SPEEDUP,
            ),
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

    def test_delayed_completion_after_deadline_does_not_claim_scroll(self):
        clock = _FakeClock()
        self.navigation = NavigationCore(
            self.actuator, Mock(), (),
            policy=NavigationPolicy(max_seconds=1.0), clock=clock,
        )
        after = replace(self.source, captured_at=self.source.captured_at + timedelta(seconds=1))

        def delayed_completion():
            clock.advance(1.0)
            return after

        with self.assertRaisesRegex(RuntimeError, "completion budget exhausted"):
            self.navigation.scroll_resource_inventory(
                upward=True, adjusted=False,
                observe_content=Mock(return_value=self.source), confirm_scroll=delayed_completion,
            )

        self.actuator.execute_action.assert_called_once()


class BagTabSelectionTests(unittest.TestCase):
    """Typed Bag subtab selection uses measured controls and typed completion."""

    def setUp(self):
        self.actuator = Mock()
        self.actuator.execute_action.return_value = True
        self.navigation = NavigationCore(
            self.actuator, Mock(), (),
            policy=NavigationPolicy(max_observations=4, poll_seconds=0, stable_observations=2),
            sleep=lambda _: None,
        )

    def _bag(self, tab: BagTab | None, *, seconds: int = 0, extra_ids=()):
        observation = make_observation(
            ScreenType.PNC_BAG,
            visible_ids=(
                UiElementId.PNC_BAG_SUBTAB_RESOURCE,
                UiElementId.PNC_BAG_SUBTAB_SPEEDUP,
                UiElementId.PNC_BAG_SUBTAB_TREASURE,
            ) + extra_ids,
            active_bag_tab=tab,
        )
        if seconds:
            observation = replace(
                observation, captured_at=observation.captured_at + timedelta(seconds=seconds),
            )
        return observation

    def _observer(self, *observations):
        sequence = iter(observations)
        return Mock(side_effect=lambda _label: next(sequence))

    def test_speedup_start_selects_resource_with_measured_control(self):
        before = self._bag(BagTab.SPEEDUP)
        after_one = self._bag(BagTab.RESOURCE, seconds=1)
        after_two = self._bag(BagTab.RESOURCE, seconds=2)
        result = self.navigation.select_bag_tab(
            BagTab.RESOURCE, observe_content=self._observer(before, after_one, after_two),
        )
        action, observed = self.actuator.execute_action.call_args.args
        self.assertIsInstance(action, TapAction)
        self.assertEqual(UiElementId.PNC_BAG_SUBTAB_RESOURCE, action.selector_id)
        self.assertIs(before, observed)
        self.assertIs(after_two, result)
        self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_already_selected_tab_is_a_noop(self):
        before = self._bag(BagTab.RESOURCE)
        result = self.navigation.select_bag_tab(
            BagTab.RESOURCE, observe_content=self._observer(before),
        )
        self.assertIs(before, result)
        self.actuator.execute_action.assert_not_called()

    def test_unknown_selection_or_unresolved_guard_does_not_tap(self):
        selected = self._bag(BagTab.SPEEDUP)
        sources = (
            self._bag(None),
            replace(selected, decision=replace(selected.decision, guard=GuardVerdict.UNRESOLVED)),
        )
        for before in sources:
            with self.subTest(tab=before.active_bag_tab, guard=before.decision.guard):
                with self.assertRaisesRegex(RuntimeError, "freshly observed"):
                    self.navigation.select_bag_tab(
                        BagTab.RESOURCE, observe_content=self._observer(before),
                    )
                self.actuator.execute_action.assert_not_called()

    def test_unclear_target_completion_does_not_succeed(self):
        before = self._bag(BagTab.SPEEDUP)
        afters = tuple(
            replace(after, decision=replace(after.decision, guard=GuardVerdict.UNRESOLVED))
            for after in (self._bag(BagTab.RESOURCE, seconds=index + 1) for index in range(4))
        )
        with self.assertRaisesRegex(RuntimeError, "completion budget exhausted"):
            self.navigation.select_bag_tab(
                BagTab.RESOURCE, observe_content=self._observer(before, *afters),
            )
        self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_mismatched_tab_completion_fails_closed(self):
        before = self._bag(BagTab.SPEEDUP)
        afters = tuple(self._bag(BagTab.SPEEDUP, seconds=index + 1) for index in range(4))
        with self.assertRaisesRegex(RuntimeError, "completion budget exhausted"):
            self.navigation.select_bag_tab(
                BagTab.RESOURCE, observe_content=self._observer(before, *afters),
            )
        self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_stale_completion_is_rejected(self):
        before = self._bag(BagTab.SPEEDUP)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.navigation.select_bag_tab(
                BagTab.RESOURCE, observe_content=self._observer(before, before),
            )
        self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_military_and_misc_select_with_measured_controls(self):
        for tab, selector in (
            (BagTab.MILITARY, UiElementId.PNC_BAG_SUBTAB_MILITARY),
            (BagTab.MISC, UiElementId.PNC_BAG_SUBTAB_MISC),
        ):
            with self.subTest(tab=tab):
                self.actuator.execute_action.reset_mock()
                before = self._bag(BagTab.TREASURE, extra_ids=(selector,))
                after_one = self._bag(tab, seconds=1, extra_ids=(selector,))
                after_two = self._bag(tab, seconds=2, extra_ids=(selector,))
                result = self.navigation.select_bag_tab(
                    tab, observe_content=self._observer(before, after_one, after_two),
                )
                action, observed = self.actuator.execute_action.call_args.args
                self.assertIsInstance(action, TapAction)
                self.assertEqual(selector, action.selector_id)
                self.assertIs(before, observed)
                self.assertIs(after_two, result)
                self.assertEqual(tab, result.active_bag_tab)
                self.assertEqual(1, self.actuator.execute_action.call_count)

    def test_unsupported_tab_has_no_measured_control(self):
        before = self._bag(BagTab.SPEEDUP)
        with self.assertRaisesRegex(RuntimeError, "visual evidence"):
            self.navigation.select_bag_tab(
                BagTab.MILITARY, observe_content=self._observer(before),
            )
        self.actuator.execute_action.assert_not_called()

    def test_non_template_control_does_not_tap(self):
        before = make_observation(
            ScreenType.PNC_BAG,
            visible_ids=(UiElementId.PNC_BAG_SUBTAB_RESOURCE,),
            source_kinds={UiElementId.PNC_BAG_SUBTAB_RESOURCE: VisibleElementSourceKind.OCR},
            active_bag_tab=BagTab.SPEEDUP,
        )
        with self.assertRaisesRegex(RuntimeError, "visual evidence"):
            self.navigation.select_bag_tab(
                BagTab.RESOURCE, observe_content=self._observer(before),
            )
        self.actuator.execute_action.assert_not_called()


class _FakeClock:
    """Deterministic monotonic clock for gesture completion tests."""

    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds
