"""Higher-level action execution that can re-observe and promote selector taps to OCR."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selector_interactions import (
    is_settled_primary_navigation_miss,
    safe_navigation_outcomes,
    settle_reviewed_navigation_observation,
)
from pnc_automation.app.pnc.vision.selectors import ClickOutcome, SelectorDefinition, SelectorRegistry


class ObservationCallback(Protocol):
    """Captures a fresh observation for one action label and request."""

    def __call__(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Returns the freshly captured observation."""


@dataclass(frozen=True, slots=True)
class ObservedActionExecutionPolicy:
    """Centralizes bounded settle behavior for observed selector taps."""

    max_settle_observations: int = 3

    def __post_init__(self) -> None:
        """Rejects invalid negative settle budgets."""

        if self.max_settle_observations < 0:
            raise ValueError("ObservedActionExecutionPolicy.max_settle_observations cannot be negative.")


@dataclass(frozen=True, slots=True)
class SelectorInteractionResult:
    """Summarizes one selector-backed tap observed through the shared interaction path."""

    selector_id: UiElementId
    source_screen: ScreenType
    initial_source_kind: VisibleElementSourceKind
    first_after_screen: ScreenType
    final_after_screen: ScreenType
    initial_destination_artifact_path: Path | None = None
    final_destination_artifact_path: Path | None = None
    fallback_attempted: bool = False
    fallback_used: bool = False
    fallback_source_kind: VisibleElementSourceKind | None = None


@dataclass(frozen=True, slots=True)
class ObservedActionExecutionResult:
    """Returns the final observation plus selector-interaction diagnostics."""

    observation: Observation
    selector_interactions: tuple[SelectorInteractionResult, ...] = ()


@dataclass(frozen=True, slots=True)
class _ObservedNavigationTap:
    """Carries the shared metadata required for one fallback-eligible navigation tap."""

    selector: SelectorDefinition
    source_element: VisibleElement
    reviewed_outcomes: tuple[ClickOutcome, ...]


@dataclass(slots=True)
class ObservedActionExecutor:
    """Executes actions while sharing the canonical selector-level fallback policy."""

    selector_registry: SelectorRegistry
    action_executor: ActionExecutor
    logger: logging.LoggerAdapter
    policy: ObservedActionExecutionPolicy = field(default_factory=ObservedActionExecutionPolicy)
    sleep: Callable[[float], None] = time.sleep

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool:
        """Executes one action without observing, for callers that own follow-up capture timing."""

        return self.action_executor.execute_action(action, observation)

    def execute_actions(
        self,
        actions: Sequence[ActionRequest],
        initial_observation: Observation,
        *,
        observe: ObservationCallback,
    ) -> ObservedActionExecutionResult:
        """Executes the action sequence and returns the freshest observed result."""

        current_observation = initial_observation
        observed_after_action = False
        executed_any_action = False
        selector_interactions: list[SelectorInteractionResult] = []
        for index, action in enumerate(actions):
            candidate = self._resolve_observed_navigation_tap(action, current_observation)
            if candidate is not None:
                interaction_result = self._execute_observed_navigation_tap(
                    action=action,
                    before=current_observation,
                    candidate=candidate,
                    label_prefix=f"post_action_{index + 1}",
                    observe=observe,
                )
                current_observation = interaction_result.observation
                selector_interactions.extend(interaction_result.selector_interactions)
                executed_any_action = True
                observed_after_action = True
                continue
            action_executed = self.action_executor.execute_action(action, current_observation)
            executed_any_action = executed_any_action or action_executed
            if getattr(action, "observe_after", False) and action_executed:
                current_observation = self.action_executor.observe_action_follow_up(
                    action=action,
                    label_prefix=f"post_action_{index + 1}",
                    observe=observe,
                )
                if not self.action_executor.validate_follow_up(action, current_observation):
                    return ObservedActionExecutionResult(
                        observation=current_observation,
                        selector_interactions=tuple(selector_interactions),
                    )
                observed_after_action = True
        if executed_any_action and not observed_after_action:
            self._sleep_for_observe()
            current_observation = observe("post_actions")
        return ObservedActionExecutionResult(
            observation=current_observation,
            selector_interactions=tuple(selector_interactions),
        )

    def _resolve_observed_navigation_tap(
        self,
        action: ActionRequest,
        observation: Observation,
    ) -> _ObservedNavigationTap | None:
        """Returns one reviewed navigation tap or `None` when normal execution is sufficient."""

        if not isinstance(action, TapAction) or not action.observe_after:
            return None
        selector = self.selector_registry.require(action.selector_id)
        source_element = observation.require(action.selector_id)
        if selector.interaction_kind != SelectorInteractionKind.NAVIGATION:
            return None
        reviewed_outcomes = safe_navigation_outcomes(selector)
        if not reviewed_outcomes:
            if source_element.source_kind == VisibleElementSourceKind.GEOMETRY:
                raise SelectorResolutionError(
                    "Geometry-backed navigation fallback requires at least one safe reviewed click outcome.",
                    selector_id=selector.id,
                    screen_type=observation.screen_type,
                )
            return None
        return _ObservedNavigationTap(
            selector=selector,
            source_element=source_element,
            reviewed_outcomes=reviewed_outcomes,
        )

    def _execute_observed_navigation_tap(
        self,
        *,
        action: TapAction,
        before: Observation,
        candidate: _ObservedNavigationTap,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> ObservedActionExecutionResult:
        """Executes one geometry-backed navigation tap through the shared primary-to-OCR flow."""

        follow_up_request = action.follow_up_request or ObservationRequest.navigation_follow_up(candidate.reviewed_outcomes)
        self.action_executor.execute_action(action, before)
        self._sleep_for_observe(action)
        first_after = observe(label_prefix, request=follow_up_request)
        settled_after = (
            first_after
            if self._should_preserve_first_follow_up(first_after)
            else settle_reviewed_navigation_observation(
                first_observation=first_after,
                label_prefix=label_prefix,
                request=follow_up_request,
                reviewed_outcomes=candidate.reviewed_outcomes,
                max_settle_observations=self.policy.max_settle_observations,
                observe=observe,
                sleep=self._sleep_for_observe,
            )
        )
        final_after = settled_after
        if (
            final_after.screen_type == ScreenType.UNKNOWN
            and not final_after.has(UiElementId.PNC_STATUS_BANNER)
            and follow_up_request != ObservationRequest.full_runtime_default()
        ):
            final_after = observe(
                f"{label_prefix}_runtime_retry",
                request=ObservationRequest.full_runtime_default(),
            )
        fallback_attempted = False
        fallback_used = False
        fallback_source_kind: VisibleElementSourceKind | None = None
        if (
            not final_after.has(UiElementId.PNC_STATUS_BANNER)
            and is_settled_primary_navigation_miss(candidate.selector, before, settled_after, candidate.source_element)
        ):
            fallback_attempted = True
            retry_source = observe(
                f"{label_prefix}_ocr_retry_source",
                request=ObservationRequest.source_screen_retry(before.screen_type),
            )
            retry_element = retry_source.get(action.selector_id)
            if retry_element is not None and retry_element.source_kind == VisibleElementSourceKind.OCR:
                fallback_used = True
                fallback_source_kind = retry_element.source_kind
                self.action_executor.execute_action(action, retry_source)
                self._sleep_for_observe(action)
                retry_after = observe(f"{label_prefix}_ocr_retry_after", request=follow_up_request)
                final_after = settle_reviewed_navigation_observation(
                    first_observation=retry_after,
                    label_prefix=f"{label_prefix}_ocr_retry_after",
                    request=follow_up_request,
                    reviewed_outcomes=candidate.reviewed_outcomes,
                    max_settle_observations=self.policy.max_settle_observations,
                    observe=observe,
                    sleep=self._sleep_for_observe,
                )
            else:
                final_after = retry_source
        interaction = SelectorInteractionResult(
            selector_id=action.selector_id,
            source_screen=before.screen_type,
            initial_source_kind=candidate.source_element.source_kind,
            first_after_screen=first_after.screen_type,
            final_after_screen=final_after.screen_type,
            initial_destination_artifact_path=first_after.artifact_path,
            final_destination_artifact_path=final_after.artifact_path,
            fallback_attempted=fallback_attempted,
            fallback_used=fallback_used,
            fallback_source_kind=fallback_source_kind,
        )
        self.logger.info(
            "Observed selector interaction resolved.",
            extra={
                "selector_id": action.selector_id.value,
                "source_screen": before.screen_type.name,
                "initial_source_kind": interaction.initial_source_kind.value,
                "fallback_attempted": interaction.fallback_attempted,
                "fallback_source_kind": None if interaction.fallback_source_kind is None else interaction.fallback_source_kind.value,
                "first_after_screen": interaction.first_after_screen.name,
                "final_after_screen": interaction.final_after_screen.name,
            },
        )
        return ObservedActionExecutionResult(
            observation=final_after,
            selector_interactions=(interaction,),
        )

    def _should_preserve_first_follow_up(self, observation: Observation) -> bool:
        """Returns whether the initial follow-up should be preserved because it carries a transient rejection banner."""

        return observation.has(UiElementId.PNC_STATUS_BANNER)

    def _sleep_for_observe(self, action: ActionRequest | None = None) -> None:
        """Applies the shared post-action observe delay used by follow-up captures."""

        if action is None:
            delay_ms = self.action_executor.post_action_observe_delay_ms
        else:
            delay_ms = self.action_executor._observe_delay_ms_for(action)
        if delay_ms <= 0:
            return
        self.sleep(delay_ms / 1000.0)
