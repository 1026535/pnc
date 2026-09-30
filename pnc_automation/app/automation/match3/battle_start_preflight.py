"""Fail-closed Campaign formation-to-battle-start preflight.

This application/session-level check binds the owned stage-to-formation
transition proof, the current formation frame's exact account and castle
identity, a separately qualified continuation-off observation, and a
caller-proposed finite AP/attempt ceiling into one immutable
:class:`Match3StartPreflight` proposal.

The proposal is reviewable evidence only. It authorizes no input: it cannot
dispatch a Formation Challenge/GoFight/Start tap, toggle Auto or
continuation, edit heroes, or touch the journal, and it grants no resource
or spending authority. Only a later durable exact-identity journal boundary
can turn a qualified proposal into one authorized battle start.

No production observation producer currently emits qualified
continuation-off evidence, so runtime callers cannot assemble this proposal;
unit tests may construct synthetic evidence to exercise the pure contract.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from enum import StrEnum

from pnc_automation.app.automation.match3.formation_preparation import (
    FORMATION_PREPARATION_LAYOUT_ID,
    FormationPreparationProof,
)
from pnc_automation.app.pnc.domain.campaign import (
    CampaignStageDetail,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.match3 import (
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Target,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.infra.emulator.provenance import FrameRef


_PREFLIGHT_CONSTRUCTION_KEY = object()


class Match3ContinuationState(StrEnum):
    """The persisted battle-continuation states a future producer may qualify."""

    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class Match3ContinuationObservation:
    """One qualified continuation-state observation bound to a single formation frame.

    A proposal qualifies only the ``OFF`` state observed on the exact proven
    formation frame; ``UNKNOWN`` and ``ON`` fail closed. No production
    producer emits this evidence yet.
    """

    state: Match3ContinuationState
    frame_ref: FrameRef
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Check the retained evidence carries its declared types."""

        if not isinstance(self.state, Match3ContinuationState):
            raise TypeError("Match3ContinuationObservation.state must be a Match3ContinuationState.")
        if not isinstance(self.frame_ref, FrameRef):
            raise TypeError("Match3ContinuationObservation.frame_ref must be a FrameRef.")
        if self.source_screen is not None and not isinstance(self.source_screen, ScreenType):
            raise TypeError("Match3ContinuationObservation.source_screen must be a ScreenType.")
        if self.source_layout_id is not None and not isinstance(self.source_layout_id, str):
            raise TypeError("Match3ContinuationObservation.source_layout_id must be a string.")


@dataclass(frozen=True, slots=True)
class Match3StartBudget:
    """A caller-proposed finite ceiling for one battle start.

    The ceiling is a reviewable bound on action points and attempts, never
    spending authority; a qualified proposal still cannot dispatch input.
    """

    max_action_points: int
    max_attempts: int

    def __post_init__(self) -> None:
        """Require finite positive integer ceilings."""

        for field_name in ("max_action_points", "max_attempts"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"Match3StartBudget.{field_name} must be an integer.")
            if value <= 0:
                raise ValueError(f"Match3StartBudget.{field_name} must be positive.")


class Match3StartPreflightError(TaskVerificationError):
    """Raised when formation-to-start preflight evidence fails a required check."""


@dataclass(frozen=True, slots=True)
class Match3StartPreflight:
    """Immutable reviewable proposal for one bounded Campaign battle start.

    The retained transition proof, verified identity, continuation-off
    evidence, and budget are kept for independent review. This type performs
    no dispatch and grants no resource authority; source action points and
    cost remain past source-frame observations, never formation facts.
    """

    transition: FormationPreparationProof
    formation_frame: FrameRef
    account_id: str
    castle: CastleIdentity
    continuation: Match3ContinuationObservation
    budget: Match3StartBudget
    _construction_key: InitVar[object | None] = None

    def __post_init__(self, _construction_key: object | None) -> None:
        """Require the evidence-checking factory and check retained invariants."""

        if _construction_key is not _PREFLIGHT_CONSTRUCTION_KEY:
            raise ValueError("Use require_match3_start_preflight to construct a proposal.")

        for field_name, value, expected in (
            ("transition", self.transition, FormationPreparationProof),
            ("formation_frame", self.formation_frame, FrameRef),
            ("account_id", self.account_id, str),
            ("castle", self.castle, CastleIdentity),
            ("continuation", self.continuation, Match3ContinuationObservation),
            ("budget", self.budget, Match3StartBudget),
        ):
            if not isinstance(value, expected):
                raise TypeError(f"Match3StartPreflight.{field_name} must be a {expected.__name__}.")
        if not self.account_id.strip():
            raise ValueError("The retained account identity must not be blank.")
        if self.formation_frame != self.transition.destination_frame:
            raise ValueError("The retained formation frame must be the proven destination frame.")
        if (
            self.continuation.frame_ref != self.formation_frame
            or self.continuation.state is not Match3ContinuationState.OFF
        ):
            raise ValueError("The retained continuation evidence must prove OFF on the formation frame.")
        cost = self.transition.stage_detail.challenge_cost
        if cost is None:
            raise ValueError("The retained stage detail must observe the Challenge cost.")
        if self.budget.max_action_points < cost:
            raise ValueError("The retained budget must cover at least one observed Challenge cost.")

    @property
    def request(self) -> Match3Request:
        """Returns the retained Campaign battle request."""

        return self.transition.request

    @property
    def target(self) -> Match3Target:
        """Returns the retained Campaign target identity."""

        return self.transition.target

    @property
    def context(self) -> Match3Context:
        """Returns the retained request context."""

        return self.request.context

    @property
    def mode(self) -> Match3Mode:
        """Returns the requested battle policy; the Campaign variant lives on the stage detail."""

        return self.request.mode

    @property
    def stage_detail(self) -> CampaignStageDetail:
        """Returns the source-frame Campaign stage facts retained by the transition."""

        return self.transition.stage_detail


def require_match3_start_preflight(
    *,
    transition: FormationPreparationProof,
    formation: Observation,
    continuation: Match3ContinuationObservation,
    budget: Match3StartBudget,
    account_id: str,
    castle: CastleIdentity,
) -> Match3StartPreflight:
    """Binds a proven formation transition plus identity, continuation, and
    budget evidence into an immutable start proposal.

    The transition proof can only be built by its evidence-checking factory.
    The remaining checks bind current formation identity, continuation, and
    budget. Every required check fails closed with a stable ``check`` detail.
    """

    if not isinstance(transition, FormationPreparationProof):
        raise TypeError("transition must be a FormationPreparationProof.")
    if not isinstance(formation, Observation):
        raise TypeError("formation must be an Observation.")
    if not isinstance(continuation, Match3ContinuationObservation):
        raise TypeError("continuation must be a Match3ContinuationObservation.")
    if not isinstance(budget, Match3StartBudget):
        raise TypeError("budget must be a Match3StartBudget.")
    if not isinstance(account_id, str):
        raise TypeError("account_id must be a string.")
    if not account_id.strip():
        raise ValueError("account_id must not be blank.")
    if not isinstance(castle, CastleIdentity):
        raise TypeError("castle must be a CastleIdentity.")
    _require_formation_identity(formation, transition, account_id, castle)
    _require_continuation_off(continuation, formation)
    _require_budget(budget, transition.stage_detail)
    assert formation.frame_ref is not None
    return Match3StartPreflight(
        transition=transition,
        formation_frame=formation.frame_ref,
        account_id=account_id,
        castle=castle,
        continuation=continuation,
        budget=budget,
        _construction_key=_PREFLIGHT_CONSTRUCTION_KEY,
    )


def _require_formation_identity(
    formation: Observation,
    transition: FormationPreparationProof,
    account_id: str,
    castle: CastleIdentity,
) -> None:
    """Require the current formation frame and its exact observed identity."""

    if formation.frame_ref is None or formation.frame_ref != transition.destination_frame:
        raise Match3StartPreflightError(
            "The formation observation must be the proven destination frame.",
            check="formation_frame",
        )
    decision = formation.decision
    if decision.guard is not GuardVerdict.CLEAR or decision.coordinate_only:
        raise Match3StartPreflightError(
            "The formation observation must be clear and unblocked.",
            check="formation_guard",
            guard=decision.guard.value,
            coordinate_only=decision.coordinate_only,
        )
    if decision.effective_screen is not ScreenType.PNC_HERO_FORMATION:
        raise Match3StartPreflightError(
            "The formation observation must be the Hero Formation surface.",
            check="formation_screen",
            effective_screen=decision.effective_screen.value,
        )
    if decision.layout_id != FORMATION_PREPARATION_LAYOUT_ID:
        raise Match3StartPreflightError(
            "The formation observation must carry the reviewed preparation layout.",
            check="formation_layout",
            layout_id=decision.layout_id,
        )
    if formation.verified_pnc_account_id != account_id:
        raise Match3StartPreflightError(
            "The formation frame must verify the exact expected account identity.",
            check="account_identity",
        )
    match = formation.current_castle_match(castle)
    if not match.matches:
        raise Match3StartPreflightError(
            "The formation frame must prove the exact expected castle identity.",
            check="castle_identity",
            match_status=match.status.value,
        )


def _require_continuation_off(
    continuation: Match3ContinuationObservation, formation: Observation
) -> None:
    """Require qualified continuation-off evidence on the proven formation frame."""

    frame = formation.frame_ref
    assert frame is not None
    if continuation.frame_ref != frame:
        raise Match3StartPreflightError(
            "The continuation evidence must be bound to the proven formation frame.",
            check="continuation_frame",
        )
    if (
        continuation.source_screen is not ScreenType.PNC_HERO_FORMATION
        or continuation.source_layout_id != FORMATION_PREPARATION_LAYOUT_ID
    ):
        raise Match3StartPreflightError(
            "The continuation evidence must carry the formation frame provenance.",
            check="continuation_provenance",
        )
    if continuation.state is not Match3ContinuationState.OFF:
        raise Match3StartPreflightError(
            "The persisted continuation preference must be proven off.",
            check="continuation_state",
            continuation_state=continuation.state.value,
        )


def _require_budget(budget: Match3StartBudget, detail: CampaignStageDetail) -> None:
    """Require the proposed ceiling to cover at least one observed Challenge."""

    assert detail.challenge_cost is not None
    if budget.max_action_points < detail.challenge_cost:
        raise Match3StartPreflightError(
            "The proposed ceiling must cover the observed Challenge cost.",
            check="budget_ap",
            max_action_points=budget.max_action_points,
            challenge_cost=detail.challenge_cost,
        )
