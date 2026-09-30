"""Campaign formation-to-battle-start preflight contract tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from pnc_automation.app.automation.match3 import (
    FORMATION_PREPARATION_LAYOUT_ID,
    FormationPreparationProof,
    Match3ContinuationObservation,
    Match3ContinuationState,
    Match3StartBudget,
    Match3StartPreflight,
    Match3StartPreflightError,
    UnavailableMatch3Component,
    require_formation_preparation_proof,
    require_match3_start_preflight,
)
from pnc_automation.app.pnc.domain.campaign import (
    CampaignMode,
    CampaignNodeFacts,
    CampaignStageDetail,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.match3 import (
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Target,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    Observation,
    VisibleElement,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

_SESSION = "session-1"
_EPOCH = 1
_STAGE_LAYOUT = "campaign_stage_chapter_6"
_LEFT_CHALLENGE_BOUNDS = Bounds(28, 714, 190, 68)
_CENTERED_CHALLENGE_BOUNDS = Bounds(178, 643, 184, 60)
_FORMATION_BACK_BOUNDS = Bounds(23, 7, 57, 63)
_ACCOUNT_ID = "acct-1"
_CASTLE = CastleIdentity(kingdom="287", castle_name="Castle-A", castle_level=10)


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
    """Source-frame Campaign stage facts, defaulting to an affordable stage."""

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


def _formation_observation(frame: FrameRef, **overrides: object) -> Observation:
    """A clear formation preparation frame carrying verified identity."""

    values: dict[str, object] = {
        "decision": ScreenDecision(
            base_screen=ScreenType.PNC_HERO_FORMATION,
            effective_screen=ScreenType.PNC_HERO_FORMATION,
            layout_id=FORMATION_PREPARATION_LAYOUT_ID,
            guard=GuardVerdict.CLEAR,
        ),
        "visible_elements": {UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON: _back_element(frame)},
        "current_castle": _CASTLE,
        "current_castle_evidence": CurrentCastleEvidenceKind.EXACT,
        "verified_pnc_account_id": _ACCOUNT_ID,
        "frame_ref": frame,
    }
    values.update(overrides)
    return Observation(**values)  # type: ignore[arg-type]


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
    *, stage: int = 4, challenge_bounds: Bounds = _LEFT_CHALLENGE_BOUNDS, tap_point: tuple[int, int] = (40, 730)
) -> tuple[FormationPreparationProof, Observation]:
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
    destination = _formation_observation(destination_frame)
    request = _request(stage=stage)
    proof = require_formation_preparation_proof(
        request=request, source=source, dispatch=dispatch, destination=destination
    )
    return proof, destination


def _continuation(frame: FrameRef, **overrides: object) -> Match3ContinuationObservation:
    """Synthetic qualified continuation-off evidence bound to the formation frame.

    No production producer emits this evidence yet; fixtures construct it to
    exercise the pure contract only.
    """

    values: dict[str, object] = {
        "state": Match3ContinuationState.OFF,
        "frame_ref": frame,
        "source_screen": ScreenType.PNC_HERO_FORMATION,
        "source_layout_id": FORMATION_PREPARATION_LAYOUT_ID,
    }
    values.update(overrides)
    return Match3ContinuationObservation(**values)  # type: ignore[arg-type]


class BattleStartPreflightTests(unittest.TestCase):
    """A fully bound transition, identity, continuation, and ceiling propose out."""

    def setUp(self) -> None:
        self.proof, self.destination = _valid_transition()
        assert self.destination.frame_ref is not None
        self.frame = self.destination.frame_ref
        self.continuation = _continuation(self.frame)
        self.budget = Match3StartBudget(max_action_points=12, max_attempts=1)

    def _preflight(
        self,
        *,
        transition=None,
        formation=None,
        continuation=None,
        budget=None,
        account_id: str = _ACCOUNT_ID,
        castle: CastleIdentity = _CASTLE,
    ) -> Match3StartPreflight:
        return require_match3_start_preflight(
            transition=self.proof if transition is None else transition,
            formation=self.destination if formation is None else formation,
            continuation=self.continuation if continuation is None else continuation,
            budget=self.budget if budget is None else budget,
            account_id=account_id,
            castle=castle,
        )

    def test_valid_6_4_left_challenge_proposal(self) -> None:
        """A bound 6-4 transition plus qualified evidence produces the proposal."""

        proposal = self._preflight()
        self.assertIs(proposal.transition, self.proof)
        self.assertIs(proposal.request, self.proof.request)
        self.assertIs(proposal.target, self.proof.target)
        self.assertIs(proposal.formation_frame, self.frame)
        self.assertEqual(proposal.account_id, _ACCOUNT_ID)
        self.assertIs(proposal.castle, _CASTLE)
        self.assertIs(proposal.continuation, self.continuation)
        self.assertIs(proposal.budget, self.budget)
        self.assertIs(proposal.context, Match3Context.CAMPAIGN)
        self.assertIs(proposal.mode, Match3Mode.SOLVER)
        self.assertIs(proposal.stage_detail, self.proof.stage_detail)

    def test_valid_6_5_centered_challenge_proposal(self) -> None:
        proof, destination = _valid_transition(
            stage=5, challenge_bounds=_CENTERED_CHALLENGE_BOUNDS, tap_point=(270, 673)
        )
        assert destination.frame_ref is not None
        proposal = require_match3_start_preflight(
            transition=proof,
            formation=destination,
            continuation=_continuation(destination.frame_ref),
            budget=Match3StartBudget(max_action_points=12, max_attempts=1),
            account_id=_ACCOUNT_ID,
            castle=_CASTLE,
        )
        self.assertEqual(proposal.stage_detail.stage_number, 5)

    def test_source_facts_remain_source_frame_observations(self) -> None:
        """The proposal never relabels source AP/cost as formation facts."""

        proposal = self._preflight()
        self.assertEqual(proposal.stage_detail.action_points, 60)
        self.assertEqual(proposal.stage_detail.challenge_cost, 12)
        self.assertEqual(proposal.stage_detail.source_screen, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertIs(proposal.stage_detail.frame_ref, self.proof.source_frame)

    def test_mode_is_battle_policy_not_campaign_variant(self) -> None:
        """Match3Mode and CampaignMode are distinct values on distinct fields."""

        proposal = self._preflight()
        self.assertIs(proposal.mode, Match3Mode.SOLVER)
        self.assertIs(proposal.stage_detail.mode, CampaignMode.STANDARD)
        self.assertNotEqual(proposal.mode.value, proposal.stage_detail.mode.value)

    def test_every_context_mode_pair_remains_unavailable(self) -> None:
        """The proposal adds no availability; every pair still reports not implemented."""

        component = UnavailableMatch3Component()
        for context in Match3Context:
            for mode in Match3Mode:
                with self.subTest(context=context, mode=mode):
                    self.assertFalse(component.availability(context, mode).available)


class FormationIdentityTests(unittest.TestCase):
    """The current formation frame and exact identity gates fail closed."""

    def setUp(self) -> None:
        self.proof, self.destination = _valid_transition()
        assert self.destination.frame_ref is not None
        self.frame = self.destination.frame_ref
        self.continuation = _continuation(self.frame)
        self.budget = Match3StartBudget(max_action_points=12, max_attempts=1)

    def _assert_formation(self, formation: Observation, check: str, **kwargs: object) -> None:
        """Assert one typed rejection carries the expected guard name."""

        values: dict[str, object] = {
            "transition": self.proof,
            "formation": formation,
            "continuation": self.continuation,
            "budget": self.budget,
            "account_id": _ACCOUNT_ID,
            "castle": _CASTLE,
        }
        values.update(kwargs)
        with self.assertRaises(Match3StartPreflightError) as error:
            require_match3_start_preflight(**values)  # type: ignore[arg-type]
        self.assertEqual(error.exception.details["check"], check)

    def _formation_with(self, **overrides: object) -> Observation:
        """Rebuild the formation observation with selected fields replaced."""

        values: dict[str, object] = {
            "decision": self.destination.decision,
            "visible_elements": dict(self.destination.visible_elements),
            "current_castle": _CASTLE,
            "current_castle_evidence": CurrentCastleEvidenceKind.EXACT,
            "verified_pnc_account_id": _ACCOUNT_ID,
            "frame_ref": self.frame,
        }
        values.update(overrides)
        return Observation(**values)  # type: ignore[arg-type]

    def test_formation_from_other_frame_fails_closed(self) -> None:
        """A later or foreign formation frame never stands in for the proven one."""

        other = _frame(capture=12, input_sequence=5)
        self._assert_formation(_formation_observation(other), "formation_frame")

    def test_formation_without_frame_fails_closed(self) -> None:
        self._assert_formation(self._formation_with(frame_ref=None), "formation_frame")

    def test_blocked_formation_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(
                decision=replace(self.destination.decision, guard=GuardVerdict.BLOCKED)
            ),
            "formation_guard",
        )

    def test_wrong_formation_screen_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(
                decision=replace(
                    self.destination.decision, effective_screen=ScreenType.PNC_CAMPAIGN_STAGE
                )
            ),
            "formation_screen",
        )

    def test_wrong_formation_layout_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(
                decision=replace(
                    self.destination.decision, layout_id="hero_formation_save_form"
                )
            ),
            "formation_layout",
        )

    def test_unverified_account_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(verified_pnc_account_id=None), "account_identity"
        )

    def test_wrong_account_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(verified_pnc_account_id="acct-2"), "account_identity"
        )

    def test_expected_account_mismatch_fails_closed(self) -> None:
        self._assert_formation(self.destination, "account_identity", account_id="acct-9")

    def test_missing_castle_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(current_castle=None, current_castle_evidence=None),
            "castle_identity",
        )

    def test_name_only_castle_fails_closed(self) -> None:
        """Name-only evidence without a roster cannot prove the exact castle."""

        self._assert_formation(
            self._formation_with(current_castle_evidence=CurrentCastleEvidenceKind.NAME_ONLY),
            "castle_identity",
        )

    def test_castle_mismatch_fails_closed(self) -> None:
        self._assert_formation(
            self._formation_with(
                current_castle=CastleIdentity(kingdom="287", castle_name="Castle-B", castle_level=10)
            ),
            "castle_identity",
        )


class ContinuationEvidenceTests(unittest.TestCase):
    """The qualified continuation-off gates fail closed."""

    def setUp(self) -> None:
        self.proof, self.destination = _valid_transition()
        assert self.destination.frame_ref is not None
        self.frame = self.destination.frame_ref
        self.continuation = _continuation(self.frame)
        self.budget = Match3StartBudget(max_action_points=12, max_attempts=1)

    def _assert_continuation(self, continuation: Match3ContinuationObservation, check: str) -> None:
        """Assert one typed rejection carries the expected guard name."""

        with self.assertRaises(Match3StartPreflightError) as error:
            require_match3_start_preflight(
                transition=self.proof,
                formation=self.destination,
                continuation=continuation,
                budget=self.budget,
                account_id=_ACCOUNT_ID,
                castle=_CASTLE,
            )
        self.assertEqual(error.exception.details["check"], check)

    def test_unknown_continuation_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, state=Match3ContinuationState.UNKNOWN),
            "continuation_state",
        )

    def test_on_continuation_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, state=Match3ContinuationState.ON),
            "continuation_state",
        )

    def test_continuation_from_other_frame_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, frame_ref=_frame(capture=12, input_sequence=5)),
            "continuation_frame",
        )

    def test_continuation_wrong_screen_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, source_screen=ScreenType.PNC_CAMPAIGN_STAGE),
            "continuation_provenance",
        )

    def test_continuation_wrong_layout_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, source_layout_id="hero_formation_save_form"),
            "continuation_provenance",
        )

    def test_continuation_missing_provenance_fails_closed(self) -> None:
        self._assert_continuation(
            replace(self.continuation, source_screen=None, source_layout_id=None),
            "continuation_provenance",
        )


class StartBudgetTests(unittest.TestCase):
    """The caller-proposed ceiling fails closed and validates its own shape."""

    def setUp(self) -> None:
        self.proof, self.destination = _valid_transition()
        assert self.destination.frame_ref is not None
        self.continuation = _continuation(self.destination.frame_ref)

    def test_ceiling_below_observed_cost_fails_closed(self) -> None:
        with self.assertRaises(Match3StartPreflightError) as error:
            require_match3_start_preflight(
                transition=self.proof,
                formation=self.destination,
                continuation=self.continuation,
                budget=Match3StartBudget(max_action_points=11, max_attempts=1),
                account_id=_ACCOUNT_ID,
                castle=_CASTLE,
            )
        self.assertEqual(error.exception.details["check"], "budget_ap")

    def test_non_positive_ceiling_rejected_at_construction(self) -> None:
        for values in ((0, 1), (12, 0), (-1, 1)):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    Match3StartBudget(max_action_points=values[0], max_attempts=values[1])

    def test_non_integer_ceiling_rejected_at_construction(self) -> None:
        with self.assertRaises(TypeError):
            Match3StartBudget(max_action_points="12", max_attempts=1)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3StartBudget(max_action_points=12, max_attempts=True)


class PreflightInputTests(unittest.TestCase):
    """Untyped or unqualified inputs fail at the boundary."""

    def setUp(self) -> None:
        self.proof, self.destination = _valid_transition()
        assert self.destination.frame_ref is not None
        self.frame = self.destination.frame_ref
        self.continuation = _continuation(self.frame)
        self.budget = Match3StartBudget(max_action_points=12, max_attempts=1)

    def _call(self, **overrides: object):
        values: dict[str, object] = {
            "transition": self.proof,
            "formation": self.destination,
            "continuation": self.continuation,
            "budget": self.budget,
            "account_id": _ACCOUNT_ID,
            "castle": _CASTLE,
        }
        values.update(overrides)
        return require_match3_start_preflight(**values)  # type: ignore[arg-type]

    def test_untyped_arguments_rejected(self) -> None:
        for name in ("transition", "formation", "continuation", "budget", "castle"):
            with self.subTest(argument=name):
                with self.assertRaises(TypeError):
                    self._call(**{name: object()})
        with self.assertRaises(TypeError):
            self._call(account_id=7)

    def test_blank_account_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._call(account_id="   ")

    def test_proposal_requires_evidence_checking_factory(self) -> None:
        """Even matching retained fields cannot bypass formation identity checks."""

        with self.assertRaises(ValueError):
            Match3StartPreflight(
                transition=self.proof,
                formation_frame=self.frame,
                account_id=_ACCOUNT_ID,
                castle=_CASTLE,
                continuation=self.continuation,
                budget=self.budget,
            )

    def test_proposal_cannot_be_relabelled_after_validation(self) -> None:
        with self.assertRaises(ValueError):
            replace(
                require_match3_start_preflight(
                    transition=self.proof,
                    formation=self.destination,
                    continuation=self.continuation,
                    budget=self.budget,
                    account_id=_ACCOUNT_ID,
                    castle=_CASTLE,
                ),
                continuation=replace(
                    self.continuation, state=Match3ContinuationState.UNKNOWN
                ),
            )

    def test_continuation_observation_rejects_untyped_fields(self) -> None:
        with self.assertRaises(TypeError):
            Match3ContinuationObservation(state="off", frame_ref=self.frame)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
