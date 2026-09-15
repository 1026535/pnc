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
from pnc_automation.app.pnc.domain.building_operations import (
    BuildingActionIdentity,
    BuildingConstructionTarget,
    BuildingMutationKind,
    BuildingMutationReceipt,
    BuildingReceiptStatus,
    BuildingUpgradeTarget,
    observable_building_instance_key,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    home_city_object_id_for_screen,
    is_repeatable_home_city_object,
    is_upgradeable_primary_screen,
    require_building_construction_source,
)
from pnc_automation.app.automation.tasks.building_workflow_support import (
    building_requirement_is_visible,
    building_requirement_text,
    home_build_help_is_available,
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
from pnc_automation.app.pnc.domain.observation import (
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    VisibleElementSourceKind,
)
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
    building_action_kind: BuildingMutationKind | None = None
    building_max_mutations: int = 1
    building_max_diamond_spend: int = 0

    def __post_init__(self) -> None:
        """Reject invalid optional building mutation budgets at composition time."""

        if self.building_action_kind is not None and not isinstance(
            self.building_action_kind, BuildingMutationKind
        ):
            raise TypeError("CoreMutationBoundary.building_action_kind must be a BuildingMutationKind or None.")
        if type(self.building_max_mutations) is not int or self.building_max_mutations <= 0:
            raise ValueError("CoreMutationBoundary.building_max_mutations must be positive.")
        if type(self.building_max_diamond_spend) is not int or self.building_max_diamond_spend < 0:
            raise ValueError("CoreMutationBoundary.building_max_diamond_spend must be non-negative.")

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
            if (
                policy.quest_id == DailyQuestId.UPGRADE_BUILDING
                and policy.task_id == TaskId.BUILDING_UPGRADE
                and policy.max_mutations == 1
                and policy.max_diamond_spend is not None
            ):
                return policy
        raise PermissionError("The core mutation scope has no supported exact capability policy.")

    def supports_mutation(
        self,
        *,
        capability: DailyQuestId | None,
        action_kind: BuildingMutationKind | None = None,
    ) -> bool:
        """Check the exact Daily capability or feature action bound to this scope."""

        if action_kind is not None:
            return self.building_action_kind == action_kind
        try:
            return capability is not None and capability == self.policy.quest_id
        except PermissionError:
            return False

    def authorize(
        self,
        *,
        capability: DailyQuestId | None = None,
        action_kind: BuildingMutationKind | None = None,
    ) -> None:
        """Reject unsupported capabilities and missing authority before device access."""
        if self.building_action_kind is not None:
            if action_kind != self.building_action_kind:
                raise PermissionError("Building mutation authority does not match the requested action kind.")
            daily_policy = next(
                (
                    item
                    for item in self.target.capabilities
                    if item.quest_id == DailyQuestId.UPGRADE_BUILDING
                    and item.task_id == TaskId.BUILDING_UPGRADE
                ),
                None,
            )
            if capability is DailyQuestId.UPGRADE_BUILDING:
                if self.building_action_kind is not BuildingMutationKind.UPGRADE or daily_policy is None:
                    raise PermissionError("The mutation scope has no exact Upgrade Building Daily capability.")
                self.authorizer.require(
                    account_id=self.target.account_id,
                    castle_ref=self.target.castle_ref,
                    policy=daily_policy,
                    maintenance_date=self.boundary.maintenance_date,
                )
            elif capability is None:
                self.authorizer.require_building(
                    account_id=self.target.account_id,
                    castle_ref=self.target.castle_ref,
                    action_kind=self.building_action_kind.value,
                    maintenance_date=self.boundary.maintenance_date,
                    max_mutations=self.building_max_mutations,
                    max_diamond_spend=self.building_max_diamond_spend,
                )
            else:
                raise PermissionError("Building mutation authority has an unrelated Daily capability.")
            return
        if capability is not None and capability != self.policy.quest_id:
            raise PermissionError("The mutation scope does not authorize this Daily capability.")
        self.authorizer.require(
            account_id=self.target.account_id,
            castle_ref=self.target.castle_ref,
            maintenance_date=self.boundary.maintenance_date,
            policy=self.policy,
        )

    def verify_active_castle(
        self,
        runtime: CoreRuntime,
        *,
        capability: DailyQuestId | None = None,
        action_kind: BuildingMutationKind | None = None,
    ) -> None:
        """Require the canonical nonselecting preflight before executing a mutation."""

        self.authorize(capability=capability, action_kind=action_kind)
        self._verify_active_castle_identity(runtime)

    def _verify_active_castle_identity(self, runtime: CoreRuntime) -> None:
        """Share the exact nonselecting identity proof for dispatch and reconciliation."""

        if runtime.preflight_active_castle_identity() != self.target.castle:
            raise PermissionError(
                "The active castle does not match the authorized mutation target."
            )

    def reconcile_building_operation(
        self,
        *,
        runtime: CoreRuntime,
        observe: Callable[[str], Observation],
        operation_id: str,
        action_kind: BuildingMutationKind,
        checkpoint: DailyTaskCheckpoint,
        daily_quest_id: DailyQuestId | None = None,
        expected_target: BuildingConstructionTarget | BuildingUpgradeTarget | None = None,
    ) -> tuple[BuildingActionIdentity, BuildingMutationReceipt | None, JournaledMutationResult] | None:
        """Reconcile a named durable building intent before opening obsolete UI preconditions."""

        if self.building_action_kind != action_kind:
            raise PermissionError("Building mutation authority does not match the requested action kind.")
        self.authorize(capability=daily_quest_id, action_kind=action_kind)
        self._require_building_checkpoint(
            checkpoint,
            operation_id,
            action_kind=action_kind,
            daily_context=daily_quest_id is DailyQuestId.UPGRADE_BUILDING,
        )
        intent = next(
            (item for item in checkpoint.mutation_intents if item.operation_id == operation_id),
            None,
        )
        if intent is None:
            return None
        if intent.action_kind != action_kind.value or not isinstance(intent.target, dict):
            raise ValueError("Stored building operation has a different action identity.")
        target = (
            BuildingConstructionTarget.from_metadata(intent.target)
            if action_kind is BuildingMutationKind.CONSTRUCT
            else BuildingUpgradeTarget.from_metadata(intent.target)
        )
        if expected_target is not None and not _building_targets_match_for_retry(
            target,
            expected_target,
        ):
            raise ValueError("Stored building operation has different target parameters.")
        identity = BuildingActionIdentity(
            kind=action_kind,
            operation_id=operation_id,
            target=target,
            daily_quest_id=daily_quest_id,
        )

        def reconcile() -> MutationReconciliation:
            after = observe(f"{action_kind.value}_existing_receipt")
            proof, status = _building_receipt_proof(identity, after)
            return MutationReconciliation(
                postcondition_proven=proof,
                original_precondition_proven=False,
                artifact_paths=(() if after.artifact_path is None else (str(after.artifact_path),)),
                metadata={"receipt_status": status.value, "target": target.as_metadata()},
            )

        result = JournaledMutationDispatcher(self.journal_store).reconcile_existing(
            checkpoint=checkpoint,
            operation_id=operation_id,
            reconcile=reconcile,
        )
        return identity, _receipt_from_result(identity, result), result

    def execute_building(
        self,
        *,
        runtime: CoreRuntime,
        observe: Callable[[str], Observation],
        identity: BuildingActionIdentity,
        checkpoint: DailyTaskCheckpoint,
        source: Observation,
        queue_available: bool = False,
    ) -> tuple[DailyTaskCheckpoint, BuildingMutationReceipt | None, JournaledMutationResult]:
        """Dispatch one target-bound building action through the shared journal."""

        if self.building_action_kind != identity.kind:
            raise PermissionError("Mutation scope does not authorize this exact building action kind.")
        self.authorize(capability=identity.daily_quest_id, action_kind=identity.kind)
        self._require_building_checkpoint(
            checkpoint,
            identity.operation_id,
            action_kind=identity.kind,
            daily_context=identity.daily_quest_id is DailyQuestId.UPGRADE_BUILDING,
        )
        if identity.kind is BuildingMutationKind.CONSTRUCT:
            selector = UiElementId.PNC_BUILDING_CONSTRUCTION_BUILD_BUTTON
            expected_screen = ScreenType.PNC_BUILDING_CONSTRUCTION
        else:
            selector = UiElementId.PNC_BUILDING_UPGRADE_BUTTON
            expected_screen = ScreenType.PNC_BUILDING_DETAILS
        executor = runtime.runtime.require_observed_action_executor(
            "Building mutations require the canonical observed action executor."
        )
        existing = next(
            (item for item in checkpoint.mutation_intents if item.operation_id == identity.operation_id),
            None,
        )
        needs_precondition = existing is None or existing.state == MutationIntentState.PREPARED
        if identity.kind is BuildingMutationKind.CONSTRUCT and needs_precondition:
            target = identity.target
            if not isinstance(target, BuildingConstructionTarget):
                raise TypeError("Construction action requires a construction target.")
            source_screen = require_building_construction_source(target.building).menu_screen_type
            if source.screen_type == source_screen:
                if not source.has(target.option_selector_id):
                    raise RuntimeError("Building construction option is not freshly observed.")
                if not executor.execute_action(
                    TapAction(
                        selector_id=target.option_selector_id,
                        reason=f"select_{target.building.value}_construction_option",
                    ),
                    source,
                ):
                    raise RuntimeError("Construction option was not selected.")
                source = observe("building_construct_confirmation")
            if source.screen_type != expected_screen or not source.has(selector):
                raise RuntimeError("Building construction requires a fresh normal Build control.")
        elif identity.kind is BuildingMutationKind.UPGRADE and needs_precondition:
            target = identity.target
            if not isinstance(target, BuildingUpgradeTarget):
                raise TypeError("Upgrade action requires an upgrade target.")
            _require_upgrade_policy_state(source, target, queue_available=queue_available)
            if source.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON):
                if not target.allow_speedups:
                    raise RuntimeError(
                        "Building upgrade is already active; speedup use is not authorized."
                    )
                raise RuntimeError(
                    "Authorized building speedup requires a typed item, quantity, availability, "
                    "and cost before Auto can be journaled; no speedup input was sent."
                )
            target_screen = home_city_object_id_for_screen(source.screen_type)
            valid_primary = (
                source.screen_type == expected_screen
                or (
                    is_upgradeable_primary_screen(source.screen_type)
                    and target_screen == target.building
                )
            )
            if not valid_primary and selector == UiElementId.PNC_BUILDING_UPGRADE_BUTTON:
                raise RuntimeError("Building upgrade requires a fresh target-specific normal control.")
            if not source.has(selector):
                raise RuntimeError("Building upgrade requires a fresh target-specific normal control.")

        def dispatch() -> None:
            if not executor.execute_action(
                TapAction(selector_id=selector, reason=f"{identity.kind.value}_{identity.target.building.value}"),
                source,
            ):
                raise RuntimeError("Building action was not executed; its journal prevents replay.")

        def reconcile() -> MutationReconciliation:
            after = observe(f"{identity.kind.value}_receipt")
            if identity.kind is BuildingMutationKind.UPGRADE:
                if after.screen_type == ScreenType.PNC_BUILD_SPEEDUP_CONFIRM:
                    follow_up = _execute_building_follow_up(
                        boundary=self,
                        runtime=runtime,
                        observe=observe,
                        identity=identity,
                        checkpoint=checkpoint,
                        source=after,
                        selector=UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON,
                        expected_precondition="inventory speedup confirmation is visible",
                        expected_postcondition="target building level proves the inventory speedup",
                        suffix="speedup_confirm",
                    )
                    if follow_up.committed:
                        after = observe("building_upgrade_speedup_receipt")
                    else:
                        return MutationReconciliation(
                            postcondition_proven=False,
                            original_precondition_proven=False,
                            artifact_paths=follow_up.artifact_paths,
                        )
                elif after.screen_type == ScreenType.PNC_BUILDING_UPGRADE_WARNING:
                    follow_up = _execute_building_follow_up(
                        boundary=self,
                        runtime=runtime,
                        observe=observe,
                        identity=identity,
                        checkpoint=checkpoint,
                        source=after,
                        selector=UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON,
                        expected_precondition="building upgrade warning confirm is visible",
                        expected_postcondition="building upgrade receipt is observed after warning confirmation",
                    )
                    if follow_up.committed:
                        after = observe("building_upgrade_warning_receipt")
                    else:
                        return MutationReconciliation(
                            postcondition_proven=False,
                            original_precondition_proven=False,
                            artifact_paths=follow_up.artifact_paths,
                        )
                elif after.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL):
                    follow_up = _execute_building_follow_up(
                        boundary=self,
                        runtime=runtime,
                        observe=observe,
                        identity=identity,
                        checkpoint=checkpoint,
                        source=after,
                        selector=UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
                        expected_precondition="building upgrade confirmation is visible",
                        expected_postcondition="building upgrade receipt is observed after confirmation",
                    )
                    if follow_up.committed:
                        after = observe("building_upgrade_confirmation_receipt")
                    else:
                        return MutationReconciliation(
                            postcondition_proven=False,
                            original_precondition_proven=False,
                            artifact_paths=follow_up.artifact_paths,
                        )
            proof, status = _building_receipt_proof(identity, after)
            if proof and identity.kind is BuildingMutationKind.UPGRADE:
                target = identity.target
                assert isinstance(target, BuildingUpgradeTarget)
                if target.request_help and after.screen_type == ScreenType.PNC_HOME_CITY and home_build_help_is_available(after):
                    help_result = _execute_building_follow_up(
                        boundary=self,
                        runtime=runtime,
                        observe=observe,
                        identity=identity,
                        checkpoint=checkpoint,
                        source=after,
                        selector=UiElementId.PNC_HOME_BUILD_BUTTON,
                        expected_precondition="post-upgrade Help is visible for the target build",
                        expected_postcondition="post-upgrade Help is consumed without replaying Upgrade",
                        suffix="help",
                        proof=lambda frame: (
                            frame.screen_type == ScreenType.PNC_HOME_CITY
                            and not home_build_help_is_available(frame)
                        ),
                    )
                    if not help_result.committed:
                        return MutationReconciliation(
                            postcondition_proven=False,
                            original_precondition_proven=False,
                            artifact_paths=help_result.artifact_paths,
                        )
            return MutationReconciliation(
                postcondition_proven=proof,
                original_precondition_proven=(after.screen_type == expected_screen and after.has(selector)),
                artifact_paths=(() if after.artifact_path is None else (str(after.artifact_path),)),
                metadata={"receipt_status": status.value, "target": identity.target.as_metadata()},
            )

        _, diamond_budget = self._building_mutation_limits(
            identity.kind,
            daily_context=identity.daily_quest_id is DailyQuestId.UPGRADE_BUILDING,
        )
        result = JournaledMutationDispatcher(self.journal_store).execute(
            checkpoint=checkpoint,
            operation=MutationOperation(
                operation_id=identity.operation_id,
                quest_id=identity.daily_quest_id,
                expected_precondition=f"{identity.kind.value} target has normal control",
                expected_postcondition=f"{identity.kind.value} target receipt is observed",
                diamond_budget=diamond_budget,
                metadata=identity.as_metadata(),
                action_kind=identity.kind,
                target=identity.target.as_metadata(),
            ),
            dispatch=dispatch,
            reconcile=reconcile,
            revalidate_precondition=(
                (lambda: True)
                if existing is not None and existing.state == MutationIntentState.PREPARED
                else None
            ),
        )
        receipt = _receipt_from_result(identity, result)
        return result.checkpoint, receipt, result

    def _require_building_checkpoint(
        self,
        checkpoint: DailyTaskCheckpoint,
        operation_id: str,
        *,
        action_kind: BuildingMutationKind,
        daily_context: bool = False,
    ) -> None:
        """Validate identity while allowing this operation's own receipt to reconcile."""

        self._require_checkpoint_identity(checkpoint)
        persisted = self.journal_store.load(
            game_reset_id=checkpoint.game_reset_id,
            account_id=checkpoint.account_id,
            castle=checkpoint.castle,
        )
        if persisted is not None and persisted != checkpoint:
            raise RuntimeError("Mutation checkpoint is stale relative to the durable journal.")
        if persisted is None and checkpoint.mutation_intents:
            raise RuntimeError("Mutation history is missing from the durable journal.")
        existing = next(
            (intent for intent in checkpoint.mutation_intents if intent.operation_id == operation_id),
            None,
        )
        if existing is None:
            mutation_count = sum(
                intent.action_kind == action_kind.value
                and intent.metadata.get("building_subaction") is not True
                for intent in checkpoint.mutation_intents
            )
            max_mutations, _ = self._building_mutation_limits(
                action_kind,
                daily_context=daily_context,
            )
            if mutation_count >= max_mutations:
                raise PermissionError("The building mutation acknowledgement cap has been exhausted.")
        unresolved = tuple(
            intent for intent in checkpoint.mutation_intents
            if intent.operation_id != operation_id
            and intent.metadata.get("parent_operation_id") != operation_id
            and intent.state != MutationIntentState.COMMITTED
        )
        if unresolved:
            raise RuntimeError("An unresolved mutation must be reconciled before another building action.")

    def _require_checkpoint_identity(self, checkpoint: DailyTaskCheckpoint) -> None:
        """Require checkpoint account, castle, reset and date to match this boundary."""

        if (
            checkpoint.account_id != self.target.account_id
            or checkpoint.castle != self.target.castle
            or checkpoint.game_reset_id != self.boundary.game_reset_id
            or checkpoint.maintenance_date != self.boundary.maintenance_date.isoformat()
        ):
            raise PermissionError("Mutation checkpoint does not match its authorized boundary.")

    def _building_mutation_limits(
        self,
        action_kind: BuildingMutationKind,
        *,
        daily_context: bool = False,
    ) -> tuple[int, int]:
        """Return the exact mutation and premium budget bound for one building action kind."""

        if daily_context and action_kind is BuildingMutationKind.UPGRADE:
            daily_policy = next(
                (
                    item
                    for item in self.target.capabilities
                    if item.quest_id == DailyQuestId.UPGRADE_BUILDING
                    and item.task_id == TaskId.BUILDING_UPGRADE
                ),
                None,
            )
            if daily_policy is not None:
                return (
                    daily_policy.max_mutations,
                    0 if daily_policy.max_diamond_spend is None else daily_policy.max_diamond_spend,
                )
        return self.building_max_mutations, self.building_max_diamond_spend

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
        node_title: str,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Start one normal research item; uncertain dispatch is never replayed."""

        self.authorize()
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
            or _is_active_research_detail(source)
        ):
            raise RuntimeError("Research requires a fresh, guarded normal Start control.")
        executor = runtime.runtime.require_observed_action_executor(
            "Core Research requires the canonical observed action executor."
        )

        def dispatch() -> None:
            executed = executor.execute_action(
                TapAction(
                    selector_id=UiElementId.PNC_RESEARCH_START_BUTTON,
                    reason="start_research",
                ),
                source,
            )
            if not executed:
                raise RuntimeError("Research Start was not executed; its journal prevents replay.")

        def reconcile() -> MutationReconciliation:
            after = runtime.navigation.confirm_content_after_action(
                source,
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
                expected_precondition=f"Selected research {node_title} has a normal Start control",
                expected_postcondition="Guarded active research detail with no Start control",
                metadata={"node_title": node_title},
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


def _require_upgrade_policy_state(
    observation: Observation,
    target: BuildingUpgradeTarget,
    *,
    queue_available: bool = False,
) -> None:
    """Reject unsupported queue/material states before a normal Upgrade input."""

    if observation.blocking_popup:
        raise RuntimeError("Building upgrade is blocked by an unresolved popup.")
    if not queue_available:
        raise RuntimeError(
            "Building upgrade requires a positive current-frame Home build-control queue proof."
        )
    if building_requirement_is_visible(observation):
        requirement = building_requirement_text(observation) or "unknown prerequisite"
        if target.allow_premium_material_purchases:
            raise RuntimeError(
                "Premium-material purchase was requested, but no target-bound purchase control "
                "was published in this building observation."
            )
        if target.prerequisite_mode.value == "fail":
            raise RuntimeError(f"Building upgrade prerequisite is unmet: {requirement}.")
        if not observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON):
            raise RuntimeError(
                f"Building upgrade prerequisite '{requirement}' has no typed Go control."
            )
        raise RuntimeError(
            "Building upgrade QUEUE requires a typed prerequisite target and route; no input was sent."
        )
    # Preserve the existing typed dispositions when a production observer has
    # published one.  The current-frame Home proof above remains mandatory;
    # these optional facts never establish availability on their own.
    for entry in observation.entries(ListEntryKind.BUILDING):
        queue_state = entry.metadata.get("queue_state")
        if queue_state in {"full", "gift", "third", "third_queue", "unknown"}:
            raise RuntimeError(
                f"Building upgrade cannot dispatch while the build queue is '{queue_state}'."
            )
    if (
        observation.has(UiElementId.PNC_BUILD_SPEEDUP_PREMIUM_BUILD_NOW_BUTTON)
        and not observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
    ):
        raise RuntimeError("Only the premium Build Now control is visible; normal Upgrade is required.")


def _execute_building_follow_up(
    *,
    boundary: CoreMutationBoundary,
    runtime: CoreRuntime,
    observe: Callable[[str], Observation],
    identity: BuildingActionIdentity,
    checkpoint: DailyTaskCheckpoint,
    source: Observation,
    selector: UiElementId,
    expected_precondition: str,
    expected_postcondition: str,
    suffix: str | None = None,
    proof: Callable[[Observation], bool] | None = None,
) -> JournaledMutationResult:
    """Journal one target-bound warning/speedup/Help follow-up exactly once."""

    executor = runtime.runtime.require_observed_action_executor(
        "Building follow-up requires the canonical observed action executor."
    )
    operation_id = f"{identity.operation_id}:{suffix or selector.value.lower()}"
    current = checkpoint
    # The parent operation may have entered reconciliation before this
    # follow-up was discovered. Always use the latest durable checkpoint.
    persisted = boundary.journal_store.load(
        game_reset_id=checkpoint.game_reset_id,
        account_id=checkpoint.account_id,
        castle=checkpoint.castle,
    )
    if persisted is not None:
        current = persisted

    def dispatch() -> None:
        if not source.has(selector):
            raise RuntimeError("Building follow-up control is no longer visible; no input was sent.")
        if not executor.execute_action(
            TapAction(selector_id=selector, reason=f"{identity.kind.value}_{suffix or selector.value.lower()}"),
            source,
        ):
            raise RuntimeError("Building follow-up input was not executed; its journal prevents replay.")

    def reconcile() -> MutationReconciliation:
        after = observe(f"{identity.kind.value}_{suffix or selector.value.lower()}_receipt")
        postcondition = (
            proof(after)
            if proof is not None
            else _building_receipt_proof(identity, after)[0]
        )
        return MutationReconciliation(
            postcondition_proven=postcondition,
            original_precondition_proven=after.has(selector),
            artifact_paths=(() if after.artifact_path is None else (str(after.artifact_path),)),
            metadata={"building_subaction": True, "parent_operation_id": identity.operation_id},
        )

    return JournaledMutationDispatcher(boundary.journal_store).execute(
        checkpoint=current,
        operation=MutationOperation(
            operation_id=operation_id,
            quest_id=identity.daily_quest_id,
            expected_precondition=expected_precondition,
            expected_postcondition=expected_postcondition,
            diamond_budget=0,
            metadata={
                "building_subaction": True,
                "parent_operation_id": identity.operation_id,
                "target": identity.target.as_metadata(),
            },
            action_kind=identity.kind,
            target=identity.target.as_metadata(),
        ),
        dispatch=dispatch,
        reconcile=reconcile,
    )


def _building_receipt_proof(
    identity: BuildingActionIdentity,
    observation: Observation,
) -> tuple[bool, BuildingReceiptStatus]:
    """Accept only a fresh target-correlated timer, queue row, or level receipt."""

    target = identity.target
    target_building = target.building.value
    if observation.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON):
        if home_city_object_id_for_screen(observation.screen_type) == target.building:
            return True, BuildingReceiptStatus.STARTED
        if any(
            object_.metadata.get("home_city_object_id") == target_building
            and (
                _spatial_object_matches_construction_target(object_, target)
                if isinstance(target, BuildingConstructionTarget)
                else _spatial_object_matches_upgrade_target(object_, target)
            )
            for object_ in observation.spatial_objects()
        ):
            return True, BuildingReceiptStatus.STARTED
    for entry in observation.entries(ListEntryKind.BUILDING):
        if entry.metadata.get("building_operation_id") == identity.operation_id:
            return True, BuildingReceiptStatus.STARTED
        if (
            entry.metadata.get("active_build") is True
            and entry.metadata.get("home_city_object_id") == target_building
            and (
                isinstance(target, BuildingUpgradeTarget)
                and not is_repeatable_home_city_object(target.building)
            )
        ):
            return True, BuildingReceiptStatus.STARTED
    if identity.kind is BuildingMutationKind.UPGRADE:
        assert isinstance(target, BuildingUpgradeTarget)
        level_element = observation.get(UiElementId.PNC_BUILDING_LEVEL_LABEL)
        if (
            home_city_object_id_for_screen(observation.screen_type) == target.building
            and level_element is not None
            and level_element.extracted_text is not None
        ):
            raw_level = level_element.extracted_text.replace("Lv.", "").replace("LV", "").strip()
            try:
                if int(raw_level) >= target.next_level:
                    return True, BuildingReceiptStatus.LEVEL_INCREASED
            except ValueError:
                pass
        for object_ in observation.spatial_objects():
            metadata = object_.metadata
            if metadata.get("home_city_object_id") != target.building.value:
                continue
            if not _spatial_object_matches_upgrade_target(object_, target):
                continue
            if object_.level is not None and object_.level >= target.next_level:
                return True, BuildingReceiptStatus.LEVEL_INCREASED
    return False, BuildingReceiptStatus.PENDING_CLARIFICATION


def _spatial_object_matches_upgrade_target(
    object_: DetectedSpatialObject,
    target: BuildingUpgradeTarget,
) -> bool:
    """Match a Home spatial object using the same observable identity as target acquisition."""

    try:
        return observable_building_instance_key(target.building, object_) == target.instance_key
    except (AttributeError, TypeError, ValueError):
        return False


def _building_targets_match_for_retry(
    stored: BuildingConstructionTarget | BuildingUpgradeTarget,
    requested: BuildingConstructionTarget | BuildingUpgradeTarget,
) -> bool:
    """Compare caller-known target parameters without weakening stored identity."""

    if type(stored) is not type(requested):
        return False
    if isinstance(stored, BuildingConstructionTarget) and isinstance(requested, BuildingConstructionTarget):
        return (
            stored.building == requested.building
            and stored.slot_id == requested.slot_id
            and stored.slot_family == requested.slot_family
            and stored.option_selector_id == requested.option_selector_id
            and (
                requested.slot_instance_key is None
                or stored.slot_instance_key == requested.slot_instance_key
            )
        )
    if isinstance(stored, BuildingUpgradeTarget) and isinstance(requested, BuildingUpgradeTarget):
        return stored == requested
    return False


def _spatial_object_matches_construction_target(
    object_: DetectedSpatialObject,
    target: BuildingConstructionTarget,
) -> bool:
    """Correlate a newly published building to the exact observed source geometry."""

    if target.slot_instance_key is None:
        return False
    parts = target.slot_instance_key.split(":", 2)
    if len(parts) != 3 or parts[0] != "home-slot":
        return False
    bounds = object_.bounds
    point = object_.action_point
    point_text = "none" if point is None else f"{point[0]},{point[1]}"
    return parts[2] == f"{bounds.x},{bounds.y},{bounds.width},{bounds.height}:{point_text}"


def _receipt_from_result(
    identity: BuildingActionIdentity,
    result: JournaledMutationResult,
) -> BuildingMutationReceipt | None:
    """Materialize a receipt only after the journal reports a proven postcondition."""

    if not result.committed and not result.pending_clarification:
        return None
    status = BuildingReceiptStatus.STARTED if result.committed else BuildingReceiptStatus.PENDING_CLARIFICATION
    intent = next(
        (item for item in result.checkpoint.mutation_intents if item.operation_id == identity.operation_id),
        None,
    )
    metadata = {} if intent is None else intent.metadata
    raw_status = metadata.get("receipt_status")
    if result.committed and isinstance(raw_status, str):
        try:
            status = BuildingReceiptStatus(raw_status)
        except ValueError:
            status = BuildingReceiptStatus.STARTED
    return BuildingMutationReceipt(
        operation_id=identity.operation_id,
        action_kind=identity.kind,
        status=status,
        target=identity.target,
        artifact_paths=result.artifact_paths,
    )
