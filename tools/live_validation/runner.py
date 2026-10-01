"""The tracked bounded live-case runner for released V44 assignments.

One run reserves exactly one configured account through the canonical
``ApplicationRunner``/``ScriptRunner`` path, attaches one
``input_dispatch_observer``, executes each selected frozen case through the
existing ``CoreRuntime`` seams, and produces exactly one result per selected
case plus one serialized v3 evidence document. The runner owns attribution,
journaling, and curation only — it holds no scheduler, permission engine,
parallel capture path, or incident index of its own.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pnc_automation.app.automation.engine.developmental_control import (
    BodyEntryWitness,
    DevelopmentalControlScope,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    TapDispatch,
)

from tools.live_validation.annotation import AnnotationExchange
from tools.live_validation.binding import (
    AssignmentBinding,
    CaseSelection,
    binding_static_findings,
)
from tools.live_validation.cases import (
    BODY_ENTRY_OPERATION_ID,
    CaseGate,
    CasePurpose,
    CaseSpec,
    frozen_case_ids,
    require_case,
)
from tools.live_validation.evidence import (
    ArtifactRef,
    CaseResult,
    CaseStatus,
    LiveEvidence,
    LogicalAttemptRecord,
    collect_artifact,
    compute_totals,
    frame_ref_dict,
    now_utc,
    sha256_file,
    write_live_evidence,
)
from tools.live_validation.events import AttributionPhase, DispatchCollector
from tools.live_validation.journal import AttemptStatus, LogicalAttemptJournal


_NAV_INPUT_ALLOWANCE_PER_CASE = 24
_BASE_INPUT_ALLOWANCE = 16
_POSTCONDITION_MAX_CAPTURES = 4
_POSTCONDITION_POLL_SECONDS = 1.0


class PreflightRefusal(RuntimeError):
    """The run cannot start under this released assignment; nothing connected."""

    def __init__(self, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))


@dataclass(frozen=True, slots=True)
class SourceProbe:
    """The runner-owned read of the candidate's Git state."""

    head_sha: str
    dirty_paths: tuple[str, ...]
    source_root: Path

    @property
    def tree_clean(self) -> bool:
        return not self.dirty_paths


@dataclass(slots=True)
class LiveConnection:
    """Owns the leased session graph for one run.

    ``core.close()`` ends the session and restores the input recorder;
    ``bundle.close()`` releases the canonical account/instance leases. Both are
    recorded into the evidence cleanup block.
    """

    bundle: Any
    core: Any
    account: Any


@dataclass(frozen=True, slots=True)
class RunnerDeps:
    """Composition seams; the CLI supplies the real implementations."""

    probe_source: Callable[[AssignmentBinding], SourceProbe]
    connect: Callable[..., LiveConnection]
    annotation_factory: Callable[[Path], AnnotationExchange] | None
    now_utc: Callable[[], datetime] = now_utc
    sleep: Callable[[float], None] = time.sleep
    postcondition_timeout_seconds: float = 30.0
    operation_budget_seconds: float = 2700.0


def git_source_probe(binding: AssignmentBinding) -> SourceProbe:
    """Reads HEAD and the porcelain diff inside the bound source root."""

    def _git(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=binding.source_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    head = _git("rev-parse", "HEAD")
    porcelain = _git("status", "--porcelain", "--untracked-files=all")
    dirty = tuple(line for line in porcelain.splitlines() if line.strip())
    return SourceProbe(
        head_sha=head,
        dirty_paths=dirty,
        source_root=binding.source_root,
    )


def _is_guarded_home(observation: Observation) -> bool:
    return (
        observation.screen_type is ScreenType.PNC_HOME_CITY
        and not observation.blocking_popup
        and observation.decision.guard is GuardVerdict.CLEAR
    )


def _detail(error: BaseException) -> str:
    message = str(error).strip()
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


class LiveCaseRunner:
    """Executes one released assignment's selected cases against one session."""

    def __init__(self, binding: AssignmentBinding, deps: RunnerDeps) -> None:
        self._binding = binding
        self._deps = deps
        self._specs = {selection.case_id: require_case(selection.case_id)
                       for selection in binding.selected_cases}
        self._artifact_index: dict[Path, ArtifactRef] = {}

    def run(self) -> tuple[LiveEvidence, Path]:
        """Runs preflight, the selected cases, cleanup, and terminal check."""

        self._preflight_static()
        probe = self._deps.probe_source(self._binding)
        self._preflight_probe(probe)

        run_dir = self._binding.report_root / self._binding.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        journal = LogicalAttemptJournal(run_dir / "attempts.jsonl")
        collector = DispatchCollector()
        started = self._deps.now_utc()

        results: list[CaseResult] = []
        attempts: list[LogicalAttemptRecord] = []
        observed_final_state: dict[str, Any] = {
            "screen_type": None,
            "blocking_popup": None,
            "artifact_path": None,
            "frame_fingerprint": None,
        }
        cleanup: dict[str, Any] = {
            "session_closed": False,
            "lease_released": False,
            "observer_restored": False,
            "instance_preserved": True,
            "reservation_disposition": self._binding.reservation_disposition,
        }
        coverage_start = started
        connection: LiveConnection | None = None
        run_broken: str | None = None
        try:
            with collector.phase(AttributionPhase.SETUP):
                connection = self._deps.connect(
                    binding=self._binding,
                    run_dir=run_dir,
                    observer=collector.append,
                )
                executor = connection.core.runtime.require_observed_action_executor(
                    "V44 live validation requires the canonical selector-backed action executor."
                ).action_executor
                executor.configure_input_attempt_budget(
                    self._input_budget(),
                    duration_seconds=self._deps.operation_budget_seconds,
                )
                identity = connection.core.preflight_active_castle_identity()
                actual_castle = f"{identity.kingdom}:{identity.castle_name}"
                if actual_castle != self._binding.target_castle_ref:
                    raise PreflightRefusal((
                        f"active castle '{actual_castle}' does not match the "
                        f"bound target '{self._binding.target_castle_ref}'.",
                    ))
            installed_recorder = executor.input_dispatch_recorder
            for selection in self._binding.selected_cases:
                spec = self._specs[selection.case_id]
                if run_broken is not None:
                    results.append(
                        CaseResult(
                            case_id=spec.case_id,
                            purpose=spec.purpose.value,
                            status=CaseStatus.NOT_RUN,
                            artifacts=(),
                            receipt_event_ids=(),
                            dispatch_event_ids=(),
                            body_entry_event_id=None,
                            source_artifact=None,
                            follow_up_artifact=None,
                            unresolved_boundary=None,
                            detail=f"Run ended before this case: {run_broken}",
                        )
                    )
                    continue
                with collector.phase(AttributionPhase.CASE, case_id=spec.case_id):
                    try:
                        results.append(
                            self._run_case(
                                spec,
                                selection,
                                connection.core,
                                journal,
                                collector,
                                attempts,
                            )
                        )
                    except Exception as error:  # noqa: BLE001 - evidence, not control flow
                        run_broken = _detail(error)
                        results.append(
                            self._case_outcome(
                                spec,
                                collector,
                                mark=None,
                                status=CaseStatus.FAILED,
                                detail=f"Unattributed run failure: {_detail(error)}",
                                unresolved_boundary="runtime_session",
                            )
                        )
            with collector.phase(AttributionPhase.CLEANUP):
                try:
                    final = connection.core.capture_once(
                        "v44_final_state", include_content=True
                    )
                    observed_final_state.update(
                        {
                            "screen_type": final.screen_type.value,
                            "blocking_popup": final.blocking_popup,
                            "artifact_path": (
                                None
                                if final.artifact_path is None
                                else str(final.artifact_path)
                            ),
                            "frame_fingerprint": final.frame_fingerprint,
                        }
                    )
                    self._curate(
                        final.artifact_path,
                        kind="final_state_frame",
                        purpose="Observed final screen state after cleanup.",
                        artifacts=[],
                    )
                except Exception as error:  # noqa: BLE001
                    observed_final_state["capture_error"] = _detail(error)
                try:
                    connection.core.close()
                    cleanup["session_closed"] = True
                    cleanup["observer_restored"] = (
                        executor.input_dispatch_recorder is not installed_recorder
                    )
                except Exception as error:  # noqa: BLE001
                    cleanup["session_close_error"] = _detail(error)
        finally:
            if connection is not None:
                try:
                    connection.bundle.close()
                    cleanup["lease_released"] = True
                except Exception as error:  # noqa: BLE001
                    cleanup["lease_release_error"] = _detail(error)
            journal.close()

        finished = self._deps.now_utc()
        terminal_probe = self._deps.probe_source(self._binding)
        terminal_check = {
            "head_matches": terminal_probe.head_sha == self._binding.candidate_sha,
            "tree_clean": terminal_probe.tree_clean,
            "dirty_paths": list(terminal_probe.dirty_paths),
            "checked_at": finished.isoformat(),
        }
        evidence = LiveEvidence(
            assignment_id=self._binding.assignment_id,
            run_id=self._binding.run_id,
            candidate_sha=self._binding.candidate_sha,
            source_root=self._binding.source_root,
            import_root=self._binding.import_root,
            report_root=self._binding.report_root,
            entry_point=self._binding.entry_point,
            entry_sha256=self._binding.entry_sha256,
            started_at=started,
            finished_at=finished,
            actual_target={
                "account_id": self._binding.target_account_id,
                "castle": self._binding.target_castle_ref,
                "instance_id": self._binding.target_instance_id,
                "live_role": self._binding.target_role,
            },
            case_results=tuple(results),
            artifacts=tuple(self._artifact_index.values()),
            attributed_dispatches=collector.events,
            logical_attempts=tuple(attempts),
            incident_refs=(),
            resource_actions=(),
            coverage={
                "start": coverage_start.isoformat(),
                "end": finished.isoformat(),
                "unsupported_input_primitives": ["keypress", "text_payload"],
            },
            observed_final_state=observed_final_state,
            totals=compute_totals(collector.events, tuple(attempts)),
            cleanup=cleanup,
            terminal_binding_check=terminal_check,
        )
        path = write_live_evidence(
            evidence, run_dir / "live_evidence.json"
        )
        return evidence, path

    # -- preflight -----------------------------------------------------------

    def _preflight_static(self) -> None:
        findings = binding_static_findings(self._binding, case_ids=frozen_case_ids())
        for selection in self._binding.selected_cases:
            spec = self._specs[selection.case_id]
            if selection.params != dict(spec.params):
                findings.append(
                    f"case '{selection.case_id}' params {selection.params!r} do not "
                    f"equal the frozen spec params {dict(spec.params)!r}."
                )
        needs_allowance = any(
            spec.control_effect is WorkflowEffect.RESOURCE_CHANGING
            for spec in self._specs.values()
        )
        if needs_allowance and not self._binding.resource_allowance_ref:
            findings.append(
                "a selected case changes resources but the assignment names no "
                "resource_allowance_ref."
            )
        if any(spec.purpose is CasePurpose.ACCEPTANCE for spec in self._specs.values()):
            findings.append(
                "acceptance cases are not executable by the tracked runner; "
                "a captured menu never satisfies an acceptance route."
            )
        if findings:
            raise PreflightRefusal(tuple(findings))

    def _preflight_probe(self, probe: SourceProbe) -> None:
        findings: list[str] = []
        if probe.head_sha != self._binding.candidate_sha:
            findings.append(
                f"HEAD {probe.head_sha} does not match the bound candidate "
                f"{self._binding.candidate_sha}."
            )
        if not probe.tree_clean:
            findings.append(
                f"source tree is not clean: {list(probe.dirty_paths)[:5]}"
            )
        entry = self._binding.entry_point
        if not entry.exists():
            findings.append(f"entry point does not exist: {entry}")
        elif sha256_file(entry) != self._binding.entry_sha256:
            findings.append(f"entry point sha256 mismatch: {entry}")
        for ref in self._binding.offline_evidence:
            if not ref.path.exists():
                findings.append(f"required offline evidence missing: {ref.path}")
            elif sha256_file(ref.path) != ref.sha256:
                findings.append(f"offline evidence sha256 mismatch: {ref.path}")
        if findings:
            raise PreflightRefusal(tuple(findings))

    def _input_budget(self) -> int:
        controls = sum(spec.max_control_attempts for spec in self._specs.values())
        return (
            _BASE_INPUT_ALLOWANCE
            + _NAV_INPUT_ALLOWANCE_PER_CASE * len(self._binding.selected_cases)
            + controls
        )

    # -- case execution --------------------------------------------------------

    def _run_case(
        self,
        spec: CaseSpec,
        selection: CaseSelection,
        core: Any,
        journal: LogicalAttemptJournal,
        collector: DispatchCollector,
        attempts: list[LogicalAttemptRecord],
    ) -> CaseResult:
        if spec.purpose is CasePurpose.DISCOVERY:
            return self._run_discovery(spec, core, collector)
        if spec.purpose is CasePurpose.DEVELOPMENT_VALIDATION:
            return self._run_validation(spec, core, journal, collector, attempts)
        return self._case_outcome(
            spec,
            collector,
            mark=None,
            status=CaseStatus.BLOCKED,
            detail="Acceptance cases are not executable by the tracked runner.",
            unresolved_boundary="acceptance_not_executable",
        )

    def _precondition_check(
        self,
        spec: CaseSpec,
        core: Any,
    ) -> str | None:
        """Returns the violated gate token, or None when all pass."""

        if CaseGate.GUARDED_HOME_CITY not in spec.required_preconditions:
            return None
        observation = core.capture_once(
            f"{spec.case_id}_precondition", include_content=True
        )
        if not _is_guarded_home(observation):
            return CaseGate.GUARDED_HOME_CITY.value
        return None

    def _run_discovery(
        self,
        spec: CaseSpec,
        core: Any,
        collector: DispatchCollector,
    ) -> CaseResult:
        mark = collector.mark()
        violated = self._precondition_check(spec, core)
        if violated is not None:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                detail=f"Precondition '{violated}' is not satisfied.",
                unresolved_boundary="precondition",
            )
        prepared: list[tuple[Observation, TapSpatialObjectAction]] = []
        try:
            source, action, follow_up = core.enter_building_body_for_discovery(
                spec.target,
                entry_effect=spec.entry_effect,
                on_body_prepared=lambda src, act: prepared.append((src, act)),
                home_city_slot=spec.home_city_slot,
            )
        except (SelectorResolutionError, HomeCityScanError) as error:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.FAILED,
                detail=f"Body entry refused by the qualified navigation seam: {_detail(error)}",
                unresolved_boundary="qualified_body_entry",
            )
        body_event_id = self._find_body_tap(collector, mark, source)
        status = CaseStatus.PASSED
        detail = "Qualified body entry sent and raw follow-up persisted."
        boundary = None
        if body_event_id is None:
            status = CaseStatus.FAILED
            detail = "Entry send returned without an attributed tap receipt."
            boundary = "entry_receipt"
        artifacts: list[ArtifactRef] = []
        self._curate(source.artifact_path, kind="source_frame",
                     purpose=f"{spec.case_id} authorizing source frame.", artifacts=artifacts)
        self._curate(follow_up.artifact_path, kind="follow_up_frame",
                     purpose=f"{spec.case_id} raw post-tap observed state.", artifacts=artifacts)
        return CaseResult(
            case_id=spec.case_id,
            purpose=spec.purpose.value,
            status=status,
            artifacts=tuple(artifacts),
            receipt_event_ids=tuple(
                attributed.event_id
                for attributed in collector.events_since(mark)
                if isinstance(attributed.event, InputDispatchRecord)
            ),
            dispatch_event_ids=tuple(
                attributed.event_id for attributed in collector.events_since(mark)
            ),
            body_entry_event_id=body_event_id,
            source_artifact=source.artifact_path,
            follow_up_artifact=follow_up.artifact_path,
            unresolved_boundary=boundary,
            detail=detail,
        )

    def _run_validation(
        self,
        spec: CaseSpec,
        core: Any,
        journal: LogicalAttemptJournal,
        collector: DispatchCollector,
        attempts: list[LogicalAttemptRecord],
    ) -> CaseResult:
        mark = collector.mark()
        if self._deps.annotation_factory is None:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                detail="No annotation exchange is configured for this run.",
                unresolved_boundary="annotation_unavailable",
            )
        violated = self._precondition_check(spec, core)
        if violated is not None:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                detail=f"Precondition '{violated}' is not satisfied.",
                unresolved_boundary="precondition",
            )
        prepared: list[tuple[Observation, TapSpatialObjectAction]] = []
        try:
            source, action, follow_up = core.enter_building_body_for_discovery(
                spec.target,
                entry_effect=spec.entry_effect,
                on_body_prepared=lambda src, act: prepared.append((src, act)),
                home_city_slot=spec.home_city_slot,
            )
        except (SelectorResolutionError, HomeCityScanError) as error:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                detail=f"Body entry refused before the control stage: {_detail(error)}",
                unresolved_boundary="qualified_body_entry",
            )
        body_event_id = self._find_body_tap(collector, mark, source)
        if body_event_id is None:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.FAILED,
                detail="Entry send returned without an attributed tap receipt.",
                unresolved_boundary="entry_receipt",
            )
        body_receipt = next(
            attributed.event
            for attributed in collector.events_since(mark)
            if attributed.event_id == body_event_id
        )
        witness = BodyEntryWitness(
            case_id=spec.case_id,
            operation_id=spec.operation_id,
            observation=source,
            action=action,
            receipt=body_receipt,
        )
        input_chain: list[InputDispatchRecord] = [body_receipt]
        latest_follow_up = follow_up
        current = follow_up
        artifacts: list[ArtifactRef] = []
        self._curate(source.artifact_path, kind="source_frame",
                     purpose=f"{spec.case_id} authorizing source frame.", artifacts=artifacts)
        self._curate(follow_up.artifact_path, kind="follow_up_frame",
                     purpose=f"{spec.case_id} post-entry observed state.", artifacts=artifacts)

        if current.screen_type not in spec.allowed_source_screens:
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                artifacts=artifacts,
                body_entry_event_id=body_event_id,
                source_artifact=source.artifact_path,
                follow_up_artifact=follow_up.artifact_path,
                detail=(
                    f"Post-entry screen '{current.screen_type.value}' is not an allowed "
                    f"source for control '{spec.control_name}'."
                ),
                unresolved_boundary="control_source_screen",
            )

        annotation = self._deps.annotation_factory(
            Path(self._binding.report_root) / self._binding.run_id / "annotation"
        )
        for attempt_number in range(1, spec.max_control_attempts + 1):
            if current.frame_ref is None:
                return self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    artifacts=artifacts,
                    body_entry_event_id=body_event_id,
                    source_artifact=source.artifact_path,
                    follow_up_artifact=follow_up.artifact_path,
                    detail="The control-source frame has no fresh provenance; no input authorized.",
                    unresolved_boundary="follow_up_provenance",
                )
            attempt_id, consumed = journal.begin(
                case_id=spec.case_id,
                control_name=spec.control_name or "",
                operation_id=spec.operation_id,
                number=attempt_number,
                limit=spec.max_control_attempts,
                source_frame=frame_ref_dict(current.frame_ref),
            )
            request = annotation.prepare(
                case_id=spec.case_id,
                control_name=spec.control_name or "",
                observation=current,
            )
            proof = annotation.await_proof(
                request, current, foreground_target=spec.target
            )
            if proof is None:
                journal.finish(attempt_id, status=AttemptStatus.ANNOTATION_TIMEOUT)
                attempts.append(
                    self._attempt_record(
                        attempt_id, consumed, "annotation_timeout", None
                    )
                )
                return self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    artifacts=artifacts,
                    body_entry_event_id=body_event_id,
                    source_artifact=source.artifact_path,
                    follow_up_artifact=follow_up.artifact_path,
                    detail="Tester annotation did not arrive before the bounded deadline.",
                    unresolved_boundary="annotation_timeout",
                )
            scope = DevelopmentalControlScope(
                assignment_id=self._binding.assignment_id,
                case_id=spec.case_id,
                case_spec_ref=spec.case_id,
                purpose=spec.developmental_purpose,
                operation_id=spec.operation_id,
                released_action_id=spec.released_action_id,
                control_name=spec.control_name or "",
                target=spec.target,
                home_city_slot=spec.home_city_slot,
                allowed_source_screens=spec.allowed_source_screens,
                effect=spec.control_effect or WorkflowEffect.READ_ONLY,
                read_only=False,
                resource_allowance_ref=(
                    self._binding.resource_allowance_ref
                    if spec.control_effect is WorkflowEffect.RESOURCE_CHANGING
                    else None
                ),
                attempt=consumed,
                body_entry=witness,
                input_chain=tuple(input_chain),
                latest_input_follow_up=latest_follow_up,
            )
            try:
                result = core.execute_developmental_control(scope, proof, current)
            except SelectorResolutionError as error:
                journal.finish(attempt_id, status=AttemptStatus.REFUSED,
                               detail=_detail(error))
                attempts.append(
                    self._attempt_record(attempt_id, consumed, "refused", None)
                )
                refreshed = core.capture_once(
                    f"{spec.case_id}_reproof_{attempt_number}", include_content=True
                )
                if (
                    refreshed.frame_ref is None
                    or proof.frame_ref.input_sequence != refreshed.frame_ref.input_sequence
                ):
                    return self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.FAILED,
                        artifacts=artifacts,
                        body_entry_event_id=body_event_id,
                        source_artifact=source.artifact_path,
                        follow_up_artifact=follow_up.artifact_path,
                        detail="Intervening input invalidated the refused frame chain.",
                        unresolved_boundary="intervening_input",
                    )
                current = refreshed
                self._curate(current.artifact_path, kind="reproof_frame",
                             purpose=f"{spec.case_id} fresh frame after a refused attempt.",
                             artifacts=artifacts)
                continue
            except Exception as error:  # noqa: BLE001 - uncertain send, never replay
                journal.finish(attempt_id, status=AttemptStatus.UNCERTAIN,
                               detail=_detail(error))
                attempts.append(
                    self._attempt_record(attempt_id, consumed, "uncertain", None)
                )
                return self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.FAILED,
                    artifacts=artifacts,
                    body_entry_event_id=body_event_id,
                    source_artifact=source.artifact_path,
                    follow_up_artifact=follow_up.artifact_path,
                    detail=f"Control dispatch ended uncertain; no replay: {_detail(error)}",
                    unresolved_boundary="uncertain_send",
                )
            event_id = collector.receipt_event_id(result.receipt, case_id=spec.case_id)
            journal.finish(attempt_id, status=AttemptStatus.DISPATCHED,
                           dispatch_event_id=event_id)
            attempts.append(
                self._attempt_record(attempt_id, consumed, "dispatched", event_id)
            )
            input_chain.append(result.receipt)
            latest_follow_up = result.follow_up
            self._curate(result.follow_up.artifact_path, kind="follow_up_frame",
                         purpose=f"{spec.case_id} immediate post-control observed state.",
                         artifacts=artifacts)
            final, satisfied = self._await_postcondition(spec, core)
            if satisfied:
                self._curate(
                    final.artifact_path if final is not None else None,
                    kind="postcondition_frame",
                    purpose=f"{spec.case_id} guarded Home return evidence.",
                    artifacts=artifacts,
                )
                return self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.PASSED,
                    artifacts=artifacts,
                    body_entry_event_id=body_event_id,
                    source_artifact=source.artifact_path,
                    follow_up_artifact=(
                        final.artifact_path if final is not None else follow_up.artifact_path
                    ),
                    detail="Control dispatched and the guarded Home postcondition was observed.",
                    unresolved_boundary=None,
                )
            return self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.FAILED,
                artifacts=artifacts,
                body_entry_event_id=body_event_id,
                source_artifact=source.artifact_path,
                follow_up_artifact=follow_up.artifact_path,
                detail="Control dispatched but the guarded Home postcondition was not observed.",
                unresolved_boundary="postcondition",
            )
        return self._case_outcome(
            spec, collector, mark=mark, status=CaseStatus.FAILED,
            artifacts=artifacts,
            body_entry_event_id=body_event_id,
            source_artifact=source.artifact_path,
            follow_up_artifact=follow_up.artifact_path,
            detail="Control attempt budget exhausted before a dispatch.",
            unresolved_boundary="attempt_budget",
        )

    def _await_postcondition(
        self, spec: CaseSpec, core: Any
    ) -> tuple[Observation | None, bool]:
        """Passively re-observes until the case's required gates hold."""

        if CaseGate.GUARDED_HOME_CITY not in spec.required_postconditions:
            return None, True
        deadline = time.monotonic() + self._deps.postcondition_timeout_seconds
        last: Observation | None = None
        for _ in range(_POSTCONDITION_MAX_CAPTURES):
            last = core.capture_once(
                f"{spec.case_id}_postcondition", include_content=True
            )
            if _is_guarded_home(last):
                return last, True
            if time.monotonic() >= deadline:
                break
            self._deps.sleep(_POSTCONDITION_POLL_SECONDS)
        return last, False

    def _find_body_tap(
        self,
        collector: DispatchCollector,
        mark: int,
        source: Observation,
    ) -> str | None:
        """Binds the case's body-entry receipt to its authorizing frame."""

        frame = source.frame_ref
        if frame is None:
            return None
        for attributed in collector.events_since(mark):
            event = attributed.event
            if not isinstance(event, InputDispatchRecord):
                continue
            if not isinstance(event.dispatch, TapDispatch):
                continue
            if (
                event.source_frame.session_id == frame.session_id
                and event.source_frame.session_epoch == frame.session_epoch
                and event.source_frame.capture_sequence == frame.capture_sequence
                and event.source_frame.input_sequence == frame.input_sequence
            ):
                return attributed.event_id
        return None

    @staticmethod
    def _attempt_record(
        attempt_id: str,
        consumed: Any,
        status: str,
        dispatch_event_id: str | None,
    ) -> LogicalAttemptRecord:
        return LogicalAttemptRecord(
            attempt_id=attempt_id,
            case_id=consumed.case_id,
            control_name=consumed.control_name,
            number=consumed.number,
            limit=consumed.limit,
            status=status,
            journal_ref=consumed.journal_ref,
            dispatch_event_id=dispatch_event_id,
        )

    def _curate(
        self,
        path: Path | None,
        *,
        kind: str,
        purpose: str,
        artifacts: list[ArtifactRef],
    ) -> None:
        """Hashes one frame into the run's deduplicated artifact index."""

        if path is None:
            return
        path = Path(path)
        ref = self._artifact_index.get(path)
        if ref is None:
            ref = collect_artifact(path, kind=kind, purpose=purpose)
            self._artifact_index[path] = ref
        artifacts.append(ref)

    def _case_outcome(
        self,
        spec: CaseSpec,
        collector: DispatchCollector,
        *,
        mark: int | None,
        status: CaseStatus,
        detail: str,
        unresolved_boundary: str | None,
        artifacts: list[ArtifactRef] | None = None,
        body_entry_event_id: str | None = None,
        source_artifact: Path | None = None,
        follow_up_artifact: Path | None = None,
    ) -> CaseResult:
        events = collector.events_since(mark) if mark is not None else ()
        return CaseResult(
            case_id=spec.case_id,
            purpose=spec.purpose.value,
            status=status,
            artifacts=tuple(artifacts or ()),
            receipt_event_ids=tuple(
                attributed.event_id
                for attributed in events
                if isinstance(attributed.event, InputDispatchRecord)
            ),
            dispatch_event_ids=tuple(attributed.event_id for attributed in events),
            body_entry_event_id=body_entry_event_id,
            source_artifact=source_artifact,
            follow_up_artifact=follow_up_artifact,
            unresolved_boundary=unresolved_boundary,
            detail=detail,
        )
