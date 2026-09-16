"""Bounded workflow contracts for the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Literal, Protocol, TypeVar

from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyMaintenanceCoordinator, DailyMaintenanceResult, DailyReadOnlySurvey,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationResult
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.navigation_core import require_resource_inventory_surface
from pnc_automation.app.automation.tasks.building_workflow_support import (
    build_queue_first_slot_is_idle,
    can_open_build_queue,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyQuestRow, DailyTaskCheckpoint, DailyTargetOutcome,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.trial_challenge import TrialCategory
from pnc_automation.app.pnc.domain.building_details import BuildingDetailPhase
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    require_building_construction_source,
)
from pnc_automation.app.pnc.domain.building_operations import (
    BuildingActionIdentity,
    BuildingConstructionTarget,
    BuildingMutationKind,
    BuildingMutationReceipt,
    BuildingUpgradeTarget,
    observable_building_instance_key,
    observable_construction_slot_key,
)
from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import TreasureIdentity
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.domain.action_requests import (
    KeyEventAction,
    TapAction,
    TapListEntryAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    home_city_scan_step_budget,
    home_city_scan_steps,
)
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.domain.mail import MailboxAvailability, MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


def _resolve_unique_home_building_identity(
    observation: Observation,
    *,
    target: HomeCityObjectId,
    expected_instance_key: str | None = None,
) -> str:
    """Derive one observable Home identity without inventing a hidden game id."""

    if (
        observation.screen_type != ScreenType.PNC_HOME_CITY
        or observation.blocking_popup
        or observation.spatial_surface is None
        or observation.spatial_surface.surface_type != SpatialSurfaceType.HOME_CITY_SURFACE
    ):
        raise RuntimeError("Building identity requires a fresh Home-city spatial surface.")
    candidates = tuple(
        object_
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        if object_.metadata.get("home_city_object_id") == target.value
    )
    if len(candidates) != 1:
        raise RuntimeError("Building upgrade requires one exact Home object instance identity.")
    instance_key = observable_building_instance_key(target, candidates[0])
    if expected_instance_key is not None and instance_key != expected_instance_key:
        raise RuntimeError("Building Home object identity changed before its detail was opened.")
    return instance_key


class WorkflowEffect(StrEnum):
    """Declares the bounded effect class permitted by the core runner."""

    READ_ONLY = "read_only"
    NONSPENDING_STATE_CHANGE = "nonspending_state_change"
    RESOURCE_CHANGING = "resource_changing"


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    """Defines the reviewed lifecycle and effect policy for one core workflow."""

    name: str
    entry_screen: ScreenType
    exit_screen: ScreenType
    effect: WorkflowEffect
    mutation_capability: DailyQuestId | None = None
    mutation_action_kind: BuildingMutationKind | None = None
    reconciliation_operation_id: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed workflow identity, endpoints, or effect declarations."""

        if not self.name.strip():
            raise ValueError("WorkflowSpec.name cannot be empty.")
        if not isinstance(self.entry_screen, ScreenType) or self.entry_screen == ScreenType.UNKNOWN:
            raise ValueError("WorkflowSpec.entry_screen must be a known screen.")
        if not isinstance(self.exit_screen, ScreenType) or self.exit_screen == ScreenType.UNKNOWN:
            raise ValueError("WorkflowSpec.exit_screen must be a known screen.")
        if not isinstance(self.effect, WorkflowEffect):
            raise TypeError("WorkflowSpec.effect must be a WorkflowEffect enum value.")
        if self.mutation_capability is not None:
            if not isinstance(self.mutation_capability, DailyQuestId):
                raise TypeError("WorkflowSpec.mutation_capability must be a DailyQuestId.")
            if self.effect != WorkflowEffect.RESOURCE_CHANGING and self.reconciliation_operation_id is None:
                raise ValueError("A mutation capability requires the RESOURCE_CHANGING effect.")
        if self.mutation_action_kind is not None:
            if not isinstance(self.mutation_action_kind, BuildingMutationKind):
                raise TypeError("WorkflowSpec.mutation_action_kind must be a BuildingMutationKind.")
            if self.effect != WorkflowEffect.RESOURCE_CHANGING:
                raise ValueError("A building mutation action requires the RESOURCE_CHANGING effect.")
        if self.reconciliation_operation_id is not None and (
            not isinstance(self.reconciliation_operation_id, str)
            or not self.reconciliation_operation_id.strip()
            or self.effect != WorkflowEffect.NONSPENDING_STATE_CHANGE
            or self.mutation_capability != DailyQuestId.HERO_HALL
        ):
            raise ValueError("Reconciliation requires one named Hero intent and the non-spending effect.")


T = TypeVar("T")


class CoreWorkflow(Protocol, Generic[T]):
    """A typed workflow that can use only the constrained core context."""

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the workflow lifecycle and effect contract."""

    def execute(self, context: "WorkflowContext") -> T:
        """Runs the workflow body through the constrained context."""


@dataclass(frozen=True, slots=True)
class CoreWorkflowResult(Generic[T]):
    """Reports a typed result only after the reviewed exit screen is confirmed."""

    workflow_name: str
    succeeded: bool
    value: T
    exit_screen: ScreenType
    trace_path: str


class WorkflowContext:
    """Exposes only reviewed navigation and fresh, expected-screen content capture."""

    __slots__ = (
        "_runtime", "_last_navigation_count", "_last_observation", "_effect",
        "_mutation_boundary", "_research_node", "_reconciliation_operation_id",
        "_building_queue_available",
    )

    def __init__(
        self,
        runtime: CoreRuntime,
        *,
        last_observation: Observation,
        effect: WorkflowEffect = WorkflowEffect.READ_ONLY,
        mutation_boundary: CoreMutationBoundary | None = None,
        reconciliation_operation_id: str | None = None,
    ) -> None:
        """Starts a context after the runner has confirmed the workflow entry screen."""

        if not isinstance(effect, WorkflowEffect):
            raise TypeError("WorkflowContext.effect must be a WorkflowEffect.")
        self._runtime = runtime
        self._last_navigation_count = runtime.observation_count
        self._last_observation = last_observation
        self._effect = effect
        self._mutation_boundary = mutation_boundary
        self._research_node: str | None = None
        self._reconciliation_operation_id = reconciliation_operation_id
        self._building_queue_available = False

    def reconcile_hero_hall(self, checkpoint: DailyTaskCheckpoint) -> JournaledMutationResult:
        """Read only the Hero receipt named by this non-spending workflow's contract."""

        if (
            self._effect != WorkflowEffect.NONSPENDING_STATE_CHANGE
            or self._mutation_boundary is None or self._reconciliation_operation_id is None
        ):
            raise PermissionError("Hero reconciliation requires an exact existing-intent scope.")
        try:
            return self._mutation_boundary.reconcile_hero_hall(
                runtime=self._runtime, observe=self._observe_hero_hall,
                daily_survey=self._survey_daily_requirements, checkpoint=checkpoint,
                operation_id=self._reconciliation_operation_id,
            )
        finally:
            self._sync_from_runtime()

    def recruit_hero_hall(
        self, checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Execute one authorized free-single increment, or reconcile its existing intent."""

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Hero Hall requires an exact resource-changing boundary.")
        try:
            return self._mutation_boundary.recruit_hero_hall(
                runtime=self._runtime, observe=self._observe_hero_hall,
                daily_survey=self._survey_daily_requirements, checkpoint=checkpoint,
            )
        finally:
            self._sync_from_runtime()

    def _observe_hero_hall(self, label: str) -> Observation:
        """Capture through the canonical recovery owner without a workflow-local bypass."""

        return self._observe_operation_content(label, operation="Hero Hall")

    def acknowledge_hero_recruit_result(self) -> Observation:
        """Use fresh result content and the shared phase-owned acknowledgment."""

        before = self._observe_hero_hall("hero_result_acknowledgment_source")
        try:
            return self._runtime.navigation.acknowledge_hero_recruit_result(
                before, observe_content=self._observe_hero_hall,
            )
        finally:
            self._sync_from_runtime()

    def use_resource_item(
        self, checkpoint: DailyTaskCheckpoint, *, allow_empty_skip: bool = False,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Delegate one existing pack use, full scan and Daily proof to its exact boundary."""

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Resource Item requires an exact resource-changing boundary.")
        try:
            return self._mutation_boundary.use_resource_item(
                runtime=self._runtime, observe=self._observe_resource_inventory,
                open_inventory=self._open_resource_inventory,
                daily_survey=self._survey_daily_requirements, checkpoint=checkpoint,
                allow_empty_skip=allow_empty_skip,
            )
        finally:
            self._sync_from_runtime()

    def _open_resource_inventory(self) -> None:
        """Use the reviewed Bag route; an unselected tab supplies no entry authority."""

        self.navigate(ScreenType.PNC_BAG)
        self.select_bag_tab(BagTab.RESOURCE)
        self._observe_resource_inventory("resource_inventory_entry")

    def _survey_daily_requirements(self) -> DailyReadOnlySurvey:
        """Use one canonical full-survey composition for mutation completion receipts."""

        # The Daily workflow adapter also imports this context; defer that one import.
        from pnc_automation.app.automation.daily_maintenance.core_daily_maintenance import _CoreDailyQuestSession

        if self._mutation_boundary is None:
            raise PermissionError("Mutation receipt survey requires its existing boundary.")
        return DailyMaintenanceCoordinator.for_read_only(
            session=_CoreDailyQuestSession(self), journal_store=self._mutation_boundary.journal_store,
            catalog=DailyQuestCatalog(),
        ).survey_read_only()

    def _observe_resource_inventory(self, label: str) -> Observation:
        """Require current published Resource-tab facts after canonical recovery."""

        observation = self._observe_operation_content(
            label, operation="Resource Item", ready=True,
        )
        require_resource_inventory_surface(observation)
        return observation

    def open_research_category(self, category: ResearchCategory) -> Observation:
        """Open one measured category and invalidate any mutation priming."""

        self._research_node = None
        try:
            return self._runtime.navigation.open_research_category(
                category, observe_content=self._observe_research_content,
            )
        finally:
            self._sync_from_runtime()

    def open_research_node(self, title: str, category: ResearchCategory) -> Observation:
        """Reacquire one exact supported node before proving its idle detail."""

        self._research_node = None
        try:
            observation = self._runtime.navigation.open_research_node(
                title, category, observe_content=self._observe_research_content,
            )
            start = observation.get(UiElementId.PNC_RESEARCH_START_BUTTON)
            if (
                category == ResearchCategory.DEVELOPMENT and start is not None
                and start.source_kind == VisibleElementSourceKind.TEMPLATE
            ):
                self._research_node = title
            return observation
        finally:
            self._sync_from_runtime()

    def scroll_research_tree(self) -> Observation:
        """Swipe the proved category grid once and invalidate node priming."""

        self._research_node = None
        try:
            return self._runtime.navigation.scroll_research_tree(
                observe_content=self._observe_research_content,
            )
        finally:
            self._sync_from_runtime()

    def close_research_detail(self, category: ResearchCategory | None = None) -> Observation:
        """Back out of the proved detail and invalidate node priming."""

        self._research_node = None
        try:
            return self._runtime.navigation.close_research_detail(
                observe_content=self._observe_research_content, category=category,
            )
        finally:
            self._sync_from_runtime()

    def start_research(self, checkpoint: DailyTaskCheckpoint) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Use the canonical one-research boundary only after this context selected its node."""

        if (
            self._effect != WorkflowEffect.RESOURCE_CHANGING
            or self._mutation_boundary is None or self._research_node is None
        ):
            raise PermissionError("Research requires exact authority and a freshly selected node.")
        title = self._research_node
        self._research_node = None
        try:
            return self._mutation_boundary.start_research(
                runtime=self._runtime, observe=self._observe_research_content,
                node_title=title, checkpoint=checkpoint,
            )
        finally:
            self._sync_from_runtime()

    def open_trial_stats(self, category: TrialCategory) -> Observation:
        """Open the proved Gear Stats entry and return its fresh detail observation."""

        try:
            return self._runtime.navigation.open_trial_stats(
                category, observe_content=self._observe_trial_content,
            )
        finally:
            self._sync_from_runtime()

    def _observe_trial_content(self, label: str) -> Observation:
        """Keep Trial captures fresh; operation owners evaluate their published facts."""

        return self._observe_operation_content(label, operation="Trial")

    def _observe_research_content(self, label: str) -> Observation:
        """Keep research captures fresh; operation owners evaluate their published facts."""

        return self._observe_operation_content(label, operation="Research")

    def run_daily_maintenance(self, checkpoint: DailyTaskCheckpoint) -> DailyMaintenanceResult:
        """Run the whole claim sweep under the canonical target and journal authority."""

        from pnc_automation.app.automation.daily_maintenance.core_daily_maintenance import (
            _CoreDailyClaimExecutor, _CoreDailyQuestSession,
        )

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Daily maintenance requires an exact resource-changing boundary.")
        return self._mutation_boundary.run_daily_maintenance(
            session=_CoreDailyQuestSession(self),
            claim_executor=_CoreDailyClaimExecutor(self),
            checkpoint=checkpoint,
        )

    def claim_daily_reward(
        self, row: DailyQuestRow, checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Claim one exact row through the authorized canonical journal boundary."""

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Daily claims require an authorized resource-changing workflow.")
        return self._mutation_boundary.claim(
            runtime=self._runtime, observe=self._observe_daily_claim,
            row=row, checkpoint=checkpoint,
        )

    def _observe_daily_claim(self, label: str) -> Observation:
        """Require fresh, positively unblocked Daily evidence on both sides of a claim."""

        observation = self._observe_operation_content(label, operation="Daily claim")
        if (
            observation.screen_type != ScreenType.PNC_QUEST_DAILY
            or observation.decision is None
            or observation.decision.effective_screen != ScreenType.PNC_QUEST_DAILY
            or observation.decision.guard != GuardVerdict.CLEAR
        ):
            raise RuntimeError("Daily claim requires a positively unblocked Daily screen.")
        return observation

    def scroll_daily_quest(self, *, adjusted: bool = False) -> Observation:
        """Scroll a fresh Daily viewport without exposing a general swipe operation."""

        try:
            return self._runtime.navigation.scroll_daily_quest(
                adjusted=adjusted, observe_content=self._observe_daily_claim,
            )
        finally:
            self._sync_from_runtime()

    def navigate(self, target: ScreenType) -> Observation:
        """Navigates through the reviewed graph and records the fresh completion observation."""

        if not isinstance(target, ScreenType) or target == ScreenType.UNKNOWN:
            raise ValueError("Workflow navigation requires a known screen target.")
        self._research_node = None
        detail = None if self._last_observation is None else self._last_observation.building_detail
        if (
            detail is not None
            and detail.building_id is HomeCityObjectId.INSTITUTE
            and detail.phase is BuildingDetailPhase.UPGRADE
        ):
            self.close_building_upgrade_detail(HomeCityObjectId.INSTITUTE)
        observation = self._runtime.navigation.navigate(target)
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        """Captures content only after navigation and requires the expected typed screen."""

        if not isinstance(expected_screen, ScreenType) or expected_screen == ScreenType.UNKNOWN:
            raise ValueError("Content observation requires a known expected screen.")
        observation = self._runtime.observe("workflow_content", include_content=True)
        if self._runtime.observation_count <= self._last_navigation_count:
            raise RuntimeError("Workflow content observation was not captured after navigation.")
        if self._last_observation is not None and observation.captured_at <= self._last_observation.captured_at:
            raise RuntimeError("Workflow content observation was stale relative to the last workflow observation.")
        if observation.blocking_popup:
            raise RuntimeError("Workflow content observation encountered a blocking popup.")
        if observation.screen_type != expected_screen:
            raise RuntimeError(
                f"Workflow content reached unexpected screen '{observation.screen_type.name}'."
            )
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def open_building(self, target: HomeCityObjectId) -> Observation:
        """Opens one exact building through NavigationCore and records its fresh endpoint."""

        if not isinstance(target, HomeCityObjectId):
            raise ValueError("Building navigation requires a known HomeCityObjectId target.")
        self._research_node = None
        observation = self._runtime.navigation.open_building(
            target,
            observe_content=lambda label: self._runtime.observe(label, include_content=True),
        )
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def open_building_with_identity(
        self,
        target: HomeCityObjectId,
        *,
        expected_instance_key: str | None = None,
    ) -> tuple[Observation, str]:
        """Open one building and bind its identity to the exact dispatch frame."""

        if not isinstance(target, HomeCityObjectId):
            raise ValueError("Building navigation requires a known HomeCityObjectId target.")
        acquired: list[str] = []

        def remember(object_: object) -> None:
            from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject

            if not isinstance(object_, DetectedSpatialObject):
                raise TypeError("Building navigation returned an invalid spatial target.")
            instance_key = observable_building_instance_key(target, object_)
            if expected_instance_key is not None and instance_key != expected_instance_key:
                raise RuntimeError(
                    "Building Home object identity changed before its detail was opened."
                )
            acquired.append(instance_key)

        self._research_node = None
        observation = self._runtime.navigation.open_building(
            target,
            observe_content=lambda label: self._runtime.observe(label, include_content=True),
            on_target_acquired=remember,
        )
        if len(acquired) != 1:
            raise RuntimeError("Building navigation did not publish one exact dispatch identity.")
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation, acquired[0]

    def open_building_upgrade_detail(self, target: HomeCityObjectId) -> Observation:
        """Open the internal upgrade detail of the currently displayed building panel.

        Must follow a fresh same-building primary/detail observation (for
        example ``open_building_with_identity``); the exact Home instance proof
        is carried by the uninterrupted observation chain, since detail panels
        do not re-identify the spatial instance. Returns the fresh typed
        UPGRADE detail observation.
        """

        if not isinstance(target, HomeCityObjectId):
            raise ValueError("Upgrade detail navigation requires a known HomeCityObjectId target.")
        self._research_node = None
        observation = self._runtime.navigation.open_building_upgrade_detail(
            target,
            observe_content=lambda label: self._runtime.observe(label, include_content=True),
        )
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def open_construction_slot(self, target: object) -> tuple[Observation, str]:
        """Acquire one exact Home empty slot, then return its typed construction menu."""

        from pnc_automation.app.pnc.domain.building_operations import BuildingConstructionTarget

        if not isinstance(target, BuildingConstructionTarget):
            raise TypeError("Construction slot acquisition requires a BuildingConstructionTarget.")
        source = require_building_construction_source(target.building)
        current = self._ensure_home_city_for_building_flow("building_construct_home")
        query = SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_EMPTY_SLOT,
            metadata_key="home_city_object_id",
            metadata_value=source.slot_id.value,
        )
        executor = self._runtime.runtime.require_observed_action_executor(
            "Construction slot acquisition requires the canonical observed action executor."
        )
        scan_steps = home_city_scan_steps()
        scan_budget = home_city_scan_step_budget()
        for step_index in range(scan_budget + 1):
            if (
                current.screen_type != ScreenType.PNC_HOME_CITY
                or current.blocking_popup
                or current.spatial_surface is None
                or current.spatial_surface.surface_type != SpatialSurfaceType.HOME_CITY_SURFACE
            ):
                raise RuntimeError("Construction slot acquisition requires a fresh Home-city spatial surface.")
            candidates = tuple(
                object_
                for object_ in current.spatial_objects(SpatialObjectKind.HOME_EMPTY_SLOT)
                if object_.matches(query)
            )
            if len(candidates) > 1:
                raise RuntimeError("The exact construction slot is ambiguous; no tap was sent.")
            if candidates:
                slot_instance_key = observable_construction_slot_key(
                    target.slot_id,
                    candidates[0],
                )
                if (
                    target.slot_instance_key is not None
                    and target.slot_instance_key != slot_instance_key
                ):
                    raise RuntimeError(
                        "The exact construction slot identity changed before its menu opened."
                    )
                execution = executor.execute_actions(
                    (
                        TapSpatialObjectAction(
                            query=query,
                            reason="building_construct_exact_home_slot",
                            use_action_point=True,
                        ),
                    ),
                    current,
                    observe=lambda label, request=None: self._runtime.observe(
                        f"building_construct_slot_{step_index}_{label}", include_content=True,
                    ),
                )
                current = execution.observation
                if current.screen_type != source.menu_screen_type:
                    raise RuntimeError("The exact construction slot did not open its canonical building menu.")
                self._last_navigation_count = self._runtime.observation_count
                self._last_observation = current
                return current, slot_instance_key
            if step_index == scan_budget:
                break
            execution = executor.execute_actions(
                (scan_steps[step_index % len(scan_steps)],),
                current,
                observe=lambda label, request=None: self._runtime.observe(
                    f"building_construct_slot_{step_index}_{label}", include_content=True,
                ),
            )
            current = execution.observation
        raise RuntimeError("Construction slot acquisition exceeded the bounded Home-city search budget.")

    def resolve_home_building_instance(
        self,
        target: HomeCityObjectId,
        *,
        expected_instance_key: str | None = None,
    ) -> str:
        """Carry the exact Home object identity across the detail navigation boundary."""

        if not isinstance(target, HomeCityObjectId):
            raise ValueError("Building identity requires a known HomeCityObjectId target.")
        current = self._ensure_home_city_for_building_flow("building_upgrade_home")
        return _resolve_unique_home_building_identity(
            current,
            target=target,
            expected_instance_key=expected_instance_key,
        )

    def open_daily_upgrade_go(self) -> Observation:
        """Consume only the existing Upgrade Building Daily row's visual Go action."""

        self.navigate(ScreenType.PNC_QUEST_DAILY)
        daily = self.observe_content(expected_screen=ScreenType.PNC_QUEST_DAILY)
        rows = tuple(
            entry
            for entry in daily.entries(ListEntryKind.DAILY_QUEST)
            if entry.metadata.get("quest_id") == DailyQuestId.UPGRADE_BUILDING.value
            and entry.metadata.get("row_state") == "go"
            and entry.row_status == RowRecognitionStatus.COMPLETE
            and entry.action_point is not None
            and entry.action_bounds is not None
        )
        if len(rows) != 1 or not daily.has(UiElementId.PNC_QUEST_GO_BUTTON):
            raise RuntimeError("Daily Upgrade Building Go row is missing or ambiguous; no input was sent.")
        executor = self._runtime.runtime.require_observed_action_executor(
            "Daily Upgrade Building Go requires the canonical observed action executor."
        )
        result = executor.execute_action(
            TapListEntryAction(
                reason="daily_upgrade_building_go",
                entry_kind=ListEntryKind.DAILY_QUEST,
                metadata_key="quest_id",
                metadata_value=DailyQuestId.UPGRADE_BUILDING.value,
                use_action_point=True,
            ),
            daily,
            observe=lambda label: self._runtime.observe(label, include_content=True),
        )
        if not result:
            raise RuntimeError("Daily Upgrade Building Go was not consumed; no mutation was attempted.")
        arrived = self._runtime.observe("daily_upgrade_building_arrival", include_content=True)
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = arrived
        if arrived.blocking_popup or arrived.screen_type in {
            ScreenType.PNC_QUEST_DAILY,
            ScreenType.UNKNOWN,
        }:
            raise RuntimeError("Daily Upgrade Building Go did not reach a usable building state.")
        return arrived

    def ensure_building_queue_available(self) -> Observation:
        """Prove the current Home build control can open the queue before an upgrade."""

        current = self._ensure_home_city_for_building_flow("building_upgrade_queue_home")
        if not can_open_build_queue(current):
            raise RuntimeError(
                "Building upgrade requires a fresh Home build control that positively opens the queue."
            )
        executor = self._runtime.runtime.require_observed_action_executor(
            "Building queue availability requires the canonical observed action executor."
        )
        opened = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    reason="building_upgrade_open_queue_for_availability",
                    observe_after=True,
                    follow_up_request=ObservationRequest.build_queue_follow_up(),
                ),
            ),
            current,
            observe=lambda label, request=None: self._runtime.observe(
                f"building_upgrade_queue_{label}", include_content=True,
            ),
        ).observation
        if (
            opened.screen_type != ScreenType.PNC_BUILD_QUEUE
            or opened.blocking_popup
            or not build_queue_first_slot_is_idle(opened)
        ):
            raise RuntimeError(
                "Building queue availability was not positively observed: "
                "the first queue slot is not proven idle."
            )
        close = opened.get(UiElementId.PNC_POPUP_CLOSE_BUTTON)
        if close is None or close.source_kind is not VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Build Queue has no measured close control; no return action sent.")
        returned = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON,
                    reason="building_upgrade_leave_queue_after_availability",
                    observe_after=True,
                    follow_up_request=ObservationRequest.build_queue_follow_up(),
                ),
            ),
            opened,
            observe=lambda label, request=None: self._runtime.observe(
                f"building_upgrade_queue_{label}", include_content=True,
            ),
        ).observation
        if returned.screen_type != ScreenType.PNC_HOME_CITY or returned.blocking_popup:
            raise RuntimeError("Building queue availability did not return to an unblocked Home city.")
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = returned
        self._building_queue_available = True
        return opened

    def close_building_upgrade_detail(self, target: HomeCityObjectId) -> Observation:
        """Close the qualified internal upgrade panel before graph navigation."""
        observation = self._runtime.navigation.close_building_upgrade_detail(
            target,
            observe_content=lambda label: self._runtime.observe(label, include_content=True),
        )
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def reconcile_building_operation(
        self,
        *,
        operation_id: str,
        action_kind: BuildingMutationKind,
        checkpoint: DailyTaskCheckpoint,
        daily_quest_id: DailyQuestId | None = None,
        expected_target: BuildingConstructionTarget | BuildingUpgradeTarget | None = None,
    ) -> tuple[BuildingActionIdentity, BuildingMutationReceipt | None, JournaledMutationResult] | None:
        """Reconcile a named durable building operation before reacquiring UI preconditions."""

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Building reconciliation requires an exact resource-changing boundary.")
        try:
            return self._mutation_boundary.reconcile_building_operation(
                runtime=self._runtime,
                observe=lambda label: self._observe_operation_content(label, operation="Building"),
                operation_id=operation_id,
                action_kind=action_kind,
                checkpoint=checkpoint,
                daily_quest_id=daily_quest_id,
                expected_target=expected_target,
            )
        finally:
            self._sync_from_runtime()

    def _ensure_home_city_for_building_flow(self, label: str) -> Observation:
        """Return a fresh Home frame for a target identity acquisition."""

        if self._last_observation is None or self._last_observation.screen_type != ScreenType.PNC_HOME_CITY:
            self.navigate(ScreenType.PNC_HOME_CITY)
        current = self._runtime.observe(label, include_content=True)
        if current.screen_type != ScreenType.PNC_HOME_CITY or current.blocking_popup:
            raise RuntimeError("Building target acquisition requires a fresh unblocked Home-city observation.")
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = current
        return current

    def execute_building(
        self,
        identity: BuildingActionIdentity,
        checkpoint: DailyTaskCheckpoint,
        source: Observation,
    ) -> tuple[DailyTaskCheckpoint, BuildingMutationReceipt | None, JournaledMutationResult]:
        """Execute one exact building action through the shared journal boundary."""

        if self._effect != WorkflowEffect.RESOURCE_CHANGING or self._mutation_boundary is None:
            raise PermissionError("Building mutations require an exact resource-changing boundary.")
        try:
            return self._mutation_boundary.execute_building(
                runtime=self._runtime,
                observe=lambda label: self._observe_operation_content(label, operation="Building"),
                identity=identity,
                checkpoint=checkpoint,
                source=source,
                queue_available=getattr(self, "_building_queue_available", False),
            )
        finally:
            self._sync_from_runtime()

    def open_mailbox(self, mailbox: MailboxType) -> MailboxAvailability:
        """Inspect and, when available, open one reviewed mail category."""

        if not isinstance(mailbox, MailboxType):
            raise ValueError("Mailbox navigation requires a MailboxType value.")
        try:
            return self._runtime.navigation.open_mailbox(
                mailbox,
                observe_content=self._observe_mail_content,
            )
        finally:
            self._sync_from_runtime()

    def open_mail_thread(self, row_key: str) -> Observation:
        """Open one exact observed mailbox thread row by its canonical key."""

        try:
            return self._runtime.navigation.open_mail_thread(
                row_key,
                observe_content=self._observe_mail_content,
            )
        finally:
            self._sync_from_runtime()

    def scroll_mailbox(self) -> Observation:
        """Scroll one observed mailbox list once and prove a fresh list frame."""

        try:
            return self._runtime.navigation.scroll_mailbox(observe_content=self._observe_mail_content)
        finally:
            self._sync_from_runtime()

    def scroll_castle_roster(self, direction: Literal["up", "down"]) -> Observation:
        """Scroll one castle-roster window through the reviewed fresh-content boundary."""

        if direction not in {"up", "down"}:
            raise ValueError("Castle-roster scrolling requires direction 'up' or 'down'.")
        try:
            return self._runtime.navigation.scroll_castle_roster(
                direction,
                observe_content=self._observe_castle_roster_content,
            )
        finally:
            self._sync_from_runtime()

    def select_castle(self, target: CastleIdentity) -> Observation:
        """Select one exact castle through the observed Manage Characters roster."""

        if self._effect != WorkflowEffect.NONSPENDING_STATE_CHANGE:
            raise PermissionError("Selecting a castle requires the NONSPENDING_STATE_CHANGE workflow effect.")
        if not isinstance(target, CastleIdentity):
            raise ValueError("Castle selection requires a CastleIdentity value.")
        try:
            return self._runtime.navigation.select_castle(
                target,
                observe_content=self._observe_castle_selection_content,
            )
        finally:
            self._sync_from_runtime()

    def verify_active_castle_identity(self, target: CastleIdentity) -> CastleIdentity:
        """Revalidate one selected castle through the canonical exact identity preflight."""

        if not isinstance(target, CastleIdentity):
            raise ValueError("Castle identity verification requires a CastleIdentity value.")
        active_castle = self._runtime.preflight_active_castle_identity()
        match = resolve_current_castle_match(
            current_castle=active_castle,
            evidence_kind=CurrentCastleEvidenceKind.EXACT,
            target=target,
            roster=None,
        )
        if match.status != CurrentCastleMatchStatus.MATCH:
            raise RuntimeError("Active castle identity did not exactly match the requested castle target.")
        self._sync_from_runtime()
        return active_castle

    def select_bag_tab(self, tab: BagTab) -> Observation:
        """Select one typed Bag subtab and require fresh content confirming it."""

        if not isinstance(tab, BagTab):
            raise ValueError("Bag tab selection requires a BagTab value.")
        try:
            return self._runtime.navigation.select_bag_tab(
                tab,
                observe_content=self._observe_bag_content,
            )
        finally:
            self._sync_from_runtime()

    def open_bag_chest_preview(self, identity: TreasureIdentity) -> Observation:
        """Open one qualified Treasure magnifier and return its fresh preview observation."""

        if not isinstance(identity, TreasureIdentity):
            raise ValueError("Bag chest preview requires a TreasureIdentity.")
        try:
            return self._runtime.navigation.open_bag_chest_preview(
                identity,
                observe_content=self._observe_bag_content,
            )
        finally:
            self._sync_from_runtime()

    def _observe_bag_content(self, label: str) -> Observation:
        """Capture fresh Bag content for one constrained subtab operation."""

        return self._observe_operation_content(label, operation="Bag")

    def select_chat_channel(self, channel: ChatChannel) -> Observation:
        """Select one typed chat channel and require fresh content confirming it."""

        if not isinstance(channel, ChatChannel):
            raise ValueError("Chat channel selection requires a ChatChannel value.")
        try:
            return self._runtime.navigation.select_chat_channel(
                channel,
                observe_content=self._observe_chat_content,
            )
        finally:
            self._sync_from_runtime()

    def send_chat_message(
        self,
        channel: ChatChannel,
        message: str,
        active_castle: CastleIdentity,
    ) -> Observation:
        """Send one chat message only for the reviewed non-spending effect."""

        if self._effect != WorkflowEffect.NONSPENDING_STATE_CHANGE:
            raise PermissionError("Sending chat requires the NONSPENDING_STATE_CHANGE workflow effect.")
        try:
            return self._runtime.navigation.send_chat_message(
                channel,
                message,
                active_castle,
                observe_content=self._observe_chat_content,
            )
        finally:
            self._sync_from_runtime()

    def _observe_mail_content(self, label: str) -> Observation:
        """Capture fresh mail content for one constrained operation."""

        return self._observe_operation_content(label, operation="Mail")

    def _observe_chat_content(self, label: str) -> Observation:
        """Capture fresh chat content for one constrained channel operation."""

        return self._observe_operation_content(label, operation="Chat")

    def _observe_castle_roster_content(self, label: str) -> Observation:
        """Capture fresh roster content for one constrained scroll operation."""

        return self._observe_operation_content(label, operation="Castle roster")

    def _observe_castle_selection_content(self, label: str) -> Observation:
        """Capture fresh Manage Characters content for one selection operation."""

        return self._observe_operation_content(label, operation="Castle selection")

    def _observe_operation_content(
        self, label: str, *, operation: str, ready: bool = False,
    ) -> Observation:
        """Capture fresh content while preserving shared workflow freshness checks."""

        observer = self._runtime.observe_ready if ready else self._runtime.observe
        observation = observer(label, include_content=True)
        if self._runtime.observation_count <= self._last_navigation_count:
            raise RuntimeError(f"{operation} operation content was not captured after the previous workflow observation.")
        if self._last_observation is not None and observation.captured_at <= self._last_observation.captured_at:
            raise RuntimeError(f"{operation} operation content was stale relative to the previous workflow observation.")
        if observation.blocking_popup:
            raise RuntimeError(f"{operation} operation content encountered a blocking popup.")
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

    def _sync_from_runtime(self) -> None:
        """Keep freshness bookkeeping aligned after core-owned completion polling."""

        if self._runtime.last_observation is not None:
            self._last_navigation_count = self._runtime.observation_count
            self._last_observation = self._runtime.last_observation


@dataclass(slots=True)
class CoreWorkflowRunner(Generic[T]):
    """Owns entry, execution, and exit without replaying failed or ambiguous actions."""

    runtime: CoreRuntime
    mutation_boundary: CoreMutationBoundary | None = None

    def run(self, workflow: CoreWorkflow[T]) -> CoreWorkflowResult[T]:
        """Run a bounded workflow, requiring exact authority for supported mutations."""

        spec = workflow.spec
        if not isinstance(spec, WorkflowSpec):
            raise TypeError("Core workflows must expose a validated WorkflowSpec.")
        mutating = spec.effect == WorkflowEffect.RESOURCE_CHANGING
        reconciling = spec.reconciliation_operation_id is not None
        scoped = mutating or reconciling
        if scoped and (
            self.mutation_boundary is None
            or not self.mutation_boundary.supports_mutation(
                capability=spec.mutation_capability,
                action_kind=spec.mutation_action_kind,
            )
        ):
            self.runtime.record(
                {
                    "event": "workflow_rejected",
                    "workflow": spec.name,
                    "effect": spec.effect.value if isinstance(spec.effect, WorkflowEffect) else "invalid",
                }
            )
            raise PermissionError(
                "The resource-changing workflow has no supported exact mutation boundary."
            )
        if mutating:
            self.mutation_boundary.authorize(
                capability=spec.mutation_capability,
                action_kind=spec.mutation_action_kind,
            )
        elif reconciling:
            self.mutation_boundary.require_hero_reconciliation(spec.reconciliation_operation_id)
        self.runtime.record({"event": "workflow_started", "workflow": spec.name, "effect": spec.effect.value})
        try:
            if mutating:
                self.mutation_boundary.verify_active_castle(
                    self.runtime,
                    capability=spec.mutation_capability,
                    action_kind=spec.mutation_action_kind,
                )
            elif reconciling:
                self.mutation_boundary.verify_hero_reconciliation_target(
                    self.runtime, spec.reconciliation_operation_id,
                )
            entry = self.runtime.navigation.navigate(spec.entry_screen)
            context = WorkflowContext(
                self.runtime, last_observation=entry, effect=spec.effect,
                mutation_boundary=self.mutation_boundary if scoped else None,
                reconciliation_operation_id=spec.reconciliation_operation_id,
            )
            value = workflow.execute(context)
            exit_observation = self.runtime.navigation.navigate(spec.exit_screen)
            result = CoreWorkflowResult(
                workflow_name=spec.name,
                succeeded=True,
                value=value,
                exit_screen=exit_observation.screen_type,
                trace_path=str(self.runtime.trace_path),
            )
            self.runtime.record(
                {
                    "event": "workflow_succeeded",
                    "workflow": spec.name,
                    "screen": exit_observation.screen_type.name,
                }
            )
            return result
        except Exception as error:
            self.runtime.record(
                {
                    "event": "workflow_failed",
                    "workflow": spec.name,
                    "error_type": type(error).__name__,
                    **_last_safe_metadata(self.runtime.last_observation),
                }
            )
            raise

    def recover_to_home(self) -> Observation:
        """Explicitly returns Home through the reviewed graph, without guessing or replay."""

        return self.runtime.navigation.navigate(ScreenType.PNC_HOME_CITY)


def _last_safe_metadata(observation: Observation | None) -> dict[str, object]:
    """Returns screen and artifact metadata without exception text or identity values."""

    if observation is None:
        return {}
    return {
        "screen": observation.screen_type.name,
        "artifact": None if observation.artifact_path is None else str(observation.artifact_path),
    }
