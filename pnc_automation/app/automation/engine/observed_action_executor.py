"""Higher-level action execution that can re-observe and promote selector taps to OCR."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, LaunchAppAction, TapAction
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    TASK_OWNED_POPUP_SCREEN_TYPES,
    decide_popup_recovery,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selector_interactions import (
    is_settled_primary_navigation_miss,
    is_transitional_observation,
    safe_navigation_outcomes,
    settle_reviewed_navigation_observation,
)
from pnc_automation.app.pnc.vision.selectors import ClickOutcome, SelectorDefinition, SelectorRegistry


_SAFE_TRANSIENT_POPUP_SELECTORS: tuple[UiElementId, ...] = (
    UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
    UiElementId.PNC_POPUP_CLOSE_BUTTON,
)

class ObservationCallback(Protocol):
    """Captures a fresh observation for one action label and request."""

    def __call__(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Returns the freshly captured observation."""


@dataclass(frozen=True, slots=True)
class ObservedActionExecutionPolicy:
    """Centralizes bounded settle behavior for observed selector taps."""

    max_settle_observations: int = 3
    update_poll_interval_seconds: int = 10
    update_max_wait_seconds: int = 600
    update_max_popup_dismissals: int = 6

    def __post_init__(self) -> None:
        """Rejects invalid negative settle budgets."""

        if self.max_settle_observations < 0:
            raise ValueError("ObservedActionExecutionPolicy.max_settle_observations cannot be negative.")
        if self.update_poll_interval_seconds <= 0:
            raise ValueError("Update poll interval must be positive.")
        if self.update_max_wait_seconds < self.update_poll_interval_seconds:
            raise ValueError("Update wait budget must include at least one poll interval.")
        if self.update_max_popup_dismissals < 0:
            raise ValueError("Update popup dismissal budget cannot be negative.")


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
    update_recovered: bool = False


@dataclass(frozen=True, slots=True)
class _InterruptionRecoveryResult:
    """Carries one recovered observation and whether an exact update was involved."""

    observation: Observation | None
    update_recovered: bool = False


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

        recovered = self._recover_interruption_if_required(
            initial_observation,
            label_prefix="pre_action_update",
            observe=observe,
        )
        if recovered.observation is not None:
            return ObservedActionExecutionResult(
                observation=recovered.observation,
                update_recovered=recovered.update_recovered,
            )
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
                if interaction_result.update_recovered:
                    return ObservedActionExecutionResult(
                        observation=current_observation,
                        selector_interactions=tuple(selector_interactions),
                        update_recovered=True,
                    )
                recovered = self._recover_interruption_if_required(
                    current_observation,
                    label_prefix=f"post_action_{index + 1}_update",
                    observe=observe,
                )
                if recovered.observation is not None:
                    return ObservedActionExecutionResult(
                        observation=recovered.observation,
                        selector_interactions=tuple(selector_interactions),
                        update_recovered=recovered.update_recovered,
                    )
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
                recovered = self._recover_interruption_if_required(
                    current_observation,
                    label_prefix=f"post_action_{index + 1}_update",
                    observe=observe,
                )
                if recovered.observation is not None:
                    return ObservedActionExecutionResult(
                        observation=recovered.observation,
                        selector_interactions=tuple(selector_interactions),
                        update_recovered=recovered.update_recovered,
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
            recovered = self._recover_interruption_if_required(
                current_observation,
                label_prefix="post_actions_update",
                observe=observe,
            )
            if recovered.observation is not None:
                return ObservedActionExecutionResult(
                    observation=recovered.observation,
                    selector_interactions=tuple(selector_interactions),
                    update_recovered=recovered.update_recovered,
                )
        return ObservedActionExecutionResult(
            observation=current_observation,
            selector_interactions=tuple(selector_interactions),
        )

    def recover_interruption_if_required(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> Observation | None:
        """Recovers one exact update or one bounded episode of safe transient popups.

        This is intentionally executor-owned: callers provide the current observation
        and capture callback, while this method owns the safe selector whitelist,
        fingerprint guard, and popup bound.  A ``None`` return means no interruption
        was present in the supplied observation.
        """

        return self._recover_interruption_if_required(
            observation,
            label_prefix=label_prefix,
            observe=observe,
        ).observation

    def recover_update_if_required(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> Observation | None:
        """Confirms one exact required-update interruption, if present.

        This name intentionally remains update-only.  Callers that also need safe
        transient popup handling must use ``recover_interruption_if_required``.
        """

        decision = decide_popup_recovery(
            screen_type=observation.screen_type,
            blocking_popup=observation.blocking_popup,
            visible_selector_ids=frozenset(observation.visible_elements),
            popup_overlay=observation.popup_overlay,
        )
        if decision is None or decision.control_kind != PopupControlKind.UPDATE_CONFIRM:
            return None
        return self._recover_required_update(
            observation,
            label_prefix=label_prefix,
            observe=observe,
        )

    def _recover_interruption_if_required(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> _InterruptionRecoveryResult:
        """Returns an executor-owned interruption result for internal action-loop use."""

        decision = decide_popup_recovery(
            screen_type=observation.screen_type,
            blocking_popup=observation.blocking_popup,
            visible_selector_ids=frozenset(observation.visible_elements),
            popup_overlay=observation.popup_overlay,
        )
        if decision is None or decision.control_kind != PopupControlKind.UPDATE_CONFIRM:
            if not self._is_popup_observation(observation):
                return _InterruptionRecoveryResult(None)
            return self._recover_transient_popups(
                observation,
                label_prefix=label_prefix,
                observe=observe,
            )
        recovered = self._recover_required_update(
            observation,
            label_prefix=label_prefix,
            observe=observe,
        )
        return _InterruptionRecoveryResult(recovered, update_recovered=True)

    def _recover_required_update(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> Observation:
        """Confirms one detected game update and polls until typed Home is restored."""

        if not self._has_typed_popup_control(observation, PopupControlKind.UPDATE_CONFIRM):
            raise self._transient_recovery_error(
                "Required game update confirmation lacks exact typed popup evidence.",
                observation,
                selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
            )
        self.logger.info(
            "Confirming required game update and entering bounded Home recovery.",
            extra={"screen_type": observation.screen_type},
        )
        try:
            dispatch_observation = self._observation_bound_to_popup_candidate(
                observation,
                UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
            )
            confirmed = self.action_executor.execute_action(
                TapAction(
                    selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                    reason="confirm_required_game_update",
                ),
                dispatch_observation,
            )
        except Exception as error:
            raise SelectorResolutionError(
                "Required game update Confirm dispatch failed.",
                selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                screen_type=observation.screen_type,
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
                dispatch_error=type(error).__name__,
            ) from error
        if not confirmed:
            raise SelectorResolutionError(
                "Required game update Confirm was detected but not dispatched.",
                selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                screen_type=observation.screen_type,
            )
        poll_count = self.policy.update_max_wait_seconds // self.policy.update_poll_interval_seconds
        launched_from_android_home = False
        dismissed_popup_fingerprints: set[str] = set()
        dismissed_popup_identities: set[tuple[object, ...]] = set()
        current = observation
        required_newer_than = observation.captured_at
        for index in range(poll_count):
            self.sleep(float(self.policy.update_poll_interval_seconds))
            current = observe(
                f"{label_prefix}_wait_{index + 1}",
                request=ObservationRequest.full_runtime_default(),
            )
            if current.frame_fingerprint in dismissed_popup_fingerprints:
                raise self._transient_recovery_error(
                    "Post-update popup remained after its one safe dismissal attempt; its visual fingerprint was already consumed.",
                    current,
                    fingerprint=current.frame_fingerprint,
                )
            if required_newer_than is not None and current.captured_at <= required_newer_than:
                raise self._transient_recovery_error(
                    "Required game update recovery received a stale post-dispatch observation.",
                    current,
                    captured_at=current.captured_at.isoformat(),
                    required_newer_than=required_newer_than.isoformat(),
                )
            required_newer_than = None
            if current.screen_type == ScreenType.PNC_HOME_CITY and not current.blocking_popup:
                self.logger.info(
                    "Required game update completed and typed Home was restored.",
                    extra={"poll_count": index + 1},
                )
                return current
            typed_identity = self._typed_popup_identity(current)
            if typed_identity is not None and typed_identity in dismissed_popup_identities:
                current = self._settle_same_typed_popup(
                    current,
                    typed_identity=typed_identity,
                    label_prefix=f"{label_prefix}_popup_{index + 1}",
                    observe=observe,
                )
                if current.screen_type == ScreenType.PNC_HOME_CITY and not current.blocking_popup:
                    self.logger.info(
                        "Required game update completed and typed Home was restored after popup settle.",
                        extra={"poll_count": index + 1},
                    )
                    return current
            if self._has_typed_popup_control(current, PopupControlKind.UPDATE_CONFIRM):
                continue
            popup_selector = self._transient_popup_selector(current)
            if popup_selector is not None:
                fingerprint = current.frame_fingerprint
                if not fingerprint:
                    raise SelectorResolutionError(
                        "Post-update popup dismissal requires a visual frame fingerprint.",
                        selector_id=popup_selector,
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                    )
                if fingerprint in dismissed_popup_fingerprints:
                    raise SelectorResolutionError(
                        "Post-update popup remained after its one safe dismissal attempt; its visual fingerprint was already consumed.",
                        selector_id=popup_selector,
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                    )
                if len(dismissed_popup_fingerprints) >= self.policy.update_max_popup_dismissals:
                    raise SelectorResolutionError(
                        "Game update exceeded the bounded post-update popup dismissal budget.",
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                    )
                typed_identity = self._typed_popup_identity(current)
                if typed_identity is not None and typed_identity in dismissed_popup_identities:
                    current = self._settle_same_typed_popup(
                        current,
                        typed_identity=typed_identity,
                        label_prefix=f"{label_prefix}_popup_settle_{index + 1}",
                        observe=observe,
                    )
                    continue
                try:
                    dispatch_observation = self._observation_bound_to_popup_candidate(current, popup_selector)
                    dispatched = self.action_executor.execute_action(
                        TapAction(
                            selector_id=popup_selector,
                            reason="dismiss_post_update_popup",
                        ),
                        dispatch_observation,
                    )
                except Exception as error:
                    raise SelectorResolutionError(
                        "Post-update popup close control dispatch failed.",
                        selector_id=popup_selector,
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                        dispatch_error=type(error).__name__,
                    ) from error
                if not dispatched:
                    raise SelectorResolutionError(
                        "Post-update popup close control was detected but dispatch failed.",
                        selector_id=popup_selector,
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                    )
                dismissed_popup_fingerprints.add(fingerprint)
                if typed_identity is not None:
                    dismissed_popup_identities.add(typed_identity)
                required_newer_than = current.captured_at
                continue
            if current.screen_type == ScreenType.ANDROID_HOME and not launched_from_android_home:
                launched = self.action_executor.execute_action(
                    LaunchAppAction(reason="relaunch_pnc_after_required_update"),
                    current,
                )
                if not launched:
                    raise SelectorResolutionError(
                        "P&C relaunch after required update was not dispatched.",
                        screen_type=current.screen_type,
                        artifact_path=None if current.artifact_path is None else str(current.artifact_path),
                    )
                launched_from_android_home = True
                required_newer_than = current.captured_at
                continue
            if current.screen_type in {
                ScreenType.ANDROID_HOME,
                ScreenType.PNC_HOME_CITY_ROOT,
                ScreenType.PNC_LOADING,
                ScreenType.UNKNOWN,
            }:
                continue
            raise SelectorResolutionError(
                "Game update left the bounded recovery path on an unexpected screen.",
                screen_type=current.screen_type,
                artifact_path=None if current.artifact_path is None else str(current.artifact_path),
            )
        raise SelectorResolutionError(
            "Game update did not return to Home within the ten-minute recovery budget.",
            screen_type=current.screen_type,
            artifact_path=None if current.artifact_path is None else str(current.artifact_path),
        )

    def _recover_transient_popups(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> _InterruptionRecoveryResult:
        """Dismisses only newly fingerprinted safe transient popups in one bounded episode."""

        current = observation
        dismissed_fingerprints: set[str] = set()
        dismissed_identities: set[tuple[object, ...]] = set()
        while self._is_popup_observation(current):
            decision = decide_popup_recovery(
                screen_type=current.screen_type,
                blocking_popup=current.blocking_popup,
                visible_selector_ids=frozenset(current.visible_elements),
                popup_overlay=current.popup_overlay,
            )
            if decision is not None and decision.control_kind == PopupControlKind.UPDATE_CONFIRM:
                recovered = self._recover_required_update(
                    current,
                    label_prefix=f"{label_prefix}_update",
                    observe=observe,
                )
                return _InterruptionRecoveryResult(recovered, update_recovered=True)
            selector = self._transient_popup_selector(current)
            if selector is None:
                raise self._transient_recovery_error(
                    "Transient popup has no explicit safe close selector; Android Back is forbidden.",
                    current,
                )
            fingerprint = current.frame_fingerprint
            if not fingerprint:
                raise self._transient_recovery_error(
                    "Transient popup recovery requires a fresh visual frame fingerprint.",
                    current,
                    selector_id=selector,
                )
            if fingerprint in dismissed_fingerprints:
                raise self._transient_recovery_error(
                    "Transient popup visual fingerprint was already consumed in this recovery episode.",
                    current,
                    selector_id=selector,
                )
            typed_identity = self._typed_popup_identity(current)
            if typed_identity is not None and typed_identity in dismissed_identities:
                raise self._transient_recovery_error(
                    "Transient popup typed identity was already consumed in this recovery episode.",
                    current,
                    selector_id=selector,
                    popup_identity=typed_identity,
                )
            if len(dismissed_fingerprints) >= self.policy.update_max_popup_dismissals:
                raise self._transient_recovery_error(
                    "Transient popup recovery exhausted its bounded distinct-popup dismissal budget.",
                    current,
                    selector_id=selector,
                    dismissed_count=len(dismissed_fingerprints),
                )
            dispatch_observation = self._observation_bound_to_popup_candidate(current, selector)
            try:
                dispatched = self.action_executor.execute_action(
                    TapAction(
                        selector_id=selector,
                        reason="dismiss_transient_popup",
                    ),
                    dispatch_observation,
                )
            except Exception as error:
                raise self._transient_recovery_error(
                    "Transient popup close control dispatch failed.",
                    current,
                    selector_id=selector,
                    dispatch_error=type(error).__name__,
                ) from error
            if not dispatched:
                raise self._transient_recovery_error(
                    "Transient popup close control was detected but dispatch failed.",
                    current,
                    selector_id=selector,
                )
            dismissed_fingerprints.add(fingerprint)
            if typed_identity is not None:
                dismissed_identities.add(typed_identity)
            current = observe(
                f"{label_prefix}_popup_{len(dismissed_fingerprints)}",
                request=ObservationRequest.full_runtime_default(),
            )
            if current.frame_fingerprint == fingerprint:
                raise self._transient_recovery_error(
                    "Transient popup dismissal produced an unchanged visual fingerprint; refusing a second candidate from the stale frame.",
                    current,
                    selector_id=selector,
                    fingerprint=fingerprint,
                )
            if current.captured_at <= dispatch_observation.captured_at:
                raise self._transient_recovery_error(
                    "Transient popup dismissal received a stale post-dispatch observation.",
                    current,
                    selector_id=selector,
                    captured_at=current.captured_at.isoformat(),
                    required_newer_than=dispatch_observation.captured_at.isoformat(),
                )
            if typed_identity is not None and self._typed_popup_identity(current) == typed_identity:
                current = self._settle_same_typed_popup(
                    current,
                    typed_identity=typed_identity,
                    label_prefix=f"{label_prefix}_popup_{len(dismissed_fingerprints)}",
                    observe=observe,
                )
            else:
                current = self._settle_popup_dismissal_observation(
                    current,
                    label_prefix=f"{label_prefix}_popup_{len(dismissed_fingerprints)}",
                    observe=observe,
                )
            if current.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON):
                recovered = self._recover_required_update(
                    current,
                    label_prefix=f"{label_prefix}_update",
                    observe=observe,
                )
                return _InterruptionRecoveryResult(recovered, update_recovered=True)
            if not self._is_popup_observation(current):
                return _InterruptionRecoveryResult(current)
        return _InterruptionRecoveryResult(current)

    def _settle_same_typed_popup(
        self,
        observation: Observation,
        *,
        typed_identity: tuple[object, ...],
        label_prefix: str,
        observe: ObservationCallback,
    ) -> Observation:
        """Waits for a typed popup to finish dismissing without dispatching a second tap."""

        current = observation
        for settle_index in range(self.policy.max_settle_observations):
            if self._typed_popup_identity(current) != typed_identity:
                if is_transitional_observation(current):
                    return self._settle_popup_dismissal_observation(
                        current,
                        label_prefix=label_prefix,
                        observe=observe,
                    )
                return current
            self._sleep_for_observe()
            next_observation = observe(
                f"{label_prefix}_typed_settle_{settle_index + 1}",
                request=ObservationRequest.full_runtime_default(),
            )
            if next_observation.captured_at <= current.captured_at:
                raise self._transient_recovery_error(
                    "Transient popup semantic settle received a stale observation; refusing another candidate.",
                    next_observation,
                    popup_identity=typed_identity,
                    captured_at=next_observation.captured_at.isoformat(),
                    required_newer_than=current.captured_at.isoformat(),
                )
            current = next_observation
        if self._typed_popup_identity(current) == typed_identity:
            raise self._transient_recovery_error(
                "Transient popup remained after its one safe dismissal attempt with the same typed identity.",
                current,
                popup_identity=typed_identity,
            )
        return current

    def _settle_popup_dismissal_observation(
        self,
        observation: Observation,
        *,
        label_prefix: str,
        observe: ObservationCallback,
    ) -> Observation:
        """Passively settles loading/unknown frames after a popup close tap.

        These captures belong to the interruption episode and therefore do not
        consume a task or navigation step budget.  Full-runtime requests preserve
        the same broad observation semantics used by update recovery.
        """

        current = observation
        for settle_index in range(self.policy.max_settle_observations):
            if not is_transitional_observation(current):
                return current
            self._sleep_for_observe()
            next_observation = observe(
                f"{label_prefix}_settle_{settle_index + 1}",
                request=ObservationRequest.full_runtime_default(),
            )
            if next_observation.captured_at <= current.captured_at:
                raise self._transient_recovery_error(
                    "Transient popup dismissal settle received a stale observation.",
                    next_observation,
                    captured_at=next_observation.captured_at.isoformat(),
                    required_newer_than=current.captured_at.isoformat(),
                )
            current = next_observation
        return current

    @staticmethod
    def _is_popup_observation(observation: Observation) -> bool:
        """Returns whether the observation is a blocking popup state covered by recovery."""

        if observation.screen_type in TASK_OWNED_POPUP_SCREEN_TYPES:
            return False
        return (
            observation.screen_type in {ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET}
            or any(observation.has(selector_id) for selector_id in _SAFE_TRANSIENT_POPUP_SELECTORS)
            or observation.blocking_popup
        )

    @staticmethod
    def _has_typed_popup_control(observation: Observation, kind: PopupControlKind) -> bool:
        """Require exact typed evidence before authorizing affirmative popup controls."""

        return observation.popup_overlay is not None and observation.popup_overlay.candidate(kind) is not None

    @staticmethod
    def _typed_popup_identity(observation: Observation) -> tuple[object, ...] | None:
        """Return semantic popup evidence stable across animated frame pixels."""

        overlay = observation.popup_overlay
        if overlay is None:
            return None
        candidates = tuple(
            (
                candidate.control_kind,
                candidate.evidence_kind,
                candidate.reason,
            )
            for candidate in overlay.candidates
        )
        return (
            observation.screen_type,
            overlay.layout_id,
            overlay.evidence_kind,
            overlay.reason,
            candidates,
        )

    @staticmethod
    def _transient_popup_selector(observation: Observation) -> UiElementId | None:
        """Returns the sole explicit safe selector allowed for a transient popup."""

        decision = decide_popup_recovery(
            screen_type=observation.screen_type,
            blocking_popup=observation.blocking_popup,
            visible_selector_ids=frozenset(observation.visible_elements),
            popup_overlay=observation.popup_overlay,
        )
        return None if decision is None else decision.selector_id

    @staticmethod
    def _observation_bound_to_popup_candidate(observation: Observation, selector: UiElementId) -> Observation:
        """Dispatch the measured candidate selected from this exact observation frame."""

        overlay = observation.popup_overlay
        if overlay is None:
            return observation
        if selector == UiElementId.PNC_UPDATE_CONFIRM_BUTTON:
            candidate = overlay.candidate(PopupControlKind.UPDATE_CONFIRM)
        else:
            decision = decide_popup_recovery(
                screen_type=observation.screen_type,
                blocking_popup=observation.blocking_popup,
                visible_selector_ids=frozenset(observation.visible_elements),
                popup_overlay=overlay,
            )
            candidate = None if decision is None or decision.control_kind is None else overlay.candidate(decision.control_kind)
        if candidate is None:
            return observation
        elements = dict(observation.visible_elements)
        elements[selector] = VisibleElement(
            selector_id=selector,
            bounds=candidate.bounds,
            confidence=candidate.confidence,
            source_kind=(
                VisibleElementSourceKind.TEMPLATE
                if candidate.evidence_kind.value == "template"
                else VisibleElementSourceKind.GEOMETRY
                if candidate.evidence_kind.value == "geometry"
                else VisibleElementSourceKind.OCR
            ),
            extracted_text=candidate.extracted_text,
            action_point=candidate.action_point,
        )
        return replace(observation, visible_elements=elements)

    @staticmethod
    def _transient_recovery_error(
        message: str,
        observation: Observation,
        **details: object,
    ) -> SelectorResolutionError:
        """Builds one popup recovery error with the current artifact when available."""

        if observation.artifact_path is not None:
            details.setdefault("artifact_path", str(observation.artifact_path))
        overlay = observation.popup_overlay
        if overlay is not None:
            details.setdefault("popup_layout", overlay.layout_id)
            candidate = overlay.candidate(PopupControlKind.UPDATE_CONFIRM)
            if candidate is None:
                decision = decide_popup_recovery(
                    screen_type=observation.screen_type,
                    blocking_popup=observation.blocking_popup,
                    visible_selector_ids=frozenset(observation.visible_elements),
                    popup_overlay=overlay,
                )
                candidate = (
                    None
                    if decision is None or decision.control_kind is None
                    else overlay.candidate(decision.control_kind)
                )
            if candidate is not None:
                details.setdefault("popup_control_kind", candidate.control_kind)
                details.setdefault("popup_action_point", candidate.action_point)
                details.setdefault("popup_evidence_kind", candidate.evidence_kind)
                details.setdefault("popup_confidence", candidate.confidence)
        details.setdefault("screen_type", observation.screen_type)
        return SelectorResolutionError(message, **details)

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
        first_recovery = self._recover_interruption_if_required(
            first_after,
            label_prefix=f"{label_prefix}_interruption",
            observe=observe,
        )
        interruption_recovered = first_recovery.observation is not None
        if first_recovery.observation is not None:
            settled_after = first_recovery.observation
        else:
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
            not interruption_recovered
            and not final_after.has(UiElementId.PNC_STATUS_BANNER)
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
            update_recovered=first_recovery.update_recovered,
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
