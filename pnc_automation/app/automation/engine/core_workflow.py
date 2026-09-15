"""Bounded workflow contracts for the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Generic, Literal, Protocol, TypeVar

from pnc_automation.app.automation.daily_maintenance.coordinator import (
    DailyMaintenanceCoordinator, DailyMaintenanceResult, DailyReadOnlySurvey,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationResult
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.navigation_core import require_resource_inventory_surface
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId, DailyQuestRow, DailyTaskCheckpoint, DailyTargetOutcome,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    CurrentCastleMatchStatus,
    resolve_current_castle_match,
)
from pnc_automation.app.pnc.domain.mail import MailboxAvailability, MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


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
        "_mutation_boundary", "_research_node", "_research_queue_observation",
        "_reconciliation_operation_id",
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
        self._research_queue_observation: Observation | None = None
        self._reconciliation_operation_id = reconciliation_operation_id

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

    def open_research_node(self, title: str, category: ResearchCategory) -> Observation:
        """Reacquire one exact supported node before proving its idle detail."""

        self._research_node = None
        try:
            observation = self._runtime.navigation.open_research_node(
                title, category, observe_content=self._observe_research_content,
            )
            self._research_node = title
            return observation
        finally:
            self._sync_from_runtime()

    def scroll_research_tree(self) -> Observation:
        """Scroll one proved Development viewport through the constrained navigator."""

        self._research_node = None
        try:
            return self._runtime.navigation.scroll_research_tree(
                observe_content=self._observe_research_content,
            )
        finally:
            self._sync_from_runtime()

    def close_research_detail(self) -> Observation:
        """Return an unfunded idle detail to its preserved Development grid."""

        self._research_node = None
        try:
            return self._runtime.navigation.close_research_detail(
                observe_content=self._observe_research_content,
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

    def _observe_research_content(self, label: str) -> Observation:
        """Keep research captures fresh; operation owners evaluate their published facts."""

        observation = self._observe_operation_content(label, operation="Research")
        proof = self._research_queue_observation
        if (
            proof is None
            or proof.screen_type != ScreenType.PNC_RESEARCH_QUEUE
            or proof.blocking_popup
            or proof.decision.guard != GuardVerdict.CLEAR
            or proof.research_start_queue_available is not True
            or observation.screen_type != ScreenType.PNC_RESEARCH_TREE
            or observation.blocking_popup
            or observation.decision.guard != GuardVerdict.CLEAR
            or observation.research_start_queue_available is not None
            or not observation.has(UiElementId.PNC_RESEARCH_START_BUTTON)
            or not any(
                evidence.reason == "visual_anchor:research_tree_node_detail"
                for evidence in observation.decision.evidence
            )
            or observation.captured_at <= proof.captured_at
        ):
            return observation
        # Detail OCR is allowed to omit queue status. Carry only the fresh,
        # route-scoped queue proof; a detail's explicit False remains authoritative.
        enriched = replace(observation, research_start_queue_available=True)
        self._last_observation = enriched
        return enriched

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
        if target != ScreenType.PNC_RESEARCH_TREE:
            self._research_queue_observation = None
        self._research_node = None
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
        self._research_queue_observation = None
        self._research_node = None
        observation = self._runtime.navigation.open_building(
            target,
            observe_content=(
                self._observe_research_content
                if target == HomeCityObjectId.INSTITUTE
                else lambda label: self._runtime.observe(label, include_content=True)
            ),
        )
        queue_observation = getattr(self._runtime.navigation, "research_queue_observation", None)
        if (
            target == HomeCityObjectId.INSTITUTE
            and observation.research_start_queue_available is True
            and isinstance(queue_observation, Observation)
        ):
            self._research_queue_observation = queue_observation
        self._last_navigation_count = self._runtime.observation_count
        self._last_observation = observation
        return observation

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
            self.mutation_boundary is None or spec.mutation_capability != self.mutation_boundary.policy.quest_id
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
            self.mutation_boundary.authorize()
        elif reconciling:
            self.mutation_boundary.require_hero_reconciliation(spec.reconciliation_operation_id)
        self.runtime.record({"event": "workflow_started", "workflow": spec.name, "effect": spec.effect.value})
        try:
            if mutating:
                self.mutation_boundary.verify_active_castle(self.runtime)
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
