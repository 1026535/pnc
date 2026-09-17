"""Compose the explicit Workshop policy with its authorized mutation scope.

Direct and Daily adapters share this one composition so neither has to
assemble a target, budget, and ``CoreMutationBoundary`` independently. The
returned value is composition only: ``CoreMutationBoundary`` remains the
single authority for exact acknowledgement enforcement, durable invocation
registration, and pending-operation reconciliation. Account/role resolution
and the maintenance date/reset identity stay with the existing outer
config/runtime owners.
"""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.application_service import (
    DailyRunBoundary,
)
from pnc_automation.app.automation.daily_maintenance.authorization import (
    DailyMutationAuthorizer,
)
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.pnc.domain.daily_maintenance import MutationBudgetKind
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopMutationKind,
    WorkshopPolicy,
)
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class WorkshopRunAuthority:
    """Pair the explicit run policy with its authorized ``pet_workshop.run`` scope.

    ``policy`` is the typed ``WorkshopPolicy`` the planner and legal-action
    check consume; ``mutation_boundary`` is the canonical
    ``CoreMutationBoundary`` that owns authorization, invocation durability,
    and no-replay reconciliation for every journaled Workshop operation.
    """

    policy: WorkshopPolicy
    mutation_boundary: CoreMutationBoundary

    def __post_init__(self) -> None:
        """Rejects untyped or wrongly scoped composition members."""

        if not isinstance(self.policy, WorkshopPolicy):
            raise TypeError("WorkshopRunAuthority.policy must be a WorkshopPolicy.")
        if not isinstance(self.mutation_boundary, CoreMutationBoundary):
            raise TypeError("WorkshopRunAuthority.mutation_boundary must be a CoreMutationBoundary.")
        if self.mutation_boundary.feature_action_kind is not WorkshopMutationKind.RUN:
            raise ValueError("WorkshopRunAuthority requires the pet_workshop.run mutation scope.")


def build_workshop_run_authority(
    *,
    target: DailyMaintenanceTargetConfig,
    policy: WorkshopPolicy,
    boundary: DailyRunBoundary,
    authorizer: DailyMutationAuthorizer,
    journal_store: DailyRunJournalStore,
    budget_kind: MutationBudgetKind = MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
    max_mutations: int | None = None,
) -> WorkshopRunAuthority:
    """Construct and authorize the exact ``pet_workshop.run`` scope for one run.

    ``target`` is the resolved account/castle model, ``policy`` the explicit
    ``WorkshopPolicy`` for this invocation, ``boundary`` the shared
    maintenance date/reset identity, and ``authorizer``/``journal_store`` the
    existing authority and durable-journal owners. ``budget_kind`` selects the
    supported typed budget: ``COUNTED`` requires a positive ``max_mutations``
    cap while ``OBSERVED_WORKSHOP_BAR`` carries none. Authorization is proved
    here through ``CoreMutationBoundary``/``DailyMutationAuthorizer``; no
    invocation is registered — that belongs to the caller's
    pending-reconciliation and fresh-identity preparation step.
    """

    mutation_boundary = CoreMutationBoundary(
        target=target,
        boundary=boundary,
        authorizer=authorizer,
        journal_store=journal_store,
        feature_action_kind=WorkshopMutationKind.RUN,
        feature_budget_kind=budget_kind,
        feature_max_mutations=max_mutations,
    )
    mutation_boundary.authorize(action_kind=WorkshopMutationKind.RUN)
    return WorkshopRunAuthority(policy=policy, mutation_boundary=mutation_boundary)
