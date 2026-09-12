"""Shared connected runtime composition for the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from pnc_automation.app.authoring.config.models import AccountConfig, CastleIdentity, LiveAutomationRole
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.domain.observation import CurrentCastleEvidenceKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.automation.engine.script_runner import ConnectedAccountRuntime, ScriptRunner
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


@dataclass(slots=True)
class CoreRuntime:
    """Owns one connected runtime, pure screenshot perception, and reviewed navigation."""

    runtime: ConnectedAccountRuntime
    navigation: NavigationCore
    artifact_directory: str
    trace_path: Path
    _perception: NavigationPerception
    _run_id: str
    _observed_action_executor: ObservedActionExecutor | None = None
    _capture_count: int = 0
    _last_observation: Observation | None = None
    _last_observe_recovered: bool = False

    def close(self) -> None:
        """Releases the connected runtime owned by this replacement-core operation."""

        self.runtime.close()

    def __enter__(self) -> "CoreRuntime":
        """Enters an explicitly scoped replacement-core runtime."""

        return self

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the replacement-core runtime on exit."""

        self.close()

    @property
    def observation_count(self) -> int:
        """Returns the number of fresh screenshots captured by this core runtime."""

        return self._capture_count

    @property
    def last_observation(self) -> Observation | None:
        """Returns the latest observation, including one from a failed transition attempt."""

        return self._last_observation

    def observe(self, label: str, *, include_content: bool = False) -> Observation:
        """Captures one frame, then delegates safe interruption recovery to the connected executor."""

        self._last_observe_recovered = False
        observation = self._observe_once(label, include_content=include_content)
        if self._observed_action_executor is None:
            return observation
        recovered = self._observed_action_executor.recover_interruption_if_required(
            observation,
            label_prefix=f"core_{self._run_id}_{sanitize_artifact_segment(label)}_interruption",
            observe=lambda recovery_label, request=None: self._observe_once(
                recovery_label,
                include_content=include_content,
            ),
        )
        if recovered is None:
            return observation
        self._last_observe_recovered = True
        return recovered

    def _observe_once(self, label: str, *, include_content: bool) -> Observation:
        """Captures and perceives one frame without recursively entering popup recovery."""

        self._capture_count += 1
        capture_label = (
            f"core_{self._run_id}_{self._capture_count:04d}_{sanitize_artifact_segment(label)}"
        )
        screenshot = self.runtime.observation_service.screenshot_service.capture(
            self.runtime.session,
            artifact_directory=self.artifact_directory,
            label=capture_label,
            persist=True,
        )
        self.record(
            {
                "event": "capture",
                "artifact": None if screenshot.artifact_path is None else str(screenshot.artifact_path),
                "include_content": include_content,
            }
        )
        observation = self._perception.build(screenshot, include_content=include_content)
        self._last_observation = observation
        self.record(
            {
                "event": "observation",
                "screen": observation.screen_type.name,
                "blocked": observation.blocking_popup,
                "artifact": None if observation.artifact_path is None else str(observation.artifact_path),
                "include_content": include_content,
            }
        )
        return observation

    def record(self, entry: dict[str, object]) -> None:
        """Appends sanitized navigation metadata to the run's JSONL trace."""

        safe_entry = _sanitize_trace_entry(entry)
        with self.trace_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(safe_entry, sort_keys=True, default=str) + "\n")

    def preflight_active_castle_identity(self) -> CastleIdentity:
        """Verifies the active castle through Manage Characters without switching it."""

        self.runtime.session.ensure_app_foregrounded()
        self._settle_initial_screen()
        selection_observation = self.navigation.navigate(ScreenType.PNC_CASTLE_SELECTION)
        identity = self.observe("active_castle_identity", include_content=True)
        if identity.captured_at <= selection_observation.captured_at:
            raise RuntimeError("Active castle identity capture was stale relative to navigation completion.")
        if identity.blocking_popup:
            raise RuntimeError("Active castle identity was blocked by a popup; no recovery action was sent.")
        if identity.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise RuntimeError("Active castle identity preflight reached an unexpected screen.")
        if identity.current_castle is None:
            raise RuntimeError("Active castle identity was not observed; no castle switch is allowed.")
        if identity.resolved_current_castle_evidence != CurrentCastleEvidenceKind.EXACT:
            raise RuntimeError("Active castle identity lacked exact Manage Characters evidence.")
        self.record({"event": "active_castle_identity_verified", "screen": identity.screen_type.name})
        self.navigation.navigate(ScreenType.PNC_HOME_CITY)
        return identity.current_castle

    def _settle_initial_screen(self) -> Observation:
        """Waits passively through loading until a known screen is stable."""

        policy = self.navigation.policy
        started = self.navigation.clock()
        previous_screen = ScreenType.UNKNOWN
        previous_captured_at = None
        stable = 0
        for index in range(policy.max_observations):
            if self.navigation.clock() - started >= policy.max_seconds:
                break
            observation = self.observe(f"preflight_settle_{index}")
            if self._last_observe_recovered:
                # Popup recovery owns an independent bounded episode. Restart
                # only this passive settle clock and stability state before
                # counting its fresh known result.
                started = self.navigation.clock()
                previous_screen = ScreenType.UNKNOWN
                stable = 0
            elapsed = self.navigation.clock() - started
            if previous_captured_at is not None and observation.captured_at <= previous_captured_at:
                raise RuntimeError("Preflight received a stale capture while settling the initial screen.")
            previous_captured_at = observation.captured_at
            if observation.blocking_popup:
                raise RuntimeError("Preflight encountered a blocking popup; no recovery action was sent.")
            if observation.screen_type == ScreenType.UNKNOWN:
                raise RuntimeError("Preflight encountered an unknown screen; no recovery action was sent.")
            if observation.screen_type == ScreenType.PNC_LOADING:
                stable = 0
            else:
                stable = stable + 1 if observation.screen_type == previous_screen else 1
                if elapsed < policy.max_seconds and stable >= policy.stable_observations:
                    return observation
            previous_screen = observation.screen_type
            if self.navigation.clock() - started >= policy.max_seconds:
                break
            self.navigation.sleep(policy.poll_seconds)
        raise RuntimeError("Preflight loading settle budget exhausted without a stable known screen.")


def build_core_runtime(
    script_runner: ScriptRunner,
    account: AccountConfig,
    artifact_directory: str,
    policy: NavigationPolicy | None = None,
    *,
    trace_path: Path | None = None,
    required_role: LiveAutomationRole | None = None,
) -> CoreRuntime:
    """Builds exactly one connected runtime graph for replacement-core work."""

    if not artifact_directory.strip():
        raise ValueError("Core runtime artifact_directory cannot be empty.")
    connected_runtime = script_runner.build_connected_runtime(
        account=account,
        required_role=required_role,
    )
    try:
        return _assemble_core_runtime(
            script_runner=script_runner,
            connected_runtime=connected_runtime,
            account=account,
            artifact_directory=artifact_directory,
            policy=policy,
            trace_path=trace_path,
        )
    except BaseException:
        connected_runtime.close()
        raise


def _assemble_core_runtime(
    *,
    script_runner: ScriptRunner,
    connected_runtime: ConnectedAccountRuntime,
    account: AccountConfig,
    artifact_directory: str,
    policy: NavigationPolicy | None,
    trace_path: Path | None,
) -> CoreRuntime:
    """Assembles replacement-core services while the caller owns the connected runtime."""

    observed_action_executor = connected_runtime.require_observed_action_executor(
        "Replacement navigation requires the canonical selector-backed action executor."
    )
    recognizer = connected_runtime.observation_service.observation_builder.visual_recognizer
    if recognizer is None:
        raise RuntimeError("Replacement navigation requires the reviewed visual catalog.")
    perception = NavigationPerception(
        recognizer,
        connected_runtime.observation_service.observation_builder.enricher,
    )
    run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    resolved_trace_path = trace_path or _default_trace_path(
        script_runner=script_runner,
        artifact_directory=artifact_directory,
        run_id=run_id,
    )
    resolved_trace_path.parent.mkdir(parents=True, exist_ok=True)
    holder: dict[str, CoreRuntime] = {}

    def observe(label: str) -> Observation:
        """Adapts the core's identity-only callback to the shared runtime object."""

        return holder["runtime"].observe(label)

    def record(entry: dict[str, object]) -> None:
        """Routes core events through the runtime's sanitized trace writer."""

        holder["runtime"].record(entry)

    navigation = NavigationCore(
        observed_action_executor.action_executor,
        observe,
        reviewed_navigation_edges(),
        policy=policy or NavigationPolicy(),
        record=record,
    )
    result = CoreRuntime(
        runtime=connected_runtime,
        navigation=navigation,
        artifact_directory=artifact_directory,
        trace_path=resolved_trace_path,
        _perception=perception,
        _run_id=run_id,
        _observed_action_executor=observed_action_executor,
    )
    holder["runtime"] = result
    return result


def _default_trace_path(*, script_runner: ScriptRunner, artifact_directory: str, run_id: str) -> Path:
    """Returns a unique trace path under the canonical artifact root."""

    artifact_root = script_runner.config.artifact_root
    return (
        artifact_root
        / datetime.now(tz=UTC).strftime("%Y-%m-%d")
        / sanitize_artifact_segment(artifact_directory)
        / f"{run_id}_core_trace.jsonl"
    )


def _sanitize_trace_entry(entry: dict[str, object]) -> dict[str, object]:
    """Keeps traces to stable navigation metadata and strips identity-bearing values."""

    allowed = {
        "event",
        "source",
        "selector",
        "target",
        "screen",
        "blocked",
        "include_content",
        "artifact",
        "error_type",
        "workflow",
        "effect",
        "identity_verified",
    }
    safe: dict[str, object] = {}
    for key, value in entry.items():
        if key not in allowed:
            continue
        if key == "artifact":
            safe[key] = None if value is None else Path(str(value)).name
        elif key in {"blocked", "include_content", "identity_verified"}:
            safe[key] = bool(value)
        elif value is not None:
            safe[key] = str(value)
    return safe
