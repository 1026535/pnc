"""Stage Detail -> Hero Formation preparation proof contract tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from pnc_automation.app.automation.match3 import (
    FORMATION_PREPARATION_LAYOUT_ID,
    FormationPreparationError,
    FormationPreparationProof,
    require_formation_preparation_proof,
)
from pnc_automation.app.pnc.domain.campaign import (
    CampaignChapterIdentity,
    CampaignMode,
    CampaignNodeFacts,
    CampaignStageDetail,
)
from pnc_automation.app.pnc.domain.match3 import (
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Target,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    VisibleElement,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    SwipeDispatch,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

_SESSION = "session-1"
_EPOCH = 1
_STAGE_LAYOUT = "campaign_stage_chapter_6"
_LEFT_CHALLENGE_BOUNDS = Bounds(28, 714, 190, 68)
_CENTERED_CHALLENGE_BOUNDS = Bounds(178, 643, 184, 60)
_FORMATION_BACK_BOUNDS = Bounds(23, 7, 57, 63)


def _frame(*, capture: int, input_sequence: int, session: str = _SESSION, epoch: int = _EPOCH) -> FrameRef:
    """One session frame reference."""

    return FrameRef(
        session_id=session,
        session_epoch=epoch,
        capture_sequence=capture,
        input_sequence=input_sequence,
        captured_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
    )


def _stage_detail(frame: FrameRef, *, chapter: int = 6, stage: int = 4, **overrides: object) -> CampaignStageDetail:
    """Source-frame Campaign stage facts, defaulting to an affordable supported stage."""

    values: dict[str, object] = {
        "chapter_number": chapter,
        "stage_number": stage,
        "mode": CampaignMode.STANDARD,
        "action_points": 60,
        "max_action_points": 120,
        "challenge_cost": 12,
        "frame_ref": frame,
        "source_screen": ScreenType.PNC_CAMPAIGN_STAGE,
        "source_layout_id": _STAGE_LAYOUT,
    }
    values.update(overrides)
    return CampaignStageDetail(**values)  # type: ignore[arg-type]


def _challenge_element(frame: FrameRef, bounds: Bounds) -> VisibleElement:
    """The same-frame published stage Challenge control."""

    return VisibleElement(
        selector_id=UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
        bounds=bounds,
        confidence=0.98,
        frame_ref=frame,
        source_screen=ScreenType.PNC_CAMPAIGN_STAGE,
        source_layout_id=_STAGE_LAYOUT,
    )


def _stage_observation(
    *, detail: CampaignStageDetail, elements: dict[UiElementId, VisibleElement], frame: FrameRef
) -> Observation:
    """A clear, unblocked Campaign stage-detail observation."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_CAMPAIGN_STAGE,
            effective_screen=ScreenType.PNC_CAMPAIGN_STAGE,
            layout_id=_STAGE_LAYOUT,
            guard=GuardVerdict.CLEAR,
        ),
        visible_elements=elements,
        campaign_stage=detail,
        frame_ref=frame,
    )


def _formation_observation(frame: FrameRef, back: VisibleElement) -> Observation:
    """A clear, unblocked formation preparation destination observation."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_HERO_FORMATION,
            effective_screen=ScreenType.PNC_HERO_FORMATION,
            layout_id=FORMATION_PREPARATION_LAYOUT_ID,
            guard=GuardVerdict.CLEAR,
        ),
        visible_elements={UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON: back},
        frame_ref=frame,
    )


def _back_element(frame: FrameRef) -> VisibleElement:
    """The dedicated formation Back control provenanced to its frame."""

    return VisibleElement(
        selector_id=UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
        bounds=_FORMATION_BACK_BOUNDS,
        confidence=0.99,
        frame_ref=frame,
        source_screen=ScreenType.PNC_HERO_FORMATION,
        source_layout_id=FORMATION_PREPARATION_LAYOUT_ID,
    )


def _request(*, stage: int = 4, chapter: int = 6, mode: CampaignMode | None = CampaignMode.STANDARD) -> Match3Request:
    """A Campaign request selecting the given observed node ordinals."""

    return Match3Request(
        context=Match3Context.CAMPAIGN,
        mode=Match3Mode.SOLVER,
        target=Match3Target(
            context=Match3Context.CAMPAIGN,
            campaign_node=CampaignNodeFacts(
                chapter_number=chapter, stage_number=stage, mode=mode
            ),
        ),
    )


def _dispatch(source_frame: FrameRef, point: tuple[int, int]) -> InputDispatchRecord:
    """The actual Challenge tap receipt authorized by the source frame."""

    return InputDispatchRecord(
        source_frame=source_frame,
        dispatch=TapDispatch(point=point, input_sequence=source_frame.input_sequence + 1),
    )


def _valid_transition(
    *, stage: int, challenge_bounds: Bounds, tap_point: tuple[int, int]
) -> tuple[Match3Request, Observation, InputDispatchRecord, Observation]:
    """One complete valid stage-detail -> formation-preparation transition."""

    source_frame = _frame(capture=10, input_sequence=4)
    detail = _stage_detail(source_frame, stage=stage)
    challenge = _challenge_element(source_frame, challenge_bounds)
    source = _stage_observation(
        detail=detail,
        elements={UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON: challenge},
        frame=source_frame,
    )
    dispatch = _dispatch(source_frame, tap_point)
    destination_frame = _frame(capture=11, input_sequence=5)
    destination = _formation_observation(destination_frame, _back_element(destination_frame))
    return _request(stage=stage), source, dispatch, destination


class FormationPreparationProofTests(unittest.TestCase):
    """The proof succeeds only across one fully bound source, tap, and destination."""

    def test_valid_stage_6_4_left_challenge_produces_proof(self) -> None:
        """A valid 6-4 transition with a left-position Challenge tap proves out."""

        request, source, dispatch, destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        proof = require_formation_preparation_proof(
            request=request, source=source, dispatch=dispatch, destination=destination
        )
        self.assertIs(proof.request, request)
        self.assertIs(proof.target, request.target)
        self.assertIs(proof.stage_detail, source.campaign_stage)
        self.assertIs(proof.challenge, source.get(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertIs(proof.dispatch, dispatch)
        self.assertIs(proof.source_frame, source.frame_ref)
        self.assertIs(proof.destination_frame, destination.frame_ref)
        self.assertIs(proof.destination_decision, destination.decision)
        self.assertIs(
            proof.formation_back,
            destination.get(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON),
        )

    def test_valid_stage_6_5_centered_challenge_produces_proof(self) -> None:
        """A valid 6-5 transition with a centered Challenge tap proves out."""

        request, source, dispatch, destination = _valid_transition(
            stage=5, challenge_bounds=_CENTERED_CHALLENGE_BOUNDS, tap_point=(270, 673)
        )
        proof = require_formation_preparation_proof(
            request=request, source=source, dispatch=dispatch, destination=destination
        )
        self.assertEqual(proof.stage_detail.chapter_number, 6)
        self.assertEqual(proof.stage_detail.stage_number, 5)
        self.assertEqual(proof.destination_decision.layout_id, FORMATION_PREPARATION_LAYOUT_ID)

    def test_source_facts_remain_source_frame_observations(self) -> None:
        """The proof never relabels source AP/cost as formation-screen facts."""

        request, source, dispatch, destination = _valid_transition(
            stage=5, challenge_bounds=_CENTERED_CHALLENGE_BOUNDS, tap_point=(270, 673)
        )
        proof = require_formation_preparation_proof(
            request=request, source=source, dispatch=dispatch, destination=destination
        )
        self.assertEqual(proof.stage_detail.action_points, 60)
        self.assertEqual(proof.stage_detail.challenge_cost, 12)
        self.assertEqual(proof.stage_detail.source_screen, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertIs(proof.stage_detail.frame_ref, proof.source_frame)

    def test_selected_entry_ordinals_satisfy_target_identity(self) -> None:
        """A selected chapter row may carry the observed node instead of campaign_node."""

        chapter_frame = _frame(capture=6, input_sequence=2)
        chapter_decision = ScreenDecision(
            base_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            effective_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            layout_id="campaign_chapter_6",
        )
        entry = DetectedListEntry(
            kind=ListEntryKind.CAMPAIGN_STAGE,
            bounds=Bounds(40, 300, 300, 80),
            campaign_node=CampaignNodeFacts(chapter_number=6, stage_number=5),
            frame_ref=chapter_frame,
            source_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            source_layout_id="campaign_chapter_6",
        )
        request = Match3Request(
            context=Match3Context.CAMPAIGN,
            mode=Match3Mode.SOLVER,
            target=Match3Target(
                context=Match3Context.CAMPAIGN,
                frame_ref=chapter_frame,
                source_decision=chapter_decision,
                selected_entry=entry,
            ),
        )
        _, source, dispatch, destination = _valid_transition(
            stage=5, challenge_bounds=_CENTERED_CHALLENGE_BOUNDS, tap_point=(270, 673)
        )
        proof = require_formation_preparation_proof(
            request=request, source=source, dispatch=dispatch, destination=destination
        )
        self.assertIs(proof.target.selected_entry, entry)

    def test_unobserved_mode_does_not_gate_identity(self) -> None:
        """Variant comparison applies only when both sides observed a mode."""

        request, source, dispatch, destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        request = _request(stage=4, mode=None)
        proof = require_formation_preparation_proof(
            request=request, source=source, dispatch=dispatch, destination=destination
        )
        self.assertIsNone(proof.target.campaign_node.mode)


class FormationPreparationRequestTests(unittest.TestCase):
    """Target identity and request-context gates fail closed."""

    def setUp(self) -> None:
        self.request, self.source, self.dispatch, self.destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )

    def _assert_check(self, request: Match3Request, check: str) -> None:
        """Assert one typed rejection carries the expected guard name."""

        with self.assertRaises(FormationPreparationError) as error:
            require_formation_preparation_proof(
                request=request,
                source=self.source,
                dispatch=self.dispatch,
                destination=self.destination,
            )
        self.assertEqual(error.exception.details["check"], check)

    def test_non_campaign_request_fails_closed(self) -> None:
        with self.assertRaises(FormationPreparationError) as error:
            require_formation_preparation_proof(
                request=Match3Request(
                    context=Match3Context.ARENA,
                    mode=Match3Mode.SOLVER,
                    target=Match3Target(context=Match3Context.ARENA),
                ),
                source=self.source,
                dispatch=self.dispatch,
                destination=self.destination,
            )
        self.assertEqual(error.exception.details["check"], "request_context")

    def test_missing_target_fails_closed(self) -> None:
        self._assert_check(
            Match3Request(context=Match3Context.CAMPAIGN, mode=Match3Mode.SOLVER),
            "target_missing",
        )

    def test_target_without_ordinals_fails_closed(self) -> None:
        self._assert_check(
            Match3Request(
                context=Match3Context.CAMPAIGN,
                mode=Match3Mode.SOLVER,
                target=Match3Target(context=Match3Context.CAMPAIGN),
            ),
            "target_ordinals",
        )

    def test_target_with_partial_ordinals_fails_closed(self) -> None:
        self._assert_check(
            Match3Request(
                context=Match3Context.CAMPAIGN,
                mode=Match3Mode.SOLVER,
                target=Match3Target(
                    context=Match3Context.CAMPAIGN,
                    campaign_node=CampaignNodeFacts(chapter_number=6),
                ),
            ),
            "target_ordinals",
        )

    def test_target_stage_mismatch_fails_closed(self) -> None:
        self._assert_check(_request(stage=5), "target_identity")

    def test_target_chapter_mismatch_fails_closed(self) -> None:
        self._assert_check(_request(stage=4, chapter=7), "target_identity")

    def test_conflicting_chapter_identity_fails_closed(self) -> None:
        self._assert_check(
            Match3Request(
                context=Match3Context.CAMPAIGN,
                mode=Match3Mode.SOLVER,
                target=Match3Target(
                    context=Match3Context.CAMPAIGN,
                    campaign_node=CampaignNodeFacts(chapter_number=6, stage_number=4),
                    campaign_chapter=CampaignChapterIdentity(chapter_number=7),
                ),
            ),
            "target_identity",
        )

    def test_observed_variant_mismatch_fails_closed(self) -> None:
        self._assert_check(_request(stage=4, mode=CampaignMode.ELITE), "target_mode")


class FormationPreparationSourceTests(unittest.TestCase):
    """Source stage-detail gates fail closed."""

    def setUp(self) -> None:
        self.request, self.source, self.dispatch, self.destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        assert self.source.frame_ref is not None
        self.frame = self.source.frame_ref
        assert self.source.campaign_stage is not None
        self.detail = self.source.campaign_stage

    def _assert_source(self, source: Observation, check: str) -> None:
        """Assert one typed rejection carries the expected guard name."""

        with self.assertRaises(FormationPreparationError) as error:
            require_formation_preparation_proof(
                request=self.request,
                source=source,
                dispatch=self.dispatch,
                destination=self.destination,
            )
        self.assertEqual(error.exception.details["check"], check)

    def _source_with(self, **observation_overrides: object) -> Observation:
        """Rebuild the source observation with selected fields replaced."""

        values: dict[str, object] = {
            "decision": self.source.decision,
            "visible_elements": dict(self.source.visible_elements),
            "campaign_stage": self.detail,
            "frame_ref": self.frame,
        }
        values.update(observation_overrides)
        return Observation(**values)  # type: ignore[arg-type]

    def test_non_stage_source_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(
                decision=ScreenDecision(
                    base_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
                    effective_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
                    layout_id="campaign_chapter_6",
                    guard=GuardVerdict.CLEAR,
                )
            ),
            "source_screen",
        )

    def test_blocked_source_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(
                decision=replace(self.source.decision, guard=GuardVerdict.BLOCKED)
            ),
            "source_guard",
        )

    def test_coordinate_only_source_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(
                decision=replace(self.source.decision, coordinate_only=True)
            ),
            "source_guard",
        )

    def test_source_without_frame_fails_closed(self) -> None:
        self._assert_source(self._source_with(frame_ref=None), "source_frame")

    def test_source_without_stage_detail_fails_closed(self) -> None:
        self._assert_source(self._source_with(campaign_stage=None), "stage_detail")

    def test_stage_detail_from_other_frame_fails_closed(self) -> None:
        other = _frame(capture=9, input_sequence=4)
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, frame_ref=other)),
            "stage_detail_provenance",
        )

    def test_stage_detail_without_ordinals_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, chapter_number=None)),
            "stage_ordinals",
        )

    def test_other_stage_with_qualified_transition_is_bound(self) -> None:
        """Stage ordinals are evidence, not a hardcoded eligibility catalog."""

        request = _request(stage=3)
        source = self._source_with(campaign_stage=replace(self.detail, stage_number=3))
        proof = require_formation_preparation_proof(
            request=request,
            source=source,
            dispatch=self.dispatch,
            destination=self.destination,
        )
        self.assertEqual(proof.stage_detail.stage_number, 3)

    def test_stage_10_1_close_only_fails_closed(self) -> None:
        """The Stage 10-1 recognizer publishes Close only; it cannot qualify."""

        frame = _frame(capture=10, input_sequence=4)
        detail = _stage_detail(
            frame,
            stage=1,
            chapter=10,
            source_layout_id="campaign_stage_10_1_live028",
        )
        close = VisibleElement(
            selector_id=UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
            bounds=Bounds(320, 700, 120, 60),
            confidence=0.99,
            frame_ref=frame,
            source_screen=ScreenType.PNC_CAMPAIGN_STAGE,
            source_layout_id="campaign_stage_10_1_live028",
        )
        source = Observation(
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                effective_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                layout_id="campaign_stage_10_1_live028",
                guard=GuardVerdict.CLEAR,
            ),
            visible_elements={UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON: close},
            campaign_stage=detail,
            frame_ref=frame,
        )
        self._assert_source(source, "challenge_control")

    def test_missing_challenge_control_fails_closed(self) -> None:
        """A stage frame without the Challenge control cannot prove a transition."""

        elements = {
            UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON: VisibleElement(
                selector_id=UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                bounds=Bounds(320, 700, 120, 60),
                confidence=0.99,
                frame_ref=self.frame,
                source_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                source_layout_id=_STAGE_LAYOUT,
            )
        }
        self._assert_source(self._source_with(visible_elements=elements), "challenge_control")

    def test_challenge_from_other_frame_fails_closed(self) -> None:
        """A control stamped to another frame cannot stand in for same-frame proof."""

        elements = dict(self.source.visible_elements)
        challenge = elements[UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON]
        elements[UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON] = replace(
            challenge, frame_ref=_frame(capture=9, input_sequence=4)
        )
        self._assert_source(self._source_with(visible_elements=elements), "challenge_provenance")

    def test_missing_action_points_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, action_points=None)),
            "action_points",
        )

    def test_missing_challenge_cost_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, challenge_cost=None)),
            "challenge_cost",
        )

    def test_insufficient_action_points_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, action_points=5)),
            "insufficient_ap",
        )

    def test_action_points_above_observed_max_fails_closed(self) -> None:
        self._assert_source(
            self._source_with(campaign_stage=replace(self.detail, action_points=130)),
            "action_points_max",
        )


class FormationPreparationDispatchTests(unittest.TestCase):
    """The Challenge receipt gates fail closed."""

    def setUp(self) -> None:
        self.request, self.source, self.dispatch, self.destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        assert self.source.frame_ref is not None
        self.frame = self.source.frame_ref
        assert isinstance(self.dispatch.dispatch, TapDispatch)
        self.tap = self.dispatch.dispatch

    def _assert_dispatch(self, dispatch: InputDispatchRecord, check: str) -> None:
        """Assert one typed rejection carries the expected guard name."""

        with self.assertRaises(FormationPreparationError) as error:
            require_formation_preparation_proof(
                request=self.request,
                source=self.source,
                dispatch=dispatch,
                destination=self.destination,
            )
        self.assertEqual(error.exception.details["check"], check)

    def test_wrong_source_frame_fails_closed(self) -> None:
        self._assert_dispatch(
            InputDispatchRecord(
                source_frame=_frame(capture=9, input_sequence=4),
                dispatch=self.tap,
            ),
            "dispatch_source_frame",
        )

    def test_non_tap_dispatch_fails_closed(self) -> None:
        self._assert_dispatch(
            InputDispatchRecord(
                source_frame=self.frame,
                dispatch=SwipeDispatch(
                    start=(40, 730),
                    end=(180, 730),
                    duration_ms=120,
                    input_source="adb",
                    gesture_primitive="swipe",
                    input_sequence=5,
                ),
            ),
            "dispatch_kind",
        )

    def test_stale_dispatch_fails_closed(self) -> None:
        for input_sequence in (4, 6):
            with self.subTest(input_sequence=input_sequence):
                self._assert_dispatch(
                    InputDispatchRecord(
                        source_frame=self.frame,
                        dispatch=replace(self.tap, input_sequence=input_sequence),
                    ),
                    "dispatch_sequence",
                )

    def test_tap_outside_challenge_bounds_fails_closed(self) -> None:
        for point in ((0, 0), (400, 730), (40, 900)):
            with self.subTest(point=point):
                self._assert_dispatch(
                    InputDispatchRecord(
                        source_frame=self.frame,
                        dispatch=replace(self.tap, point=point),
                    ),
                    "dispatch_point",
                )

    def test_selector_outcome_is_not_a_dispatch_receipt(self) -> None:
        """Only a typed InputDispatchRecord can carry the transition."""

        with self.assertRaises(TypeError):
            require_formation_preparation_proof(
                request=self.request,
                source=self.source,
                dispatch=object(),  # type: ignore[arg-type]
                destination=self.destination,
            )


class FormationPreparationDestinationTests(unittest.TestCase):
    """The formation destination gates fail closed."""

    def setUp(self) -> None:
        self.request, self.source, self.dispatch, self.destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        assert self.destination.frame_ref is not None
        self.frame = self.destination.frame_ref

    def _assert_destination(self, destination: Observation, check: str) -> None:
        """Assert one typed rejection carries the expected guard name."""

        with self.assertRaises(FormationPreparationError) as error:
            require_formation_preparation_proof(
                request=self.request,
                source=self.source,
                dispatch=self.dispatch,
                destination=destination,
            )
        self.assertEqual(error.exception.details["check"], check)

    def _destination_with(self, **observation_overrides: object) -> Observation:
        """Rebuild the destination observation with selected fields replaced."""

        values: dict[str, object] = {
            "decision": self.destination.decision,
            "visible_elements": dict(self.destination.visible_elements),
            "frame_ref": self.frame,
        }
        values.update(observation_overrides)
        return Observation(**values)  # type: ignore[arg-type]

    def _destination_frame(self, **overrides: int | str) -> FrameRef:
        """Rebuild the destination frame with selected fields replaced."""

        return replace(self.frame, **overrides)  # type: ignore[arg-type]

    def _destination_for_frame(self, frame: FrameRef) -> Observation:
        """A fresh destination observation whose controls carry the new frame."""

        return self._destination_with(
            frame_ref=frame,
            visible_elements={
                UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON: _back_element(frame)
            },
        )

    def test_wrong_destination_screen_fails_closed(self) -> None:
        self._assert_destination(
            self._destination_with(
                decision=ScreenDecision(
                    base_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                    effective_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                    layout_id=FORMATION_PREPARATION_LAYOUT_ID,
                    guard=GuardVerdict.CLEAR,
                )
            ),
            "destination_screen",
        )

    def test_blocked_destination_fails_closed(self) -> None:
        self._assert_destination(
            self._destination_with(
                decision=replace(self.destination.decision, guard=GuardVerdict.BLOCKED)
            ),
            "destination_guard",
        )

    def test_wrong_destination_layout_fails_closed(self) -> None:
        """Another formation variant never stands in for the preparation layout."""

        self._assert_destination(
            self._destination_with(
                decision=replace(self.destination.decision, layout_id="hero_formation_save_form")
            ),
            "destination_layout",
        )

    def test_missing_formation_back_fails_closed(self) -> None:
        self._assert_destination(
            self._destination_with(visible_elements={}),
            "destination_back",
        )

    def test_formation_back_from_other_frame_fails_closed(self) -> None:
        """The dedicated Back control must carry the destination frame provenance."""

        elements = dict(self.destination.visible_elements)
        back = elements[UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON]
        elements[UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON] = replace(
            back, frame_ref=_frame(capture=12, input_sequence=5)
        )
        self._assert_destination(
            self._destination_with(visible_elements=elements),
            "destination_back_provenance",
        )

    def test_missing_destination_frame_fails_closed(self) -> None:
        self._assert_destination(self._destination_with(frame_ref=None), "destination_frame")

    def test_different_session_fails_closed(self) -> None:
        self._assert_destination(
            self._destination_for_frame(self._destination_frame(session_id="other")),
            "destination_session",
        )

    def test_different_epoch_fails_closed(self) -> None:
        self._assert_destination(
            self._destination_for_frame(self._destination_frame(session_epoch=2)),
            "destination_epoch",
        )

    def test_stale_destination_fails_closed(self) -> None:
        for capture in (9, 10):
            with self.subTest(capture=capture):
                self._assert_destination(
                    self._destination_for_frame(self._destination_frame(capture_sequence=capture)),
                    "destination_stale",
                )

    def test_intervening_input_fails_closed(self) -> None:
        """Any device input between the tap and the destination breaks the chain."""

        self._assert_destination(
            self._destination_for_frame(self._destination_frame(input_sequence=6)),
            "destination_sequence",
        )


class FormationPreparationProofTypeTests(unittest.TestCase):
    """The immutable proof cannot be assembled from unqualified evidence."""

    def test_proof_rejects_relabeled_frames(self) -> None:
        """A proof built by hand must still bind the same session/sequence chain."""

        request, source, dispatch, destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        assert source.frame_ref is not None
        assert destination.frame_ref is not None
        assert source.campaign_stage is not None
        with self.assertRaises(ValueError):
            FormationPreparationProof(
                request=request,
                stage_detail=source.campaign_stage,
                challenge=source.get(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON),  # type: ignore[arg-type]
                dispatch=dispatch,
                source_frame=source.frame_ref,
                destination_frame=replace(destination.frame_ref, session_id="other"),
                destination_decision=destination.decision,
                formation_back=destination.get(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON),  # type: ignore[arg-type]
            )

    def test_proof_rejects_untyped_fields(self) -> None:
        request, source, dispatch, destination = _valid_transition(
            stage=4, challenge_bounds=_LEFT_CHALLENGE_BOUNDS, tap_point=(40, 730)
        )
        assert source.frame_ref is not None
        assert destination.frame_ref is not None
        with self.assertRaises(TypeError):
            FormationPreparationProof(
                request="request",  # type: ignore[arg-type]
                stage_detail=source.campaign_stage,  # type: ignore[arg-type]
                challenge=source.get(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON),  # type: ignore[arg-type]
                dispatch=dispatch,
                source_frame=source.frame_ref,
                destination_frame=destination.frame_ref,
                destination_decision=destination.decision,
                formation_back=destination.get(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON),  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
