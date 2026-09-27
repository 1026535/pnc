"""Navigation core chat tests."""

from datetime import UTC, datetime, timedelta
import time, unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import SelectChatChannelAction
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_chat import chat_frame
from tests.support.pnc.navigation.core_frames import Actuator
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_chat_route_has_reviewed_home_entry_and_back_edges(self):
        edges = reviewed_navigation_edges()

        self.assertIn(
            (ScreenType.PNC_HOME_CITY, UiElementId.PNC_CHAT_SHORTCUT, frozenset({ScreenType.PNC_CHAT})),
            {(edge.source, edge.selector, edge.destinations) for edge in edges},
        )
        self.assertIn(
            (
                ScreenType.PNC_CHAT,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP, ScreenType.PNC_MORE_MENU}),
            ),
            {(edge.source, edge.selector, edge.destinations) for edge in edges},
        )


    def test_chat_back_replans_from_world_parent_and_returns_home_once(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)

        def frame(screen, selector, captured_at):
            return Observation(
                screen_type=screen,
                visible_elements={
                    selector: VisibleElement(
                        selector,
                        Bounds(10, 20, 40, 40),
                        1.0,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    ),
                },
                image_size=(540, 960),
                captured_at=captured_at,
            )

        frames = iter(
            (
                frame(ScreenType.PNC_CHAT, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, now),
                frame(ScreenType.PNC_CHAT, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, now + timedelta(seconds=1)),
                frame(ScreenType.PNC_WORLD_MAP, UiElementId.PNC_WORLD_HOME_NAV, now + timedelta(seconds=2)),
                frame(ScreenType.PNC_WORLD_MAP, UiElementId.PNC_WORLD_HOME_NAV, now + timedelta(seconds=3)),
                frame(ScreenType.PNC_WORLD_MAP, UiElementId.PNC_WORLD_HOME_NAV, now + timedelta(seconds=4)),
                frame(ScreenType.PNC_HOME_CITY, UiElementId.PNC_HOME_WORLD_SWITCH, now + timedelta(seconds=5)),
                frame(ScreenType.PNC_HOME_CITY, UiElementId.PNC_HOME_WORLD_SWITCH, now + timedelta(seconds=6)),
            )
        )
        observed_labels = []
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda label: (observed_labels.append(label) or next(frames)),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertEqual(ScreenType.PNC_HOME_CITY, result.screen_type)
        self.assertEqual(
            [UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_WORLD_HOME_NAV],
            [action.selector_id for action in actuator.actions],
        )
        self.assertEqual(1, sum(action.selector_id == UiElementId.PNC_BACK_BUTTON_TOP_LEFT for action in actuator.actions))
        self.assertEqual(2, len(actuator.actions))
        self.assertEqual(
            [
                "core_route_source",
                "core_1_source",
                "core_1_after_0",
                "core_1_after_1",
                "core_2_source",
                "core_2_after_0",
                "core_2_after_1",
            ],
            observed_labels,
        )


    def test_chat_back_replans_from_more_parent_to_home(self):
        """Chat Back may restore More, which has a reviewed route to Home."""

        now = datetime(2026, 9, 27, tzinfo=UTC)

        def frame(screen, selector, offset):
            return Observation(
                screen_type=screen,
                visible_elements={
                    selector: VisibleElement(
                        selector,
                        Bounds(10, 20, 40, 40),
                        1.0,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    ),
                },
                image_size=(540, 960),
                captured_at=now + timedelta(seconds=offset),
            )

        steps = (
            (ScreenType.PNC_CHAT, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            (ScreenType.PNC_CHAT, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            (ScreenType.PNC_MORE_MENU, UiElementId.PNC_MORE_SETTINGS),
            (ScreenType.PNC_MORE_MENU, UiElementId.PNC_MORE_SETTINGS),
            (ScreenType.PNC_MORE_MENU, UiElementId.PNC_MORE_SETTINGS),
            (ScreenType.PNC_SETTINGS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            (ScreenType.PNC_SETTINGS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            (ScreenType.PNC_SETTINGS, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            (ScreenType.PNC_HOME_CITY, UiElementId.PNC_HOME_WORLD_SWITCH),
            (ScreenType.PNC_HOME_CITY, UiElementId.PNC_HOME_WORLD_SWITCH),
        )
        frames = iter(frame(screen, selector, offset) for offset, (screen, selector) in enumerate(steps))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(
            [action.selector_id for action in actuator.actions],
            [
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                UiElementId.PNC_MORE_SETTINGS,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            ],
        )

    def test_select_chat_channel_returns_without_tap_when_requested_channel_is_active(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = chat_frame(ChatChannel.ALLIANCE, captured_at=now)
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: source,
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.select_chat_channel(
            ChatChannel.ALLIANCE,
            observe_content=lambda _: source,
        )

        self.assertIs(source, result)
        self.assertEqual([], actuator.actions)


    def test_select_chat_channel_requires_fresh_chat_source_and_template_tab(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        cases = (
            chat_frame(None, screen=ScreenType.PNC_HOME_CITY, captured_at=now),
            chat_frame(ChatChannel.ALLIANCE, captured_at=now),
            chat_frame(
                ChatChannel.ALLIANCE,
                selector=UiElementId.PNC_CHAT_TAB_KINGDOM,
                source_kind=VisibleElementSourceKind.GEOMETRY,
                captured_at=now,
            ),
        )
        for source in cases:
            with self.subTest(source=source.screen_type, selectors=tuple(source.visible_elements)):
                actuator = Actuator()
                core = NavigationCore(
                    actuator,
                    lambda _: source,
                    reviewed_navigation_edges(),
                    NavigationPolicy(max_observations=4),
                    sleep=lambda _: None,
                )
                with self.assertRaises(RuntimeError):
                    core.select_chat_channel(
                        ChatChannel.WORLD,
                        observe_content=lambda _: source,
                    )
                self.assertEqual([], actuator.actions)


    def test_select_chat_channel_timeout_on_wrong_or_unknown_channel_never_retaps(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = chat_frame(
            ChatChannel.ALLIANCE,
            selector=UiElementId.PNC_CHAT_TAB_KINGDOM,
            captured_at=now,
        )
        after_frames = tuple(
            chat_frame(channel, captured_at=now + timedelta(seconds=index + 1))
            for index, channel in enumerate(
                (ChatChannel.ALLIANCE, None, ChatChannel.ALLIANCE, None)
            )
        )
        frames = iter((source, *after_frames))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: source,
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.select_chat_channel(
                ChatChannel.WORLD,
                observe_content=lambda _: next(frames),
            )

        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SelectChatChannelAction)


    def test_select_chat_channel_rejects_stale_interrupted_and_late_completion_without_retapping(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = chat_frame(
            ChatChannel.WORLD,
            selector=UiElementId.PNC_CHAT_TAB_ALLIANCE,
            captured_at=now,
        )
        cases = (
            (
                "stale",
                (chat_frame(ChatChannel.ALLIANCE, captured_at=now),),
                NavigationPolicy(max_observations=4),
                None,
            ),
            (
                "interrupted",
                (chat_frame(ChatChannel.ALLIANCE, captured_at=now + timedelta(seconds=1), blocked=True),),
                NavigationPolicy(max_observations=4),
                None,
            ),
            (
                "late",
                (chat_frame(ChatChannel.ALLIANCE, captured_at=now + timedelta(seconds=1)),),
                NavigationPolicy(max_observations=4, max_seconds=1),
                iter((0.0, 0.0, 1.0)).__next__,
            ),
        )
        for name, frames, policy, clock in cases:
            with self.subTest(reason=name):
                actuator = Actuator()
                frame_iterator = iter((source, *frames))
                core = NavigationCore(
                    actuator,
                    lambda _: source,
                    reviewed_navigation_edges(),
                    policy,
                    sleep=lambda _: None,
                    clock=clock or time.monotonic,
                )
                with self.assertRaises(RuntimeError):
                    core.select_chat_channel(
                        ChatChannel.ALLIANCE,
                        observe_content=lambda _: next(frame_iterator),
                    )
                self.assertEqual(1, len(actuator.actions))


    def test_select_chat_channel_taps_once_and_requires_stable_requested_channel(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = chat_frame(
            ChatChannel.WORLD,
            selector=UiElementId.PNC_CHAT_TAB_ALLIANCE,
            captured_at=now,
        )
        after_frames = (
            chat_frame(ChatChannel.WORLD, captured_at=now + timedelta(seconds=1)),
            chat_frame(ChatChannel.ALLIANCE, captured_at=now + timedelta(seconds=2)),
            chat_frame(ChatChannel.ALLIANCE, captured_at=now + timedelta(seconds=3)),
        )
        frames = iter((source, *after_frames))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: source,
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.select_chat_channel(
            ChatChannel.ALLIANCE,
            observe_content=lambda _: next(frames),
        )

        self.assertEqual(ChatChannel.ALLIANCE, result.active_chat_channel)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SelectChatChannelAction)
        self.assertEqual(ChatChannel.ALLIANCE, actuator.actions[0].channel)
