"""Typed construction and upgrade workflows for the replacement core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationResult
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.automation.tasks.building_workflow_support import (
    building_requirement_is_visible,
    building_requirement_text,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_for_screen,
)
from pnc_automation.app.pnc.domain.building_operations import (
    BuildingActionIdentity,
    BuildingConstructionTarget,
    BuildingMutationKind,
    BuildingMutationReceipt,
    BuildingUpgradeTarget,
)
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, DailyTaskCheckpoint
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.policy_models import BuildingConstructionPolicy, BuildingUpgradePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import TaskVerificationError


class BuildingMutationDisposition(StrEnum):
    """Workflow-level result disposition."""

    STARTED = "started"
    PENDING_CLARIFICATION = "pending_clarification"


@dataclass(frozen=True, slots=True)
class BuildingMutationResult:
    """Reports one durable building operation and its target-bound receipt."""

    checkpoint: DailyTaskCheckpoint
    action: BuildingActionIdentity
    receipt: BuildingMutationReceipt | None
    disposition: BuildingMutationDisposition
    message: str
    retry_permitted: bool = False


def prepare_building_construction_workflow(
    *,
    policy: BuildingConstructionPolicy,
    checkpoint: DailyTaskCheckpoint,
    mutation_boundary: CoreMutationBoundary | None,
) -> "BuildingConstructionWorkflow":
    """Validate the exact building scope before a runtime is connected."""

    if not isinstance(mutation_boundary, CoreMutationBoundary):
        raise PermissionError("Building construction requires an explicit CoreMutationBoundary.")
    if mutation_boundary.building_action_kind != BuildingMutationKind.CONSTRUCT:
        raise PermissionError("Mutation scope does not authorize building construction.")
    return BuildingConstructionWorkflow(policy=policy, checkpoint=checkpoint)


def prepare_building_upgrade_workflow(
    *,
    policy: BuildingUpgradePolicy,
    checkpoint: DailyTaskCheckpoint,
    mutation_boundary: CoreMutationBoundary | None,
    target: BuildingUpgradeTarget | None = None,
    daily_quest_id: DailyQuestId | None = None,
) -> "BuildingUpgradeWorkflow":
    """Validate the exact building scope before a runtime is connected."""

    if not isinstance(mutation_boundary, CoreMutationBoundary):
        raise PermissionError("Building upgrade requires an explicit CoreMutationBoundary.")
    if mutation_boundary.building_action_kind != BuildingMutationKind.UPGRADE:
        raise PermissionError("Mutation scope does not authorize building upgrade.")
    if daily_quest_id not in {None, DailyQuestId.UPGRADE_BUILDING}:
        raise ValueError("Building upgrade can carry only the existing Upgrade Building Daily context.")
    return BuildingUpgradeWorkflow(
        policy=policy,
        checkpoint=checkpoint,
        target=target,
        daily_quest_id=daily_quest_id,
    )


@dataclass(frozen=True, slots=True)
class BuildingConstructionWorkflow(CoreWorkflow[BuildingMutationResult]):
    """Construct one exact catalog building through the normal Build control."""

    policy: BuildingConstructionPolicy
    checkpoint: DailyTaskCheckpoint

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="building_construct",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
        mutation_action_kind=BuildingMutationKind.CONSTRUCT,
    )

    def __post_init__(self) -> None:
        """Reject malformed construction workflow inputs."""

        if not isinstance(self.policy, BuildingConstructionPolicy):
            raise TypeError("BuildingConstructionWorkflow.policy must be a BuildingConstructionPolicy.")
        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("BuildingConstructionWorkflow.checkpoint must be a DailyTaskCheckpoint.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the fixed Home-to-Home construction contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> BuildingMutationResult:
        """Navigate to the exact source menu and submit ordinary Build once."""

        operation_id = _require_operation_id(self.policy.operation_id, action="construction")
        reconciled = _reconcile_existing_building(
            context,
            operation_id=operation_id,
            action_kind=BuildingMutationKind.CONSTRUCT,
            checkpoint=self.checkpoint,
            expected_target=BuildingConstructionTarget.for_building(self.policy.building),
        )
        if reconciled is not None:
            return _result_from_reconciliation(reconciled, action_name="Construction")
        target = BuildingConstructionTarget.for_building(self.policy.building)
        content, slot_instance_key = context.open_construction_slot(target)
        target = target.bind_slot(slot_instance_key)
        if content.screen_type != _menu_screen(target):
            raise TaskVerificationError(
                "Construction slot did not open its canonical building menu."
            )
        if not content.has(target.option_selector_id):
            raise TaskVerificationError(
                "Construction menu did not expose the exact catalog option."
            )
        action = BuildingActionIdentity(
            kind=BuildingMutationKind.CONSTRUCT,
            operation_id=operation_id,
            target=target,
        )
        checkpoint, receipt, result = context.execute_building(action, self.checkpoint, content)
        return BuildingMutationResult(
            checkpoint=checkpoint,
            action=action,
            receipt=receipt,
            disposition=(
                BuildingMutationDisposition.STARTED
                if result.committed
                else BuildingMutationDisposition.PENDING_CLARIFICATION
            ),
            message=(
                f"Construction of '{target.building.value}' started."
                if result.committed
                else _pending_building_message(result, action="Construction")
            ),
            retry_permitted=getattr(result, "retry_permitted", False),
        )


@dataclass(frozen=True, slots=True)
class BuildingUpgradeWorkflow(CoreWorkflow[BuildingMutationResult]):
    """Upgrade one exact observed building instance through normal Upgrade."""

    policy: BuildingUpgradePolicy
    checkpoint: DailyTaskCheckpoint
    target: BuildingUpgradeTarget | None = None
    daily_quest_id: DailyQuestId | None = None

    def __post_init__(self) -> None:
        """Reject malformed upgrade workflow inputs."""

        if not isinstance(self.policy, BuildingUpgradePolicy):
            raise TypeError("BuildingUpgradeWorkflow.policy must be a BuildingUpgradePolicy.")
        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("BuildingUpgradeWorkflow.checkpoint must be a DailyTaskCheckpoint.")
        if self.target is not None and not isinstance(self.target, BuildingUpgradeTarget):
            raise TypeError("BuildingUpgradeWorkflow.target must be a BuildingUpgradeTarget or None.")
        if self.daily_quest_id not in {None, DailyQuestId.UPGRADE_BUILDING}:
            raise ValueError("Building upgrade can carry only the existing Upgrade Building Daily context.")

    @property
    def spec(self) -> WorkflowSpec:
        """Return the exact direct or Daily-scoped Home-to-Home contract."""

        daily_quest_id = self.daily_quest_id or self.policy.daily_quest_id
        return WorkflowSpec(
            name="building_upgrade",
            entry_screen=ScreenType.PNC_HOME_CITY,
            exit_screen=ScreenType.PNC_HOME_CITY,
            effect=WorkflowEffect.RESOURCE_CHANGING,
            mutation_capability=daily_quest_id,
            mutation_action_kind=BuildingMutationKind.UPGRADE,
        )

    def execute(self, context: WorkflowContext) -> BuildingMutationResult:
        """Select a priority target, revalidate its detail, then dispatch once."""

        daily_quest_id = self.daily_quest_id or self.policy.daily_quest_id
        operation_id = _resolve_upgrade_operation_id(
            self.policy.operation_id,
            checkpoint=self.checkpoint,
            daily_quest_id=daily_quest_id,
        )
        reconciled = _reconcile_existing_building(
            context,
            operation_id=operation_id,
            action_kind=BuildingMutationKind.UPGRADE,
            checkpoint=self.checkpoint,
            daily_quest_id=daily_quest_id,
            expected_target=self.target,
        )
        if reconciled is not None:
            return _result_from_reconciliation(reconciled, action_name="Upgrade")
        arrival = None
        if daily_quest_id is DailyQuestId.UPGRADE_BUILDING:
            arrival = context.open_daily_upgrade_go()
        ensure_queue = getattr(context, "ensure_building_queue_available", None)
        if callable(ensure_queue):
            ensure_queue()
        target = self.target
        if target is None:
            if not self.policy.priority:
                raise TaskVerificationError("Building upgrade policy has no target priority.")
            arrived_building = None if arrival is None else home_city_object_id_for_screen(arrival.screen_type)
            if arrival is not None and arrival.screen_type != ScreenType.PNC_HOME_CITY and arrived_building is None:
                raise TaskVerificationError(
                    "Daily Upgrade Building Go did not expose a typed building-owned arrival; "
                    "an exact target is required before mutation."
                )
            if arrived_building is not None and arrived_building.value not in {
                item.value for item in self.policy.priority
            }:
                raise TaskVerificationError("Daily Upgrade Building Go reached a building outside the requested priority.")
            target, source = _select_priority_upgrade_target(
                context,
                policy=self.policy,
                priorities=(
                    (arrived_building,)
                    if arrived_building is not None
                    else tuple(HomeCityObjectId(item.value) for item in self.policy.priority)
                ),
            )
        else:
            arrived_building = None if arrival is None else home_city_object_id_for_screen(arrival.screen_type)
            if arrival is not None and arrived_building is not None and arrived_building != target.building:
                raise TaskVerificationError(
                    "Daily Upgrade Building Go reached an uncorrelated building state."
                )
            source, instance_key = context.open_building_with_identity(
                target.building,
                expected_instance_key=target.instance_key,
            )
            if instance_key != target.instance_key:
                raise TaskVerificationError(
                    "Building upgrade target instance changed before opening its detail screen."
                )
            _validate_target_observation(source, target)
        action = BuildingActionIdentity(
            kind=BuildingMutationKind.UPGRADE,
            operation_id=operation_id,
            target=target,
            daily_quest_id=daily_quest_id,
        )
        checkpoint, receipt, result = context.execute_building(action, self.checkpoint, source)
        return BuildingMutationResult(
            checkpoint=checkpoint,
            action=action,
            receipt=receipt,
            disposition=(
                BuildingMutationDisposition.STARTED
                if result.committed
                else BuildingMutationDisposition.PENDING_CLARIFICATION
            ),
            message=(
                f"Upgrade of '{target.building.value}' started."
                if result.committed
                else _pending_building_message(result, action="Upgrade")
            ),
            retry_permitted=getattr(result, "retry_permitted", False),
        )


def _select_priority_upgrade_target(
    context: WorkflowContext,
    *,
    policy: BuildingUpgradePolicy,
    priorities: tuple[HomeCityObjectId, ...],
) -> tuple[BuildingUpgradeTarget, Observation]:
    """Return the first eligible priority target without mutating skipped candidates."""

    ineligible_reasons: list[str] = []
    for index, building in enumerate(priorities):
        source, instance_key = context.open_building_with_identity(building)
        target = _target_from_observation(
            source,
            building,
            policy,
            instance_key=instance_key,
        )
        reason = _ineligible_upgrade_reason(source, target)
        if reason is None:
            return target, source
        ineligible_reasons.append(f"{building.value}: {reason}")
        if index + 1 < len(priorities):
            context.navigate(ScreenType.PNC_HOME_CITY)
    detail = "; ".join(ineligible_reasons)
    raise TaskVerificationError(
        f"No requested building upgrade is currently eligible ({detail})."
    )


def _ineligible_upgrade_reason(
    observation: Observation,
    target: BuildingUpgradeTarget,
) -> str | None:
    """Classify only safe skip cases; explicit advanced branches remain fail-closed."""

    if building_requirement_is_visible(observation):
        if target.prerequisite_mode.value == "queue" or target.allow_premium_material_purchases:
            return None
        return building_requirement_text(observation) or "unmet prerequisite"
    if observation.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON):
        if target.allow_speedups:
            return None
        return "an upgrade is already active"
    if not observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON):
        return "normal Upgrade is unavailable"
    return None


def _menu_screen(target: BuildingConstructionTarget) -> ScreenType:
    """Return the source menu screen from the canonical source target."""

    from pnc_automation.app.pnc.domain.building_catalog import require_building_construction_source

    return require_building_construction_source(target.building).menu_screen_type


def _target_from_observation(
    observation: Observation,
    building: HomeCityObjectId,
    policy: BuildingUpgradePolicy,
    *,
    instance_key: str,
) -> BuildingUpgradeTarget:
    """Build an upgrade target from a Home identity and detail-level fact."""

    _require_target_detail_ownership(observation, building)
    level_element = observation.get(UiElementId.PNC_BUILDING_LEVEL_LABEL)
    level_text = None if level_element is None else level_element.extracted_text
    if level_text is None:
        raise TaskVerificationError("Building upgrade requires a current level label.")
    try:
        current_level = int(level_text.replace("Lv.", "").replace("LV", "").strip())
    except ValueError as error:
        raise TaskVerificationError("Building level label is not an exact integer.") from error
    return BuildingUpgradeTarget(
        building=building,
        instance_key=instance_key,
        current_level=current_level,
        next_level=current_level + 1,
        prerequisite_mode=policy.prerequisite_mode,
        allow_speedups=policy.allow_speedups,
        allow_premium_material_purchases=policy.allow_premium_material_purchases,
        request_help=policy.request_help,
    )


def _validate_target_observation(observation: Observation, target: BuildingUpgradeTarget) -> None:
    """Require an explicit target to remain the exact observed instance and level."""

    _require_target_detail_ownership(observation, target.building)
    level_element = observation.get(UiElementId.PNC_BUILDING_LEVEL_LABEL)
    level_text = None if level_element is None else level_element.extracted_text
    if level_text is None:
        raise TaskVerificationError("Building upgrade requires a current level label.")
    try:
        current_level = int(level_text.replace("Lv.", "").replace("LV", "").strip())
    except ValueError as error:
        raise TaskVerificationError("Building level label is not an exact integer.") from error
    if current_level != target.current_level:
        raise TaskVerificationError("Building upgrade target no longer matches the observed level.")


def _require_target_detail_ownership(observation: Observation, building: HomeCityObjectId) -> None:
    """Require the typed detail screen to name the exact Home building owner."""

    owner = home_city_object_id_for_screen(observation.screen_type)
    if owner != building:
        raise TaskVerificationError(
            "Building upgrade requires an exact building-owned detail screen; "
            "a level label alone cannot authorize the target."
        )


def _require_operation_id(operation_id: str | None, *, action: str) -> str:
    """Require direct callers to provide the durable identity before any input."""

    if operation_id is None or not operation_id.strip():
        raise PermissionError(
            f"Typed building {action} requires a caller-owned durable operation_id."
        )
    return operation_id.strip()


def _reconcile_existing_building(
    context: WorkflowContext,
    *,
    operation_id: str,
    action_kind: BuildingMutationKind,
    checkpoint: DailyTaskCheckpoint,
    daily_quest_id: DailyQuestId | None = None,
    expected_target: BuildingConstructionTarget | BuildingUpgradeTarget | None = None,
) -> tuple[BuildingActionIdentity, BuildingMutationReceipt | None, JournaledMutationResult] | None:
    """Use the durable operation before any new navigation or precondition acquisition."""

    reconcile = getattr(context, "reconcile_building_operation", None)
    if not callable(reconcile):
        return None
    return reconcile(
        operation_id=operation_id,
        action_kind=action_kind,
        checkpoint=checkpoint,
        daily_quest_id=daily_quest_id,
        expected_target=expected_target,
    )


def _pending_building_message(result: object, *, action: str) -> str:
    """Expose a durable prepared/reconciliation retry instead of implying a replay is safe."""

    if getattr(result, "retry_permitted", False):
        return (
            f"{action} intent is durably prepared but not dispatched; retry after fresh "
            "precondition validation. No input was replayed."
        )
    return f"{action} outcome is unproved; no replay was attempted."


def _result_from_reconciliation(
    reconciled: tuple[BuildingActionIdentity, BuildingMutationReceipt | None, JournaledMutationResult],
    *,
    action_name: str,
) -> BuildingMutationResult:
    """Materialize one workflow result from an existing durable operation."""

    action, receipt, result = reconciled
    return BuildingMutationResult(
        checkpoint=result.checkpoint,
        action=action,
        receipt=receipt,
        disposition=(
            BuildingMutationDisposition.STARTED
            if result.committed
            else BuildingMutationDisposition.PENDING_CLARIFICATION
        ),
        message=(
            f"{action_name} receipt already committed; no input was replayed."
            if result.committed
            else _pending_building_message(result, action=action_name)
        ),
        retry_permitted=result.retry_permitted,
    )


def _resolve_upgrade_operation_id(
    operation_id: str | None,
    *,
    checkpoint: DailyTaskCheckpoint,
    daily_quest_id: DailyQuestId | None,
) -> str:
    """Use a caller id, or derive one only from the durable Daily checkpoint."""

    if operation_id is not None and operation_id.strip():
        return operation_id.strip()
    if daily_quest_id is not DailyQuestId.UPGRADE_BUILDING:
        raise PermissionError(
            "Typed building upgrade requires a caller-owned durable operation_id."
        )
    castle = checkpoint.castle
    return (
        "daily-building-upgrade:"
        f"{checkpoint.game_reset_id}:{checkpoint.account_id}:"
        f"{castle.kingdom}:{castle.castle_name}"
    )
