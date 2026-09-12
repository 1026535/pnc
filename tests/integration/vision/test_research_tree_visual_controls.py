"""Development Research Tree identity and safe Back-control coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.tasks.research_task import ResearchTask
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationAdditions,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorResolutionError,
    SelectorStatus,
    build_default_selector_registry,
)
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.automation.session import FakeSession
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)
from tests.support.core.logging import build_logger
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.observations import make_entry, make_observation


FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_tree_development.png"
DETAIL_FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_node_detail.png"
ACTIVE_DETAIL_FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_node_detail_active.png"
RELOADED_ACTIVE_DETAIL_FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_node_detail_active_reloaded.png"
TITLE_BOX = (108, 10, 303, 43)
ICON_BOX = (463, 80, 530, 120)
BACK_BOX = (25, 11, 77, 43)
DETAIL_HEADER_BOX = (480, 276, 522, 317)
DETAIL_TIME_LABELS_BOX = (100, 526, 365, 549)
DETAIL_RESEARCH_BUTTON_BOX = (304, 447, 439, 496)
ACTIVE_SPEEDUP_BOX = (372, 425, 502, 469)


def _detail_ocr_lines() -> tuple[OcrLine, ...]:
    """Return the normalized OCR rows observed on the reviewed detail frame."""

    return (
        OcrLine("Construction I (2/5)", Bounds(58, 284, 175, 20), 1.0),
        OcrLine("Might +695", Bounds(181, 347, 80, 16), 1.0),
        OcrLine("Build Speed +3%", Bounds(181, 379, 120, 16), 1.0),
        OcrLine("06", Bounds(175, 452, 20, 14), 1.0),
        OcrLine("Research", Bounds(325, 461, 91, 19), 1.0),
        OcrLine("Research Now", Bounds(115, 468, 121, 17), 1.0),
        OcrLine("Original Time", Bounds(107, 529, 98, 14), 1.0),
        OcrLine("Actual Time", Bounds(277, 529, 87, 14), 1.0),
        OcrLine("00:45:41", Bounds(106, 549, 62, 14), 1.0),
        OcrLine("00:44:47", Bounds(275, 548, 65, 16), 1.0),
        OcrLine("Institute : Lv.3", Bounds(106, 610, 104, 14), 1.0),
        OcrLine("490,250/16,400", Bounds(106, 673, 113, 16), 1.0),
        OcrLine("740,224/7,010", Bounds(106, 725, 104, 16), 1.0),
    )


def _active_detail_ocr_lines() -> tuple[OcrLine, ...]:
    """Return live-shaped OCR rows from the active research detail frame."""

    return (
        OcrLine("Construction I (2/5)", Bounds(59, 262, 174, 18), 1.0),
        OcrLine("Might +695", Bounds(181, 323, 81, 16), 1.0),
        OcrLine("Build Speed +3%", Bounds(181, 355, 119, 16), 1.0),
        OcrLine("00:44:45", Bounds(169, 438, 57, 13), 1.0),
        OcrLine("Speedup", Bounds(394, 435, 88, 24), 1.0),
        OcrLine("Original Time", Bounds(107, 505, 98, 14), 1.0),
        OcrLine("Actual Time", Bounds(277, 505, 87, 14), 1.0),
        OcrLine("00:45:41", Bounds(106, 524, 62, 14), 1.0),
        OcrLine("00:44:47", Bounds(276, 524, 65, 14), 1.0),
        OcrLine("No idle queue", Bounds(106, 586, 103, 14), 1.0),
        OcrLine("00:44:45", Bounds(216, 585, 65, 14), 1.0),
        OcrLine("Speedup", Bounds(412, 584, 75, 19), 1.0),
        OcrLine("Institute : Lv.3", Bounds(105, 633, 104, 16), 1.0),
        OcrLine("473,850/16,400", Bounds(105, 697, 113, 16), 1.0),
        OcrLine("733,214/7,010", Bounds(106, 749, 104, 16), 1.0),
    )


def _load_fixture() -> Image.Image:
    """Load the reviewed Development tree fixture as an independent RGB image."""

    with Image.open(FIXTURE_PATH) as source:
        return source.convert("RGB")


def _load_detail_fixture() -> Image.Image:
    """Load the normalized reviewed research detail fixture."""

    with Image.open(DETAIL_FIXTURE_PATH) as source:
        return source.convert("RGB")


def _load_active_detail_fixture() -> Image.Image:
    """Load the normalized reviewed active research detail fixture."""

    with Image.open(ACTIVE_DETAIL_FIXTURE_PATH) as source:
        return source.convert("RGB")


def _load_reloaded_active_detail_fixture() -> Image.Image:
    """Load the second normalized active detail capture after elapsed progress."""

    with Image.open(RELOADED_ACTIVE_DETAIL_FIXTURE_PATH) as source:
        return source.convert("RGB")


def _bounds_from_box(box: tuple[int, int, int, int]) -> Bounds:
    """Convert a Pillow left/top/right/bottom box to image-space bounds."""

    left, top, right, bottom = box
    return Bounds(left, top, right - left, bottom - top)


def _scale_box(box: tuple[int, int, int, int], scale: float) -> Bounds:
    """Scale a Pillow box into the normalized fixture's target image space."""

    left, top, right, bottom = box
    scaled_left = round(left * scale)
    scaled_top = round(top * scale)
    return Bounds(
        scaled_left,
        scaled_top,
        round(right * scale) - scaled_left,
        round(bottom * scale) - scaled_top,
    )


def _capture_image(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach one deterministic frame proof to an image."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Attach frame provenance to one deterministic fixture capture."""

    return _capture_image(image, session_id="research-tree-visual-controls")


def _perception(lines: tuple[OcrLine, ...] = ()) -> NavigationPerception:
    """Wire the production perception path with deterministic OCR lines."""

    ocr = _FakeOcrService(lines=lines)
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "research-tree-visual-controls-test",
        ),
    )


def _observation_builder(lines: tuple[OcrLine, ...]) -> ObservationBuilder:
    """Wire the production builder, registry, recognizer, and selector engine."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=_FakeOcrService(lines=lines),
    )


def _action_executor(session: FakeSession) -> ActionExecutor:
    """Build an offline executor with the production selector registry."""

    return ActionExecutor(
        selector_registry=build_default_selector_registry(),
        session=session,
        stable_click_delay_ms=0,
        post_action_observe_delay_ms=0,
        chat_stable_click_delay_ms=0,
        chat_post_action_observe_delay_ms=0,
        logger=build_logger(),
        sleep=lambda _: None,
    )


class ResearchTreeVisualControlTests(unittest.TestCase):
    """Keep the Development tree identity and measured Back bounded."""

    def test_development_profile_exposes_only_measured_back(self) -> None:
        """Recognizes the reviewed identity and publishes its template Back control."""

        recognition = load_visual_screen_recognizer().recognize(_load_fixture())

        self.assertEqual(recognition.profile_ids, ("research_tree_development",))
        self.assertEqual(
            {item.screen_type for item in recognition.evidence},
            {ScreenType.PNC_RESEARCH_TREE},
        )
        self.assertEqual(
            {item.selector_id for item in recognition.controls},
            {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
        )
        back = recognition.controls[0]
        self.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(back.bounds, Bounds(25, 11, 52, 32))
        self.assertEqual(back.action_point, (51, 27))

        scaled = load_visual_screen_recognizer().recognize(_load_fixture().resize((900, 1600)))
        self.assertEqual(scaled.profile_ids, ("research_tree_development",))
        scaled_back = scaled.controls[0]
        self.assertEqual(scaled_back.bounds, Bounds(42, 18, 86, 54))

    def test_missing_identity_anchor_abstains(self) -> None:
        """Removing either independent identity anchor prevents the profile match."""

        recognizer = load_visual_screen_recognizer()
        for box in (TITLE_BOX, ICON_BOX):
            with self.subTest(box=box):
                image = _load_fixture()
                image.paste((0, 0, 0), box)
                recognition = recognizer.recognize(image)
                self.assertNotIn("research_tree_development", recognition.profile_ids)
                self.assertFalse(recognition.controls)

    def test_missing_back_anchor_keeps_identity_but_blocks_back(self) -> None:
        """A recognized tree without the measured Back match publishes no Back target."""

        image = _load_fixture()
        image.paste((0, 0, 0), BACK_BOX)

        recognition = load_visual_screen_recognizer().recognize(image)

        self.assertEqual(recognition.profile_ids, ("research_tree_development",))
        self.assertFalse(recognition.controls)

    def test_institute_fixture_does_not_match_development_tree_profile(self) -> None:
        """Keeps the Development tree profile scoped away from its Institute source."""

        with Image.open(TEST_DATA_ROOT / "screen_recognition" / "institute_audit.png") as source:
            recognition = load_visual_screen_recognizer().recognize(source.convert("RGB"))

        self.assertNotIn("research_tree_development", recognition.profile_ids)

    def test_research_detail_profile_exposes_only_blue_research_action(self) -> None:
        """Recognizes detail chrome and maps only the blue normal Research control."""

        recognizer = load_visual_screen_recognizer()
        recognition = recognizer.recognize(_load_detail_fixture())

        self.assertEqual(recognition.profile_ids, ("research_tree_node_detail",))
        self.assertEqual(
            {item.screen_type for item in recognition.evidence},
            {ScreenType.PNC_RESEARCH_TREE},
        )
        self.assertEqual(
            {item.selector_id for item in recognition.controls},
            {UiElementId.PNC_RESEARCH_START_BUTTON},
        )
        start = recognition.controls[0]
        self.assertEqual(start.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertTrue(_bounds_from_box(DETAIL_RESEARCH_BUTTON_BOX).contains_point(start.action_point))

        scaled = recognizer.recognize(_load_detail_fixture().resize((900, 1600)))
        self.assertEqual(scaled.profile_ids, ("research_tree_node_detail",))
        scaled_start = scaled.controls[0]
        self.assertTrue(_scale_box(DETAIL_RESEARCH_BUTTON_BOX, 900 / 540).contains_point(scaled_start.action_point))

    def test_active_detail_profile_exposes_identity_without_controls(self) -> None:
        """Recognizes the running detail state without exposing Speedup or cancel controls."""

        recognizer = load_visual_screen_recognizer()
        recognition = recognizer.recognize(_load_active_detail_fixture())

        self.assertEqual(recognition.profile_ids, ("research_tree_node_detail_active",))
        self.assertEqual(
            {item.screen_type for item in recognition.evidence},
            {ScreenType.PNC_RESEARCH_TREE},
        )
        self.assertEqual(recognition.controls, ())
        self.assertTrue(_bounds_from_box(ACTIVE_SPEEDUP_BOX).contains_point((437, 447)))

        reloaded = recognizer.recognize(_load_reloaded_active_detail_fixture())
        self.assertEqual(reloaded.profile_ids, ("research_tree_node_detail_active",))
        self.assertEqual(reloaded.controls, ())

        scaled = recognizer.recognize(_load_active_detail_fixture().resize((900, 1600)))
        self.assertEqual(scaled.profile_ids, ("research_tree_node_detail_active",))
        self.assertEqual(scaled.controls, ())

        base = recognizer.recognize(_load_detail_fixture())
        self.assertEqual(base.profile_ids, ("research_tree_node_detail",))

    def test_active_detail_observation_owns_tree_without_start(self) -> None:
        """Carries active detail identity through NavigationPerception without Start."""

        observation = _perception(_active_detail_ocr_lines()).build(
            _capture(_load_active_detail_fixture())
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(observation.decision.layout_id, "research_tree_development")
        self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
        self.assertFalse(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_START_BUTTON))

    def test_active_detail_required_update_still_owns_popup(self) -> None:
        """Keeps the required-update modal guard ahead of active-detail ownership."""

        popup_lines = (
            *_active_detail_ocr_lines(),
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _perception(popup_lines).build(
            _capture(_load_active_detail_fixture())
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_START_BUTTON))

    def test_research_detail_observation_binds_start_to_shared_tree_layout(self) -> None:
        """Binds the proved detail action to the current frame and tree layout."""

        observation = _perception().build(_capture(_load_detail_fixture()))

        self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
        start = observation.require(UiElementId.PNC_RESEARCH_START_BUTTON)
        self.assertEqual(start.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(start.source_screen, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(start.source_layout_id, "research_tree_development")
        self.assertEqual(start.frame_ref, observation.frame_ref)

    def test_production_builder_publishes_start_to_research_consumer(self) -> None:
        """Carries the measured Start through the legacy task's observed action boundary."""

        detail = _observation_builder(_detail_ocr_lines()).build(
            _capture(_load_detail_fixture())
        )
        self.assertEqual(detail.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(detail.decision.guard, GuardVerdict.CLEAR)
        start = detail.require(UiElementId.PNC_RESEARCH_START_BUTTON)
        self.assertEqual(start.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(start.source_screen, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(start.source_layout_id, "research_tree_development")
        self.assertEqual(start.frame_ref, detail.frame_ref)

        task = ResearchTask()
        context = Mock(params=task.parse_params({"priority": ["development"]}))
        before = make_observation(
            ScreenType.PNC_RESEARCH_TREE,
            list_entries=(
                make_entry(
                    ListEntryKind.RESEARCH,
                    title="Construction I",
                    metadata={"category": "development"},
                ),
            ),
        )
        start_action = next(
            action
            for action in task.plan(context, before)
            if isinstance(action, TapAction)
            and action.selector_id == UiElementId.PNC_RESEARCH_START_BUTTON
        )
        active = _observation_builder(_active_detail_ocr_lines()).build(
            _capture(_load_active_detail_fixture())
        )
        session = FakeSession()
        result = _make_observed_action_executor(session).execute_actions(
            (start_action,),
            detail,
            observe=lambda label, request=None: active,
        )

        self.assertEqual(session.taps, [start.action_point])
        self.assertTrue(task.verify(context, before, result.observation).succeeded)

    def test_production_builder_blocks_start_behind_required_update(self) -> None:
        """Keeps the measured background Start unavailable when an update owns the frame."""

        popup_lines = (
            *_detail_ocr_lines(),
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _observation_builder(popup_lines).build(
            _capture(_load_detail_fixture())
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_START_BUTTON))

    def test_research_detail_owns_frame_before_generic_popup_fallback(self) -> None:
        """Keeps live detail OCR from letting a generic popup fallback steal ownership."""

        detail_lines = _detail_ocr_lines()
        generic_popup = ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, "generic_detail_conflict"),),
        )

        def conflicting_popup(
            *, image: Image.Image, lines: tuple[OcrLine, ...], anchors: tuple[object, ...]
        ) -> ObservationAdditions:
            del image, anchors
            self.assertTrue(
                {"RESEARCH", "RESEARCHNOW"}.issubset(
                    {line.text.replace(" ", "").upper() for line in lines}
                )
            )
            return generic_popup

        unowned_capture = _capture(_load_detail_fixture())
        unowned_context = ObservationOcrContext(
            unowned_capture.image,
            _FakeOcrService(lines=detail_lines),
            unowned_capture.frame_ref,
            "research-tree-visual-controls-test",
        )
        with patch(
            "pnc_automation.app.pnc.vision.pnc_observation_enricher._build_popup_additions",
            side_effect=conflicting_popup,
        ) as fallback:
            unowned = PncObservationEnricher().detect_interruption(
                unowned_capture.image,
                ocr_context=unowned_context,
            )
            self.assertEqual(unowned.screen_evidence[0].screen_type, ScreenType.PNC_POPUP)
            fallback.assert_called_once()
            fallback.reset_mock()

            owned = _perception(detail_lines).build(_capture(_load_detail_fixture()))
            fallback.assert_not_called()

        self.assertEqual(owned.screen_type, ScreenType.PNC_RESEARCH_TREE)
        self.assertTrue(owned.has(UiElementId.PNC_RESEARCH_START_BUTTON))
        self.assertEqual(owned.decision.guard, GuardVerdict.CLEAR)

    def test_research_start_dispatches_observed_blue_action_point(self) -> None:
        """Dispatches Start only at the template point observed in the current detail frame."""

        observation = _perception().build(_capture(_load_detail_fixture()))
        start = observation.require(UiElementId.PNC_RESEARCH_START_BUTTON)
        session = FakeSession()

        self.assertTrue(
            _action_executor(session).execute_action(
                TapAction(selector_id=UiElementId.PNC_RESEARCH_START_BUTTON),
                observation,
            )
        )
        self.assertEqual(session.taps, [start.action_point])
        self.assertTrue(_bounds_from_box(DETAIL_RESEARCH_BUTTON_BOX).contains_point(start.action_point))

    def test_research_start_rejects_foreign_frame_geometry(self) -> None:
        """Rejects a Start target rebound to a different captured detail frame."""

        capture = _capture(_load_detail_fixture())
        observation = _perception().build(capture)
        start = observation.require(UiElementId.PNC_RESEARCH_START_BUTTON)
        foreign = _capture(_load_detail_fixture())
        observation.visible_elements[UiElementId.PNC_RESEARCH_START_BUTTON] = replace(
            start,
            frame_ref=foreign.frame_ref,
        )
        session = FakeSession()

        with self.assertRaises(SelectorResolutionError):
            _action_executor(session).execute_action(
                TapAction(selector_id=UiElementId.PNC_RESEARCH_START_BUTTON),
                observation,
            )
        self.assertEqual(session.taps, [])

    def test_research_detail_popup_suppresses_start(self) -> None:
        """Keeps a required update popup as the owner even when detail anchors remain visible."""

        popup_lines = (
            *_detail_ocr_lines(),
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _perception(popup_lines).build(_capture(_load_detail_fixture()))

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_RESEARCH_START_BUTTON))

    def test_research_detail_requires_both_identity_anchors(self) -> None:
        """Abstains from the detail profile when either independent identity anchor is absent."""

        recognizer = load_visual_screen_recognizer()
        for box in (DETAIL_HEADER_BOX, DETAIL_TIME_LABELS_BOX):
            with self.subTest(box=box):
                image = _load_detail_fixture()
                image.paste((0, 0, 0), box)
                recognition = recognizer.recognize(image)
                self.assertNotIn("research_tree_node_detail", recognition.profile_ids)
                self.assertNotIn(
                    UiElementId.PNC_RESEARCH_START_BUTTON,
                    {item.selector_id for item in recognition.controls},
                )

    def test_gold_research_now_alone_never_produces_start(self) -> None:
        """Retains detail identity while withholding Start when only gold Research Now remains."""

        image = _load_detail_fixture()
        image.paste((8, 29, 65), DETAIL_RESEARCH_BUTTON_BOX)
        recognition = load_visual_screen_recognizer().recognize(image)

        self.assertEqual(recognition.profile_ids, ("research_tree_node_detail",))
        self.assertNotIn(
            UiElementId.PNC_RESEARCH_START_BUTTON,
            {item.selector_id for item in recognition.controls},
        )

    def test_blocking_popup_suppresses_research_tree_back(self) -> None:
        """A blocking update prompt owns the frame even when tree anchors remain visible."""

        popup_lines = (
            OcrLine(
                "New version detected. Tap Confirm to update.",
                Bounds(58, 380, 420, 28),
                1.0,
            ),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        observation = _perception(popup_lines).build(_capture(_load_fixture()))

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_back_dispatch_is_bound_to_the_current_research_tree_frame(self) -> None:
        """Dispatches Back only from the current visually matched frame."""

        observation = _perception().build(_capture(_load_fixture()))
        self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)
        back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        self.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(back.source_screen, ScreenType.PNC_RESEARCH_TREE)
        self.assertEqual(back.source_layout_id, "research_tree_development")
        self.assertEqual(back.frame_ref, observation.frame_ref)

        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        self.assertTrue(
            executor.execute_action(
                TapAction(selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
                observation,
            )
        )
        self.assertEqual(session.taps, [(51, 27)])

    def test_foreign_frame_back_geometry_is_rejected(self) -> None:
        """Rejects a Back target rebound to a different captured frame."""

        capture = _capture(_load_fixture())
        observation = _perception().build(capture)
        back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        foreign = _capture(_load_fixture())
        observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT] = replace(
            back,
            frame_ref=foreign.frame_ref,
        )

        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(
                TapAction(selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT),
                observation,
            )
        self.assertEqual(session.taps, [])

    def test_research_start_is_supported_only_on_proved_detail(self) -> None:
        """The base Development profile stays inert while detail owns the blue Start control."""

        registry = build_default_selector_registry()
        definition = registry.require(UiElementId.PNC_RESEARCH_START_BUTTON)
        self.assertEqual(definition.detection_kind, DetectionKind.SEMANTIC)
        self.assertEqual(definition.status, SelectorStatus.PLANNED)
        self.assertIs(registry.require_supported(UiElementId.PNC_RESEARCH_START_BUTTON), definition)
        self.assertNotIn(
            UiElementId.PNC_RESEARCH_START_BUTTON,
            {
                item.selector_id
                for item in load_visual_screen_recognizer().recognize(_load_fixture()).controls
            },
        )
        self.assertIn(
            UiElementId.PNC_RESEARCH_START_BUTTON,
            {
                item.selector_id
                for item in load_visual_screen_recognizer().recognize(_load_detail_fixture()).controls
            },
        )


if __name__ == "__main__":
    unittest.main()
