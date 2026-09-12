"""Replacement navigation must prove a transition, not retry an uncertain tap."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy, reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import Bounds, DetectedListEntry, ListEntryKind, Observation, VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import decide_popup_recovery
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier, ScreenEvidence
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition, load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult, OcrService
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import make_captured_frame


def _perception(recognizer, guard):
    return NavigationPerception(
        recognizer, guard, ScreenClassifier(),
        lambda capture: ObservationOcrContext(capture.image, guard.ocr_service, capture.frame_ref, 'test'),
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

    def detect_interruption(self, image, *, ocr_context, owned_dismiss_bounds=()):
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

        result = _perception(
            load_visual_screen_recognizer(),
            PncObservationEnricher(ocr),
        ).build(capture)

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
            load_visual_screen_recognizer(),
            PncObservationEnricher(ocr),
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
            def detect_interruption(self, image, *, ocr_context, owned_dismiss_bounds=()):
                del image, owned_dismiss_bounds
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
        perception = _perception(load_visual_screen_recognizer(), PncObservationEnricher(ocr))
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

    def test_capture_without_provenance_does_not_gain_dispatch_proof(self):
        capture = self.capture('home_city_core.png')
        result = _perception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertIsNone(result.frame_ref)
        self.assertTrue(result.visible_elements)
        self.assertTrue(all(control.frame_ref is None for control in result.visible_elements.values()))

    def test_shared_native_ocr_context_is_bound_and_rows_reject_foreign_frames(self):
        capture = replace(self.capture('home_city_core.png'), frame_ref=make_captured_frame(b'frame').frame_ref)
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
            row = replace(row, frame_ref=make_captured_frame(b'foreign').frame_ref)
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
        result = _perception(recognizer, PncObservationEnricher(ocr_service=ocr)).build(capture)
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
