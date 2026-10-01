"""The tracked bounded live-case runner for released V44 assignments.

One run reserves exactly one configured account through the canonical
``ApplicationRunner``/``ScriptRunner`` path, attaches one
``input_dispatch_observer``, executes each selected frozen case through the
existing ``CoreRuntime`` seams, and produces exactly one result per selected
case plus one serialized v3 evidence document. Discovery cases retain their
qualified body-entry context in memory for the run; dependent control cases
reuse that retained witness and never reopen the building. The runner owns
attribution, journaling, and curation only — it holds no scheduler,
permission engine, parallel capture path, or incident index of its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pnc_automation
from pnc_automation.app.automation.engine.developmental_control import (
    BodyEntryWitness,
    DevelopmentalControlScope,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
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
    validate_selected_order,
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
from tools.live_validation.events import (
    AttributionPhase,
    DispatchCollector,
    ReceiptIntegrityError,
)
from tools.live_validation.finalize import write_run_finalization
from tools.live_validation.journal import (
    AttemptIntent,
    AttemptStatus,
    LogicalAttemptJournal,
    pending_attempts,
)
from tools.test_selection.contexts import fingerprint
from tools.test_selection.git_changes import working_paths


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
    source_fingerprint: str = "0" * 64

    @property
    def tree_clean(self) -> bool:
        return not self.dirty_paths


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    """The resolved identity of the code actually executing this run.

    ``entry_point`` is the launched CLI file, ``import_root`` the directory
    holding the imported ``pnc_automation`` package, ``tool_root`` the
    checkout containing this runner module, and ``git_toplevel`` that
    checkout's Git root. ``entry_tracked`` is true only when the bound entry
    is tracked inside the bound source root.
    """

    entry_point: Path
    import_root: Path
    tool_root: Path
    git_toplevel: Path | None
    entry_tracked: bool


@dataclass(frozen=True, slots=True)
class _RetainedBodyContext:
    """One discovery case's retained body entry for its dependent control case."""

    witness: BodyEntryWitness
    follow_up: Observation
    body_event_id: str
    last_input_sequence: int


@dataclass(slots=True)
class LiveConnection:
    """Owns the leased session graph for one run.

    ``core.close()`` ends the session and restores the input recorder;
    ``bundle.close()`` releases the canonical account/instance leases. The
    runner closes each independently so one failure cannot mask the other.
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
    execution_identity: Callable[[], ExecutionIdentity]
    now_utc: Callable[[], datetime] = now_utc
    sleep: Callable[[float], None] = time.sleep
    postcondition_timeout_seconds: float = 30.0
    operation_budget_seconds: float = 2700.0


def _norm(path: Path | str) -> str:
    """Case-insensitive resolved path key for same-checkout comparisons."""

    return os.path.normcase(str(Path(path).resolve()))


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
        source_fingerprint=fingerprint({
            path: hashlib.sha256((binding.source_root / path).read_bytes()).hexdigest()
            for path in working_paths(binding.source_root)
        }),
    )


def compute_execution_identity(entry_point: Path | str) -> ExecutionIdentity:
    """Resolves the executing entry, import root, and tool checkout via Git.

    Module ``__file__`` paths — not ``sys.path`` order — bind the executing
    code to the released checkout, so a stray environment cannot substitute a
    different ``pnc_automation`` or runner silently.
    """

    entry = Path(entry_point).resolve()
    import_root = Path(pnc_automation.__file__).resolve().parent.parent
    tool_root = Path(__file__).resolve().parents[2]
    git_toplevel: Path | None = None
    entry_tracked = False
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=tool_root,
            capture_output=True,
            text=True,
            check=True,
        )
        git_toplevel = Path(completed.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        git_toplevel = None
    if git_toplevel is not None:
        relative = os.path.relpath(_norm(entry), _norm(git_toplevel))
        if not relative.startswith(".."):
            completed = subprocess.run(
                ["git", "ls-files", "--error-unmatch", relative],
                cwd=git_toplevel,
                capture_output=True,
                text=True,
            )
            entry_tracked = completed.returncode == 0
    return ExecutionIdentity(
        entry_point=entry,
        import_root=import_root,
        tool_root=tool_root,
        git_toplevel=git_toplevel,
        entry_tracked=entry_tracked,
    )


def admit_reservation(
    status: Any,
    *,
    receipt_path: Path | None,
    renew: Callable[[Path], Any],
) -> str:
    """Admits a caller-owned active reservation and defers a foreign one.

    ``status`` is the registry's secret-free ``InstanceReservationStatus`` for
    the bound instance. Returns ``"none"`` or ``"expired"`` when nothing
    active covers it, and ``"own"`` when the presented private receipt renews
    the recorded claim and that claim covers this instance. A foreign active
    reservation refuses before any lease or ADB access.
    """

    if status.reservation_state != "active":
        return status.reservation_state
    owner = f"{status.owner_label or 'unknown'}:{status.scope_id or 'unknown'}"
    if receipt_path is None:
        raise PreflightRefusal(
            (
                f"instance '{status.display_name}' is covered by an active "
                f"reservation owned by {owner}; defer until it expires or its "
                "owner releases it.",
            )
        )
    try:
        renewed = renew(Path(receipt_path))
    except Exception as error:
        raise PreflightRefusal(
            (
                f"the presented reservation receipt does not own the active "
                f"claim on '{status.display_name}' ({owner}); deferring.",
            )
        ) from error
    if status.display_name.strip().casefold() not in renewed.instance_keys:
        raise PreflightRefusal(
            (
                f"the presented receipt owns reservation scope "
                f"'{renewed.scope_id}', which does not cover "
                f"'{status.display_name}'.",
            )
        )
    return "own"


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
        self._preflight_execution_identity()

        run_dir = self._binding.report_root / self._binding.run_id
        try:
            run_dir.mkdir(parents=True)
        except FileExistsError as error:
            raise PreflightRefusal(
                (
                    f"run directory already exists; the run_id "
                    f"'{self._binding.run_id}' has been used: {run_dir}",
                )
            ) from error
        journal = LogicalAttemptJournal(run_dir / "attempts.jsonl")
        collector = DispatchCollector()
        observer = collector.append
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
            "instance_preserved": None,
            "reservation_disposition": self._binding.reservation_disposition,
        }
        coverage_start = started
        connection: LiveConnection | None = None
        executor: Any = None
        installed_recorder: Any = None
        actual_target: dict[str, Any] = {key: None for key in
                                       ("account_id", "castle", "instance_id", "live_role")}
        setup_error: str | None = None
        halt_inputs: str | None = None
        contexts: dict[str, _RetainedBodyContext] = {}
        try:
            connection = self._deps.connect(
                binding=self._binding,
                run_dir=run_dir,
                observer=observer,
            )
            with collector.phase(AttributionPhase.SETUP):
                try:
                    core = connection.core
                    executor = core.runtime.require_observed_action_executor(
                        "V44 live validation requires the canonical selector-backed action executor."
                    ).action_executor
                    installed_recorder = executor.input_dispatch_recorder
                    executor.configure_input_attempt_budget(
                        self._input_budget(),
                        duration_seconds=self._deps.operation_budget_seconds,
                    )
                    actual_target.update(
                        account_id=connection.account.id,
                        instance_id=connection.account.instance_id,
                        live_role=self._binding.target_role,
                    )
                    identity = core.preflight_active_castle_identity()
                    actual_target["castle"] = f"{identity.kingdom}:{identity.castle_name}"
                    if actual_target["castle"] != self._binding.target_castle_ref:
                        raise PreflightRefusal(("Observed castle differs from the released target.",))
                except Exception as error:  # noqa: BLE001 - setup failure is evidence
                    setup_error = _detail(error)
            if setup_error is None:
                for selection in self._binding.selected_cases:
                    spec = self._specs[selection.case_id]
                    if halt_inputs is not None:
                        results.append(
                            self._not_run_result(spec, f"Run halted: {halt_inputs}")
                        )
                        continue
                    with collector.phase(AttributionPhase.CASE, case_id=spec.case_id):
                        try:
                            result, halt = self._run_case(
                                spec,
                                selection,
                                connection.core,
                                journal,
                                collector,
                                attempts,
                                contexts,
                            )
                        except ReceiptIntegrityError as error:
                            halt = _detail(error)
                            result = self._case_outcome(
                                spec,
                                collector,
                                mark=None,
                                status=CaseStatus.FAILED,
                                detail=f"Receipt integrity failure: {_detail(error)}",
                                unresolved_boundary="receipt_integrity",
                            )
                        except Exception as error:  # noqa: BLE001 - evidence, not control flow
                            halt = _detail(error)
                            result = self._case_outcome(
                                spec,
                                collector,
                                mark=None,
                                status=CaseStatus.FAILED,
                                detail=f"Unattributed run failure: {_detail(error)}",
                                unresolved_boundary="runtime_session",
                            )
                        results.append(result)
                        if halt is None and collector.integrity_errors:
                            halt = "; ".join(collector.integrity_errors)
                        halt_inputs = halt or halt_inputs
            else:
                for selection in self._binding.selected_cases:
                    spec = self._specs[selection.case_id]
                    results.append(
                        self._not_run_result(
                            spec, f"Connected setup failed: {setup_error}"
                        )
                    )
        except Exception as error:
            setup_error = setup_error or _detail(error)
            completed = {row.case_id for row in results}
            results.extend(self._not_run_result(spec, setup_error)
                           for spec in self._specs.values() if spec.case_id not in completed)
        finally:
            if connection is not None:
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
                            executor is None
                            or executor.input_dispatch_recorder is not installed_recorder
                        )
                    except Exception as error:  # noqa: BLE001
                        cleanup["session_close_error"] = _detail(error)
                    try:
                        connection.bundle.close()
                        cleanup["lease_released"] = True
                    except Exception as error:  # noqa: BLE001
                        cleanup["lease_release_error"] = _detail(error)
            journal.close()

        for pending in pending_attempts(journal.path):
            attempts.append(
                LogicalAttemptRecord(
                    attempt_id=pending.attempt_id,
                    case_id=pending.case_id,
                    control_name=pending.control_name,
                    number=pending.number,
                    limit=pending.limit,
                    status="unfinished",
                    journal_ref=pending.journal_ref,
                    dispatch_event_id=None,
                    intent=pending.intent,
                )
            )
        finished = self._deps.now_utc()
        terminal_check = {
            "head_matches": False,
            "tree_clean": False,
            "execution_identity_matches": False,
            "entry_sha256_matches": False,
            "checked_at": finished.isoformat(),
        }
        try:
            terminal_probe = self._deps.probe_source(self._binding)
            terminal_check.update(head_matches=terminal_probe.head_sha == self._binding.candidate_sha,
                                  tree_clean=terminal_probe.tree_clean,
                                  dirty_paths=list(terminal_probe.dirty_paths))
            self._preflight_probe(terminal_probe)
            self._preflight_execution_identity()
            terminal_check["execution_identity_matches"] = True
            terminal_check["entry_sha256_matches"] = True
        except Exception as error:
            terminal_check["error"] = _detail(error)
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
            actual_target=actual_target,
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
        write_run_finalization(
            run_dir / "finalization.json",
            evidence_path=path,
            run_id=self._binding.run_id,
            assignment_id=self._binding.assignment_id,
            now=self._deps.now_utc(),
        )
        if setup_error is not None:
            raise PreflightRefusal(
                (
                    f"connected setup failed: {setup_error}; "
                    f"not-run evidence retained at {path}",
                )
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
        try:
            validate_selected_order(
                selection.case_id for selection in self._binding.selected_cases
            )
        except (KeyError, ValueError) as error:
            findings.append(str(error))
        if self._binding.read_only and any(
            spec.entry_effect is not WorkflowEffect.READ_ONLY
            or spec.developmental_purpose is not None for spec in self._specs.values()
        ):
            findings.append(
                "a read_only assignment cannot select state-changing building or control cases."
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
            else:
                try:
                    proof = json.loads(ref.path.read_text(encoding="utf-8"))
                    metadata = proof["metadata"]
                    if (proof.get("succeeded") is not True
                            or metadata.get("commit_sha") != probe.head_sha
                            or metadata.get("source_fingerprint") != probe.source_fingerprint):
                        findings.append(f"offline evidence is not passing proof for this candidate: {ref.path}")
                except (ValueError, KeyError, TypeError) as error:
                    findings.append(f"offline evidence lacks repository result metadata: {ref.path}: {error}")
        if not self._binding.offline_evidence:
            findings.append("released live assignment requires exact-candidate offline evidence.")
        if findings:
            raise PreflightRefusal(tuple(findings))

    def _preflight_execution_identity(self) -> None:
        """Binds the actually executing code to the released assignment."""

        identity = self._deps.execution_identity()
        findings: list[str] = []
        if _norm(identity.entry_point) != _norm(self._binding.entry_point):
            findings.append(
                f"executing entry '{identity.entry_point}' is not the bound "
                f"entry_point '{self._binding.entry_point}'."
            )
        if _norm(identity.import_root) != _norm(self._binding.import_root):
            findings.append(
                f"imported pnc_automation root '{identity.import_root}' is not "
                f"the bound import_root '{self._binding.import_root}'."
            )
        if _norm(identity.import_root) != _norm(identity.tool_root):
            findings.append("Imported production code and executing tools must share one checkout.")
        if _norm(identity.tool_root) != _norm(self._binding.source_root):
            findings.append(
                f"executing tools root '{identity.tool_root}' is not the bound "
                f"source_root '{self._binding.source_root}'."
            )
        if identity.git_toplevel is None:
            findings.append("the executing tools tree is not inside a Git checkout.")
        elif _norm(identity.git_toplevel) != _norm(self._binding.source_root):
            findings.append(
                f"the executing tools checkout '{identity.git_toplevel}' is not "
                f"the bound source_root '{self._binding.source_root}'."
            )
        if not identity.entry_tracked:
            findings.append(
                f"entry point '{self._binding.entry_point}' is not tracked in "
                "the bound checkout."
            )
        elif not identity.entry_point.is_file() or sha256_file(identity.entry_point) != self._binding.entry_sha256:
            findings.append("executing entry sha256 does not match the bound entry_sha256.")
        report_root = self._binding.report_root.resolve()
        if not report_root.is_relative_to(self._binding.source_root.resolve() / ".local-data"):
            findings.append("report_root must stay under the checkout's ignored .local-data directory.")
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
        contexts: dict[str, _RetainedBodyContext],
    ) -> tuple[CaseResult, str | None]:
        """Returns the case outcome plus an optional run-halt reason."""

        if spec.purpose is CasePurpose.DISCOVERY:
            return self._run_discovery(spec, core, journal, collector, attempts, contexts)
        if spec.purpose is CasePurpose.DEVELOPMENT_VALIDATION:
            return self._run_validation(spec, core, journal, collector, attempts, contexts)
        return (
            self._case_outcome(
                spec,
                collector,
                mark=None,
                status=CaseStatus.BLOCKED,
                detail="Acceptance cases are not executable by the tracked runner.",
                unresolved_boundary="acceptance_not_executable",
            ),
            None,
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

    def _sent_since(self, collector: DispatchCollector, mark: int) -> bool:
        """Whether any dispatch receipt was observed after the mark."""

        return any(
            isinstance(attributed.event, InputDispatchRecord)
            for attributed in collector.events_since(mark)
        )

    def _finish_body_intent(
        self,
        holder: dict[str, Any],
        journal: LogicalAttemptJournal,
        attempts: list[LogicalAttemptRecord],
        *,
        status: AttemptStatus,
        dispatch_event_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Terminates a journaled body intent and records it for evidence."""

        if "id" not in holder:
            return
        journal.finish(
            holder["id"],
            status=status,
            dispatch_event_id=dispatch_event_id,
            detail=detail,
        )
        attempts.append(
            self._attempt_record(
                holder["id"],
                holder["consumed"],
                status.value,
                dispatch_event_id,
                intent=AttemptIntent.BODY_ENTRY.value,
            )
        )

    def _run_discovery(
        self,
        spec: CaseSpec,
        core: Any,
        journal: LogicalAttemptJournal,
        collector: DispatchCollector,
        attempts: list[LogicalAttemptRecord],
        contexts: dict[str, _RetainedBodyContext],
    ) -> tuple[CaseResult, str | None]:
        mark = collector.mark()
        violated = self._precondition_check(spec, core)
        if violated is not None:
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    detail=f"Precondition '{violated}' is not satisfied.",
                    unresolved_boundary="precondition",
                ),
                None,
            )
        holder: dict[str, Any] = {}

        def on_prepared(source: Observation, action: TapSpatialObjectAction) -> None:
            """Journals and fsyncs the body intent before the entry send."""

            if "id" in holder:
                return
            attempt_id, consumed = journal.begin(
                case_id=spec.case_id,
                control_name=spec.operation_id,
                operation_id=spec.operation_id,
                number=1,
                limit=1,
                source_frame=(
                    frame_ref_dict(source.frame_ref)
                    if source.frame_ref is not None
                    else {}
                ),
                intent=AttemptIntent.BODY_ENTRY,
            )
            holder["id"] = attempt_id
            holder["consumed"] = consumed
            holder["source"] = source
            holder["action"] = action

        try:
            source, action, follow_up = core.enter_building_body_for_discovery(
                spec.target,
                entry_effect=spec.entry_effect,
                on_body_prepared=on_prepared,
                home_city_slot=spec.home_city_slot,
            )
        except Exception as error:
            known = (self._find_body_tap(collector, mark, holder["source"], holder["action"])
                     if "source" in holder else None)
            if "id" in holder or self._sent_since(collector, mark):
                self._finish_body_intent(
                    holder,
                    journal,
                    attempts,
                    status=AttemptStatus.DISPATCHED if known else AttemptStatus.UNCERTAIN,
                    dispatch_event_id=known,
                    detail=f"body send ended uncertain: {_detail(error)}",
                )
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.FAILED,
                        detail=(
                            "Body entry ended uncertain after inputs were sent; "
                            f"later inputs are halted: {_detail(error)}"
                        ),
                        body_entry_event_id=known,
                        unresolved_boundary="follow_up_capture" if known else "uncertain_send",
                    ),
                    f"uncertain body send in {spec.case_id}: {_detail(error)}",
                )
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.FAILED,
                    detail=f"Body entry refused by the qualified navigation seam: {_detail(error)}",
                    unresolved_boundary="qualified_body_entry",
                ),
                None if isinstance(error, (SelectorResolutionError, HomeCityScanError)) else _detail(error),
            )
        body_event_id = self._find_body_tap(collector, mark, source, action)
        if "id" not in holder and body_event_id is not None:
            raise ReceiptIntegrityError(
                f"{spec.case_id}: a body-entry receipt exists without a "
                "journaled body intent."
            )
        if body_event_id is not None:
            self._finish_body_intent(holder, journal, attempts,
                                     status=AttemptStatus.DISPATCHED,
                                     dispatch_event_id=body_event_id)
        artifacts: list[ArtifactRef] = []
        self._curate(source.artifact_path, kind="source_frame",
                     purpose=f"{spec.case_id} authorizing source frame.", artifacts=artifacts)
        self._curate(follow_up.artifact_path, kind="follow_up_frame",
                     purpose=f"{spec.case_id} raw post-tap observed state.", artifacts=artifacts)
        postcondition = self._postcondition_dict(follow_up)
        if body_event_id is None:
            self._finish_body_intent(
                holder,
                journal,
                attempts,
                status=AttemptStatus.UNCERTAIN,
                detail="entry send produced no attributable receipt",
            )
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.FAILED,
                    artifacts=artifacts,
                    source_artifact=source.artifact_path,
                    follow_up_artifact=follow_up.artifact_path,
                    postcondition=postcondition,
                    detail="Entry send returned without an attributed tap receipt.",
                    unresolved_boundary="entry_receipt",
                ),
                f"{spec.case_id}: body entry produced no attributable receipt",
            )
        body_receipt = next(
            attributed.event
            for attributed in collector.events_since(mark)
            if attributed.event_id == body_event_id
        )
        source_frame = source.frame_ref
        after = follow_up.frame_ref
        if (source_frame is None or after is None or follow_up.artifact_path is None
                or after.session_id != source_frame.session_id
                or after.session_epoch != source_frame.session_epoch
                or after.input_sequence != body_receipt.dispatch.input_sequence
                or after.capture_sequence != source_frame.capture_sequence + 1):
            raise ReceiptIntegrityError("Body entry has no persisted immediate follow-up for its receipt.")
        witness = BodyEntryWitness(
            case_id=spec.case_id,
            operation_id=spec.operation_id,
            observation=source,
            action=action,
            receipt=body_receipt,
        )
        contexts[spec.case_id] = _RetainedBodyContext(
            witness=witness,
            follow_up=follow_up,
            body_event_id=body_event_id,
            last_input_sequence=body_receipt.dispatch.input_sequence,
        )
        if follow_up.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_LOADING}:
            return (self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                artifacts=artifacts, body_entry_event_id=body_event_id,
                source_artifact=source.artifact_path, follow_up_artifact=follow_up.artifact_path,
                postcondition=postcondition, detail="Body input recorded; a foreground menu is not yet observed.",
                unresolved_boundary="body_menu_observation"), None)
        return (
            self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.PASSED,
                artifacts=artifacts,
                body_entry_event_id=body_event_id,
                source_artifact=source.artifact_path,
                follow_up_artifact=follow_up.artifact_path,
                postcondition=postcondition,
                detail="Qualified body entry sent and raw follow-up persisted.",
                unresolved_boundary=None,
            ),
            None,
        )

    def _run_validation(
        self,
        spec: CaseSpec,
        core: Any,
        journal: LogicalAttemptJournal,
        collector: DispatchCollector,
        attempts: list[LogicalAttemptRecord],
        contexts: dict[str, _RetainedBodyContext],
    ) -> tuple[CaseResult, str | None]:
        mark = collector.mark()
        if self._deps.annotation_factory is None:
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    detail="No annotation exchange is configured for this run.",
                    unresolved_boundary="annotation_unavailable",
                ),
                None,
            )
        violated = self._precondition_check(spec, core)
        if violated is not None:
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    detail=f"Precondition '{violated}' is not satisfied.",
                    unresolved_boundary="precondition",
                ),
                None,
            )
        context = contexts.get(spec.body_case_id)
        if context is None:
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                    detail=(
                        f"Declared body case '{spec.body_case_id}' produced no "
                        "retained body context; the building is never reopened "
                        "for a return case."
                    ),
                    unresolved_boundary="body_dependency",
                ),
                None,
            )
        artifacts: list[ArtifactRef] = []
        current = core.capture_once(
            f"{spec.case_id}_resume_state", include_content=True
        )
        self._curate(
            current.artifact_path,
            kind="resume_frame",
            purpose=(
                f"{spec.case_id} passive re-observation of the retained body "
                f"context from '{spec.body_case_id}'."
            ),
            artifacts=artifacts,
        )
        witness = context.witness
        boundary = self._resume_boundary(spec, context, current)
        if boundary is not None:
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.FAILED,
                    artifacts=artifacts,
                    body_entry_event_id=context.body_event_id,
                    source_artifact=current.artifact_path,
                    detail=boundary[1],
                    unresolved_boundary=boundary[0],
                ),
                boundary[2],
            )
        input_chain: list[InputDispatchRecord] = [witness.receipt]
        latest_follow_up = context.follow_up
        annotation = self._deps.annotation_factory(
            Path(self._binding.report_root) / self._binding.run_id / "annotation"
        )
        for attempt_number in range(1, spec.max_control_attempts + 1):
            if current.frame_ref is None:
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                        artifacts=artifacts,
                        body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        detail="The control-source frame has no fresh provenance; no input authorized.",
                        unresolved_boundary="follow_up_provenance",
                    ),
                    None,
                )
            attempt_id, consumed = journal.begin(
                case_id=spec.case_id,
                control_name=spec.control_name or "",
                operation_id=spec.operation_id,
                number=attempt_number,
                limit=spec.max_control_attempts,
                source_frame=frame_ref_dict(current.frame_ref),
                intent=AttemptIntent.CONTROL,
            )
            request = annotation.prepare(
                case_id=spec.case_id,
                control_name=spec.control_name or "",
                foreground_target=spec.target,
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
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.BLOCKED,
                        artifacts=artifacts,
                        body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        detail="Tester annotation did not arrive before the bounded deadline.",
                        unresolved_boundary="annotation_timeout",
                    ),
                    None,
                )
            self._curate(
                request.request_path,
                kind="annotation_request",
                purpose=f"{spec.case_id} annotation request bound to the source frame.",
                artifacts=artifacts,
            )
            self._curate(
                request.response_path,
                kind="annotation_response",
                purpose=(
                    f"{spec.case_id} tester attestation for "
                    f"'{spec.control_name}'."
                ),
                artifacts=artifacts,
            )
            scope = DevelopmentalControlScope(
                assignment_id=self._binding.assignment_id,
                case_id=spec.case_id,
                body_case_id=spec.body_case_id,
                case_spec_ref=spec.case_id,
                purpose=spec.developmental_purpose,
                operation_id=spec.operation_id,
                released_action_id=spec.released_action_id,
                control_name=spec.control_name or "",
                target=spec.target,
                home_city_slot=spec.home_city_slot,
                allowed_source_screens=spec.allowed_source_screens,
                effect=spec.control_effect or WorkflowEffect.READ_ONLY,
                read_only=self._binding.read_only,
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
                control_mark = collector.mark()
                result = core.execute_developmental_control(scope, proof, current)
            except SelectorResolutionError as error:
                known = self._find_tap(collector, control_mark, current, proof.action_point)
                if known:
                    journal.finish(attempt_id, status=AttemptStatus.DISPATCHED,
                                   dispatch_event_id=known, detail=_detail(error))
                    attempts.append(self._attempt_record(attempt_id, consumed, "dispatched", known))
                    return (self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.FAILED,
                        artifacts=artifacts, body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        detail=f"Control dispatched but follow-up failed: {_detail(error)}",
                        unresolved_boundary="follow_up_capture"),
                        f"{spec.case_id}: follow-up failure after confirmed send")
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
                    return (
                        self._case_outcome(
                            spec, collector, mark=mark, status=CaseStatus.FAILED,
                            artifacts=artifacts,
                            body_entry_event_id=context.body_event_id,
                            source_artifact=current.artifact_path,
                            follow_up_artifact=(
                                refreshed.artifact_path or follow_up_artifact_or_none(latest_follow_up)
                            ),
                            detail="Intervening input invalidated the refused frame chain.",
                            unresolved_boundary="intervening_input",
                        ),
                        f"{spec.case_id}: intervening input invalidated the frame chain",
                    )
                current = refreshed
                self._curate(current.artifact_path, kind="reproof_frame",
                             purpose=f"{spec.case_id} fresh frame after a refused attempt.",
                             artifacts=artifacts)
                continue
            except Exception as error:  # noqa: BLE001 - uncertain send, never replay
                known = self._find_tap(collector, control_mark, current, proof.action_point)
                state = AttemptStatus.DISPATCHED if known else AttemptStatus.UNCERTAIN
                journal.finish(attempt_id, status=state, dispatch_event_id=known,
                               detail=_detail(error))
                attempts.append(
                    self._attempt_record(attempt_id, consumed, state.value, known)
                )
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.FAILED,
                        artifacts=artifacts,
                        body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        follow_up_artifact=follow_up_artifact_or_none(latest_follow_up),
                        detail=f"Control has a receipt but no follow-up: {_detail(error)}" if known
                               else f"Control dispatch ended uncertain; no replay: {_detail(error)}",
                        unresolved_boundary="follow_up_capture" if known else "uncertain_send",
                    ),
                    f"{spec.case_id}: uncertain control send",
                )
            event_id = collector.receipt_event_id(result.receipt, case_id=spec.case_id)
            if event_id is None:
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.FAILED,
                        artifacts=artifacts,
                        body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        follow_up_artifact=follow_up_artifact_or_none(latest_follow_up),
                        detail="The dispatched control receipt was not attributed to this case.",
                        unresolved_boundary="receipt_integrity",
                    ),
                    f"{spec.case_id}: control receipt not attributed",
                )
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
                return (
                    self._case_outcome(
                        spec, collector, mark=mark, status=CaseStatus.PASSED,
                        artifacts=artifacts,
                        body_entry_event_id=context.body_event_id,
                        source_artifact=current.artifact_path,
                        follow_up_artifact=(
                            final.artifact_path if final is not None else result.follow_up.artifact_path
                        ),
                        postcondition=self._postcondition_dict(final),
                        detail="Control dispatched and the guarded Home postcondition was observed.",
                        unresolved_boundary=None,
                    ),
                    None,
                )
            return (
                self._case_outcome(
                    spec, collector, mark=mark, status=CaseStatus.FAILED,
                    artifacts=artifacts,
                    body_entry_event_id=context.body_event_id,
                    source_artifact=current.artifact_path,
                    follow_up_artifact=(
                        final.artifact_path
                        if final is not None
                        else result.follow_up.artifact_path
                    ),
                    postcondition=self._postcondition_dict(final),
                    detail="Control dispatched but the guarded Home postcondition was not observed.",
                    unresolved_boundary="postcondition",
                ),
                None,
            )
        return (
            self._case_outcome(
                spec, collector, mark=mark, status=CaseStatus.FAILED,
                artifacts=artifacts,
                body_entry_event_id=context.body_event_id,
                source_artifact=current.artifact_path,
                detail="Control attempt budget exhausted before a dispatch.",
                unresolved_boundary="attempt_budget",
            ),
            None,
        )

    def _resume_boundary(
        self,
        spec: CaseSpec,
        context: _RetainedBodyContext,
        current: Observation,
    ) -> tuple[str, str, str | None] | None:
        """Revalidates the retained context against one fresh passive frame.

        Returns ``(boundary, detail, halt_reason)`` when the return cannot
        proceed; ``halt_reason`` non-None marks an integrity-level failure
        that stops every later input.
        """

        if current.frame_ref is None:
            return (
                "resume_provenance",
                "The resume capture has no provenance; the retained context cannot be revalidated.",
                f"{spec.case_id}: resume frame lacks provenance",
            )
        witness_frame = context.witness.receipt.source_frame
        frame = current.frame_ref
        if (
            frame.session_id != witness_frame.session_id
            or frame.session_epoch != witness_frame.session_epoch
        ):
            return (
                "session_continuity",
                "The resume capture belongs to a different session or epoch than "
                "the retained body receipt.",
                f"{spec.case_id}: session discontinuity after retained entry",
            )
        if frame.input_sequence != context.last_input_sequence:
            return (
                "intervening_input",
                "Unrecorded input advanced the input sequence since the retained "
                "body entry; the body is no longer freshly bound.",
                f"{spec.case_id}: intervening input since the retained entry",
            )
        if current.screen_type not in spec.allowed_source_screens:
            return (
                "control_source_screen",
                f"Resume screen '{current.screen_type.value}' is not an allowed "
                f"source for control '{spec.control_name}'.",
                None,
            )
        return None

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

    @staticmethod
    def _postcondition_dict(observation: Observation | None) -> dict[str, Any] | None:
        if observation is None:
            return None
        return {
            "screen_type": observation.screen_type.value,
            "blocking_popup": observation.blocking_popup,
            "artifact_path": (
                None if observation.artifact_path is None else str(observation.artifact_path)
            ),
            "frame_fingerprint": observation.frame_fingerprint,
            "guard": observation.decision.guard.value,
            "frame": None if observation.frame_ref is None else frame_ref_dict(observation.frame_ref),
        }

    def _find_body_tap(
        self,
        collector: DispatchCollector,
        mark: int,
        source: Observation,
        action: TapSpatialObjectAction,
    ) -> str | None:
        return self._find_tap(collector, mark, source, action.target_point)

    @staticmethod
    def _find_tap(collector: DispatchCollector, mark: int, source: Observation,
                  point: tuple[int, int]) -> str | None:
        """Binds the case's body-entry receipt to its authorizing frame.

        Exactly one attributed tap receipt may claim the source frame's
        provenance; zero returns ``None`` and a duplicate raises
        ``ReceiptIntegrityError``.
        """

        frame = source.frame_ref
        if frame is None:
            return None
        matches = []
        for attributed in collector.events_since(mark):
            event = attributed.event
            if not isinstance(event, InputDispatchRecord):
                continue
            if not isinstance(event.dispatch, TapDispatch):
                continue
            if (
                event.source_frame == frame
                and event.artifact_path == source.artifact_path
                and event.dispatch.point == point
                and event.dispatch.input_sequence == frame.input_sequence + 1
            ):
                matches.append(attributed.event_id)
        if len(matches) > 1:
            raise ReceiptIntegrityError(
                f"{len(matches)} tap receipts claim the {source.frame_ref.capture_sequence} "
                "frame's provenance."
            )
        return matches[0] if matches else None

    @staticmethod
    def _attempt_record(
        attempt_id: str,
        consumed: Any,
        status: str,
        dispatch_event_id: str | None,
        *,
        intent: str = AttemptIntent.CONTROL.value,
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
            intent=intent,
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

    def _not_run_result(self, spec: CaseSpec, detail: str) -> CaseResult:
        return CaseResult(
            case_id=spec.case_id,
            purpose=spec.purpose.value,
            status=CaseStatus.NOT_RUN,
            artifacts=(),
            receipt_event_ids=(),
            dispatch_event_ids=(),
            body_entry_event_id=None,
            body_case_id=spec.body_case_id,
            source_artifact=None,
            follow_up_artifact=None,
            postcondition=None,
            unresolved_boundary="run_halted",
            detail=detail,
        )

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
        postcondition: dict[str, Any] | None = None,
    ) -> CaseResult:
        events = (collector.events_since(mark) if mark is not None else
                  tuple(row for row in collector.events if row.case_id == spec.case_id))
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
            body_case_id=spec.body_case_id,
            source_artifact=source_artifact,
            follow_up_artifact=follow_up_artifact,
            postcondition=postcondition,
            unresolved_boundary=unresolved_boundary,
            detail=detail,
        )


def follow_up_artifact_or_none(observation: Observation | None) -> Path | None:
    """The artifact path of one retained follow-up, if it was persisted."""

    if observation is None:
        return None
    return observation.artifact_path
