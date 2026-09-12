"""Bounded workflow contracts for the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Protocol, TypeVar

from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.mail import MailboxAvailability, MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class WorkflowEffect(StrEnum):
    """Declares whether a workflow is allowed through the read-only core runner."""

    READ_ONLY = "read_only"
    RESOURCE_CHANGING = "resource_changing"


@dataclass(frozen=True, slots=True)
class WorkflowSpec:
    """Defines the reviewed lifecycle and effect policy for one core workflow."""

    name: str
    entry_screen: ScreenType
    exit_screen: ScreenType
    effect: WorkflowEffect

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

    __slots__ = ("_runtime", "_last_navigation_count", "_last_observation")

    def __init__(self, runtime: CoreRuntime, *, last_observation: Observation) -> None:
        """Starts a context after the runner has confirmed the workflow entry screen."""

        self._runtime = runtime
        self._last_navigation_count = runtime.observation_count
        self._last_observation = last_observation

    def navigate(self, target: ScreenType) -> Observation:
        """Navigates through the reviewed graph and records the fresh completion observation."""

        if not isinstance(target, ScreenType) or target == ScreenType.UNKNOWN:
            raise ValueError("Workflow navigation requires a known screen target.")
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

    def _observe_mail_content(self, label: str) -> Observation:
        """Capture fresh mail content for one constrained operation."""

        observation = self._runtime.observe(label, include_content=True)
        if self._runtime.observation_count <= self._last_navigation_count:
            raise RuntimeError("Mail operation content was not captured after the previous workflow observation.")
        if self._last_observation is not None and observation.captured_at <= self._last_observation.captured_at:
            raise RuntimeError("Mail operation content was stale relative to the previous workflow observation.")
        if observation.blocking_popup:
            raise RuntimeError("Mail operation content encountered a blocking popup.")
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

    def run(self, workflow: CoreWorkflow[T]) -> CoreWorkflowResult[T]:
        """Runs one read-only workflow and returns only after confirmed exit."""

        spec = workflow.spec
        if not isinstance(spec, WorkflowSpec):
            raise TypeError("Core workflows must expose a validated WorkflowSpec.")
        if spec.effect != WorkflowEffect.READ_ONLY:
            self.runtime.record(
                {
                    "event": "workflow_rejected",
                    "workflow": spec.name,
                    "effect": spec.effect.value if isinstance(spec.effect, WorkflowEffect) else "invalid",
                }
            )
            raise PermissionError("The replacement core runner permits read-only workflows only.")
        self.runtime.record({"event": "workflow_started", "workflow": spec.name, "effect": spec.effect.value})
        try:
            entry = self.runtime.navigation.navigate(spec.entry_screen)
            context = WorkflowContext(self.runtime, last_observation=entry)
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
