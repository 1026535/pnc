"""Fail-closed Campaign Stage Detail -> Hero Formation preparation proof.

This application/session-level check binds one owned stage-detail source
observation, the actual Challenge tap dispatch receipt authorized by its
frame, and the confirmed formation destination into one immutable proof. It
is a transition record only, never battle-start authorization: the proof
does not assert battle start, current formation action points, verified
account or castle identity, a disabled continuation preference, a durable
attempt reservation, or resource authority.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass

from pnc_automation.app.pnc.domain.campaign import CampaignNodeFacts, CampaignStageDetail
from pnc_automation.app.pnc.domain.match3 import Match3Context, Match3Request, Match3Target
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElement
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.infra.emulator.input_dispatch import InputDispatchRecord, TapDispatch
from pnc_automation.core.infra.emulator.provenance import FrameRef

FORMATION_PREPARATION_LAYOUT_ID = "hero_formation_challenge_preparation"
"""The reviewed Hero Formation variant the owned Campaign Challenge opens."""

_PROOF_CONSTRUCTION_KEY = object()

class FormationPreparationError(TaskVerificationError):
    """Raised when stage-to-formation transition evidence fails a required check."""


@dataclass(frozen=True, slots=True)
class FormationPreparationProof:
    """Immutable binding for one owned Challenge tap that reached formation preparation.

    The retained stage detail, action points, and cost remain source-frame
    observations; they are never formation-screen facts. Request, target
    identity, both frame references, the Challenge control, the dispatch
    receipt, and the destination decision are kept for independent review.
    """

    request: Match3Request
    stage_detail: CampaignStageDetail
    challenge: VisibleElement
    dispatch: InputDispatchRecord
    source_frame: FrameRef
    destination_frame: FrameRef
    destination_decision: ScreenDecision
    formation_back: VisibleElement
    _construction_key: InitVar[object | None] = None

    def __post_init__(self, _construction_key: object | None) -> None:
        """Check retained types and frame lineage; the factory checks observations."""

        for field_name, value, expected in (
            ("request", self.request, Match3Request),
            ("stage_detail", self.stage_detail, CampaignStageDetail),
            ("challenge", self.challenge, VisibleElement),
            ("dispatch", self.dispatch, InputDispatchRecord),
            ("source_frame", self.source_frame, FrameRef),
            ("destination_frame", self.destination_frame, FrameRef),
            ("destination_decision", self.destination_decision, ScreenDecision),
            ("formation_back", self.formation_back, VisibleElement),
        ):
            if not isinstance(value, expected):
                raise TypeError(f"FormationPreparationProof.{field_name} must be a {expected.__name__}.")
        if _construction_key is not _PROOF_CONSTRUCTION_KEY:
            raise ValueError("Use require_formation_preparation_proof to construct a proof.")
        if self.request.context is not Match3Context.CAMPAIGN or self.request.target is None:
            raise ValueError("The formation preparation proof requires a Campaign request with a target.")
        if self.challenge.selector_id is not UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON:
            raise ValueError("The retained Challenge control must be the Campaign battle button.")
        if self.stage_detail.frame_ref != self.source_frame:
            raise ValueError("The retained stage detail must carry the source frame provenance.")
        if self.dispatch.source_frame != self.source_frame or not isinstance(
            self.dispatch.dispatch, TapDispatch
        ):
            raise ValueError("The retained dispatch must be a tap authorized by the source frame.")
        if self.formation_back.selector_id is not UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON:
            raise ValueError("The retained formation Back must be the dedicated formation control.")
        if (
            self.destination_decision.effective_screen is not ScreenType.PNC_HERO_FORMATION
            or self.destination_decision.layout_id != FORMATION_PREPARATION_LAYOUT_ID
        ):
            raise ValueError("The retained destination must be the reviewed formation preparation layout.")
        if (
            self.destination_frame.session_id != self.source_frame.session_id
            or self.destination_frame.session_epoch != self.source_frame.session_epoch
            or self.destination_frame.capture_sequence <= self.source_frame.capture_sequence
            or self.destination_frame.input_sequence != self.dispatch.dispatch.input_sequence
        ):
            raise ValueError("The retained frames must form one same-session ordered transition.")

    @property
    def target(self) -> Match3Target:
        """Returns the retained Campaign target identity."""

        assert self.request.target is not None
        return self.request.target


def require_formation_preparation_proof(
    *,
    request: Match3Request,
    source: Observation,
    dispatch: InputDispatchRecord,
    destination: Observation,
) -> FormationPreparationProof:
    """Binds a qualified stage-detail source, one actual Challenge tap, and the
    confirmed formation destination into an immutable proof.

    Every required check fails closed with :class:`FormationPreparationError`;
    each rejection carries a stable ``check`` detail naming the failed guard.
    """

    if not isinstance(request, Match3Request):
        raise TypeError("request must be a Match3Request.")
    if not isinstance(source, Observation):
        raise TypeError("source must be an Observation.")
    if not isinstance(dispatch, InputDispatchRecord):
        raise TypeError("dispatch must be an InputDispatchRecord.")
    if not isinstance(destination, Observation):
        raise TypeError("destination must be an Observation.")
    target = _require_campaign_target(request)
    detail, challenge = _require_source_stage(source)
    _require_target_identity(target, detail)
    tap = _require_challenge_dispatch(dispatch, source, challenge)
    back = _require_formation_destination(destination, source, tap)
    return FormationPreparationProof(
        request=request,
        stage_detail=detail,
        challenge=challenge,
        dispatch=dispatch,
        source_frame=source.frame_ref,
        destination_frame=destination.frame_ref,
        destination_decision=destination.decision,
        formation_back=back,
        _construction_key=_PROOF_CONSTRUCTION_KEY,
    )


def _require_campaign_target(request: Match3Request) -> Match3Target:
    """Require the Campaign request and its selected target ordinals."""

    if request.context is not Match3Context.CAMPAIGN:
        raise FormationPreparationError(
            "Formation preparation proof requires the Campaign request context.",
            check="request_context",
            context=request.context.value,
        )
    if request.target is None:
        raise FormationPreparationError(
            "Formation preparation proof requires a selected Campaign target.",
            check="target_missing",
        )
    node = _target_node(request.target)
    if node is None or node.chapter_number is None or node.stage_number is None:
        raise FormationPreparationError(
            "The selected Campaign target must supply chapter and stage ordinals.",
            check="target_ordinals",
        )
    return request.target


def _require_source_stage(source: Observation) -> tuple[CampaignStageDetail, VisibleElement]:
    """Require a clear unblocked stage-detail frame with provenance and Challenge."""

    decision = source.decision
    if decision.effective_screen is not ScreenType.PNC_CAMPAIGN_STAGE:
        raise FormationPreparationError(
            "The source observation must be the Campaign stage-detail surface.",
            check="source_screen",
            effective_screen=decision.effective_screen.value,
        )
    _require_clear(decision, check="source_guard")
    if source.frame_ref is None:
        raise FormationPreparationError(
            "The source observation must carry its session frame reference.",
            check="source_frame",
        )
    detail = source.campaign_stage
    if detail is None:
        raise FormationPreparationError(
            "The source observation must carry Campaign stage-detail facts.",
            check="stage_detail",
        )
    if (
        detail.frame_ref != source.frame_ref
        or detail.source_screen != decision.effective_screen
        or detail.source_layout_id != decision.layout_id
    ):
        raise FormationPreparationError(
            "Campaign stage-detail facts must carry same-frame provenance.",
            check="stage_detail_provenance",
        )
    if detail.chapter_number is None or detail.stage_number is None:
        raise FormationPreparationError(
            "The Campaign stage detail must observe chapter and stage ordinals.",
            check="stage_ordinals",
        )
    challenge = source.get(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON)
    if challenge is None:
        raise FormationPreparationError(
            "The source observation must publish the stage Challenge control.",
            check="challenge_control",
        )
    _require_same_frame_element(
        challenge, frame_ref=source.frame_ref, decision=decision, check="challenge_provenance"
    )
    _require_challenge_affordable(detail)
    return detail, challenge


def _require_target_identity(target: Match3Target, detail: CampaignStageDetail) -> None:
    """Require target ordinals and observed variant to match the stage detail."""

    node = _target_node(target)
    assert node is not None
    if (
        node.chapter_number != detail.chapter_number
        or node.stage_number != detail.stage_number
        or (
            target.campaign_chapter is not None
            and target.campaign_chapter.chapter_number != detail.chapter_number
        )
    ):
        raise FormationPreparationError(
            "The selected target ordinals must match the observed stage detail.",
            check="target_identity",
            target_chapter=node.chapter_number,
            target_stage=node.stage_number,
            detail_chapter=detail.chapter_number,
            detail_stage=detail.stage_number,
        )
    if node.mode is not None and detail.mode is not None and node.mode != detail.mode:
        raise FormationPreparationError(
            "The observed Campaign variant must match the selected target.",
            check="target_mode",
            target_mode=node.mode.value,
            detail_mode=detail.mode.value,
        )


def _require_challenge_affordable(detail: CampaignStageDetail) -> None:
    """Require observed action points and Challenge cost on the source frame."""

    if detail.action_points is None:
        raise FormationPreparationError(
            "The stage detail must observe current action points.",
            check="action_points",
        )
    if detail.challenge_cost is None:
        raise FormationPreparationError(
            "The stage detail must observe the Challenge cost.",
            check="challenge_cost",
        )
    if (
        detail.max_action_points is not None
        and detail.action_points > detail.max_action_points
    ):
        raise FormationPreparationError(
            "Observed action points must not exceed the observed maximum.",
            check="action_points_max",
            action_points=detail.action_points,
            max_action_points=detail.max_action_points,
        )
    if detail.action_points < detail.challenge_cost:
        raise FormationPreparationError(
            "Observed action points must cover the observed Challenge cost.",
            check="insufficient_ap",
            action_points=detail.action_points,
            challenge_cost=detail.challenge_cost,
        )


def _require_challenge_dispatch(
    dispatch: InputDispatchRecord, source: Observation, challenge: VisibleElement
) -> TapDispatch:
    """Require one actual tap on the Challenge control authorized by the source frame."""

    if dispatch.source_frame != source.frame_ref:
        raise FormationPreparationError(
            "The dispatch must be authorized by the exact source frame.",
            check="dispatch_source_frame",
        )
    tap = dispatch.dispatch
    if not isinstance(tap, TapDispatch):
        raise FormationPreparationError(
            "The formation transition requires a tap dispatch receipt.",
            check="dispatch_kind",
        )
    assert source.frame_ref is not None
    if tap.input_sequence != source.frame_ref.input_sequence + 1:
        raise FormationPreparationError(
            "The Challenge tap must be the next dispatched input after the source frame.",
            check="dispatch_sequence",
            source_input_sequence=source.frame_ref.input_sequence,
            dispatch_input_sequence=tap.input_sequence,
        )
    if not challenge.bounds.contains_point(tap.point):
        raise FormationPreparationError(
            "The Challenge tap point must lie inside the same-frame Challenge bounds.",
            check="dispatch_point",
            point=tap.point,
        )
    return tap


def _require_formation_destination(
    destination: Observation, source: Observation, tap: TapDispatch
) -> VisibleElement:
    """Require the clear reviewed formation preparation frame at the tap's sequence."""

    decision = destination.decision
    if decision.effective_screen is not ScreenType.PNC_HERO_FORMATION:
        raise FormationPreparationError(
            "The destination observation must be the Hero Formation surface.",
            check="destination_screen",
            effective_screen=decision.effective_screen.value,
        )
    _require_clear(decision, check="destination_guard")
    if decision.layout_id != FORMATION_PREPARATION_LAYOUT_ID:
        raise FormationPreparationError(
            "The destination must be the reviewed Challenge preparation layout.",
            check="destination_layout",
            layout_id=decision.layout_id,
        )
    back = destination.get(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON)
    if back is None:
        raise FormationPreparationError(
            "The destination must publish the dedicated formation Back control.",
            check="destination_back",
        )
    if destination.frame_ref is None:
        raise FormationPreparationError(
            "The destination observation must carry its session frame reference.",
            check="destination_frame",
        )
    _require_same_frame_element(
        back, frame_ref=destination.frame_ref, decision=decision, check="destination_back_provenance"
    )
    assert source.frame_ref is not None
    source_frame, destination_frame = source.frame_ref, destination.frame_ref
    if destination_frame.session_id != source_frame.session_id:
        raise FormationPreparationError(
            "The destination frame must belong to the source session.",
            check="destination_session",
        )
    if destination_frame.session_epoch != source_frame.session_epoch:
        raise FormationPreparationError(
            "The destination frame must share the source session epoch.",
            check="destination_epoch",
        )
    if destination_frame.capture_sequence <= source_frame.capture_sequence:
        raise FormationPreparationError(
            "The destination frame must be a later capture than the source frame.",
            check="destination_stale",
            source_capture=source_frame.capture_sequence,
            destination_capture=destination_frame.capture_sequence,
        )
    if destination_frame.input_sequence != tap.input_sequence:
        raise FormationPreparationError(
            "The destination frame must sit at the dispatched tap sequence with no intervening input.",
            check="destination_sequence",
            dispatch_input_sequence=tap.input_sequence,
            destination_input_sequence=destination_frame.input_sequence,
        )
    return back


def _require_clear(decision: ScreenDecision, *, check: str) -> None:
    """Require a clear, unblocked, action-eligible screen decision."""

    if decision.guard is not GuardVerdict.CLEAR or decision.coordinate_only:
        raise FormationPreparationError(
            "The observation must be clear and unblocked.",
            check=check,
            guard=decision.guard.value,
            coordinate_only=decision.coordinate_only,
        )


def _require_same_frame_element(
    element: VisibleElement, *, frame_ref: FrameRef, decision: ScreenDecision, check: str
) -> None:
    """Require one published control to carry the frame's own provenance."""

    if (
        element.frame_ref != frame_ref
        or element.source_screen != decision.effective_screen
        or element.source_layout_id != decision.layout_id
    ):
        raise FormationPreparationError(
            "The published control must carry same-frame provenance.",
            check=check,
            selector_id=element.selector_id.value,
        )


def _target_node(target: Match3Target) -> CampaignNodeFacts | None:
    """Returns the observed Campaign node carried by the target, when present."""

    if target.campaign_node is not None:
        return target.campaign_node
    if target.selected_entry is not None:
        return target.selected_entry.campaign_node
    return None
