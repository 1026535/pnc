"""Exact durable authority for one bounded Campaign match-3 battle start.

A qualified :class:`Match3StartPreflight` proposal is reviewable evidence
only; it authorizes nothing by itself. This module binds it — the proven
transition, exact account/castle identity, continuation-off evidence, and the
observed Challenge cost — to the actual mutation acknowledgement, one durable
invocation identity, and the shared :class:`CoreMutationBoundary` that
journals the attempt before dispatch and refuses any replay for the same
invocation.

The authority stays nonoperational for production battle starts: no producer
currently emits qualified continuation-off evidence, the published control
catalog has no final Formation Challenge/GoFight/Start control, and no
lifecycle observations exist, so only deterministic injected callbacks can
exercise the journaled dispatch path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import InitVar, dataclass

from pnc_automation.app.automation.daily_maintenance.application_service import (
    DailyRunBoundary,
)
from pnc_automation.app.automation.daily_maintenance.authorization import (
    DailyMutationAuthorizer,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationResult,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.match3.battle_start_preflight import Match3StartPreflight
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import castle_identity_key
from pnc_automation.app.pnc.domain.daily_maintenance import (
    ActionPointReservation,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationBudgetKind,
)
from pnc_automation.app.pnc.domain.match3 import Match3Context, Match3MutationKind
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


_AUTHORITY_CONSTRUCTION_KEY = object()


@dataclass(frozen=True, slots=True)
class CampaignBattleStartAuthority:
    """One exact bound authority for a single journaled Campaign battle start.

    ``preflight`` is the immutable qualified proposal, ``acknowledgement``
    the actual resolved feature acknowledgement, ``invocation_id`` the
    durable identity generated once for this attempt, and
    ``mutation_boundary`` the shared owner of exact-identity enforcement,
    durable persistence before dispatch, and no-replay reconciliation.
    """

    preflight: Match3StartPreflight
    acknowledgement: MutationAcknowledgement
    invocation_id: str
    mutation_boundary: CoreMutationBoundary
    _construction_key: InitVar[object | None] = None

    def __post_init__(self, _construction_key: object | None) -> None:
        """Require factory construction and revalidate the retained relations."""

        if _construction_key is not _AUTHORITY_CONSTRUCTION_KEY:
            raise ValueError(
                "Use require_campaign_battle_start_authority to construct the authority."
            )
        if not isinstance(self.preflight, Match3StartPreflight):
            raise TypeError("CampaignBattleStartAuthority.preflight must be a Match3StartPreflight.")
        if not isinstance(self.acknowledgement, MutationAcknowledgement):
            raise TypeError(
                "CampaignBattleStartAuthority.acknowledgement must be a MutationAcknowledgement."
            )
        if not isinstance(self.invocation_id, str) or not self.invocation_id.strip():
            raise ValueError("CampaignBattleStartAuthority.invocation_id cannot be blank.")
        if not isinstance(self.mutation_boundary, CoreMutationBoundary):
            raise TypeError(
                "CampaignBattleStartAuthority.mutation_boundary must be a CoreMutationBoundary."
            )
        boundary = self.mutation_boundary
        if boundary.feature_action_kind is not Match3MutationKind.CAMPAIGN_BATTLE_START:
            raise ValueError("CampaignBattleStartAuthority requires the Campaign battle-start scope.")
        if boundary.feature_budget_kind is not MutationBudgetKind.COUNTED:
            raise ValueError("The Campaign battle-start scope requires the counted budget form.")
        if boundary.feature_max_mutations != 1 or boundary.feature_max_diamond_spend != 0:
            raise ValueError(
                "The Campaign battle-start scope must authorize exactly one zero-diamond attempt."
            )
        if self.preflight.context is not Match3Context.CAMPAIGN:
            raise PermissionError("The bound preflight must be a Campaign start proposal.")
        if self.preflight.account_id != boundary.target.account_id or castle_identity_key(
            self.preflight.castle
        ) != castle_identity_key(boundary.target.castle):
            raise PermissionError(
                "The bound preflight identity must match the mutation scope's exact castle."
            )
        detail = self.preflight.stage_detail
        if (
            detail.challenge_cost is None
            or detail.action_points is None
            or detail.action_points < detail.challenge_cost
        ):
            raise ValueError(
                "The bound preflight must observe enough action points for the Challenge cost."
            )
        acknowledgement = self.acknowledgement
        if (
            acknowledgement.action_kind != Match3MutationKind.CAMPAIGN_BATTLE_START.value
            or acknowledgement.quest_id is not None
            or acknowledgement.budget_kind is not MutationBudgetKind.COUNTED
            or acknowledgement.max_mutations != 1
            or acknowledgement.max_diamond_spend != 0
        ):
            raise PermissionError(
                "The bound acknowledgement must be the exact one-attempt Campaign battle-start slice."
            )
        if (
            acknowledgement.account_id != boundary.target.account_id
            or acknowledgement.castle_ref != boundary.target.castle_ref
            or acknowledgement.maintenance_date != boundary.boundary.maintenance_date
        ):
            raise PermissionError(
                "The bound acknowledgement must match the scope's account, castle, and run date."
            )
        if (
            acknowledgement.max_action_points is None
            or self.preflight.budget.max_action_points > acknowledgement.max_action_points
            or self.preflight.budget.max_attempts != 1
        ):
            raise PermissionError(
                "The Campaign proposal must fit the acknowledged AP ceiling and one attempt."
            )

    @property
    def reservation(self) -> ActionPointReservation:
        """The held AP reservation — exactly the observed Challenge cost."""

        cost = self.preflight.stage_detail.challenge_cost
        assert cost is not None
        return ActionPointReservation(reserved_action_points=cost)

    @property
    def operation_id(self) -> str:
        """The durable operation id for the one attempt under this invocation."""

        return f"{self.invocation_id}-start"

    def operation(self) -> MutationOperation:
        """Build the exact journaled operation this authority may dispatch once."""

        detail = self.preflight.stage_detail
        request = self.preflight.request
        return MutationOperation(
            operation_id=self.operation_id,
            quest_id=None,
            expected_precondition="formation battle start control observed at the bound cost",
            expected_postcondition="campaign battle start is observed",
            diamond_budget=0,
            metadata={
                "context": request.context.value,
                "match3_mode": request.mode.value,
                "chapter_number": detail.chapter_number,
                "stage_number": detail.stage_number,
                "campaign_mode": None if detail.mode is None else detail.mode.value,
                "challenge_cost": detail.challenge_cost,
                "max_action_points": self.preflight.budget.max_action_points,
                "max_attempts": self.preflight.budget.max_attempts,
                "account_id": self.preflight.account_id,
                "maintenance_date": self.acknowledgement.maintenance_date.isoformat(),
            },
            action_kind=Match3MutationKind.CAMPAIGN_BATTLE_START,
            target={
                "context": request.context.value,
                "chapter_number": detail.chapter_number,
                "stage_number": detail.stage_number,
                "match3_mode": request.mode.value,
                "campaign_mode": None if detail.mode is None else detail.mode.value,
            },
            invocation_id=self.invocation_id,
            action_point_reservation=self.reservation,
        )

    def dispatch_battle_start(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        dispatch: Callable[[], None],
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Journal and dispatch the one authorized attempt through the shared boundary."""

        return self.mutation_boundary.dispatch_campaign_battle_start(
            checkpoint=checkpoint,
            authority=self,
            dispatch=dispatch,
            reconcile=reconcile,
        )

    def reconcile_battle_start(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        reconcile: Callable[[], MutationReconciliation],
    ) -> JournaledMutationResult:
        """Reconcile the consumed attempt by observation only; it never re-dispatches."""

        return self.mutation_boundary.reconcile_campaign_battle_start(
            checkpoint=checkpoint,
            operation_id=self.operation_id,
            reconcile=reconcile,
        )


def require_campaign_battle_start_authority(
    *,
    target: DailyMaintenanceTargetConfig,
    boundary: DailyRunBoundary,
    authorizer: DailyMutationAuthorizer,
    journal_store: DailyRunJournalStore,
    preflight: Match3StartPreflight,
    invocation_id: str,
) -> CampaignBattleStartAuthority:
    """Bind a qualified preflight to the actual acknowledgement and exact scope.

    The preflight's observed account, castle, and Campaign context must match
    the resolved target exactly, and the acknowledgement is resolved through
    the supplied authorizer — never a caller-proposed budget, a post-send
    observer event, or a forged proposal. The returned authority builds
    exactly one durable operation under the given invocation.
    """

    if not isinstance(target, DailyMaintenanceTargetConfig):
        raise TypeError("target must be a DailyMaintenanceTargetConfig.")
    if not isinstance(boundary, DailyRunBoundary):
        raise TypeError("boundary must be a DailyRunBoundary.")
    if not isinstance(authorizer, DailyMutationAuthorizer):
        raise TypeError("authorizer must be a DailyMutationAuthorizer.")
    if not isinstance(journal_store, DailyRunJournalStore):
        raise TypeError("journal_store must be a DailyRunJournalStore.")
    if not isinstance(preflight, Match3StartPreflight):
        raise TypeError("preflight must be a Match3StartPreflight.")
    if not isinstance(invocation_id, str) or not invocation_id.strip():
        raise ValueError("invocation_id cannot be blank.")
    if preflight.context is not Match3Context.CAMPAIGN:
        raise PermissionError("Only a Campaign match-3 request may be authorized to start.")
    if preflight.account_id != target.account_id:
        raise PermissionError("The preflight account does not match the mutation target.")
    if castle_identity_key(preflight.castle) != castle_identity_key(target.castle):
        raise PermissionError("The preflight castle does not match the mutation target.")
    detail = preflight.stage_detail
    if (
        detail.challenge_cost is None
        or detail.action_points is None
        or detail.action_points < detail.challenge_cost
    ):
        raise PermissionError(
            "The observed action points must cover the observed Challenge cost."
        )
    if preflight.budget.max_attempts != 1:
        raise PermissionError("A Campaign battle-start invocation permits exactly one attempt.")
    mutation_boundary = CoreMutationBoundary(
        target=target,
        boundary=boundary,
        authorizer=authorizer,
        journal_store=journal_store,
        feature_action_kind=Match3MutationKind.CAMPAIGN_BATTLE_START,
        feature_max_mutations=1,
        feature_max_diamond_spend=0,
    )
    mutation_boundary.authorize(action_kind=Match3MutationKind.CAMPAIGN_BATTLE_START)
    acknowledgement = authorizer.require_feature(
        account_id=target.account_id,
        castle_ref=target.castle_ref,
        action_kind=Match3MutationKind.CAMPAIGN_BATTLE_START.value,
        maintenance_date=boundary.maintenance_date,
        max_mutations=1,
        max_diamond_spend=0,
    )
    if (
        acknowledgement.max_action_points is None
        or preflight.budget.max_action_points > acknowledgement.max_action_points
    ):
        raise PermissionError("The proposed AP ceiling exceeds the acknowledged AP allowance.")
    return CampaignBattleStartAuthority(
        preflight=preflight,
        acknowledgement=acknowledgement,
        invocation_id=invocation_id,
        mutation_boundary=mutation_boundary,
        _construction_key=_AUTHORITY_CONSTRUCTION_KEY,
    )
