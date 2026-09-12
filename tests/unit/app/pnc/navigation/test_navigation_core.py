"""Replacement navigation must prove a transition, not retry an uncertain tap."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationEdge,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import (
    SelectChatChannelAction,
    SwipeAction,
    TapPointAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.mail import (
    MailboxAvailability,
    MailboxType,
    mail_thread_row_key,
)
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.popup import decide_popup_recovery
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.spatial_navigation import home_city_scan_step_budget, home_city_scan_steps
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition, load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult, OcrService
from pnc_automation.core.errors import SelectorResolutionError
from tests.support.paths import REPOSITORY_ROOT, TEST_DATA_ROOT


def _perception(recognizer, guard, *, ocr_service=None):
    backend = ocr_service if ocr_service is not None else getattr(guard, "ocr_service", None)
    if backend is None:
        backend = Mock(spec=OcrService)
        backend.read_result.return_value = OcrResult(lines=(), words=())
    return NavigationPerception(
        recognizer, guard, ScreenClassifier(),
        lambda capture: ObservationOcrContext(capture.image, backend, capture.frame_ref, 'test'),
    )


def _frame_ref(label: str) -> FrameRef:
    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )


class Actuator:
    def __init__(self):
        self.actions = []

    def execute_action(self, action, observation):
        self.actions.append(action)
        return True


class Guard:
    def __init__(self, screen=None):
        self.screen = screen
        self.ocr_service = Mock(spec=OcrService)
        self.ocr_service.read_result.return_value = OcrResult(lines=(), words=())

    def detect_interruption(
        self, image, *, ocr_context, owned_dismiss_bounds=(), owned_navigation_screen=None,
    ):
        del image, ocr_context, owned_dismiss_bounds, owned_navigation_screen
        evidence = () if self.screen is None else (ScreenEvidence(self.screen, "test_interruption"),)
        return ObservationAdditions(screen_evidence=evidence, guard_verdict=GuardVerdict.BLOCKED if evidence else GuardVerdict.CLEAR)


def observation(screen, *, geometry=False, blocked=False):
    return Observation(
        decision=ScreenDecision(
            base_screen=screen,
            effective_screen=screen,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
        ),
        visible_elements={UiElementId.PNC_HOME_WORLD_SWITCH: VisibleElement(
            UiElementId.PNC_HOME_WORLD_SWITCH, Bounds(10, 20, 30, 40), 0.99,
            source_kind=VisibleElementSourceKind.GEOMETRY if geometry else VisibleElementSourceKind.TEMPLATE,
        )},
    )


def mail_frame(
    screen: ScreenType,
    *,
    selector: UiElementId | None = None,
    entries: tuple[DetectedListEntry, ...] = (),
    captured_at: datetime | None = None,
    blocked: bool = False,
) -> Observation:
    """Build one typed mail frame with optional current-frame template control."""

    visible_elements = {}
    if selector is not None:
        visible_elements[selector] = VisibleElement(
            selector,
            Bounds(10, 20, 40, 40),
            1.0,
            source_kind=VisibleElementSourceKind.TEMPLATE,
        )
    return Observation(
        screen_type=screen,
        visible_elements=visible_elements,
        list_entries=entries,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def chat_frame(
    active_channel: ChatChannel | None,
    *,
    selector: UiElementId | None = None,
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    captured_at: datetime | None = None,
    blocked: bool = False,
    screen: ScreenType = ScreenType.PNC_CHAT,
) -> Observation:
    """Build one typed Chat frame with optional current-frame tab evidence."""

    visible_elements = {}
    if selector is not None:
        visible_elements[selector] = VisibleElement(
            selector,
            Bounds(10, 20, 40, 40),
            1.0,
            source_kind=source_kind,
        )
    return Observation(
        screen_type=screen,
        visible_elements=visible_elements,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
        active_chat_channel=active_channel,
    )


def home_building_object(
    target: HomeCityObjectId,
    *,
    action_point: tuple[int, int] | None = (270, 520),
) -> DetectedSpatialObject:
    """Build one exact observed home-city building candidate for navigation tests."""

    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=Bounds(220, 470, 100, 100),
        action_point=action_point,
        metadata={"home_city_object_id": target.value},
    )


def home_building_frame(
    objects: tuple[DetectedSpatialObject, ...] = (),
    *,
    captured_at: datetime | None = None,
    image_size: tuple[int, int] | None = (540, 960),
    blocked: bool = False,
) -> Observation:
    """Build one typed Home frame with a canonical camera-relative spatial surface."""

    return Observation(
        screen_type=ScreenType.PNC_HOME_CITY,
        visible_elements={},
        spatial_surface=SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
        ),
        image_size=image_size,
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def mailbox_category(mailbox: MailboxType, *, available: bool) -> DetectedListEntry:
    """Build one typed mail-hub category entry for constrained navigation tests."""

    return DetectedListEntry(
        kind=ListEntryKind.MAILBOX_CATEGORY,
        bounds=Bounds(20, 150, 500, 80),
        title_text=f"{mailbox.value} mail",
        action_point=(480, 190),
        metadata={"mailbox_type": mailbox.value, "available": available},
    )


def mail_thread_entry(title: str = "Lux") -> DetectedListEntry:
    """Build one canonical dynamic mailbox row."""

    return DetectedListEntry(
        kind=ListEntryKind.MAIL_THREAD,
        bounds=Bounds(20, 160, 500, 100),
        title_text=title,
        subtitle_text="Daily Donation Rank Reward",
        action_point=(270, 210),
        metadata={"date_text": "2026/09/11 20:02:00"},
    )


class NavigationCoreTests(unittest.TestCase):
    def make_core(self, frames):
        actuator = Actuator()
        now = datetime.now(UTC)
        iterator = iter(replace(frame, captured_at=now + timedelta(seconds=index)) for index, frame in enumerate(frames))
        core = NavigationCore(actuator, lambda _: next(iterator), reviewed_navigation_edges(),
                              NavigationPolicy(max_observations=4), sleep=lambda _: None)
        return core, actuator, core.edges[0]

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
                frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP}),
            ),
            {(edge.source, edge.selector, edge.destinations) for edge in edges},
        )

    def test_development_research_tree_edges_are_limited_to_observed_route(self):
        """Keeps only the measured Development entry and ResearchTree Back return edges."""

        edges = {
            (edge.source, edge.selector, edge.destinations)
            for edge in reviewed_navigation_edges()
        }

        self.assertIn(
            (
                ScreenType.PNC_INSTITUTE,
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                frozenset({ScreenType.PNC_RESEARCH_TREE}),
            ),
            edges,
        )
        self.assertIn(
            (
                ScreenType.PNC_RESEARCH_TREE,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                frozenset({ScreenType.PNC_INSTITUTE}),
            ),
            edges,
        )
        self.assertEqual(
            {
                item
                for item in edges
                if (
                    item[0] == ScreenType.PNC_RESEARCH_TREE
                    or item[1] == UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON
                )
            },
            {
                (
                    ScreenType.PNC_INSTITUTE,
                    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                    frozenset({ScreenType.PNC_RESEARCH_TREE}),
                ),
                (
                    ScreenType.PNC_RESEARCH_TREE,
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                    frozenset({ScreenType.PNC_INSTITUTE}),
                ),
            },
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

    def test_navigation_edge_rejects_unknown_destination(self):
        with self.assertRaises(ValueError):
            NavigationEdge(
                ScreenType.PNC_CHAT,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                frozenset({ScreenType.UNKNOWN}),
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

    def test_building_uses_observed_point_and_rejects_absent_or_duplicate_target(self):
        image = Image.new('RGB', (540, 960))
        surface = build_home_city_spatial_surface(
            image=image, selector_registry=None,
            lines=(OcrLine('Goddess Statue', Bounds(220, 600, 110, 20), 1.0),),
        )
        home = replace(observation(ScreenType.PNC_HOME_CITY), spatial_surface=surface, image_size=image.size)
        core, actuator, _ = self.make_core([
            observation(ScreenType.PNC_GODDESS_STATUE), observation(ScreenType.PNC_GODDESS_STATUE),
        ])
        core.open_visible_building(HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: home)
        self.assertEqual(len(actuator.actions), 1)
        self.assertEqual(actuator.actions[0].target_point, (275, 524))
        for objects in ((), surface.objects * 2):
            core, actuator, _ = self.make_core([])
            candidate = replace(home, spatial_surface=replace(surface, objects=objects))
            with self.assertRaisesRegex(RuntimeError, 'absent or ambiguous'):
                core.open_visible_building(HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: candidate)
            self.assertEqual(actuator.actions, [])

    def test_castle_building_opens_from_observed_point_and_returns_home_by_template_back(self):
        target = home_building_object(HomeCityObjectId.CASTLE)
        now = datetime(2026, 9, 12, tzinfo=UTC)

        def castle_frame(captured_at: datetime) -> Observation:
            return replace(
                observation(ScreenType.PNC_CASTLE),
                visible_elements={
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT: VisibleElement(
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        Bounds(22, 8, 58, 38),
                        0.99,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    ),
                },
                image_size=(540, 960),
                captured_at=captured_at,
            )

        def home_frame(captured_at: datetime) -> Observation:
            return replace(
                observation(ScreenType.PNC_HOME_CITY),
                image_size=(540, 960),
                captured_at=captured_at,
            )

        frames = iter(
            (
                castle_frame(now + timedelta(seconds=1)),
                castle_frame(now + timedelta(seconds=2)),
                castle_frame(now + timedelta(seconds=3)),
                castle_frame(now + timedelta(seconds=4)),
                home_frame(now + timedelta(seconds=5)),
                home_frame(now + timedelta(seconds=6)),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        opened = core.open_visible_building(
            HomeCityObjectId.CASTLE,
            observe_content=lambda _: home_building_frame((target,), captured_at=now),
        )
        returned = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertEqual(ScreenType.PNC_CASTLE, opened.screen_type)
        self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((270, 520), actuator.actions[0].target_point)
        self.assertEqual(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, actuator.actions[1].selector_id)

    def test_public_home_scan_sequence_and_budget_match_canonical_navigator(self):
        steps = home_city_scan_steps()

        self.assertEqual(6, len(steps))
        self.assertEqual(18, home_city_scan_step_budget())
        self.assertEqual(
            (0.45, 0.54, 0.45, 0.26),
            (steps[-1].start_x_ratio, steps[-1].start_y_ratio, steps[-1].end_x_ratio, steps[-1].end_y_ratio),
        )

    def test_open_building_visible_target_uses_no_scan_gesture(self):
        target = home_building_object(HomeCityObjectId.GODDESS_STATUE)
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            (
                home_building_frame((target,), captured_at=now),
                home_building_frame((target,), captured_at=now + timedelta(seconds=1)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_GODDESS_STATUE),
                observation(ScreenType.PNC_GODDESS_STATUE),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.open_building(
            HomeCityObjectId.GODDESS_STATUE,
            observe_content=lambda _: next(content_frames),
        )

        self.assertEqual(ScreenType.PNC_GODDESS_STATUE, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((270, 520), actuator.actions[0].target_point)

    def test_open_building_scans_home_then_reacquires_before_one_target_tap(self):
        target = home_building_object(HomeCityObjectId.GODDESS_STATUE)
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            (
                home_building_frame(captured_at=now),
                home_building_frame((target,), captured_at=now + timedelta(seconds=1)),
                home_building_frame((target,), captured_at=now + timedelta(seconds=2)),
                home_building_frame((target,), captured_at=now + timedelta(seconds=3)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_GODDESS_STATUE),
                observation(ScreenType.PNC_GODDESS_STATUE),
            )
        )
        records: list[dict[str, object]] = []
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
            record=records.append,
        )

        result = core.open_building(
            HomeCityObjectId.GODDESS_STATUE,
            observe_content=lambda _: next(content_frames),
        )

        self.assertEqual(ScreenType.PNC_GODDESS_STATUE, result.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertEqual(home_city_scan_steps()[0], actuator.actions[0])
        self.assertIsInstance(actuator.actions[1], TapSpatialObjectAction)
        self.assertEqual((270, 520), actuator.actions[1].target_point)
        pending = [entry for entry in records if entry.get("event") == "pending_building_scan"]
        self.assertEqual(1, len(pending))
        self.assertEqual(HomeCityObjectId.GODDESS_STATUE.value, pending[0]["target"])
        self.assertEqual(1, pending[0]["step"])

    def test_open_building_rejects_target_loss_before_tap_after_scan(self):
        target = home_building_object(HomeCityObjectId.GODDESS_STATUE)
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            (
                home_building_frame(captured_at=now),
                home_building_frame((target,), captured_at=now + timedelta(seconds=1)),
                home_building_frame((target,), captured_at=now + timedelta(seconds=2)),
                home_building_frame(captured_at=now + timedelta(seconds=3)),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_GODDESS_STATUE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(RuntimeError, "absent"):
            core.open_building(
                HomeCityObjectId.GODDESS_STATUE,
                observe_content=lambda _: next(content_frames),
            )

        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)

    def test_open_building_continues_scan_for_target_in_fixed_hud_region(self):
        target = home_building_object(HomeCityObjectId.GODDESS_STATUE, action_point=(434, 654))
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            (
                home_building_frame((target,), captured_at=now),
                home_building_frame((target,), captured_at=now + timedelta(seconds=1)),
                home_building_frame((target,), captured_at=now + timedelta(seconds=2)),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_GODDESS_STATUE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.home_city_scan_step_budget",
            return_value=1,
        ):
            with self.assertRaisesRegex(RuntimeError, "exhausted"):
                core.open_building(
                    HomeCityObjectId.GODDESS_STATUE,
                    observe_content=lambda _: next(content_frames),
                )

        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)

    def test_open_building_fails_closed_for_unsafe_scan_frames_without_swipe(self):
        target = home_building_object(HomeCityObjectId.GODDESS_STATUE, action_point=(540, 520))
        now = datetime(2026, 9, 12, tzinfo=UTC)
        cases = (
            (home_building_frame(captured_at=now, image_size=None), "image dimensions"),
            (home_building_frame((home_building_object(HomeCityObjectId.GODDESS_STATUE, action_point=None),), captured_at=now), "action point"),
            (home_building_frame((target,), captured_at=now), "out-of-image"),
            (home_building_frame((home_building_object(HomeCityObjectId.GODDESS_STATUE, action_point=("bad", 520)),), captured_at=now), "malformed"),  # type: ignore[arg-type]
            (home_building_frame((target, home_building_object(HomeCityObjectId.GODDESS_STATUE)), captured_at=now), "ambiguous"),
        )
        for frame, message in cases:
            with self.subTest(message=message):
                actuator = Actuator()
                core = NavigationCore(
                    actuator,
                    lambda _: observation(ScreenType.PNC_GODDESS_STATUE),
                    reviewed_navigation_edges(),
                    NavigationPolicy(max_observations=4),
                    sleep=lambda _: None,
                )
                with self.assertRaisesRegex(RuntimeError, message):
                    core.open_building(
                        HomeCityObjectId.GODDESS_STATUE,
                        observe_content=lambda _: frame,
                    )
                self.assertEqual([], actuator.actions)

    def test_open_building_stops_scan_on_unknown_popup_or_stale_follow_up(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        initial = home_building_frame(captured_at=now)
        for follow_up in (
            Observation(screen_type=ScreenType.UNKNOWN, visible_elements={}, captured_at=now + timedelta(seconds=1)),
            Observation(screen_type=ScreenType.PNC_BAG, visible_elements={}, captured_at=now + timedelta(seconds=1)),
            home_building_frame(captured_at=now, blocked=False),
            home_building_frame(captured_at=now + timedelta(seconds=1), blocked=True),
        ):
            with self.subTest(screen=follow_up.screen_type, blocked=follow_up.blocking_popup):
                actuator = Actuator()
                content_frames = iter((initial, follow_up))
                core = NavigationCore(
                    actuator,
                    lambda _: observation(ScreenType.PNC_GODDESS_STATUE),
                    reviewed_navigation_edges(),
                    NavigationPolicy(max_observations=4),
                    sleep=lambda _: None,
                )
                with self.assertRaises(RuntimeError):
                    core.open_building(
                        HomeCityObjectId.GODDESS_STATUE,
                        observe_content=lambda _: next(content_frames),
                    )
                self.assertEqual(1, len(actuator.actions))
                self.assertIsInstance(actuator.actions[0], SwipeAction)

    def test_open_building_rejects_unsupported_route_before_observation(self):
        observed = Mock()
        core = NavigationCore(
            Actuator(),
            lambda _: observation(ScreenType.PNC_HOME_CITY),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(ValueError, "return route"):
            core.open_building(HomeCityObjectId.CAMPAIGN, observe_content=observed)

        observed.assert_not_called()

    def test_institute_focus_is_not_mistaken_for_opening_the_building(self):
        def control_frame(screen, selector):
            return replace(observation(screen), visible_elements={
                selector: VisibleElement(selector, Bounds(100, 100, 40, 20), 0.99),
            })

        home = control_frame(ScreenType.PNC_HOME_CITY, UiElementId.PNC_HOME_RESEARCH_BUTTON)
        queue = control_frame(ScreenType.PNC_RESEARCH_QUEUE, UiElementId.PNC_RESEARCH_QUEUE_GO)
        institute = observation(ScreenType.PNC_INSTITUTE)
        surface = build_home_city_spatial_surface(
            image=Image.new('RGB', (540, 960)), selector_registry=None,
            lines=(OcrLine('Institute', Bounds(240, 510, 60, 20), 1.0),),
        )
        for visible in (True, False):
            core, actuator, _ = self.make_core([
                home, home, queue, queue, queue, home, home, institute, institute,
            ])
            content = replace(home, image_size=(540, 960), spatial_surface=replace(
                surface, objects=surface.objects if visible else (),
            ))
            if visible:
                result = core.open_building(HomeCityObjectId.INSTITUTE, observe_content=lambda _: content)
                self.assertEqual(result.screen_type, ScreenType.PNC_INSTITUTE)
                self.assertEqual(actuator.actions[-1].target_point, (270, 520))
            else:
                with self.assertRaisesRegex(RuntimeError, 'absent or ambiguous'):
                    core.open_building(HomeCityObjectId.INSTITUTE, observe_content=lambda _: content)
            self.assertEqual(actuator.actions[0].selector_id, UiElementId.PNC_HOME_RESEARCH_BUTTON)
            self.assertEqual(actuator.actions[1].selector_id, UiElementId.PNC_RESEARCH_QUEUE_GO)
            self.assertEqual(len(actuator.actions), 3 if visible else 2)

    def test_open_mailbox_unavailable_category_returns_without_tap(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        core = NavigationCore(
            actuator,
            lambda _: mail_frame(ScreenType.PNC_MAIL_HUB, selector=UiElementId.PNC_MAIL_ROW_PLAYER_MAIL),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        hub = mail_frame(
            ScreenType.PNC_MAIL_HUB,
            entries=(mailbox_category(MailboxType.PLAYER, available=False),),
            captured_at=now,
        )
        self.assertEqual(
            core.open_mailbox(MailboxType.PLAYER, observe_content=lambda _: hub),
            MailboxAvailability.UNAVAILABLE,
        )
        self.assertEqual(actuator.actions, [])

    def test_open_mailbox_available_category_uses_exact_reviewed_tap_once(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter(
            (
                mail_frame(ScreenType.PNC_MAIL_HUB, selector=UiElementId.PNC_MAIL_ROW_PLAYER_MAIL, captured_at=now),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=1)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=2)),
            )
        )
        core = NavigationCore(
            actuator,
            lambda _: next(frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        hub = mail_frame(
            ScreenType.PNC_MAIL_HUB,
            entries=(mailbox_category(MailboxType.PLAYER, available=True),),
            captured_at=now,
        )
        self.assertEqual(
            core.open_mailbox(MailboxType.PLAYER, observe_content=lambda _: hub),
            MailboxAvailability.AVAILABLE,
        )
        self.assertEqual(len(actuator.actions), 1)
        self.assertEqual(actuator.actions[0].selector_id, UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)

    def test_open_mailbox_ambiguous_or_missing_category_sends_no_action(self):
        for entries in (
            (),
            (mailbox_category(MailboxType.PLAYER, available=True), mailbox_category(MailboxType.PLAYER, available=True)),
        ):
            actuator = Actuator()
            core = NavigationCore(
                actuator,
                lambda _: mail_frame(ScreenType.PNC_MAIL_HUB),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaisesRegex(RuntimeError, "missing or ambiguous"):
                core.open_mailbox(
                    MailboxType.PLAYER,
                    observe_content=lambda _: mail_frame(ScreenType.PNC_MAIL_HUB, entries=entries),
                )
            self.assertEqual(actuator.actions, [])

    def test_open_mail_thread_matches_one_row_and_rejects_stale_or_popup_completion(self):
        row = mail_thread_entry()
        row_key = mail_thread_row_key(row)
        now = datetime(2026, 9, 12, tzinfo=UTC)
        for completion in (
            (
                mail_frame(ScreenType.PNC_MAIL_THREAD, captured_at=now),
                mail_frame(ScreenType.PNC_MAIL_THREAD, captured_at=now),
            ),
            (
                mail_frame(ScreenType.PNC_POPUP, blocked=True, captured_at=now + timedelta(seconds=1)),
            ),
        ):
            actuator = Actuator()
            frames = iter(completion)
            core = NavigationCore(
                actuator,
                lambda _: next(frames),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaises(RuntimeError):
                core.open_mail_thread(
                    row_key,
                    observe_content=lambda _: mail_frame(
                        ScreenType.PNC_MAILBOX_LIST,
                        entries=(row,),
                        captured_at=now,
                    ),
                )
            self.assertEqual(len(actuator.actions), 1)
            self.assertIsInstance(actuator.actions[0], TapPointAction)

    def test_open_mail_thread_missing_or_ambiguous_row_sends_no_action(self):
        row = mail_thread_entry()
        for entries in ((), (row, row)):
            actuator = Actuator()
            core = NavigationCore(
                actuator,
                lambda _: mail_frame(ScreenType.PNC_MAIL_THREAD),
                reviewed_navigation_edges(),
                NavigationPolicy(max_observations=4),
                sleep=lambda _: None,
            )
            with self.assertRaisesRegex(RuntimeError, "absent, ambiguous"):
                core.open_mail_thread(
                    mail_thread_row_key(row),
                    observe_content=lambda _: mail_frame(ScreenType.PNC_MAILBOX_LIST, entries=entries),
                )
            self.assertEqual(actuator.actions, [])

    def test_scroll_mailbox_uses_one_bounded_swipe_without_replay(self):
        actuator = Actuator()
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter(
            (
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=1)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=2)),
                mail_frame(ScreenType.PNC_MAILBOX_LIST, captured_at=now + timedelta(seconds=3)),
            )
        )
        core = NavigationCore(
            actuator,
            lambda _: mail_frame(ScreenType.PNC_MAILBOX_LIST),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        result = core.scroll_mailbox(observe_content=lambda _: next(frames))
        self.assertEqual(result.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(len(actuator.actions), 1)
        self.assertIsInstance(actuator.actions[0], SwipeAction)

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

        with self.assertRaisesRegex(ValueError, "direction"):
            core.scroll_castle_roster("sideways", observe_content=lambda _: next(frames))
        self.assertEqual(1, len(actuator.actions))


class NavigationPerceptionTests(unittest.TestCase):
    def capture(self, name):
        with Image.open(TEST_DATA_ROOT / 'screen_recognition' / name) as image:
            return CapturedScreenshot(None, image.copy(), "PNG", ephemeral_captured_at=datetime.now(UTC))

    def test_measured_controls_and_resolution_projection(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        for size in ((540, 960), (900, 1600)):
            capture = self.capture('home_city_core.png')
            result = perception.build(replace(capture, image=capture.image.resize(size)))
            self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
            control = result.require(UiElementId.PNC_BOTTOM_NAV_QUEST)
            x, y = control.bounds.center()
            self.assertTrue(190 <= x * 540 / size[0] <= 253)
            self.assertTrue(900 <= y * 960 / size[1] <= 958)
            self.assertTrue(all(c.source_kind == VisibleElementSourceKind.TEMPLATE for c in result.visible_elements.values()))

    def test_chat_content_capture_uses_transcript_scope_and_preserves_chat_state(self):
        """Uses the transcript request for Chat and carries its typed state through perception."""

        class ChatGuard(Guard):
            def __init__(self):
                super().__init__()
                self.requests = []

            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions):
                del image, screen_type, visible_elements, ocr_context, ocr_regions
                self.requests.append(request)
                return ObservationAdditions(
                    screen_evidence=(ScreenEvidence(ScreenType.PNC_CHAT, "chat_content"),),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=True,
                    chat_draft_text=None,
                )

        guard = ChatGuard()
        result = _perception(load_visual_screen_recognizer(), guard).build(
            self.capture("chat_alliance.png"),
            include_content=True,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_CHAT)
        self.assertTrue(result.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertTrue(result.has(UiElementId.PNC_CHAT_TAB_KINGDOM))
        self.assertTrue(result.has(UiElementId.PNC_CHAT_TAB_ALLIANCE))
        self.assertEqual(result.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(result.chat_draft_empty)
        self.assertIsNone(result.chat_draft_text)
        self.assertEqual(guard.requests, [ObservationRequest.chat_transcript_observation()])

    def test_missing_control_does_not_invent_a_click_or_erase_identity(self):
        capture = self.capture('home_city_core.png')
        capture.image.paste((0, 0, 0), (195, 899, 249, 960))
        result = _perception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertFalse(result.has(UiElementId.PNC_BOTTOM_NAV_QUEST))

    def test_sanitized_home_city_x_regression_keeps_home_controls_and_no_popup(self):
        """Keeps the reviewed Home identity when a HUD sparkle resembles a popup X."""

        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        with Image.open(Path('tests/data/screen_recognition/home_city_popup_x_regression.png')) as image:
            capture = CapturedScreenshot(
                None,
                image.copy(),
                'PNG',
                ephemeral_captured_at=datetime.now(UTC),
            )

        guard = Guard()
        guard.ocr_service = ocr
        result = _perception(load_visual_screen_recognizer(), guard).build(capture)

        self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertFalse(result.blocking_popup)
        self.assertFalse(result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
        self.assertTrue(result.has(UiElementId.PNC_HOME_WORLD_SWITCH))
        self.assertTrue(result.has(UiElementId.PNC_HOME_RESEARCH_BUTTON))
        self.assertTrue(result.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_overlay_blocks_even_when_background_header_survives(self):
        result = _perception(load_visual_screen_recognizer(), Guard(ScreenType.PNC_POPUP)).build(self.capture('update_over_bag.png'))
        self.assertTrue(result.blocking_popup)
        self.assertEqual(result.visible_elements, {})

    def test_real_visual_popup_fixtures_preserve_scaled_close_evidence(self):
        """Carries measured generic-popup close evidence through navigation perception."""

        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = _perception(
            load_visual_screen_recognizer(), PncObservationEnricher(), ocr_service=ocr,
        )
        for fixture_name in (
            'generic_popup_quit_real_sanitized.png',
            'generic_popup_offer_real_sanitized.png',
        ):
            with self.subTest(fixture=fixture_name):
                capture = self.capture(fixture_name)
                capture = replace(capture, image=capture.image.resize((900, 1600)))
                result = perception.build(capture)
                base = perception.build(self.capture(fixture_name))

                self.assertEqual(ScreenType.PNC_POPUP, result.screen_type)
                self.assertTrue(result.blocking_popup)
                self.assertEqual((900, 1600), result.popup_overlay.image_size)
                candidate = result.popup_overlay.candidates[0]
                close_button = result.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
                self.assertEqual(candidate.action_point, close_button.action_point)
                expected = tuple(round(value * 900 / 540) for value in base.popup_overlay.candidates[0].action_point)
                for actual, scaled in zip(candidate.action_point, expected):
                    self.assertLessEqual(abs(actual - scaled), 2)
                self.assertEqual(VisibleElementSourceKind.GEOMETRY, close_button.source_kind)

    def test_near_black_frame_is_loading_but_ordinary_dark_unknown_stays_unknown(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        for color, expected in (((5, 5, 5), ScreenType.PNC_LOADING), ((24, 24, 24), ScreenType.UNKNOWN)):
            with self.subTest(color=color):
                image = Image.new('RGB', (540, 960), color)
                result = perception.build(
                    CapturedScreenshot(None, image, 'PNG', ephemeral_captured_at=datetime.now(UTC))
                )
                self.assertEqual(expected, result.screen_type)
                self.assertFalse(result.blocking_popup)
                self.assertEqual({}, result.visible_elements)

    def test_sparse_bright_region_keeps_black_frame_unknown(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        image = Image.new('RGB', (540, 960), (0, 0, 0))
        image.paste((255, 255, 255), (10, 10, 14, 14))

        result = perception.build(
            CapturedScreenshot(None, image, 'PNG', ephemeral_captured_at=datetime.now(UTC))
        )

        self.assertEqual(ScreenType.UNKNOWN, result.screen_type)
        self.assertFalse(result.blocking_popup)
        self.assertEqual({}, result.visible_elements)

    def test_task_owned_interruption_control_survives_perception_but_stays_blocked(self):
        """Perception reports task-owned evidence while recovery authorization rejects it."""

        class _TaskOwnedGuard(Guard):
            def detect_interruption(
                self, image, *, ocr_context, owned_dismiss_bounds=(), owned_navigation_screen=None,
            ):
                del image, ocr_context, owned_dismiss_bounds, owned_navigation_screen
                selector = UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON
                return ObservationAdditions(
                    visible_elements={selector: VisibleElement(
                        selector,
                        Bounds(20, 30, 40, 20),
                        1.0,
                    )},
                    screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, 'task_owned'),),
                    guard_verdict=GuardVerdict.BLOCKED,
                )

        result = _perception(load_visual_screen_recognizer(), _TaskOwnedGuard()).build(
            self.capture('home_city_core.png')
        )
        decision = decide_popup_recovery(
            screen_type=result.screen_type,
            blocking_popup=result.blocking_popup,
            visible_selector_ids=frozenset(result.visible_elements),
            popup_overlay=result.popup_overlay,
        )

        self.assertTrue(result.has(UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON))
        self.assertIsNotNone(decision)
        self.assertTrue(decision.blocked)
        self.assertIsNone(decision.selector_id)

    def test_more_overlay_owns_visible_root_and_unknown_has_no_controls(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        self.assertEqual(perception.build(self.capture('more_overlay.png')).screen_type, ScreenType.PNC_MORE_MENU)
        result = perception.build(self.capture('store_negative.png'))
        self.assertEqual(result.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(result.visible_elements, {})

    def test_loading_is_a_passive_state_without_controls(self):
        result = _perception(load_visual_screen_recognizer(), Guard(ScreenType.PNC_LOADING)).build(self.capture('home_city_core.png'))
        self.assertEqual(result.screen_type, ScreenType.PNC_LOADING)
        self.assertFalse(result.blocking_popup)
        self.assertEqual(result.visible_elements, {})

    def test_research_control_survives_city_background_change(self):
        result = _perception(load_visual_screen_recognizer(), Guard()).build(self.capture('home_city_panned_core.png'))
        control = result.require(UiElementId.PNC_HOME_RESEARCH_BUTTON)
        x, y = control.bounds.center()
        self.assertTrue(10 <= x <= 60 and 250 <= y <= 288)

    def test_recognized_dialog_owns_close_but_does_not_bypass_update_guard(self):
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = _perception(
            load_visual_screen_recognizer(), PncObservationEnricher(), ocr_service=ocr,
        )
        capture = self.capture('coordinate_dialog_core.png')
        result = perception.build(capture)
        self.assertEqual(result.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
        self.assertFalse(result.blocking_popup)
        self.assertTrue(result.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))
        ocr.read_result.assert_called_once()
        ocr.read_result.return_value = OcrResult(lines=(
            OcrLine('New version detected. Tap Confirm to update.', Bounds(58, 380, 420, 28), 1.0),
            OcrLine('Confirm', Bounds(221, 531, 90, 27), 1.0),
        ), words=())
        result = perception.build(capture)
        self.assertTrue(result.blocking_popup)
        self.assertTrue(result.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_content_parser_cannot_change_screen_or_invent_navigation_control(self):
        guard = Guard()
        guard.enrich = Mock(return_value=ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_BAG, 'contradiction'),),
        ))
        perception = _perception(load_visual_screen_recognizer(), guard)
        with self.assertRaisesRegex(ValueError, 'contradicted'):
            perception.build(self.capture('home_city_core.png'), include_content=True)
        guard.enrich.return_value = ObservationAdditions(visible_elements={
            UiElementId.PNC_BAG_USE_BUTTON: VisibleElement(UiElementId.PNC_BAG_USE_BUTTON, Bounds(1, 2, 3, 4), 1.0),
        })
        result = perception.build(self.capture('home_city_core.png'), include_content=True)
        self.assertFalse(result.has(UiElementId.PNC_BAG_USE_BUTTON))

    def test_content_parser_preserves_mailbox_fields_and_dynamic_entries(self):
        guard = Guard()
        category = mailbox_category(MailboxType.PLAYER, available=False)
        guard.enrich = Mock(return_value=ObservationAdditions(
            list_entries=(category,),
            screen_evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, 'home_content'),),
            mailbox_type=MailboxType.PLAYER,
            mailbox_empty=True,
        ))
        perception = _perception(load_visual_screen_recognizer(), guard)
        result = perception.build(self.capture('home_city_core.png'), include_content=True)
        observed_category = result.entries(ListEntryKind.MAILBOX_CATEGORY)
        self.assertEqual(1, len(observed_category))
        self.assertEqual(
            category,
            replace(observed_category[0], frame_ref=None, source_screen=None, source_layout_id=None),
        )
        self.assertEqual(ScreenType.PNC_HOME_CITY, observed_category[0].source_screen)
        self.assertEqual(result.mailbox_type, MailboxType.PLAYER)
        self.assertTrue(result.mailbox_empty)
    def test_capture_without_provenance_does_not_gain_dispatch_proof(self):
        capture = self.capture('home_city_core.png')
        result = _perception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertIsNone(result.frame_ref)
        self.assertTrue(result.visible_elements)
        self.assertTrue(all(control.frame_ref is None for control in result.visible_elements.values()))

    def test_shared_native_ocr_context_is_bound_and_rows_reject_foreign_frames(self):
        capture = replace(self.capture('home_city_core.png'), frame_ref=_frame_ref('frame'))
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        # Runtime composition owns OCR on the builder, not on the enricher.
        enricher = PncObservationEnricher()
        perception = NavigationPerception(
            load_visual_screen_recognizer(), enricher, ScreenClassifier(),
            lambda capture: ObservationOcrContext(capture.image, ocr, capture.frame_ref, 'test'),
        )
        row = DetectedListEntry(ListEntryKind.DAILY_QUEST, Bounds(10, 10, 100, 40), title_text='Observed row')

        def content(image, screen, controls, request, *, ocr_context, ocr_regions):
            ocr_context.validate_capture(image, capture.frame_ref)
            ocr_context.read_result(image)
            return ObservationAdditions(list_entries=(row,))

        with patch.object(PncObservationEnricher, 'enrich', side_effect=content):
            result = perception.build(capture, include_content=True)
            self.assertEqual(1, ocr.read_result.call_count)
            self.assertEqual(capture.image.size, ocr.read_result.call_args.args[0].size)
            self.assertEqual(capture.frame_ref, result.list_entries[0].frame_ref)
            self.assertEqual(result.decision.layout_id, result.list_entries[0].source_layout_id)
            row = replace(row, frame_ref=_frame_ref('foreign'))
            with self.assertRaisesRegex(SelectorResolutionError, 'different capture frame'):
                perception.build(capture, include_content=True)

    def test_popup_profile_without_controls_preserves_guard_dismissal(self):
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_POPUP, 'alliance_invitation', 'alliance_invitation'),
        ))
        close = VisibleElement(UiElementId.PNC_POPUP_CLOSE_BUTTON, Bounds(10, 20, 30, 40), 1.0)
        guard = Guard()
        guard.detect_interruption = Mock(return_value=ObservationAdditions(
            visible_elements={close.selector_id: close},
            screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, 'alliance_invitation_footer'),),
            guard_verdict=GuardVerdict.BLOCKED,
        ))
        result = _perception(recognizer, guard).build(self.capture('home_city_core.png'))
        self.assertTrue(result.blocking_popup)
        self.assertEqual(close.bounds, result.require(close.selector_id).bounds)
        # A same-named control measured on an underlying popup must not move
        # the foreground guard's independently measured dismissal point.
        recognizer.recognize.return_value = replace(
            recognizer.recognize.return_value,
            controls=(replace(close, bounds=Bounds(400, 600, 30, 40)),),
        )
        result = _perception(recognizer, guard).build(self.capture('home_city_core.png'))
        self.assertEqual(close.bounds, result.require(close.selector_id).bounds)

    def test_runtime_supplied_classifier_remains_authoritative(self):
        classifier = Mock(spec=ScreenClassifier)
        classifier.decide.return_value = ScreenDecision(
            ScreenType.PNC_HOME_CITY, ScreenType.UNKNOWN, guard=GuardVerdict.UNRESOLVED,
        )
        perception = replace(_perception(load_visual_screen_recognizer(), Guard()), screen_classifier=classifier)
        result = perception.build(self.capture('home_city_core.png'))
        classifier.decide.assert_called_once()
        self.assertIs(classifier.decide.return_value, result.decision)
        self.assertFalse(result.visible_elements)

    def test_owned_close_does_not_hide_an_additional_unowned_close(self):
        image = Image.new('RGB', (540, 960), (15, 28, 68))
        draw = ImageDraw.Draw(image)
        draw.rectangle((15, 160, 525, 620), fill=(25, 33, 50), outline=(65, 82, 110), width=4)
        for left in (478, 508):
            draw.line((left, 200, left + 18, 218), fill='white', width=4)
            draw.line((left + 18, 200, left, 218), fill='white', width=4)
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        context = ObservationOcrContext(image, ocr, None, 'test')
        result = PncObservationEnricher().detect_interruption(
            image, ocr_context=context, owned_dismiss_bounds=(Bounds(505, 195, 25, 30),),
        )
        self.assertEqual(GuardVerdict.BLOCKED, result.guard_verdict)
        self.assertLess(result.visible_elements[UiElementId.PNC_POPUP_CLOSE_BUTTON].bounds.center()[0], 500)

    def test_home_visual_identity_cannot_suppress_measured_popup(self):
        capture = self.capture('generic_popup_offer_real_sanitized.png')
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(
            evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, 'surviving_home_anchor', 'home'),),
        )
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        result = _perception(recognizer, PncObservationEnricher(), ocr_service=ocr).build(capture)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.decision.base_screen)
        self.assertEqual(ScreenType.PNC_POPUP, result.screen_type)
        self.assertTrue(result.blocking_popup)
        self.assertEqual({UiElementId.PNC_POPUP_CLOSE_BUTTON}, set(result.visible_elements))

    def test_conflicting_layouts_and_guards_abstain(self):
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_HOME_CITY, 'first', 'home-v1'),
            ScreenEvidence(ScreenType.PNC_HOME_CITY, 'second', 'home-v2'),
        ))
        guard = Guard()
        result = _perception(recognizer, guard).build(self.capture('home_city_core.png'))
        self.assertEqual(ScreenType.UNKNOWN, result.screen_type)
        self.assertEqual(GuardVerdict.UNRESOLVED, result.decision.guard)
        self.assertFalse(result.visible_elements)
        guard.detect_interruption = Mock(return_value=ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, 'update'),
                             ScreenEvidence(ScreenType.PNC_LOADING, 'loading')),
            guard_verdict=GuardVerdict.UNRESOLVED,
        ))
        result = _perception(load_visual_screen_recognizer(), guard).build(self.capture('home_city_core.png'))
        self.assertFalse(result.decision.action_eligible)
        self.assertFalse(result.visible_elements)

    def test_unreviewed_viewport_and_loading_cannot_dispatch(self):
        capture = self.capture('home_city_core.png')
        result = _perception(load_visual_screen_recognizer(), Guard()).build(
            replace(capture, image=capture.image.resize((720, 1280))))
        self.assertEqual(GuardVerdict.UNRESOLVED, result.decision.guard)
        self.assertFalse(result.visible_elements)
        loading = _perception(load_visual_screen_recognizer(), Guard(ScreenType.PNC_LOADING)).build(capture)
        self.assertEqual(GuardVerdict.BLOCKED, loading.decision.guard)
        self.assertFalse(loading.decision.action_eligible)
        self.assertFalse(loading.blocking_popup)


class GameFirstNavigationEvidenceTests(unittest.TestCase):
    directory = Path('tests/data/game_first_navigation')

    def test_fresh_game_frames_have_distinct_identities_at_both_resolutions(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        manifest = json.loads((self.directory / 'provenance.json').read_text(encoding='utf-8'))
        for case in manifest['fixtures']:
            for size in ((540, 960), (900, 1600)):
                with self.subTest(frame=case['file'], size=size), Image.open(self.directory / case['file']) as image:
                    capture = CapturedScreenshot(None, image.resize(size), 'PNG', ephemeral_captured_at=datetime.now(UTC))
                    result = perception.build(capture)
                    self.assertEqual(result.screen_type, ScreenType[case['screen']])
                    self.assertTrue(result.visible_elements)
                    self.assertTrue(all(control.source_kind == VisibleElementSourceKind.TEMPLATE for control in result.visible_elements.values()))

    def test_preferences_title_alone_does_not_identify_settings_hub(self):
        with Image.open(self.directory / 'settings_preferences_after.png') as image:
            image = image.copy()
        image.paste((0, 0, 0), (190, 65, 350, 100))
        capture = CapturedScreenshot(None, image, 'PNG', ephemeral_captured_at=datetime.now(UTC))
        result = _perception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertEqual(result.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(result.visible_elements)

    def test_preferences_and_roster_expose_only_back(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        for name in ('settings_preferences_after.png', 'settings_notifications_after.png', 'settings_manage_after.png'):
            with self.subTest(frame=name), Image.open(self.directory / name) as image:
                capture = CapturedScreenshot(None, image.copy(), 'PNG', ephemeral_captured_at=datetime.now(UTC))
                self.assertEqual(set(perception.build(capture).visible_elements), {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})
