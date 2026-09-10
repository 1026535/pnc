"""Replacement navigation must prove a transition, not retry an uncertain tap."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy, reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import Bounds, Observation, VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.screen_classifier import ScreenEvidence
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, OcrService


class Actuator:
    def __init__(self):
        self.actions = []

    def execute_action(self, action, observation):
        self.actions.append(action)
        return True


class Guard:
    def __init__(self, screen=None):
        self.screen = screen

    def detect_interruption(self, image, *, owned_dismiss_bounds=()):
        evidence = () if self.screen is None else (ScreenEvidence(self.screen, "test_interruption"),)
        return ObservationAdditions(screen_evidence=evidence)


def observation(screen, *, geometry=False, blocked=False):
    return Observation(
        screen_type=screen, blocking_popup=blocked,
        visible_elements={UiElementId.PNC_HOME_WORLD_SWITCH: VisibleElement(
            UiElementId.PNC_HOME_WORLD_SWITCH, Bounds(10, 20, 30, 40), 0.99,
            source_kind=VisibleElementSourceKind.GEOMETRY if geometry else VisibleElementSourceKind.TEMPLATE,
        )},
    )


class NavigationCoreTests(unittest.TestCase):
    def make_core(self, frames):
        actuator = Actuator()
        now = datetime.now(UTC)
        iterator = iter(replace(frame, captured_at=now + timedelta(seconds=index)) for index, frame in enumerate(frames))
        core = NavigationCore(actuator, lambda _: next(iterator), reviewed_navigation_edges(),
                              NavigationPolicy(max_observations=4), sleep=lambda _: None)
        return core, actuator, core.edges[0]

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
            return Observation(screen_type=screen, visible_elements={} if selector is None else {
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
        before = Observation(screen_type=ScreenType.PNC_SETTINGS, visible_elements={
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
            lines=(OcrLine('Goddess Statue', Bounds(220, 650, 110, 20), 1.0),),
        )
        home = replace(observation(ScreenType.PNC_HOME_CITY), spatial_surface=surface, image_size=image.size)
        core, actuator, _ = self.make_core([
            observation(ScreenType.PNC_GODDESS_STATUE), observation(ScreenType.PNC_GODDESS_STATUE),
        ])
        core.open_visible_building(HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: home)
        self.assertEqual(len(actuator.actions), 1)
        self.assertEqual(actuator.actions[0].target_point, (275, 574))
        for objects in ((), surface.objects * 2):
            core, actuator, _ = self.make_core([])
            candidate = replace(home, spatial_surface=replace(surface, objects=objects))
            with self.assertRaisesRegex(RuntimeError, 'absent or ambiguous'):
                core.open_visible_building(HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: candidate)
            self.assertEqual(actuator.actions, [])

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


class NavigationPerceptionTests(unittest.TestCase):
    def capture(self, name):
        with Image.open(Path('tests/data/screen_recognition') / name) as image:
            return CapturedScreenshot(None, image.copy(), "PNG", ephemeral_captured_at=datetime.now(UTC))

    def test_measured_controls_and_resolution_projection(self):
        perception = NavigationPerception(load_visual_screen_recognizer(), Guard())
        for size in ((540, 960), (900, 1600)):
            capture = self.capture('home_city_core.png')
            result = perception.build(replace(capture, image=capture.image.resize(size)))
            self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
            control = result.require(UiElementId.PNC_BOTTOM_NAV_QUEST)
            x, y = control.bounds.center()
            self.assertTrue(190 <= x * 540 / size[0] <= 253)
            self.assertTrue(900 <= y * 960 / size[1] <= 958)
            self.assertTrue(all(c.source_kind == VisibleElementSourceKind.TEMPLATE for c in result.visible_elements.values()))

    def test_missing_control_does_not_invent_a_click_or_erase_identity(self):
        capture = self.capture('home_city_core.png')
        capture.image.paste((0, 0, 0), (195, 899, 249, 960))
        result = NavigationPerception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertEqual(result.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertFalse(result.has(UiElementId.PNC_BOTTOM_NAV_QUEST))

    def test_overlay_blocks_even_when_background_header_survives(self):
        result = NavigationPerception(load_visual_screen_recognizer(), Guard(ScreenType.PNC_POPUP)).build(self.capture('update_over_bag.png'))
        self.assertTrue(result.blocking_popup)
        self.assertEqual(result.visible_elements, {})

    def test_more_overlay_owns_visible_root_and_unknown_has_no_controls(self):
        perception = NavigationPerception(load_visual_screen_recognizer(), Guard())
        self.assertEqual(perception.build(self.capture('more_overlay.png')).screen_type, ScreenType.PNC_MORE_MENU)
        result = perception.build(self.capture('store_negative.png'))
        self.assertEqual(result.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(result.visible_elements, {})

    def test_loading_is_a_passive_state_without_controls(self):
        result = NavigationPerception(load_visual_screen_recognizer(), Guard(ScreenType.PNC_LOADING)).build(self.capture('home_city_core.png'))
        self.assertEqual(result.screen_type, ScreenType.PNC_LOADING)
        self.assertFalse(result.blocking_popup)
        self.assertEqual(result.visible_elements, {})

    def test_research_control_survives_city_background_change(self):
        result = NavigationPerception(load_visual_screen_recognizer(), Guard()).build(self.capture('home_city_panned_core.png'))
        control = result.require(UiElementId.PNC_HOME_RESEARCH_BUTTON)
        x, y = control.bounds.center()
        self.assertTrue(10 <= x <= 60 and 250 <= y <= 288)

    def test_recognized_dialog_owns_close_but_does_not_bypass_update_guard(self):
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = NavigationPerception(load_visual_screen_recognizer(), PncObservationEnricher(ocr))
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
        self.assertEqual(result.visible_elements, {})

    def test_content_parser_cannot_change_screen_or_invent_navigation_control(self):
        guard = Guard()
        guard.enrich = Mock(return_value=ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_BAG, 'contradiction'),),
        ))
        perception = NavigationPerception(load_visual_screen_recognizer(), guard)
        with self.assertRaisesRegex(ValueError, 'contradicted'):
            perception.build(self.capture('home_city_core.png'), include_content=True)
        guard.enrich.return_value = ObservationAdditions(visible_elements={
            UiElementId.PNC_BAG_USE_BUTTON: VisibleElement(UiElementId.PNC_BAG_USE_BUTTON, Bounds(1, 2, 3, 4), 1.0),
        })
        result = perception.build(self.capture('home_city_core.png'), include_content=True)
        self.assertFalse(result.has(UiElementId.PNC_BAG_USE_BUTTON))


class GameFirstNavigationEvidenceTests(unittest.TestCase):
    directory = Path('tests/data/game_first_navigation')

    def test_fresh_game_frames_have_distinct_identities_at_both_resolutions(self):
        perception = NavigationPerception(load_visual_screen_recognizer(), Guard())
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
        result = NavigationPerception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertEqual(result.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(result.visible_elements)

    def test_preferences_and_roster_expose_only_back(self):
        perception = NavigationPerception(load_visual_screen_recognizer(), Guard())
        for name in ('settings_preferences_after.png', 'settings_notifications_after.png', 'settings_manage_after.png'):
            with self.subTest(frame=name), Image.open(self.directory / name) as image:
                capture = CapturedScreenshot(None, image.copy(), 'PNG', ephemeral_captured_at=datetime.now(UTC))
                self.assertEqual(set(perception.build(capture).visible_elements), {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})
