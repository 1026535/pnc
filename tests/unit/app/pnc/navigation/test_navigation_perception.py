"""Navigation perception tests."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.popup import decide_popup_recovery
from pnc_automation.app.pnc.domain.screen_decision import (
    GuardVerdict,
    ScreenDecision,
    ScreenEvidence,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.observation_provenance import bind_observation_content
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import (
    VisualRecognition,
    load_visual_screen_recognizer,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrResult,
    OcrService,
)

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal
from tests.support.pnc.navigation.core_frames import _frame_ref
from tests.support.pnc.navigation.core_mail import mailbox_category
from tests.support.pnc.navigation.core_perception import Guard, _perception


class NavigationPerceptionTests(unittest.TestCase):
    def capture(self, name):
        with Image.open(TEST_DATA_ROOT / 'screen_recognition' / name) as image:
            return CapturedScreenshot(None, image.copy(), "PNG", ephemeral_captured_at=datetime.now(UTC))

    def test_login_content_publishes_current_account_id(self):
        """Navigation publication retains the account fact emitted by its enricher."""

        class LoginGuard(Guard):
            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
                return ObservationAdditions(current_pnc_account_id="user@example.com")

        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_LOGIN, "login_profile"),
        ))
        capture = CapturedScreenshot(
            None, Image.new("RGB", (540, 960)), "PNG",
            ephemeral_captured_at=datetime.now(UTC),
        )
        result = _perception(recognizer, LoginGuard()).build(capture, include_content=True)

        self.assertEqual(result.screen_type, ScreenType.PNC_LOGIN)
        self.assertEqual(result.current_pnc_account_id, "user@example.com")

    def test_login_account_content_requires_clear_identified_content_scope(self):
        """A parsed account cannot escape content, unknown, or interruption gates."""

        class LoginGuard(Guard):
            def __init__(self, screen=None):
                super().__init__(screen)
                self.enrich_calls = 0

            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
                self.enrich_calls += 1
                return ObservationAdditions(current_pnc_account_id="user@example.com")

        capture = CapturedScreenshot(
            None, Image.new("RGB", (540, 960), "white"), "PNG",
            ephemeral_captured_at=datetime.now(UTC),
        )
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_LOGIN, "login_profile"),
        ))
        guard = LoginGuard()
        self.assertIsNone(_perception(recognizer, guard).build(capture).current_pnc_account_id)
        self.assertEqual(guard.enrich_calls, 0)

        recognizer.recognize.return_value = VisualRecognition()
        unknown = _perception(recognizer, guard).build(capture, include_content=True)
        self.assertEqual(unknown.screen_type, ScreenType.UNKNOWN)
        self.assertIsNone(unknown.current_pnc_account_id)
        self.assertEqual(guard.enrich_calls, 0)

        guard = LoginGuard(ScreenType.PNC_POPUP)
        recognizer.recognize.return_value = VisualRecognition(evidence=(
            ScreenEvidence(ScreenType.PNC_LOGIN, "login_profile"),
        ))
        blocked = _perception(recognizer, guard).build(capture, include_content=True)
        self.assertEqual(blocked.screen_type, ScreenType.PNC_POPUP)
        self.assertIsNone(blocked.current_pnc_account_id)
        self.assertEqual(guard.enrich_calls, 0)

    def test_common_content_binds_rows_to_the_publishing_frame(self):
        """Shared content binding keeps the existing frame, screen and layout checks."""

        frame_ref = _frame_ref("content")
        decision = ScreenDecision(
            ScreenType.PNC_DAILY_TO_DO, ScreenType.PNC_DAILY_TO_DO,
            layout_id="daily-layout", guard=GuardVerdict.CLEAR,
        )
        base = Observation(decision=decision, frame_ref=frame_ref)
        row = DetectedListEntry(
            ListEntryKind.DAILY_QUEST, Bounds(10, 10, 100, 40), title_text="Measured row",
        )
        bound = bind_observation_content(
            base, ObservationAdditions(list_entries=(row,)),
            frame_ref=frame_ref, source_screen=ScreenType.PNC_DAILY_TO_DO,
            source_layout_id="daily-layout",
        )
        self.assertEqual(bound.list_entries[0].frame_ref, frame_ref)
        self.assertEqual(bound.list_entries[0].source_screen, ScreenType.PNC_DAILY_TO_DO)
        self.assertEqual(bound.list_entries[0].source_layout_id, "daily-layout")
        with self.assertRaisesRegex(SelectorResolutionError, "different capture frame"):
            bind_observation_content(
                base, ObservationAdditions(list_entries=(replace(row, frame_ref=_frame_ref("foreign")),)),
                frame_ref=frame_ref, source_screen=ScreenType.PNC_DAILY_TO_DO,
                source_layout_id="daily-layout",
            )

    def test_live_tour_surfaces_publish_only_measured_return_controls(self):
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = _perception(
            load_visual_screen_recognizer(), PncObservationEnricher(), ocr_service=ocr,
        )
        for fixture, screen, selector in (
            ("campaign_map_chapter_6.png", ScreenType.PNC_CAMPAIGN_MAP, UiElementId.PNC_CAMPAIGN_HOME_PORTAL),
            ("campaign_map_chapter_6_pulse.png", ScreenType.PNC_CAMPAIGN_MAP, UiElementId.PNC_CAMPAIGN_HOME_PORTAL),
            ("trial_challenge.png", ScreenType.PNC_TRIAL_CHALLENGE, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            ("trial_challenge_completed_20260916.png", ScreenType.PNC_TRIAL_CHALLENGE, UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
            ("bag_arena_chest_preview.png", ScreenType.PNC_BAG_CHEST_PREVIEW, UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE),
        ):
            with self.subTest(fixture=fixture):
                result = perception.build(self.capture(fixture))
                self.assertEqual(screen, result.screen_type)
                self.assertFalse(result.blocking_popup)
                self.assertTrue(result.decision.action_eligible)
                self.assertEqual({selector}, set(result.visible_elements))
                self.assertEqual(VisibleElementSourceKind.TEMPLATE, result.require(selector).source_kind)
                self.assertIsNone(decide_popup_recovery(
                    screen_type=result.screen_type, blocking_popup=result.blocking_popup,
                    visible_selector_ids=frozenset(result.visible_elements), popup_overlay=result.popup_overlay,
                ))

    def test_chest_preview_close_requires_visible_x_and_cannot_override_update(self):
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = _perception(
            load_visual_screen_recognizer(), PncObservationEnricher(), ocr_service=ocr,
        )
        capture = self.capture("bag_arena_chest_preview.png")
        result = perception.build(capture)
        close = result.require(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE).bounds
        obscured = capture.image.copy()
        ImageDraw.Draw(obscured).rectangle(
            (close.x - 2, close.y - 2, close.x + close.width + 2, close.y + close.height + 2),
            fill="black",
        )
        result = perception.build(replace(capture, image=obscured))
        self.assertFalse(result.has(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE))
        ocr.read_result.return_value = OcrResult(lines=(
            OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        ), words=())
        result = perception.build(replace(capture, image=with_update_modal(capture.image)))
        self.assertTrue(result.blocking_popup)
        self.assertFalse(result.has(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE))

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

            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
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
        # The owned coordinate dialog is too shallow to be an update overlay,
        # so its ordinary frame does not spend a guard OCR read.
        self.assertEqual(0, ocr.read_result.call_count)
        ocr.read_result.return_value = OcrResult(lines=(
            OcrLine('New version detected. Tap Confirm to update.', Bounds(58, 380, 420, 28), 1.0),
            OcrLine('Confirm', Bounds(221, 531, 90, 27), 1.0),
        ), words=())
        result = perception.build(replace(capture, image=with_update_modal(capture.image)))
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

        def content(image, screen, controls, request, *, ocr_context, ocr_regions, layout_id=None):
            ocr_context.validate_capture(image, capture.frame_ref)
            ocr_context.read_result(image, Bounds(10, 10, 100, 40))
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

    def test_owned_close_with_additional_unowned_close_stays_unresolved(self):
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
        self.assertEqual(GuardVerdict.UNRESOLVED, result.guard_verdict)
        self.assertFalse(result.visible_elements)
        self.assertIsNotNone(result.popup_overlay)
        self.assertEqual((), result.popup_overlay.candidates)

    def test_home_visual_identity_owns_a_generic_like_popup_surface(self):
        capture = self.capture('generic_popup_offer_real_sanitized.png')
        recognizer = Mock()
        recognizer.recognize.return_value = VisualRecognition(
            evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, 'surviving_home_anchor', 'home'),),
        )
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        result = _perception(recognizer, PncObservationEnricher(), ocr_service=ocr).build(capture)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.decision.base_screen)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.screen_type)
        self.assertFalse(result.blocking_popup)
        self.assertNotIn(UiElementId.PNC_POPUP_CLOSE_BUTTON, result.visible_elements)

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
