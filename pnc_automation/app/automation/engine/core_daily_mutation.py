"""Bind the existing mutation authority and journal to supported core operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.claim_executor import (
    JournaledDailyClaimExecutor,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    JournaledMutationResult,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyMaintenanceCoordinator,
    DailyMaintenanceResult,
    DailyQuestSession,
    DailyReadOnlySurvey,
    DailyRowClaimExecutor,
    ForbiddenDailyMutationExecutor,
)
from pnc_automation.app.automation.daily_maintenance.hero_hall import HeroHallRecruitmentExecutor
from pnc_automation.app.automation.daily_maintenance.resource_item import ResourceItemExecutor
from pnc_automation.app.automation.engine.core_hero_hall_session import CoreHeroHallSession
from pnc_automation.app.automation.engine.core_resource_item_session import CoreResourceItemSession
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.research_task import _is_active_research_detail
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyQuestRow,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore


@dataclass(frozen=True, slots=True)
class _ClaimObservationSession:
    """Supply only the fresh observation dependency of the canonical claim executor."""

    observe: Callable[[str], Observation]

    def observe_daily_quest(self, label: str) -> Observation:
        """Delegate capture and guards to the constrained workflow context."""

        return self.observe(label)


@dataclass(frozen=True, slots=True)
class CoreMutationBoundary:
    """Bind supported typed operations to the existing exact authority and journal."""

    target: DailyMaintenanceTargetConfig
    boundary: DailyRunBoundary
    authorizer: DailyMutationAuthorizer
    journal_store: DailyRunJournalStore

    def require_caller(
        self, *, account_id: str, journal_root: Path | None = None,
        castle: CastleIdentity | None = None,
    ) -> None:
        """Bind an external caller to this target and the configured durable journal."""

        if account_id != self.target.account_id or (castle is not None and castle != self.target.castle):
            raise PermissionError("Caller account/castle does not match the mutation scope.")
        if journal_root is not None and self.journal_store.root != journal_root.resolve():
            raise PermissionError("Caller mutation scope must use the configured durable journal root.")

    def load_checkpoint(
        self, *, require_existing: bool = False,
        reconcilable_quest: DailyQuestId | None = None,
    ) -> DailyTaskCheckpoint:
        """Load current durable state without writing or replacing existing receipts."""

        checkpoint = self.journal_store.load(
            game_reset_id=self.boundary.game_reset_id,
            account_id=self.target.account_id,
            castle=self.target.castle,
        )
        if checkpoint is None:
            if require_existing:
                raise PermissionError("Reconciliation requires an existing durable checkpoint.")
            checkpoint = DailyTaskCheckpoint(
                self.boundary.maintenance_date.isoformat(), self.boundary.game_reset_id,
                self.target.account_id, self.target.castle,
            )
        self._require_checkpoint(checkpoint, reconcilable_quest=reconcilable_quest)
        return checkpoint

    @property
    def policy(self) -> DailyCapabilityPolicy:
        """Return the one supported capability, rejecting all unimplemented effects."""

        if not self.target.capabilities:
            return DailyCapabilityPolicy(
                DailyQuestId.CLAIM_COMPLETED,
                TaskId.DAILY_MAINTENANCE,
                self.target.max_claims,
            )
        if len(self.target.capabilities) == 1:
            policy = self.target.capabilities[0]
            if (
                policy.quest_id == DailyQuestId.UPGRADE_RESEARCH
                and policy.task_id == TaskId.RESEARCH
                and policy.max_mutations == 1
                and policy.max_diamond_spend == 0
            ):
                return policy
            if (
                policy.quest_id == DailyQuestId.USE_RESOURCE_ITEM
                and policy.task_id == TaskId.USE_RESOURCE_ITEM
                and policy.max_mutations == 1
                and policy.max_diamond_spend == 0
            ):
                return policy
            if (
                policy.quest_id == DailyQuestId.HERO_HALL
                and policy.task_id == TaskId.HERO_HALL
                and policy.max_mutations == 5
                and policy.max_diamond_spend == 0
            ):
                return policy
        raise PermissionError("The core mutation scope has no supported exact capability policy.")

    def authorize(self) -> None:
        """Reject unsupported capabilities and missing authority before device access."""

        self.authorizer.require(
            account_id=self.target.account_id,
            castle_ref=self.target.castle_ref,
            maintenance_date=self.boundary.maintenance_date,
            policy=self.policy,
        )

    def verify_active_castle(self, runtime: CoreRuntime) -> None:
        """Require the canonical nonselecting preflight before executing a mutation."""

        self.authorize()
        self._verify_active_castle_identity(runtime)

    def _verify_active_castle_identity(self, runtime: CoreRuntime) -> None:
        """Share the exact nonselecting identity proof for dispatch and reconciliation."""

        if runtime.preflight_active_castle_identity() != self.target.castle:
            raise PermissionError(
                "The active castle does not match the authorized mutation target."
            )

    def require_hero_reconciliation(self, operation_id: str) -> DailyTaskCheckpoint:
        """Validate an existing receipt scope without granting authority for a new action."""

        if self.policy.quest_id != DailyQuestId.HERO_HALL:
            raise PermissionError("Only the exact Hero Hall scope supports this reconciliation.")
        checkpoint = self.load_checkpoint(require_existing=True, reconcilable_quest=DailyQuestId.HERO_HALL)
        HeroHallRecruitmentExecutor.require_reconciliation_intent(
            checkpoint=checkpoint, operation_id=operation_id,
        )
        return checkpoint

    def verify_hero_reconciliation_target(self, runtime: CoreRuntime, operation_id: str) -> None:
        """Require durable authority for this old intent and a freshly proved target."""

        self.require_hero_reconciliation(operation_id)
        self._verify_active_castle_identity(runtime)

    def reconcile_hero_hall(
        self, *, runtime: CoreRuntime, observe: Callable[[str], Observation],
        daily_survey: Callable[[], DailyReadOnlySurvey], checkpoint: DailyTaskCheckpoint,
        operation_id: str,
    ) -> JournaledMutationResult:
        """Reconcile only the named durable Hero intent through its existing executor."""

        self.require_hero_reconciliation(operation_id)
        self._require_checkpoint(checkpoint, reconcilable_quest=DailyQuestId.HERO_HALL)
        return HeroHallRecruitmentExecutor(
            session=CoreHeroHallSession(runtime, observe, daily_survey),
            dispatcher=JournaledMutationDispatcher(self.journal_store),
        ).reconcile_existing(checkpoint=checkpoint, operation_id=operation_id)

    def run_daily_maintenance(
        self, *, session: DailyQuestSession, claim_executor: DailyRowClaimExecutor,
        checkpoint: DailyTaskCheckpoint,
    ) -> DailyMaintenanceResult:
        """Validate the entire claim sweep before its coordinator may save progress."""

        self.authorize()
        if self.policy.quest_id != DailyQuestId.CLAIM_COMPLETED:
            raise PermissionError("This scope does not authorize a Daily claim sweep.")
        self._require_checkpoint(checkpoint)
        return DailyMaintenanceCoordinator(
            session=session,
            claim_executor=claim_executor,
            capability_executor=ForbiddenDailyMutationExecutor(),
            journal_store=self.journal_store,
            catalog=DailyQuestCatalog(),
        ).run(target=self.target, checkpoint=checkpoint)

    def claim(
        self,
        *,
        runtime: CoreRuntime,
        observe: Callable[[str], Observation],
        row: DailyQuestRow,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Use the existing executor once, preserving durable budget and ambiguity."""

        self.authorize()
        if self.policy.quest_id != DailyQuestId.CLAIM_COMPLETED:
            raise PermissionError("This scope does not authorize Daily claims.")
        self._require_checkpoint(checkpoint)
        executor = runtime.runtime.require_observed_action_executor(
            "Core Daily claims require the canonical observed action executor."
        )
        return JournaledDailyClaimExecutor(
            session=_ClaimObservationSession(observe),
            action_executor=executor,
            dispatcher=JournaledMutationDispatcher(self.journal_store),
            maximum_claims=self.target.max_claims,
        ).claim(row=row, checkpoint=checkpoint)

    def _require_checkpoint(
        self, checkpoint: DailyTaskCheckpoint, *, reconcilable_quest: DailyQuestId | None = None,
    ) -> None:
        """Do not replace durable receipts with stale or cross-target caller state."""

        if (
            checkpoint.account_id != self.target.account_id
            or checkpoint.castle != self.target.castle
            or checkpoint.game_reset_id != self.boundary.game_reset_id
            or checkpoint.maintenance_date != self.boundary.maintenance_date.isoformat()
        ):
            raise PermissionError("Mutation checkpoint does not match its authorized boundary.")
        persisted = self.journal_store.load(
            game_reset_id=checkpoint.game_reset_id,
            account_id=checkpoint.account_id,
            castle=checkpoint.castle,
        )
        if persisted is not None and persisted != checkpoint:
            raise RuntimeError("Mutation checkpoint is stale relative to the durable journal.")
        if persisted is None and checkpoint.mutation_intents:
            raise RuntimeError("Mutation history is missing from the durable journal.")
        if any(
            intent.state != MutationIntentState.COMMITTED
            and not (
                intent.quest_id == reconcilable_quest
                and intent.state in {MutationIntentState.DISPATCHED, MutationIntentState.RECONCILED}
            )
            for intent in checkpoint.mutation_intents
        ):
            raise RuntimeError("An unresolved mutation must be reconciled before another claim.")

    def recruit_hero_hall(
        self, *, runtime: CoreRuntime, observe: Callable[[str], Observation],
        daily_survey: Callable[[], DailyReadOnlySurvey], checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Run or reconcile one increment through the existing five-single executor."""

        self.authorize()
        if self.policy.quest_id != DailyQuestId.HERO_HALL:
            raise PermissionError("This scope does not authorize Hero Hall.")
        self._require_checkpoint(checkpoint, reconcilable_quest=DailyQuestId.HERO_HALL)
        return HeroHallRecruitmentExecutor(
            session=CoreHeroHallSession(runtime, observe, daily_survey),
            dispatcher=JournaledMutationDispatcher(self.journal_store),
        ).execute(checkpoint=checkpoint)

    def use_resource_item(
        self, *, runtime: CoreRuntime, observe: Callable[[str], Observation],
        open_inventory: Callable[[], None], daily_survey: Callable[[], DailyReadOnlySurvey],
        checkpoint: DailyTaskCheckpoint, allow_empty_skip: bool = False,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Use or reconcile one normal pack through the existing executor and journal."""

        self.authorize()
        if self.policy.quest_id != DailyQuestId.USE_RESOURCE_ITEM:
            raise PermissionError("This scope does not authorize Resource Item use.")
        if type(allow_empty_skip) is not bool:
            raise TypeError("Resource Item allow_empty_skip must be a bool.")
        self._require_checkpoint(checkpoint, reconcilable_quest=DailyQuestId.USE_RESOURCE_ITEM)
        return ResourceItemExecutor(
            session=CoreResourceItemSession(runtime, observe, open_inventory, daily_survey),
            dispatcher=JournaledMutationDispatcher(self.journal_store),
        ).execute(checkpoint=checkpoint, allow_empty_skip=allow_empty_skip)

    def start_research(
        self,
        *,
        runtime: CoreRuntime,
        observe: Callable[[str], Observation],
        observe_task_owned_interruption: Callable[[str], Observation],
        node_title: str,
        checkpoint: DailyTaskCheckpoint,
        confirm_resource_shortfall_from_bag: bool = False,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Start one normal research item; uncertain dispatch is never replayed."""

        self.authorize()
        if type(confirm_resource_shortfall_from_bag) is not bool:
            raise TypeError("Research Bag resource confirmation opt-in must be a bool.")
        if self.policy.quest_id != DailyQuestId.UPGRADE_RESEARCH:
            raise PermissionError("This scope does not authorize Research.")
        self._require_checkpoint(checkpoint)
        if any(
            intent.quest_id == DailyQuestId.UPGRADE_RESEARCH
            for intent in checkpoint.mutation_intents
        ):
            raise PermissionError("The one-research mutation budget has been consumed.")
        source = observe("research_start_source")
        control = source.visible_elements.get(UiElementId.PNC_RESEARCH_START_BUTTON)
        if (
            source.screen_type != ScreenType.PNC_RESEARCH_TREE
            or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or not any(
                evidence.screen_type == ScreenType.PNC_RESEARCH_TREE
                and evidence.reason == "visual_anchor:research_tree_node_detail"
                for evidence in source.decision.evidence
            )
            or control is None
            or control.source_kind != VisibleElementSourceKind.TEMPLATE
            or type(source.research_start_resources_sufficient) is not bool
            or source.research_start_queue_available is not True
            or _is_active_research_detail(source)
        ):
            raise RuntimeError(
                "Research requires a fresh, guarded normal Start control with an idle queue and "
                "an exact observed resource sufficiency fact."
            )
        uses_bag_resources = source.research_start_resources_sufficient is False
        if uses_bag_resources and not confirm_resource_shortfall_from_bag:
            raise RuntimeError(
                "Research has insufficient observed resources and Bag confirmation is disabled."
            )
        executor = runtime.runtime.require_observed_action_executor(
            "Core Research requires the canonical observed action executor."
        )
        dispatched_source = source

        def dispatch() -> None:
            nonlocal dispatched_source
            if uses_bag_resources:
                revealed = executor.execute_action(
                    TapAction(
                        selector_id=UiElementId.PNC_RESEARCH_START_BUTTON,
                        reason="reveal_research_resource_shortfall",
                    ),
                    source,
                )
                if not revealed:
                    raise RuntimeError(
                        "Research resource shortfall popup was not requested; "
                        "its journal prevents replay."
                    )
                resource_popup = None
                for index in range(runtime.navigation.policy.max_observations):
                    runtime.navigation.sleep(runtime.navigation.policy.poll_seconds)
                    candidate = observe_task_owned_interruption(
                        f"research_resource_popup_after_{index}"
                    )
                    if _is_exact_research_resource_popup(candidate):
                        resource_popup = candidate
                        break
                    if candidate.screen_type not in {
                        ScreenType.PNC_RESEARCH_TREE,
                        ScreenType.PNC_LOADING,
                        ScreenType.UNKNOWN,
                    }:
                        break
                if resource_popup is None:
                    raise RuntimeError(
                        "Research resource shortfall did not produce the exact Auto Use popup; "
                        "no Bag resources were confirmed and its journal prevents replay."
                    )
                confirmed = executor.execute_action(
                    TapAction(
                        selector_id=UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON,
                        reason="confirm_research_resource_shortfall_from_bag",
                    ),
                    resource_popup,
                )
                if not confirmed:
                    raise RuntimeError(
                        "Research Bag resource confirmation was not executed; "
                        "its journal prevents replay."
                    )
                funded_detail = None
                for index in range(runtime.navigation.policy.max_observations):
                    runtime.navigation.sleep(runtime.navigation.policy.poll_seconds)
                    candidate = observe_task_owned_interruption(
                        f"research_resource_confirmed_after_{index}"
                    )
                    if _is_funded_idle_research_detail(candidate):
                        funded_detail = candidate
                        break
                    if candidate.blocking_popup and not _is_exact_research_resource_popup(candidate):
                        break
                    if candidate.screen_type not in {
                        ScreenType.PNC_POPUP,
                        ScreenType.PNC_RESEARCH_TREE,
                        ScreenType.PNC_LOADING,
                        ScreenType.UNKNOWN,
                    }:
                        break
                if funded_detail is None:
                    raise RuntimeError(
                        "Research Bag resources were confirmed, but the same funded idle detail "
                        "was not proved; the journal prevents replay."
                    )
                dispatched_source = funded_detail
            executed = executor.execute_action(
                TapAction(
                    selector_id=UiElementId.PNC_RESEARCH_START_BUTTON,
                    reason="start_research",
                ),
                dispatched_source,
            )
            if not executed:
                raise RuntimeError("Research Start was not executed; its journal prevents replay.")

        def reconcile() -> MutationReconciliation:
            after = runtime.navigation.confirm_content_after_action(
                dispatched_source,
                frozenset({ScreenType.PNC_RESEARCH_TREE}),
                "research_started",
                observe,
                completion_predicate=lambda frame: (
                    _is_active_research_detail(frame)
                    and not frame.has(UiElementId.PNC_RESEARCH_START_BUTTON)
                ),
            )
            return MutationReconciliation(
                postcondition_proven=True,
                original_precondition_proven=False,
                artifact_paths=(
                    () if after.artifact_path is None else (str(after.artifact_path),)
                ),
            )

        result = JournaledMutationDispatcher(self.journal_store).execute(
            checkpoint=checkpoint,
            operation=MutationOperation(
                operation_id="research-001",
                quest_id=DailyQuestId.UPGRADE_RESEARCH,
                expected_precondition=(
                    f"Selected research {node_title} has a normal Start control and "
                    + (
                        "an exact resource Auto Use confirmation"
                        if uses_bag_resources
                        else "sufficient resources"
                    )
                ),
                expected_postcondition="Guarded active research detail with no Start control",
                metadata={
                    "node_title": node_title,
                    "confirmed_resource_shortfall_from_bag": uses_bag_resources,
                },
            ),
            dispatch=dispatch,
            reconcile=reconcile,
        )
        return result.checkpoint, DailyTargetOutcome(
            quest_id=DailyQuestId.UPGRADE_RESEARCH,
            status=(
                DailyTargetOutcomeStatus.SUCCESS
                if result.committed
                else DailyTargetOutcomeStatus.PENDING_CLARIFICATION
            ),
            message=(
                "Research start observed."
                if result.committed
                else "Research outcome is unproved; no replay."
            ),
            artifact_paths=result.artifact_paths,
        )


def _is_exact_research_resource_popup(observation: Observation) -> bool:
    """Require the task-owned Auto Use identity before Bag resources may be confirmed."""

    overlay = observation.popup_overlay
    return (
        observation.screen_type == ScreenType.PNC_POPUP
        and observation.blocking_popup
        and observation.decision.guard == GuardVerdict.BLOCKED
        and observation.has(UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON)
        and overlay is not None
        and overlay.layout_id == "research_resource_auto_use"
        and overlay.candidate(PopupControlKind.RESEARCH_RESOURCE_CONFIRM) is not None
    )


def _is_funded_idle_research_detail(observation: Observation) -> bool:
    """Require the same normal funded detail shape before the second Research tap."""

    control = observation.visible_elements.get(UiElementId.PNC_RESEARCH_START_BUTTON)
    return (
        observation.screen_type == ScreenType.PNC_RESEARCH_TREE
        and not observation.blocking_popup
        and observation.decision.guard == GuardVerdict.CLEAR
        and any(
            evidence.screen_type == ScreenType.PNC_RESEARCH_TREE
            and evidence.reason == "visual_anchor:research_tree_node_detail"
            for evidence in observation.decision.evidence
        )
        and control is not None
        and control.source_kind == VisibleElementSourceKind.TEMPLATE
        and observation.research_start_resources_sufficient is True
        and observation.research_start_queue_available is True
        and not _is_active_research_detail(observation)
    )
