"""Contract tests for conservative screen decisions and action authorization."""

from __future__ import annotations

import logging
import unittest
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterator

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    InputTextAction,
    KeyEventAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationAdditions,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_ocr_capabilities import (
    can_attempt_screen_family_ocr,
    runtime_screen_family_ocr_types,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds


IMAGE_SIZE = (540, 960)
FRAME = FrameRef(
    session_id="contract-test-session",
    session_epoch=1,
    capture_sequence=1,
    input_sequence=0,
    captured_at=datetime(2026, 9, 10, tzinfo=UTC),
)
OTHER_FRAME = FrameRef(
    session_id="contract-test-session",
    session_epoch=1,
    capture_sequence=2,
    input_sequence=0,
    captured_at=datetime(2026, 9, 10, tzinfo=UTC),
)


class EmptySelectorEngine:
    """Returns no raw selector matches for builder contract tests."""

    def detect(self, image, registry, *, selector_ids=None, ocr_context=None):
        del image, registry, selector_ids, ocr_context
        return ()


@dataclass
class ScriptedEnricher:
    """Returns deterministic guard and enrichment stages without OCR or templates."""

    enrichments: list[ObservationAdditions]

    def recognize_guards(self, image, request, *, ocr_context):
        del image, request, ocr_context
        return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)

    def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions):
        del image, screen_type, visible_elements, request, ocr_context, ocr_regions
        if not self.enrichments:
            raise AssertionError("Scripted enricher received more calls than expected")
        return self.enrichments.pop(0)


class RecordingSession:
    """Captures any input that a contract accidentally authorizes."""

    def __init__(self) -> None:
        self.taps: list[tuple[int, int]] = []
        self.texts: list[str] = []
        self.keys: list[str] = []
        self.swipes: list[tuple[int, int, int, int]] = []

    @contextmanager
    def authorized_input(self, frame_ref: FrameRef) -> Iterator[None]:
        del frame_ref
        yield

    def tap_point(self, x: int, y: int) -> None:
        self.taps.append((x, y))

    def input_text(self, text: str) -> None:
        self.texts.append(text)

    def press_key(self, key_code: str) -> None:
        self.keys.append(key_code)

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, **kwargs) -> None:
        del kwargs
        self.swipes.append((start_x, start_y, end_x, end_y))


class ScreenDecisionContractTests(unittest.TestCase):
    """Locks the conservative identity, provenance, and input boundaries."""

    def test_mixed_supporting_and_conflicting_evidence_abstains(self) -> None:
        decision = ScreenClassifier().decide(
            {},
            evidence=(
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "home-parser"),
                ScreenEvidence(ScreenType.PNC_WORLD_MAP, "world-parser"),
            ),
            guard=GuardVerdict.CLEAR,
        )

        self.assertEqual(decision.effective_screen, ScreenType.UNKNOWN)
        self.assertFalse(decision.action_eligible)

    def test_incompatible_layouts_abstain(self) -> None:
        decision = ScreenClassifier().decide(
            {},
            evidence=(
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "home-a", "home-layout-a"),
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "home-b", "home-layout-b"),
            ),
            guard=GuardVerdict.CLEAR,
        )

        self.assertEqual(decision.effective_screen, ScreenType.UNKNOWN)
        self.assertEqual(decision.guard, GuardVerdict.UNRESOLVED)
        self.assertFalse(decision.action_eligible)

    def test_popup_over_bag_retains_base_and_uses_popup_layout(self) -> None:
        decision = ScreenClassifier().decide(
            {},
            evidence=(
                ScreenEvidence(ScreenType.PNC_BAG, "bag-parser", "bag-layout"),
                ScreenEvidence(ScreenType.PNC_POPUP, "popup-parser", "popup-layout"),
            ),
            guard=GuardVerdict.CLEAR,
        )

        self.assertEqual(decision.base_screen, ScreenType.PNC_BAG)
        self.assertEqual(decision.effective_screen, ScreenType.PNC_POPUP)
        self.assertEqual(decision.layout_id, "popup-layout")
        self.assertEqual(decision.guard, GuardVerdict.BLOCKED)
        self.assertTrue(decision.action_eligible)

    def test_unresolved_and_not_evaluated_are_never_actionable(self) -> None:
        for guard in (GuardVerdict.UNRESOLVED, GuardVerdict.NOT_EVALUATED):
            with self.subTest(guard=guard):
                decision = ScreenDecision(
                    base_screen=ScreenType.PNC_BAG,
                    effective_screen=ScreenType.PNC_BAG,
                    guard=guard,
                )
                self.assertFalse(decision.action_eligible)

    def test_two_modal_types_or_modal_layouts_conflict(self) -> None:
        classifier = ScreenClassifier()
        cases = (
            (
                ScreenEvidence(ScreenType.PNC_POPUP, "generic", "generic-modal"),
                ScreenEvidence(ScreenType.PNC_VIP_DAILY_RESET, "vip", "vip-modal"),
            ),
            (
                ScreenEvidence(ScreenType.PNC_POPUP, "generic-a", "generic-a"),
                ScreenEvidence(ScreenType.PNC_POPUP, "generic-b", "generic-b"),
            ),
        )
        for evidence in cases:
            with self.subTest(evidence=evidence):
                decision = classifier.decide({}, evidence=evidence, guard=GuardVerdict.CLEAR)
                self.assertEqual(decision.effective_screen, ScreenType.UNKNOWN)
                self.assertEqual(decision.guard, GuardVerdict.UNRESOLVED)
                self.assertFalse(decision.action_eligible)

    def test_geometry_cannot_establish_screen_identity(self) -> None:
        visible = {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT: _element(
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                source_kind=VisibleElementSourceKind.GEOMETRY,
            ),
            UiElementId.PNC_MORE_MANAGE_CHAR: _element(
                UiElementId.PNC_MORE_MANAGE_CHAR,
                source_kind=VisibleElementSourceKind.GEOMETRY,
            ),
        }

        decision = ScreenClassifier().decide(visible, guard=GuardVerdict.CLEAR)

        self.assertEqual(decision.effective_screen, ScreenType.UNKNOWN)
        self.assertFalse(decision.action_eligible)

    def test_unsupported_viewport_clears_semantic_geometry_and_raw_point_facts(self) -> None:
        additions = ObservationAdditions(
            visible_elements={
                UiElementId.PNC_MORE_MANAGE_CHAR: _element(
                    UiElementId.PNC_MORE_MANAGE_CHAR,
                    source_kind=VisibleElementSourceKind.GEOMETRY,
                    identity_evidence=False,
                )
            },
            spatial_surface=_spatial_surface(),
            screen_evidence=(ScreenEvidence(ScreenType.PNC_SETTINGS, "settings-parser"),),
        )
        unsupported = _builder(ScriptedEnricher([additions])).build(
            _screenshot((540, 1000)),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_SETTINGS),
        )
        self.assertEqual(unsupported.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(unsupported.visible_elements, {})
        self.assertIsNone(unsupported.spatial_surface)
        self.assertEqual(unsupported.decision.guard, GuardVerdict.UNRESOLVED)

        supported = _builder(ScriptedEnricher([additions])).build(
            _screenshot(),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_SETTINGS),
        )
        self.assertEqual(supported.screen_type, ScreenType.PNC_SETTINGS)
        self.assertTrue(supported.has(UiElementId.PNC_MORE_MANAGE_CHAR))
        self.assertIsNotNone(supported.spatial_surface)

    def test_every_registered_ocr_family_accepts_its_exact_screen(self) -> None:
        for screen_type in runtime_screen_family_ocr_types():
            with self.subTest(screen_type=screen_type):
                self.assertTrue(
                    can_attempt_screen_family_ocr(
                        request_screen=screen_type,
                        observed_screen=screen_type,
                    )
                )

    def test_builder_clears_all_facts_after_late_non_geometry_conflict(self) -> None:
        additions = ObservationAdditions(
            visible_elements={UiElementId.PNC_HOME_BUILD_BUTTON: _element(UiElementId.PNC_HOME_BUILD_BUTTON)},
            list_entries=(_entry(),),
            spatial_surface=_spatial_surface(),
            screen_evidence=(
                ScreenEvidence(ScreenType.PNC_HOME_CITY, "home-parser"),
                ScreenEvidence(ScreenType.PNC_WORLD_MAP, "world-parser"),
            ),
            text_field_states={
                UiElementId.PNC_CHAT_INPUT_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                    text="draft",
                    empty=False,
                )
            },
        )
        observation = _builder(ScriptedEnricher([additions])).build(_screenshot())

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(observation.visible_elements, {})
        self.assertEqual(observation.list_entries, ())
        self.assertIsNone(observation.spatial_surface)
        self.assertEqual(observation.text_field_states, {})

    def test_narrow_identity_fallback_preserves_existing_scoped_facts(self) -> None:
        scoped = ObservationAdditions(
            list_entries=(_entry(),),
            spatial_surface=_spatial_surface(),
            text_field_states={
                UiElementId.PNC_CHAT_INPUT_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                    text="scoped draft",
                    empty=False,
                )
            },
        )
        fallback_identity = ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_SETTINGS, "settings-fallback", "settings"),)
        )
        observation = _builder(ScriptedEnricher([scoped, fallback_identity])).build(
            _screenshot(),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_SETTINGS),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_SETTINGS)
        self.assertEqual(
            observation.list_entries,
            (
                replace(
                    scoped.list_entries[0],
                    frame_ref=FRAME,
                    source_screen=ScreenType.PNC_SETTINGS,
                    source_layout_id="settings",
                ),
            ),
        )
        self.assertEqual(observation.spatial_surface, scoped.spatial_surface)
        self.assertEqual(observation.text_field_states, scoped.text_field_states)

    def test_prebound_element_frame_and_row_layout_contradictions_are_rejected(self) -> None:
        builder = _builder(ScriptedEnricher([]))
        decision = ScreenDecision(
            base_screen=ScreenType.PNC_HOME_CITY,
            effective_screen=ScreenType.PNC_HOME_CITY,
            layout_id="home-layout",
            guard=GuardVerdict.CLEAR,
        )
        evidence = ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "home", "home-layout"),)
        )
        element_cases = (
            {"frame_ref": OTHER_FRAME},
            {"source_screen": ScreenType.PNC_BAG},
            {"source_layout_id": "other-layout"},
        )
        for contradiction in element_cases:
            with self.subTest(element_contradiction=contradiction):
                element = _element(
                    UiElementId.PNC_HOME_BUILD_BUTTON,
                    identity_evidence=False,
                    **contradiction,
                )
                with self.assertRaises(SelectorResolutionError):
                    builder._publish(
                        screenshot=_screenshot(),
                        decision=decision,
                        visible_elements={UiElementId.PNC_HOME_BUILD_BUTTON: element},
                        additions=evidence,
                    )

        row_cases = (
            {"frame_ref": OTHER_FRAME},
            {"source_screen": ScreenType.PNC_BAG},
            {"source_layout_id": "other-layout"},
        )
        for contradiction in row_cases:
            with self.subTest(row_contradiction=contradiction):
                row = _entry(**contradiction)
                with self.assertRaises(SelectorResolutionError):
                    builder._publish(
                        screenshot=_screenshot(),
                        decision=decision,
                        visible_elements={},
                        additions=replace(evidence, list_entries=(row,)),
                    )

    def test_coordinate_only_observation_rejects_ordinary_inputs(self) -> None:
        observation = _observation(
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_WORLD_MAP,
                effective_screen=ScreenType.PNC_WORLD_MAP,
                guard=GuardVerdict.CLEAR,
                coordinate_only=True,
            ),
            visible_elements={UiElementId.PNC_CHAT_INPUT_FIELD: _element(UiElementId.PNC_CHAT_INPUT_FIELD)},
            list_entries=(_entry(),),
        )
        executor = _executor()
        actions = (
            TapPointAction(x=10, y=10),
            TapAction(selector_id=UiElementId.PNC_CHAT_INPUT_FIELD),
            TapListEntryAction(entry_kind=ListEntryKind.DAILY_QUEST, title_text="Scoped row"),
            InputTextAction(text="blocked", selector_id=UiElementId.PNC_CHAT_INPUT_FIELD),
            KeyEventAction(key_code="KEYCODE_BACK"),
            SwipeAction(direction="up"),
        )
        for action in actions:
            with self.subTest(action=type(action).__name__):
                with self.assertRaises(SelectorResolutionError):
                    executor.execute_action(action, observation)

    def test_blocked_observation_rejects_explicit_spatial_points(self) -> None:
        observation = _observation(
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_BAG,
                effective_screen=ScreenType.PNC_POPUP,
                layout_id="popup-layout",
                guard=GuardVerdict.BLOCKED,
            ),
            visible_elements={UiElementId.PNC_POPUP_CLOSE_BUTTON: _element(UiElementId.PNC_POPUP_CLOSE_BUTTON)},
        )

        with self.assertRaisesRegex(SelectorResolutionError, "blocked screen"):
            _executor().execute_action(
                TapSpatialObjectAction(target_point=(100, 100)),
                observation,
            )

    def test_own_selector_backed_popup_control_remains_eligible(self) -> None:
        observation = _observation(
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_BAG,
                effective_screen=ScreenType.PNC_POPUP,
                layout_id="popup-layout",
                guard=GuardVerdict.BLOCKED,
            ),
            visible_elements={UiElementId.PNC_POPUP_CLOSE_BUTTON: _element(UiElementId.PNC_POPUP_CLOSE_BUTTON)},
        )
        session = RecordingSession()
        executor = _executor(session)

        self.assertTrue(executor.execute_action(TapAction(selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON), observation))
        self.assertEqual(session.taps, [(5, 5)])


def _builder(enricher: ScriptedEnricher) -> ObservationBuilder:
    return ObservationBuilder(
        selector_registry=build_default_selector_registry(),
        selector_engine=EmptySelectorEngine(),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
    )


def _screenshot(image_size: tuple[int, int] = IMAGE_SIZE) -> CapturedScreenshot:
    return CapturedScreenshot(
        artifact=None,
        image=Image.new("RGB", image_size, (8, 9, 10)),
        image_format="PNG",
        payload=b"contract-frame",
        ephemeral_captured_at=FRAME.captured_at,
        frame_ref=FRAME,
    )


def _element(
    selector_id: UiElementId,
    *,
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    identity_evidence: bool = True,
    frame_ref: FrameRef | None = None,
    source_screen: ScreenType | None = None,
    source_layout_id: str | None = None,
) -> VisibleElement:
    return VisibleElement(
        selector_id=selector_id,
        bounds=Bounds(x=5, y=5, width=10, height=10),
        confidence=1.0,
        source_kind=source_kind,
        identity_evidence=identity_evidence,
        action_point=(5, 5),
        frame_ref=frame_ref,
        source_screen=source_screen,
        source_layout_id=source_layout_id,
    )


def _entry(
    *,
    frame_ref: FrameRef | None = None,
    source_screen: ScreenType | None = None,
    source_layout_id: str | None = None,
) -> DetectedListEntry:
    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=Bounds(x=20, y=20, width=40, height=20),
        title_text="Scoped row",
        action_point=(30, 30),
        frame_ref=frame_ref,
        source_screen=source_screen,
        source_layout_id=source_layout_id,
    )


def _spatial_surface() -> SpatialSurfaceObservation:
    return SpatialSurfaceObservation(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
    )


def _observation(
    *,
    decision: ScreenDecision,
    visible_elements: dict[UiElementId, VisibleElement] | None = None,
    list_entries: tuple[DetectedListEntry, ...] = (),
) -> Observation:
    bound_elements = {
        selector_id: _bound_element(element, decision)
        for selector_id, element in (visible_elements or {}).items()
    }
    bound_entries = tuple(_bound_entry(entry, decision) for entry in list_entries)
    return Observation(
        decision=decision,
        visible_elements=bound_elements,
        list_entries=bound_entries,
        image_size=IMAGE_SIZE,
        frame_ref=FRAME,
    )


def _bound_element(element: VisibleElement, decision: ScreenDecision) -> VisibleElement:
    return replace(
        element,
        frame_ref=FRAME,
        source_screen=decision.effective_screen,
        source_layout_id=decision.layout_id,
    )


def _bound_entry(entry: DetectedListEntry, decision: ScreenDecision) -> DetectedListEntry:
    return replace(
        entry,
        frame_ref=FRAME,
        source_screen=decision.effective_screen,
        source_layout_id=decision.layout_id,
    )


def _executor(session: RecordingSession | None = None) -> ActionExecutor:
    return ActionExecutor(
        selector_registry=build_default_selector_registry(),
        session=session or RecordingSession(),
        stable_click_delay_ms=0,
        post_action_observe_delay_ms=0,
        chat_stable_click_delay_ms=0,
        chat_post_action_observe_delay_ms=0,
        logger=logging.LoggerAdapter(logging.getLogger("screen-contract"), {}),
        sleep=lambda _: None,
    )


if __name__ == "__main__":
    unittest.main()
