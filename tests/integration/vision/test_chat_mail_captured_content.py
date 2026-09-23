"""Captured Chat/Mail content checks at the bounded OCR boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.chat import ChatChannel, ChatEntryKind
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrResult,
    OcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
CHAT_BODY_REGION = Bounds(0, 125, 540, 739)
MAIL_TITLE_REGION = Bounds(97, 0, 389, 75)


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Use shared RapidOCR while rejecting full-capture backend calls."""

    delegate: OcrService
    capture_size: tuple[int, int] | None = None
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)

    def bind(self, image_size: tuple[int, int]) -> None:
        """Bind a fresh frame and reset native-call accounting."""

        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject ``None`` on the full image and explicit whole-frame bounds."""

        self.calls.append((region, image.size))
        full_size = self.capture_size
        whole = None if full_size is None else Bounds(0, 0, *full_size)
        if region == whole or (region is None and full_size == image.size):
            raise AssertionError("captured content test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


@dataclass(slots=True)
class _ControlledOcrService:
    """Return only controlled, non-private transcript lines inside each crop."""

    lines: tuple[OcrLine, ...]
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)
    capture_size: tuple[int, int] | None = None

    def bind(self, image_size: tuple[int, int]) -> None:
        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        self.calls.append((region, image.size))
        whole = None if self.capture_size is None else Bounds(0, 0, *self.capture_size)
        if region == whole or (region is None and image.size == self.capture_size):
            raise AssertionError("controlled content test reached OCR without a strict crop")
        if region is None:
            visible = self.lines
        else:
            visible = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=visible, words=tuple(word for line in visible for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _capture(name: str, *, session_id: str) -> CapturedScreenshot:
    """Load a tracked capture and attach a canonical frame reference."""

    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(tz=UTC),
        frame_ref=frame.frame_ref,
    )


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Build one measured, generic OCR line for the controlled parser case."""

    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=1.0)


def _controlled_chat_lines(*, omit_header: bool = False, omit_tabs: bool = False) -> tuple[OcrLine, ...]:
    """Return generic transcript lines at the visually inspected 540px row geometry."""

    lines: list[OcrLine] = []
    if not omit_header:
        lines.append(_line("Chat", x=105, y=9, width=76, height=35))
    if not omit_tabs:
        lines.extend(
            (
                _line("Kingdom", x=62, y=69, width=89, height=26),
                _line("Alliance", x=217, y=70, width=77, height=20),
            )
        )
    lines.extend(
        (
            _line("Example Player", x=108, y=145, width=150, height=20),
            _line("Sample message", x=108, y=177, width=180, height=22),
            _line("Second Player", x=108, y=250, width=140, height=20),
            _line("Another message", x=108, y=282, width=190, height=22),
        )
    )
    return tuple(lines)


def _builder(ocr: object) -> ObservationBuilder:
    """Wire the production builder with the supplied OCR boundary."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=ocr,
        ocr_backend_revision="captured-chat-mail-test",
    )


def _navigation(
    ocr: object,
) -> tuple[NavigationPerception, list[ObservationOcrContext]]:
    """Wire replacement navigation and retain its frame-local OCR contexts."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    recognizer = load_visual_screen_recognizer(matcher=matcher)
    contexts: list[ObservationOcrContext] = []

    def create_context(capture: CapturedScreenshot) -> ObservationOcrContext:
        context = ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "captured-chat-mail-test",
        )
        context.require_bounded_regions()
        contexts.append(context)
        return context

    return (
        NavigationPerception(
            recognizer,
            PncObservationEnricher(selector_registry=registry),
            ScreenClassifier(),
            create_context,
        ),
        contexts,
    )


def _assert_bounded(test: unittest.TestCase, ocr: _BoundedRapidOcrService | _ControlledOcrService, size: tuple[int, int]) -> None:
    """Require every backend call to identify a strict source-frame crop."""

    test.assertTrue(ocr.calls)
    whole = Bounds(0, 0, *size)
    test.assertTrue(all(region != whole for region, _ in ocr.calls))
    test.assertTrue(all(region is not None or source_size != size for region, source_size in ocr.calls))


def _assert_control_provenance(
    test: unittest.TestCase,
    observation: object,
    selector_id: UiElementId,
    capture: CapturedScreenshot,
) -> None:
    """Assert one visual control remains tied to the accepted captured frame."""

    element = observation.require(selector_id)
    test.assertEqual(element.source_kind, VisibleElementSourceKind.TEMPLATE)
    test.assertEqual(element.frame_ref, capture.frame_ref)
    test.assertEqual(element.source_screen, observation.screen_type)
    test.assertEqual(element.source_layout_id, observation.decision.layout_id)
    test.assertIsNotNone(element.action_point)
    test.assertTrue(element.bounds.contains_point(element.action_point))


class ChatMailCapturedContentTests(unittest.TestCase):
    """Exercise captured Chat/Mail content through both production consumers."""

    def test_captured_chat_channels_use_bounded_actual_crops_in_both_paths(self) -> None:
        """Preserve the measured Kingdom/Alliance selection on both saved captures."""

        for fixture_name, expected_channel in (
            ("chat_kingdom.png", ChatChannel.WORLD),
            ("chat_alliance.png", ChatChannel.ALLIANCE),
        ):
            with self.subTest(fixture=fixture_name):
                capture = _capture(fixture_name, session_id=f"captured-chat:{fixture_name}")
                delegate = _require_rapid_ocr_service(self)
                ocr = _BoundedRapidOcrService(delegate)
                builder = _builder(ocr)
                ocr.bind(capture.image.size)
                builder_context = builder.create_ocr_context(capture)
                built = builder.build(
                    capture,
                    request=ObservationRequest.chat_transcript_observation(),
                    ocr_context=builder_context,
                )
                builder_calls = tuple(ocr.calls)

                navigation, contexts = _navigation(ocr)
                ocr.bind(capture.image.size)
                perceived = navigation.build(capture, include_content=True)
                self.assertTrue(contexts)
                self.assertEqual(perceived.frame_ref, capture.frame_ref)

                for observation in (built, perceived):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
                    self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                    self.assertTrue(observation.decision.action_eligible)
                    self.assertEqual(observation.active_chat_channel, expected_channel)
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture,
                    )
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_CHAT_TAB_KINGDOM, capture,
                    )
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_CHAT_TAB_ALLIANCE, capture,
                    )
                    self.assertEqual(observation.frame_ref, capture.frame_ref)
                # Chat is a recognized base screen, so no centered popup guard
                # crop is permitted; transcript acquisition remains bounded.
                _assert_bounded(self, ocr, capture.image.size)
                self.assertTrue(
                    any(region == CHAT_BODY_REGION for region, _ in builder_calls),
                    "Builder chat transcript must use the bounded body crop.",
                )
                self.assertTrue(
                    any(region == CHAT_BODY_REGION for region, _ in ocr.calls),
                    "Navigation chat transcript must use the bounded body crop.",
                )

    def test_chat_missing_optional_header_or_tabs_retains_state_and_rows(self) -> None:
        """Keep template-owned channel state and controlled rows when OCR misses optional chrome."""

        cases = (
            ("chat_kingdom.png", ChatChannel.WORLD, True, False),
            ("chat_alliance.png", ChatChannel.ALLIANCE, False, True),
        )
        for fixture_name, expected_channel, omit_header, omit_tabs in cases:
            with self.subTest(fixture=fixture_name, omit_header=omit_header, omit_tabs=omit_tabs):
                capture = _capture(fixture_name, session_id=f"controlled-chat:{fixture_name}")
                ocr = _ControlledOcrService(
                    _controlled_chat_lines(omit_header=omit_header, omit_tabs=omit_tabs)
                )
                builder = _builder(ocr)
                ocr.bind(capture.image.size)
                context = builder.create_ocr_context(capture)
                built = builder.build(
                    capture,
                    request=ObservationRequest.chat_transcript_observation(),
                    ocr_context=context,
                )
                builder_calls = tuple(ocr.calls)
                navigation, contexts = _navigation(ocr)
                ocr.bind(capture.image.size)
                perceived = navigation.build(capture, include_content=True)
                self.assertTrue(contexts)

                for observation in (built, perceived):
                    self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
                    self.assertEqual(observation.active_chat_channel, expected_channel)
                    entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
                    self.assertEqual(len(entries), 2)
                    self.assertTrue(
                        all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in entries)
                    )
                    self.assertEqual(observation.frame_ref, capture.frame_ref)
                    for entry in entries:
                        self.assertEqual(entry.frame_ref, capture.frame_ref)
                        self.assertEqual(entry.source_screen, ScreenType.PNC_CHAT)
                        self.assertEqual(entry.source_layout_id, observation.decision.layout_id)
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture,
                    )
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_CHAT_TAB_KINGDOM, capture,
                    )
                    _assert_control_provenance(
                        self, observation, UiElementId.PNC_CHAT_TAB_ALLIANCE, capture,
                    )
                _assert_bounded(self, ocr, capture.image.size)
                self.assertTrue(builder_calls)
                self.assertTrue(any(region == CHAT_BODY_REGION for region, _ in builder_calls))
                self.assertTrue(any(region == CHAT_BODY_REGION for region, _ in ocr.calls))

    def test_navigation_no_content_flag_keeps_identity_controls_and_omits_chat_state(self) -> None:
        """Recognized no-content Chat publishes controls without popup OCR work."""

        delegate = _require_rapid_ocr_service(self)
        for fixture_name in ("chat_kingdom.png", "chat_alliance.png"):
            with self.subTest(fixture=fixture_name):
                capture = _capture(fixture_name, session_id=f"no-content-chat:{fixture_name}")
                ocr = _BoundedRapidOcrService(delegate)
                navigation, contexts = _navigation(ocr)
                ocr.bind(capture.image.size)
                observation = navigation.build(capture, include_content=False)
                self.assertTrue(contexts)
                self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertIsNone(observation.active_chat_channel)
                self.assertEqual(observation.entries(ListEntryKind.CHAT_MESSAGE), ())
                self.assertEqual(observation.frame_ref, capture.frame_ref)
                _assert_control_provenance(self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture)
                self.assertEqual(ocr.calls, [])

    def test_captured_player_mail_uses_padded_title_crop_and_preserves_compose(self) -> None:
        """Recognize Player Mail from the measured title context without body-based emptiness."""

        capture = _capture("mail_player_list.png", session_id="captured-player-mail")
        delegate = _require_rapid_ocr_service(self)
        ocr = _BoundedRapidOcrService(delegate)
        builder = _builder(ocr)
        ocr.bind(capture.image.size)
        builder_context = builder.create_ocr_context(capture)
        built = builder.build(
            capture,
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            ocr_context=builder_context,
        )
        builder_calls = tuple(ocr.calls)
        navigation, contexts = _navigation(ocr)
        ocr.bind(capture.image.size)
        perceived = navigation.build(capture, include_content=True)

        for observation in (built, perceived):
            self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
            self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
            self.assertEqual(observation.mailbox_type, MailboxType.PLAYER)
            self.assertIsNone(observation.mailbox_empty)
            self.assertEqual(observation.frame_ref, capture.frame_ref)
            _assert_control_provenance(self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture)
            _assert_control_provenance(self, observation, UiElementId.PNC_MAIL_COMPOSE_BUTTON, capture)
        self.assertTrue(contexts)
        _assert_bounded(self, ocr, capture.image.size)
        self.assertTrue(
            any(region == MAIL_TITLE_REGION for region, _ in builder_calls)
            or any(region == MAIL_TITLE_REGION for region, _ in ocr.calls),
            "Player Mail title must use the measured padded crop.",
        )

    def test_mail_header_miss_keeps_controls_and_does_not_fabricate_player_mailbox(self) -> None:
        """A missing mailbox title leaves the type unknown while visual controls remain available."""

        capture = _capture("mail_player_list.png", session_id="missing-player-mail-title")
        for path_name in ("builder", "navigation"):
            with self.subTest(path=path_name):
                ocr = _ControlledOcrService(lines=())
                builder = _builder(ocr)
                navigation, contexts = _navigation(ocr)
                ocr.bind(capture.image.size)
                if path_name == "builder":
                    context = builder.create_ocr_context(capture)
                    observation = builder.build(
                        capture,
                        request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
                        ocr_context=context,
                    )
                else:
                    observation = navigation.build(capture, include_content=True)
                self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
                self.assertIsNone(observation.mailbox_type)
                self.assertIsNone(observation.mailbox_empty)
                self.assertEqual(observation.entries(ListEntryKind.MAIL_THREAD), ())
                self.assertEqual(observation.frame_ref, capture.frame_ref)
                _assert_control_provenance(self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture)
                _assert_control_provenance(self, observation, UiElementId.PNC_MAIL_COMPOSE_BUTTON, capture)
                _assert_bounded(self, ocr, capture.image.size)
                if path_name == "navigation":
                    self.assertTrue(contexts)

    def test_mail_thread_back_is_captured_template_control_in_both_paths(self) -> None:
        """Qualify System Mail Thread identity and Back without inventing typed message content."""

        capture = _capture("collect_mail_system_thread.png", session_id="captured-system-mail-thread")
        delegate = _require_rapid_ocr_service(self)
        ocr = _BoundedRapidOcrService(delegate)
        builder = _builder(ocr)
        ocr.bind(capture.image.size)
        builder_context = builder.create_ocr_context(capture)
        built = builder.build(
            capture,
            request=ObservationRequest.mail_thread_observation(),
            ocr_context=builder_context,
        )
        navigation, contexts = _navigation(ocr)
        ocr.bind(capture.image.size)
        perceived = navigation.build(capture, include_content=True)
        for observation in (built, perceived):
            self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_THREAD)
            self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
            self.assertEqual(observation.frame_ref, capture.frame_ref)
            _assert_control_provenance(self, observation, UiElementId.PNC_BACK_BUTTON_TOP_LEFT, capture)
        self.assertTrue(contexts)
        _assert_bounded(self, ocr, capture.image.size)

    def test_update_overlay_blocks_both_content_paths(self) -> None:
        """A blocking update overlay remains authoritative over underlying captured content."""

        capture = _capture("update_over_bag.png", session_id="captured-update-overlay")
        delegate = _require_rapid_ocr_service(self)
        ocr = _BoundedRapidOcrService(delegate)
        builder = _builder(ocr)
        ocr.bind(capture.image.size)
        context = builder.create_ocr_context(capture)
        built = builder.build(
            capture,
            request=ObservationRequest.full_runtime_default(),
            ocr_context=context,
        )
        navigation, contexts = _navigation(ocr)
        ocr.bind(capture.image.size)
        perceived = navigation.build(capture, include_content=True)
        for observation in (built, perceived):
            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BAG_USE_BUTTON))
        self.assertTrue(contexts)
        _assert_bounded(self, ocr, capture.image.size)


if __name__ == "__main__":
    unittest.main()
