"""Typed Development research workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.automation.engine.task import choose_priority_entry
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResearchPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import TaskVerificationError


_MAX_DEVELOPMENT_RESEARCH_VIEWPORTS = 4
_MAX_DEVELOPMENT_DETAIL_INSPECTIONS = 8


class ResearchDisposition(StrEnum):
    """Describes the bounded outcome of one Development research attempt."""

    STARTED = "started"
    NO_VISIBLE_SUPPORTED_NODE = "no_visible_supported_node"
    PENDING_CLARIFICATION = "pending_clarification"
    FAILED = "failed"


def prepare_research_workflow(
    *, policy: ResearchPolicy, mutation_boundary: CoreMutationBoundary | None,
) -> ResearchWorkflow:
    """Require the existing exact Research scope and current journal before connection."""

    if not isinstance(mutation_boundary, CoreMutationBoundary):
        raise PermissionError("Research callers require an explicit CoreMutationBoundary.")
    if mutation_boundary.policy.quest_id != DailyQuestId.UPGRADE_RESEARCH:
        raise PermissionError("Research caller requires the exact one-Start research capability.")
    mutation_boundary.authorize()
    return ResearchWorkflow(policy=policy, checkpoint=mutation_boundary.load_checkpoint())


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Reports the durable checkpoint and observed outcome of one research attempt."""

    checkpoint: DailyTaskCheckpoint
    outcome: DailyTargetOutcome
    disposition: ResearchDisposition
    category: ResearchCategory | None = None
    node_title: str | None = None

    def __post_init__(self) -> None:
        """Keep result identity aligned with the research capability and disposition."""

        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("ResearchResult.checkpoint must be a DailyTaskCheckpoint.")
        if not isinstance(self.outcome, DailyTargetOutcome):
            raise TypeError("ResearchResult.outcome must be a DailyTargetOutcome.")
        if self.outcome.quest_id != DailyQuestId.UPGRADE_RESEARCH:
            raise ValueError("ResearchResult.outcome must identify UPGRADE_RESEARCH.")
        if not isinstance(self.disposition, ResearchDisposition):
            raise TypeError("ResearchResult.disposition must be a ResearchDisposition.")
        if self.category is not None and not isinstance(self.category, ResearchCategory):
            raise TypeError("ResearchResult.category must be a ResearchCategory or None.")
        if self.node_title is not None and not self.node_title.strip():
            raise ValueError("ResearchResult.node_title cannot be blank.")
        if self.disposition == ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE:
            if self.category is not None or self.node_title is not None:
                raise ValueError("A no-visible research result cannot identify a node.")
            if self.outcome.status != DailyTargetOutcomeStatus.PENDING_CLARIFICATION:
                raise ValueError("A no-visible research result must remain pending clarification.")
        elif self.category is None or self.node_title is None:
            raise ValueError("A targeted research result must identify its category and node title.")


@dataclass(frozen=True, slots=True)
class ResearchWorkflow(CoreWorkflow[ResearchResult]):
    """Starts one observed Development research node through the exact mutation boundary."""

    policy: ResearchPolicy
    checkpoint: DailyTaskCheckpoint

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="research",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
        mutation_capability=DailyQuestId.UPGRADE_RESEARCH,
    )

    def __post_init__(self) -> None:
        """Reject unsupported research policies before any navigation or mutation."""

        if not isinstance(self.policy, ResearchPolicy):
            raise TypeError("ResearchWorkflow.policy must be a ResearchPolicy.")
        if self.policy.priority != (ResearchCategory.DEVELOPMENT,):
            raise ValueError("ResearchWorkflow requires the exact Development-only policy.")
        if not isinstance(self.checkpoint, DailyTaskCheckpoint):
            raise TypeError("ResearchWorkflow.checkpoint must be a DailyTaskCheckpoint.")

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the resource-changing Home-to-Home research contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> ResearchResult:
        """Select one observed Development row, then delegate authorized Start exactly once."""

        context.open_building(HomeCityObjectId.INSTITUTE)
        context.navigate(ScreenType.PNC_RESEARCH_TREE)
        tree = context.observe_content(expected_screen=ScreenType.PNC_RESEARCH_TREE)
        target = None
        inspected_titles: set[str] = set()
        last_unfunded_title: str | None = None
        seen_viewports: set[tuple[tuple[object, ...], ...]] = set()
        for viewport_index in range(_MAX_DEVELOPMENT_RESEARCH_VIEWPORTS):
            signature = _development_viewport_signature(tree)
            if signature in seen_viewports:
                break
            seen_viewports.add(signature)
            while len(inspected_titles) < _MAX_DEVELOPMENT_DETAIL_INSPECTIONS:
                candidate = _select_development_node(
                    tree,
                    self.policy,
                    excluded_titles=frozenset(inspected_titles),
                )
                if candidate is None:
                    break
                title = candidate.title_text
                if title is None or not title.strip():
                    raise TaskVerificationError(
                        "Development research node has no stable title; no mutation was attempted."
                    )
                detail = context.open_research_node(
                    title=title,
                    category=ResearchCategory.DEVELOPMENT,
                )
                if (
                    detail.research_start_resources_sufficient is True
                    and detail.research_start_queue_available is True
                ):
                    target = candidate
                    break
                inspected_titles.add(title)
                last_unfunded_title = title
                tree = context.close_research_detail()
            if target is not None or len(inspected_titles) >= _MAX_DEVELOPMENT_DETAIL_INSPECTIONS:
                break
            if viewport_index + 1 < _MAX_DEVELOPMENT_RESEARCH_VIEWPORTS:
                tree = context.scroll_research_tree()
        if target is None:
            if last_unfunded_title is not None:
                return _unfunded_supported_node(self.checkpoint, last_unfunded_title)
            return _no_visible_supported_node(self.checkpoint)

        title = target.title_text
        if title is None or not title.strip():
            raise TaskVerificationError(
                "Development research node has no stable title; no mutation was attempted."
            )
        checkpoint, outcome = context.start_research(self.checkpoint)
        if outcome.quest_id != DailyQuestId.UPGRADE_RESEARCH:
            raise ValueError("WorkflowContext.start_research returned an unrelated mutation outcome.")
        return ResearchResult(
            checkpoint=checkpoint,
            outcome=outcome,
            disposition=_disposition_for_outcome(outcome),
            category=ResearchCategory.DEVELOPMENT,
            node_title=title,
        )


def _select_development_node(
    observation: Observation,
    policy: ResearchPolicy,
    *,
    excluded_titles: frozenset[str] = frozenset(),
) -> DetectedListEntry | None:
    """Select the first stable non-max Development row in viewport order."""

    candidates: list[DetectedListEntry] = []
    for entry in observation.entries(ListEntryKind.RESEARCH):
        category = _entry_category(entry)
        if (
            category == ResearchCategory.DEVELOPMENT
            and entry.title_text not in excluded_titles
            and entry.metadata.get("research_progress_state") == "incomplete"
            and entry.metadata.get("research_access_state") == "available"
        ):
            candidates.append(entry)
    if not candidates:
        return None

    matching_titles = [entry.title_text for entry in candidates]
    duplicate_titles = {
        title
        for title in matching_titles
        if title is not None and matching_titles.count(title) > 1
    }
    if duplicate_titles:
        raise TaskVerificationError(
            "Development research node is ambiguous; no node was opened or started.",
            candidate_count=len(candidates),
        )

    candidates = [
        entry
        for entry in candidates
        if _development_node_geometry_is_actionable(entry)
    ]
    if not candidates:
        return None

    target = choose_priority_entry(
        candidates,
        policy.priority,
        key_selector=lambda entry: _entry_category(entry),
    )
    if target is None:
        return None
    if target.title_text is None or matching_titles.count(target.title_text) != 1:
        raise TaskVerificationError(
            "Development research node is ambiguous; no node was opened or started.",
            candidate_count=len(candidates),
        )
    return target


def _development_node_geometry_is_actionable(entry: DetectedListEntry) -> bool:
    """Return whether one eligible Development row has complete tap geometry."""

    return (
        entry.row_status == RowRecognitionStatus.COMPLETE
        and entry.action_point is not None
        and entry.action_bounds is not None
        and entry.action_bounds.contains_point(entry.action_point)
        and entry.bounds.contains_bounds(entry.action_bounds)
    )


def _development_viewport_signature(
    observation: Observation,
) -> tuple[tuple[object, ...], ...]:
    """Describe visible Development facts so a stalled scroll cannot loop."""

    return tuple(
        (
            entry.title_text,
            entry.row_status.value,
            entry.metadata.get("research_access_state"),
            entry.metadata.get("research_progress_state"),
            entry.metadata.get("research_progress_current"),
            entry.metadata.get("research_progress_limit"),
            entry.bounds.x,
            entry.bounds.y,
        )
        for entry in observation.entries(ListEntryKind.RESEARCH)
        if _entry_category(entry) == ResearchCategory.DEVELOPMENT
    )


def _entry_category(entry: DetectedListEntry) -> ResearchCategory | None:
    """Parse one row's existing category metadata without treating unknown text as eligible."""

    raw_category = entry.metadata.get("category")
    if isinstance(raw_category, ResearchCategory):
        return raw_category
    if not isinstance(raw_category, str):
        return None
    try:
        return ResearchCategory(raw_category)
    except ValueError:
        return None


def _no_visible_supported_node(checkpoint: DailyTaskCheckpoint) -> ResearchResult:
    """Return the explicit pending disposition for incomplete supported-node evidence."""

    outcome = DailyTargetOutcome(
        quest_id=DailyQuestId.UPGRADE_RESEARCH,
        status=DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
        message="No visible supported Development research node; eligibility remains unproven.",
    )
    return ResearchResult(
        checkpoint=checkpoint,
        outcome=outcome,
        disposition=ResearchDisposition.NO_VISIBLE_SUPPORTED_NODE,
    )


def _unfunded_supported_node(
    checkpoint: DailyTaskCheckpoint,
    title: str,
) -> ResearchResult:
    """Return pending after bounded detail checks find no safely fundable node."""

    outcome = DailyTargetOutcome(
        quest_id=DailyQuestId.UPGRADE_RESEARCH,
        status=DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
        message="No inspected Development detail proved sufficient resources; no intent was created.",
    )
    return ResearchResult(
        checkpoint=checkpoint,
        outcome=outcome,
        disposition=ResearchDisposition.PENDING_CLARIFICATION,
        category=ResearchCategory.DEVELOPMENT,
        node_title=title,
    )


def _disposition_for_outcome(outcome: DailyTargetOutcome) -> ResearchDisposition:
    """Map canonical mutation outcomes to the typed workflow disposition."""

    if outcome.status == DailyTargetOutcomeStatus.SUCCESS:
        return ResearchDisposition.STARTED
    if outcome.status == DailyTargetOutcomeStatus.PENDING_CLARIFICATION:
        return ResearchDisposition.PENDING_CLARIFICATION
    if outcome.status == DailyTargetOutcomeStatus.FAILED:
        return ResearchDisposition.FAILED
    return ResearchDisposition.PENDING_CLARIFICATION
