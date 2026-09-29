"""Navigation core transitions tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationEdge,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import SwipeAction
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_mail import mail_frame
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_new_surface_returns_require_their_measured_control(self):
        for source, selector, destination in (
            (ScreenType.PNC_BLACKSMITH, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
            (ScreenType.PNC_WALL, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
            (ScreenType.PNC_RANGED_BARRACKS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
            (ScreenType.PNC_INFANTRY_BARRACKS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
            (ScreenType.PNC_TRIAL_CHALLENGE, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
            (ScreenType.PNC_TRIAL_APPLICABLE_STATS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_TRIAL_CHALLENGE),
            (ScreenType.PNC_BAG_CHEST_PREVIEW, UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE, ScreenType.PNC_BAG),
            (ScreenType.PNC_CASH_MALL, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, ScreenType.PNC_HOME_CITY),
        ):
            for present in (True, False):
                with self.subTest(source=source, present=present):
                    now = datetime.now(UTC)
                    frames = iter((
                        mail_frame(source, selector=selector if present else None, captured_at=now),
                        mail_frame(destination, captured_at=now + timedelta(seconds=1)),
                        mail_frame(destination, captured_at=now + timedelta(seconds=2)),
                    ))
                    actuator = Actuator()
                    edges = reviewed_navigation_edges()
                    core = NavigationCore(actuator, lambda _: next(frames), edges, sleep=lambda _: None)
                    edge = next(item for item in edges if item.source == source)
                    if present:
                        self.assertEqual(destination, core.transition(edge).screen_type)
                        self.assertEqual([selector], [action.selector_id for action in actuator.actions])
                    else:
                        with self.assertRaisesRegex(RuntimeError, "current-frame visual evidence"):
                            core.transition(edge)
                        self.assertEqual([], actuator.actions)


    def test_cash_mall_return_stops_on_unexpected_destination(self):
        edge = next(
            item for item in reviewed_navigation_edges() if item.source == ScreenType.PNC_CASH_MALL
        )
        self.assertEqual(frozenset({ScreenType.PNC_HOME_CITY}), edge.destinations)
        now = datetime.now(UTC)
        frames = iter((
            mail_frame(ScreenType.PNC_CASH_MALL, selector=UiElementId.PNC_BACK_BUTTON_TOP_LEFT, captured_at=now),
            mail_frame(ScreenType.PNC_WORLD_MAP, captured_at=now + timedelta(seconds=1)),
        ))
        actuator = Actuator()
        core = NavigationCore(actuator, lambda _: next(frames), reviewed_navigation_edges(), sleep=lambda _: None)

        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            core.transition(edge)
        self.assertEqual([UiElementId.PNC_BACK_BUTTON_TOP_LEFT], [action.selector_id for action in actuator.actions])


    def test_route_uses_ready_source_for_initial_and_reviewed_edge_reacquisition(self):
        """Loading-aware source reacquisition leaves post-action completion unchanged."""

        now = datetime(2026, 9, 12, tzinfo=UTC)
        home = replace(observation(ScreenType.PNC_HOME_CITY), captured_at=now)
        world = replace(observation(ScreenType.PNC_WORLD_MAP), captured_at=now + timedelta(seconds=2))
        world_after = replace(observation(ScreenType.PNC_WORLD_MAP), captured_at=now + timedelta(seconds=3))
        ready = Mock(side_effect=[home, home])
        observe = Mock(side_effect=[world, world_after])
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            observe,
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
            observe_ready=ready,
        )

        result = core.navigate(ScreenType.PNC_WORLD_MAP)

        self.assertIs(world_after, result)
        self.assertEqual(["core_route_source", "core_1_source"], [call.args[0] for call in ready.call_args_list])
        self.assertEqual(["core_1_after_0", "core_1_after_1"], [call.args[0] for call in observe.call_args_list])
        self.assertEqual(1, len(actuator.actions))


    def test_navigation_edge_rejects_unknown_destination(self):
        with self.assertRaises(ValueError):
            NavigationEdge(
                ScreenType.PNC_CHAT,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                frozenset({ScreenType.UNKNOWN}),
            )


    def test_unknown_during_transition_waits_without_retapping(self):
        home = observation(ScreenType.PNC_HOME_CITY)
        world = observation(ScreenType.PNC_WORLD_MAP)
        core, actuator, edge = self.make_core([home, observation(ScreenType.UNKNOWN), world, world])
        self.assertEqual(core.transition(edge).screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(len(actuator.actions), 1)


    def test_rank_back_replans_from_observed_world_parent(self):
        def frame(screen):
            selectors = {
                ScreenType.PNC_RANK_HUB: UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                ScreenType.PNC_WORLD_MAP: UiElementId.PNC_BOTTOM_NAV_MORE,
                ScreenType.PNC_MORE_MENU: UiElementId.PNC_MORE_SETTINGS,
            }
            selector = selectors.get(screen)
            result = observation(screen)
            if selector is None:
                return replace(result, visible_elements={})
            return replace(result, visible_elements={
                selector: VisibleElement(selector, Bounds(10, 20, 30, 40), 1.0, source_kind=VisibleElementSourceKind.TEMPLATE),
            })

        rank = frame(ScreenType.PNC_RANK_HUB)
        world = frame(ScreenType.PNC_WORLD_MAP)
        more = frame(ScreenType.PNC_MORE_MENU)
        settings = frame(ScreenType.PNC_SETTINGS)
        core, actuator, _ = self.make_core([rank, rank, world, world, world, more, more, more, settings, settings])
        self.assertEqual(core.navigate(ScreenType.PNC_SETTINGS).screen_type, ScreenType.PNC_SETTINGS)
        self.assertEqual([action.selector_id for action in actuator.actions], [
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS,
        ])


    def test_settings_back_accepts_world_but_rejects_unobserved_parent(self):
        selector = UiElementId.PNC_BACK_BUTTON_TOP_LEFT
        before = replace(observation(ScreenType.PNC_SETTINGS), visible_elements={
            selector: VisibleElement(selector, Bounds(10, 20, 30, 40), 1.0, source_kind=VisibleElementSourceKind.TEMPLATE),
        })
        for destination in (ScreenType.PNC_WORLD_MAP, ScreenType.PNC_BAG):
            after = observation(destination)
            core, actuator, _ = self.make_core([before, after, after])
            edge = next(edge for edge in core.edges if edge.source == ScreenType.PNC_SETTINGS and edge.selector == selector)
            if destination == ScreenType.PNC_WORLD_MAP:
                self.assertEqual(core.transition(edge).screen_type, destination)
            else:
                with self.assertRaisesRegex(RuntimeError, 'unexpected screen'):
                    core.transition(edge)
            self.assertEqual(len(actuator.actions), 1)


    def test_unchanged_source_exhausts_budget_without_retapping(self):
        home = observation(ScreenType.PNC_HOME_CITY)
        core, actuator, edge = self.make_core([home] * 5)
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.transition(edge)
        self.assertEqual(len(actuator.actions), 1)


    def test_stale_source_and_inferred_controls_cannot_authorize_action(self):
        for source in (observation(ScreenType.PNC_BAG), observation(ScreenType.PNC_HOME_CITY, geometry=True)):
            core, actuator, edge = self.make_core([source])
            with self.assertRaises(RuntimeError):
                core.transition(edge)
            self.assertEqual(actuator.actions, [])


    def test_popup_and_unexpected_destination_stop_without_recovery(self):
        for after in (observation(ScreenType.PNC_POPUP, blocked=True), observation(ScreenType.PNC_BAG)):
            core, actuator, edge = self.make_core([observation(ScreenType.PNC_HOME_CITY), after])
            with self.assertRaises(RuntimeError):
                core.transition(edge)
            self.assertEqual(len(actuator.actions), 1)


    def test_one_destination_frame_is_not_completion(self):
        home, world = observation(ScreenType.PNC_HOME_CITY), observation(ScreenType.PNC_WORLD_MAP)
        core, actuator, edge = self.make_core([home, world, home, world, home])
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.transition(edge)
        self.assertEqual(len(actuator.actions), 1)


    def test_unreviewed_edge_and_unreachable_route_send_no_actions(self):
        core, actuator, edge = self.make_core([observation(ScreenType.PNC_HOME_CITY)])
        with self.assertRaises(ValueError):
            core.transition(replace(edge, selector=UiElementId.PNC_BOTTOM_NAV_HERO))
        with self.assertRaisesRegex(RuntimeError, "No reviewed route"):
            core.navigate(ScreenType.PNC_HERO_HALL)
        self.assertEqual(actuator.actions, [])


    def test_stale_capture_cannot_count_as_stable_completion(self):
        home = observation(ScreenType.PNC_HOME_CITY)
        world = replace(observation(ScreenType.PNC_WORLD_MAP), captured_at=home.captured_at)
        core, actuator, edge = self.make_core([])
        frames = iter((home, world))
        core.observe = lambda _: next(frames)
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            core.transition(edge)
        self.assertEqual(len(actuator.actions), 1)


    def test_scroll_castle_roster_uses_one_typed_swipe_without_row_tap(self):
        """Keeps active-castle search to one reviewed roster gesture per call."""

        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter(
            (
                mail_frame(ScreenType.PNC_CASTLE_SELECTION, captured_at=now),
                mail_frame(ScreenType.PNC_CASTLE_SELECTION, captured_at=now + timedelta(seconds=1)),
                mail_frame(ScreenType.PNC_CASTLE_SELECTION, captured_at=now + timedelta(seconds=2)),
            )
        )
        core = NavigationCore(
            actuator,
            lambda _: mail_frame(ScreenType.PNC_CASTLE_SELECTION),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.scroll_castle_roster("down", observe_content=lambda _: next(frames))

        self.assertEqual(ScreenType.PNC_CASTLE_SELECTION, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertEqual("down", actuator.actions[0].direction)
        self.assertEqual(0.90, actuator.actions[0].start_x_ratio)
        self.assertEqual(0.18, actuator.actions[0].start_y_ratio)
        self.assertEqual(0.82, actuator.actions[0].end_y_ratio)

        with self.assertRaisesRegex(ValueError, "direction"):
            core.scroll_castle_roster("sideways", observe_content=lambda _: next(frames))
        self.assertEqual(1, len(actuator.actions))
