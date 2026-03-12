"""Live validation of reviewed navigation selectors against the current selector registry."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import yaml

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import TapAction
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import CapturedObservation
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import ClickOutcome, SelectorRegistry


class NavigationValidationStatus(StrEnum):
    """Summarizes whether one reviewed navigation case passed, failed, or was intentionally skipped."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ObservationCaptureService(Protocol):
    """Captures typed observations for live validation runs."""

    def capture_observation(self, label: str) -> CapturedObservation:
        """Captures one fresh observation with an artifact-backed screenshot."""


@dataclass(frozen=True, slots=True)
class NavigationSelectorValidationCase:
    """Represents one navigation selector validated from one reviewed host screen."""

    selector_id: UiElementId
    source_screen: ScreenType
    reviewed_outcomes: tuple[ClickOutcome, ...]

    @property
    def expected_target_screens(self) -> tuple[ScreenType, ...]:
        """Returns the distinct reviewed destination screens expected from this validation case."""

        return tuple(
            dict.fromkeys(
                outcome.target_screen
                for outcome in self.reviewed_outcomes
                if outcome.target_screen is not None
            )
        )


@dataclass(frozen=True, slots=True)
class NavigationSelectorValidationResult:
    """Captures the outcome of validating one reviewed navigation selector from one source screen."""

    selector_id: UiElementId
    source_screen: ScreenType
    status: NavigationValidationStatus
    reason: str
    expected_target_screens: tuple[ScreenType, ...]
    source_artifact_path: Path | None = None
    destination_artifact_path: Path | None = None
    destination_screen: ScreenType | None = None
    matched_target_screen: ScreenType | None = None
    missing_verification_selectors: tuple[UiElementId, ...] = ()
    observed_selectors: tuple[UiElementId, ...] = ()
    retry_attempted: bool = False
    retry_source_artifact_path: Path | None = None
    retry_destination_artifact_path: Path | None = None

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one navigation validation result."""

        document: dict[str, object] = {
            "selector_id": self.selector_id.value,
            "source_screen": self.source_screen.name,
            "status": self.status.value,
            "reason": self.reason,
            "expected_target_screens": [screen.name for screen in self.expected_target_screens],
            "observed_selectors": [selector_id.value for selector_id in self.observed_selectors],
        }
        if self.source_artifact_path is not None:
            document["source_artifact_path"] = str(self.source_artifact_path)
        if self.destination_artifact_path is not None:
            document["destination_artifact_path"] = str(self.destination_artifact_path)
        if self.retry_source_artifact_path is not None:
            document["retry_source_artifact_path"] = str(self.retry_source_artifact_path)
        if self.retry_destination_artifact_path is not None:
            document["retry_destination_artifact_path"] = str(self.retry_destination_artifact_path)
        if self.destination_screen is not None:
            document["destination_screen"] = self.destination_screen.name
        if self.matched_target_screen is not None:
            document["matched_target_screen"] = self.matched_target_screen.name
        if self.missing_verification_selectors:
            document["missing_verification_selectors"] = [
                selector_id.value for selector_id in self.missing_verification_selectors
            ]
        return document


@dataclass(frozen=True, slots=True)
class NavigationSelectorValidationReport:
    """Summarizes one live validation pass across reviewed navigation selectors."""

    results: tuple[NavigationSelectorValidationResult, ...]

    @property
    def passed_count(self) -> int:
        """Returns the number of validation cases that matched their reviewed destination contracts."""

        return sum(1 for result in self.results if result.status == NavigationValidationStatus.PASSED)

    @property
    def failed_count(self) -> int:
        """Returns the number of validation cases that diverged from their reviewed destination contracts."""

        return sum(1 for result in self.results if result.status == NavigationValidationStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        """Returns the number of validation cases intentionally skipped."""

        return sum(1 for result in self.results if result.status == NavigationValidationStatus.SKIPPED)

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of the full validation report."""

        return {
            "summary": {
                "passed": self.passed_count,
                "failed": self.failed_count,
                "skipped": self.skipped_count,
            },
            "results": [result.to_document() for result in self.results],
        }


@dataclass(slots=True)
class NavigationSelectorValidator:
    """Executes reviewed navigation-selector probes against a live runtime and reports pass/fail evidence."""

    selector_registry: SelectorRegistry
    observation_service: ObservationCaptureService
    action_executor: ActionExecutor
    screen_flows: ScreenFlowPlanner
    logger: logging.LoggerAdapter
    max_prepare_steps: int = 10
    max_recovery_steps: int = 10
    max_destination_settle_observations: int = 3
    sleep: Callable[[float], None] = time.sleep

    def validate(
        self,
        *,
        selector_ids: Sequence[UiElementId] | None = None,
    ) -> NavigationSelectorValidationReport:
        """Validates the requested reviewed navigation selectors and returns a deterministic report."""

        requested_selector_ids = None if selector_ids is None or not selector_ids else frozenset(selector_ids)
        current_capture = self.observation_service.capture_observation("navigation_validation_start")
        results: list[NavigationSelectorValidationResult] = []
        for case_index, case in enumerate(
            build_navigation_validation_cases(self.selector_registry, selector_ids=selector_ids),
            start=1,
        ):
            if requested_selector_ids is not None and case.selector_id not in requested_selector_ids:
                continue
            self.logger.info(
                "Validating navigation selector.",
                extra={"selector_id": case.selector_id.value, "source_screen": case.source_screen.name},
            )
            try:
                current_capture = self._recover_to_home(
                    current_capture,
                    case_index=case_index,
                    step_label="before_case",
                )
            except SelectorResolutionError as error:
                results.append(
                    NavigationSelectorValidationResult(
                        selector_id=case.selector_id,
                        source_screen=case.source_screen,
                        status=NavigationValidationStatus.FAILED,
                        reason=error.message,
                        expected_target_screens=case.expected_target_screens,
                        source_artifact_path=current_capture.screenshot.artifact.path,
                        observed_selectors=_sorted_selector_ids(current_capture.observation),
                    )
                )
                break
            if not case.reviewed_outcomes:
                results.append(
                    NavigationSelectorValidationResult(
                        selector_id=case.selector_id,
                        source_screen=case.source_screen,
                        status=NavigationValidationStatus.SKIPPED,
                        reason="Selector has no safe reviewed outcomes to click live.",
                        expected_target_screens=(),
                        source_artifact_path=current_capture.screenshot.artifact.path,
                        observed_selectors=_sorted_selector_ids(current_capture.observation),
                    )
                )
                continue
            try:
                source_capture = self._prepare_source_capture(case, current_capture, case_index=case_index)
                result, current_capture = self._validate_case(case, source_capture, case_index=case_index)
            except SelectorResolutionError as error:
                result = NavigationSelectorValidationResult(
                    selector_id=case.selector_id,
                    source_screen=case.source_screen,
                    status=NavigationValidationStatus.FAILED,
                    reason=error.message,
                    expected_target_screens=case.expected_target_screens,
                    source_artifact_path=current_capture.screenshot.artifact.path,
                    observed_selectors=_sorted_selector_ids(current_capture.observation),
                )
            results.append(result)
        return NavigationSelectorValidationReport(results=tuple(results))

    def _prepare_source_capture(
        self,
        case: NavigationSelectorValidationCase,
        current_capture: CapturedObservation,
        *,
        case_index: int,
    ) -> CapturedObservation:
        """Settles the live session onto the requested source screen with the selector visible."""

        latest_capture = current_capture
        for step_index in range(self.max_prepare_steps):
            observation = latest_capture.observation
            if observation.screen_type == case.source_screen and observation.has(case.selector_id):
                return latest_capture
            planned_actions = _plan_navigation_source_actions(case=case, observation=observation, screen_flows=self.screen_flows)
            if not planned_actions:
                raise SelectorResolutionError(
                    "Could not make the reviewed navigation selector visible from its declared source screen.",
                    selector_id=case.selector_id.value,
                    source_screen=case.source_screen.name,
                    observed_screen=observation.screen_type.name,
                    artifact_path=str(latest_capture.screenshot.artifact.path),
                )
            latest_capture = self._execute_actions(
                planned_actions,
                latest_capture,
                label_prefix=f"navigation_validation_{case_index}_prepare_{step_index + 1}",
            )
        raise SelectorResolutionError(
            "Could not prepare the reviewed navigation selector within the configured step budget.",
            selector_id=case.selector_id.value,
            source_screen=case.source_screen.name,
            max_prepare_steps=self.max_prepare_steps,
            artifact_path=str(latest_capture.screenshot.artifact.path),
        )

    def _validate_case(
        self,
        case: NavigationSelectorValidationCase,
        source_capture: CapturedObservation,
        *,
        case_index: int,
    ) -> tuple[NavigationSelectorValidationResult, CapturedObservation]:
        """Clicks one reviewed selector and verifies the observed destination against the stored contract."""

        destination_capture = self._execute_actions(
            (
                TapAction(
                    selector_id=case.selector_id,
                    reason="validate_navigation_selector",
                    observe_after=True,
                ),
            ),
            source_capture,
            label_prefix=f"navigation_validation_{case_index}_tap_{case.selector_id.value.lower()}",
        )
        destination_capture = self._settle_destination_capture(
            case,
            destination_capture,
            case_index=case_index,
        )
        matched_outcome, missing_selectors = match_reviewed_navigation_outcome(
            destination_capture.observation,
            case.reviewed_outcomes,
        )
        if matched_outcome is not None:
            return (
                NavigationSelectorValidationResult(
                selector_id=case.selector_id,
                source_screen=case.source_screen,
                status=NavigationValidationStatus.PASSED,
                reason="Observed destination matched a reviewed click outcome.",
                    expected_target_screens=case.expected_target_screens,
                    source_artifact_path=source_capture.screenshot.artifact.path,
                    destination_artifact_path=destination_capture.screenshot.artifact.path,
                destination_screen=destination_capture.observation.screen_type,
                matched_target_screen=matched_outcome.target_screen,
                observed_selectors=_sorted_selector_ids(destination_capture.observation),
            ),
            destination_capture,
        )

        retry_result = self._maybe_retry_with_stronger_resolution(
            case=case,
            source_capture=source_capture,
            first_destination_capture=destination_capture,
            first_missing_selectors=missing_selectors,
            case_index=case_index,
        )
        if retry_result is not None:
            return retry_result

        reason = (
            "Observed destination screen matched a reviewed target but required verification selectors were missing."
            if missing_selectors
            else "Observed destination screen did not match any reviewed click outcome."
        )
        return (
            NavigationSelectorValidationResult(
                selector_id=case.selector_id,
                source_screen=case.source_screen,
                status=NavigationValidationStatus.FAILED,
                reason=reason,
                expected_target_screens=case.expected_target_screens,
                source_artifact_path=source_capture.screenshot.artifact.path,
                destination_artifact_path=destination_capture.screenshot.artifact.path,
                destination_screen=destination_capture.observation.screen_type,
                missing_verification_selectors=missing_selectors,
                observed_selectors=_sorted_selector_ids(destination_capture.observation),
            ),
            destination_capture,
        )

    def _maybe_retry_with_stronger_resolution(
        self,
        *,
        case: NavigationSelectorValidationCase,
        source_capture: CapturedObservation,
        first_destination_capture: CapturedObservation,
        first_missing_selectors: tuple[UiElementId, ...],
        case_index: int,
    ) -> tuple[NavigationSelectorValidationResult, CapturedObservation] | None:
        """Retries one navigation validation once when the first tap came from geometry fallback."""

        source_element = source_capture.observation.get(case.selector_id)
        if source_element is None or source_element.source is None:
            return None
        if source_element.source.resolution_kind.value != "relative_bounds":
            return None
        selector = self.selector_registry.require(case.selector_id)
        if not selector.resolution.stronger_step_indexes(source_element.source.strategy_index):
            return None
        retry_source_capture = self._prepare_source_capture(case, first_destination_capture, case_index=case_index)
        retry_source_element = retry_source_capture.observation.require(case.selector_id)
        if retry_source_element.source is None or retry_source_element.source.strategy_index >= source_element.source.strategy_index:
            return None
        retry_destination_capture = self._execute_actions(
            (
                TapAction(
                    selector_id=case.selector_id,
                    reason="retry_navigation_selector_with_stronger_resolution",
                    observe_after=True,
                ),
            ),
            retry_source_capture,
            label_prefix=f"navigation_validation_{case_index}_retry_{case.selector_id.value.lower()}",
        )
        retry_destination_capture = self._settle_destination_capture(
            case,
            retry_destination_capture,
            case_index=case_index,
        )
        matched_outcome, missing_selectors = match_reviewed_navigation_outcome(
            retry_destination_capture.observation,
            case.reviewed_outcomes,
        )
        if matched_outcome is not None:
            return (
                NavigationSelectorValidationResult(
                    selector_id=case.selector_id,
                    source_screen=case.source_screen,
                    status=NavigationValidationStatus.PASSED,
                    reason="Observed destination matched a reviewed click outcome after one stronger selector-resolution retry.",
                    expected_target_screens=case.expected_target_screens,
                    source_artifact_path=source_capture.screenshot.artifact.path,
                    destination_artifact_path=first_destination_capture.screenshot.artifact.path,
                    destination_screen=retry_destination_capture.observation.screen_type,
                    matched_target_screen=matched_outcome.target_screen,
                    observed_selectors=_sorted_selector_ids(retry_destination_capture.observation),
                    retry_attempted=True,
                    retry_source_artifact_path=retry_source_capture.screenshot.artifact.path,
                    retry_destination_artifact_path=retry_destination_capture.screenshot.artifact.path,
                ),
                retry_destination_capture,
            )
        reason = (
            "Observed destination still missed reviewed verification selectors after one stronger selector-resolution retry."
            if missing_selectors or first_missing_selectors
            else "Observed destination did not match any reviewed click outcome after one stronger selector-resolution retry."
        )
        return (
            NavigationSelectorValidationResult(
                selector_id=case.selector_id,
                source_screen=case.source_screen,
                status=NavigationValidationStatus.FAILED,
                reason=reason,
                expected_target_screens=case.expected_target_screens,
                source_artifact_path=source_capture.screenshot.artifact.path,
                destination_artifact_path=first_destination_capture.screenshot.artifact.path,
                destination_screen=retry_destination_capture.observation.screen_type,
                missing_verification_selectors=missing_selectors,
                observed_selectors=_sorted_selector_ids(retry_destination_capture.observation),
                retry_attempted=True,
                retry_source_artifact_path=retry_source_capture.screenshot.artifact.path,
                retry_destination_artifact_path=retry_destination_capture.screenshot.artifact.path,
            ),
            retry_destination_capture,
        )

    def _settle_destination_capture(
        self,
        case: NavigationSelectorValidationCase,
        destination_capture: CapturedObservation,
        *,
        case_index: int,
    ) -> CapturedObservation:
        """Waits through transient post-click states and dismisses blocking popups before evaluating the result."""

        latest_capture = destination_capture
        for settle_index in range(self.max_destination_settle_observations):
            matched_outcome, _ = match_reviewed_navigation_outcome(
                latest_capture.observation,
                case.reviewed_outcomes,
            )
            if matched_outcome is not None:
                return latest_capture
            if latest_capture.observation.blocking_popup or latest_capture.observation.screen_type == ScreenType.PNC_POPUP:
                latest_capture = self._execute_actions(
                    self.screen_flows.close_blocking_popup(latest_capture.observation),
                    latest_capture,
                    label_prefix=f"navigation_validation_{case_index}_settle_popup_{settle_index + 1}",
                )
                continue
            if settle_index == self.max_destination_settle_observations - 1:
                break
            self._sleep_for_destination_settle()
            latest_capture = self.observation_service.capture_observation(
                f"navigation_validation_{case_index}_settle_{settle_index + 1}"
            )
        return latest_capture

    def _recover_to_home(
        self,
        current_capture: CapturedObservation,
        *,
        case_index: int,
        step_label: str,
    ) -> CapturedObservation:
        """Returns the live session to home city before or after one navigation validation case."""

        latest_capture = current_capture
        for step_index in range(self.max_recovery_steps):
            observation = latest_capture.observation
            if observation.screen_type == ScreenType.PNC_HOME_CITY and not observation.blocking_popup:
                return latest_capture
            planned_actions = self.screen_flows.ensure_home_city(observation)
            if not planned_actions:
                return latest_capture
            latest_capture = self._execute_actions(
                planned_actions,
                latest_capture,
                label_prefix=f"navigation_validation_{case_index}_{step_label}_{step_index + 1}",
            )
        raise SelectorResolutionError(
            "Could not recover the live validation session to home city within the configured step budget.",
            max_recovery_steps=self.max_recovery_steps,
            observed_screen=latest_capture.observation.screen_type.name,
            artifact_path=str(latest_capture.screenshot.artifact.path),
        )

    def _execute_actions(
        self,
        actions: Sequence[object],
        current_capture: CapturedObservation,
        *,
        label_prefix: str,
    ) -> CapturedObservation:
        """Executes one observed action sequence and returns the latest captured observation."""

        latest_capture: CapturedObservation | None = None

        def observe(label: str) -> Observation:
            nonlocal latest_capture
            latest_capture = self.observation_service.capture_observation(f"{label_prefix}_{label}")
            return latest_capture.observation

        self.action_executor.execute_actions(actions, current_capture.observation, observe=observe)
        if latest_capture is None:
            latest_capture = self.observation_service.capture_observation(f"{label_prefix}_confirm")
        return latest_capture

    def _sleep_for_destination_settle(self) -> None:
        """Applies the standard post-action settle delay between passive follow-up observations."""

        delay_ms = self.action_executor.post_action_observe_delay_ms
        if delay_ms <= 0:
            return
        self.sleep(delay_ms / 1000.0)


def build_navigation_validation_cases(
    selector_registry: SelectorRegistry,
    *,
    selector_ids: Sequence[UiElementId] | None = None,
) -> tuple[NavigationSelectorValidationCase, ...]:
    """Returns the reviewed navigation cases that should be live-validated from the registry."""

    requested_selector_ids = None if selector_ids is None or not selector_ids else frozenset(selector_ids)
    cases: list[NavigationSelectorValidationCase] = []
    for selector in selector_registry.all():
        if selector.interaction_kind != SelectorInteractionKind.NAVIGATION:
            continue
        if requested_selector_ids is not None and selector.id not in requested_selector_ids:
            continue
        safe_outcomes = tuple(outcome for outcome in selector.click_outcomes if outcome.safe_to_click)
        for source_screen in selector.screens:
            cases.append(
                NavigationSelectorValidationCase(
                    selector_id=selector.id,
                    source_screen=source_screen,
                    reviewed_outcomes=safe_outcomes,
                )
            )
    return tuple(sorted(cases, key=lambda case: (case.source_screen.value, case.selector_id.value)))


def match_reviewed_navigation_outcome(
    destination_observation: Observation,
    reviewed_outcomes: Sequence[ClickOutcome],
) -> tuple[ClickOutcome | None, tuple[UiElementId, ...]]:
    """Returns the reviewed click outcome that matches the observed destination, if any."""

    closest_missing_selectors: tuple[UiElementId, ...] = ()
    for outcome in reviewed_outcomes:
        if outcome.target_screen is not None and destination_observation.screen_type != outcome.target_screen:
            continue
        missing_selectors = tuple(
            selector_id
            for selector_id in outcome.verification_selectors
            if not destination_observation.has(selector_id)
        )
        if not missing_selectors:
            return outcome, ()
        if not closest_missing_selectors or len(missing_selectors) < len(closest_missing_selectors):
            closest_missing_selectors = missing_selectors
    return None, closest_missing_selectors


def write_navigation_selector_validation_report(path: Path, report: NavigationSelectorValidationReport) -> None:
    """Writes one YAML navigation-selector validation report to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(report.to_document(), sort_keys=False), encoding="utf-8", newline="\n")


def _plan_navigation_source_actions(
    *,
    case: NavigationSelectorValidationCase,
    observation: Observation,
    screen_flows: ScreenFlowPlanner,
) -> list[object]:
    """Plans one conservative step that moves the live session toward the selector's declared source state."""

    if case.source_screen == ScreenType.PNC_HOME_CITY:
        return screen_flows.ensure_home_city(observation)
    if case.source_screen == ScreenType.PNC_WORLD_MAP:
        return screen_flows.open_world_map(observation)
    if case.source_screen != ScreenType.PNC_MORE_MENU:
        raise SelectorResolutionError(
            "Navigation selector validation does not support the declared source screen yet.",
            selector_id=case.selector_id.value,
            source_screen=case.source_screen.name,
        )
    if observation.screen_type != ScreenType.PNC_MORE_MENU:
        return screen_flows.open_more_menu(observation)
    if observation.has(case.selector_id):
        return []
    if observation.has(UiElementId.PNC_MORE_SETTINGS) and case.selector_id != UiElementId.PNC_MORE_SETTINGS:
        return [
            TapAction(
                selector_id=UiElementId.PNC_MORE_SETTINGS,
                reason="expose_more_menu_selector",
                observe_after=True,
            )
        ]
    return []


def _sorted_selector_ids(observation: Observation) -> tuple[UiElementId, ...]:
    """Returns the visible selector ids in deterministic enum-value order for report serialization."""

    return tuple(sorted(observation.visible_elements, key=lambda selector_id: selector_id.value))
