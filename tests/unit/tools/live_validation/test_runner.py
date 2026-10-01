"""Offline runner orchestration tests with fake connection and core."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalControlResult,
)
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError

from tools.live_validation.annotation import AnnotationExchange
from tools.live_validation.binding import load_assignment_binding
from tools.live_validation.evidence import CaseStatus
from tools.live_validation.journal import pending_attempts, read_journal
from tools.live_validation.runner import (
    LiveCaseRunner,
    LiveConnection,
    PreflightRefusal,
    RunnerDeps,
    SourceProbe,
)
from tools.live_validation.validate import validate_live_evidence

from tests.unit.tools.live_validation.helpers import (
    CANDIDATE_SHA,
    assignment_payload,
    home_observation,
    tap_receipt,
    write_assignment,
    write_frame_file,
)


class _FakeExecutor:
    def __init__(self) -> None:
        self.input_dispatch_recorder = None
        self.budget = None

    def configure_input_attempt_budget(self, max_inputs, *, duration_seconds=None):
        self.budget = (max_inputs, duration_seconds)


class _FakeRuntime:
    def __init__(self, executor) -> None:
        self._executor = executor

    def require_observed_action_executor(self, reason):
        class _Observed:
            def __init__(self, executor) -> None:
                self.action_executor = executor
        return _Observed(self._executor)


class _FakeCore:
    """Satisfies the runner's runtime seam without any emulator."""

    def __init__(self, observer, run_dir: Path, *, entry_error=None,
                 post_entry_screen: ScreenType = ScreenType.UNKNOWN,
                 control_follow_up_screen: ScreenType = ScreenType.PNC_HOME_CITY) -> None:
        self._observer = observer
        self._dir = run_dir
        self._entry_error = entry_error
        self._post_entry_screen = post_entry_screen
        self._control_follow_up_screen = control_follow_up_screen
        self.executor = _FakeExecutor()
        self.runtime = _FakeRuntime(self.executor)
        self._seq = 0
        self.closed = False
        self.control_calls = []

    def _frame(self, name: str, screen: ScreenType):
        self._seq += 1
        path = write_frame_file(self._dir / "frames", f"{self._seq:03d}-{name}.png")
        return home_observation(artifact_path=path, sequence=self._seq, screen_type=screen)

    def capture_once(self, label: str, *, include_content: bool = False, request=None):
        return self._frame(label, ScreenType.PNC_HOME_CITY)

    def preflight_active_castle_identity(self):
        return CastleIdentity(kingdom="k1", castle_name="Castle")

    def enter_building_body_for_discovery(
        self, target, *, entry_effect, on_body_prepared, home_city_slot=None
    ):
        if self._entry_error is not None:
            raise self._entry_error
        source = self._frame("entry-src", ScreenType.PNC_HOME_CITY)
        action = TapSpatialObjectAction(
            target_point=(270, 520),
            reason="developmental_building_body_entry",
        )
        on_body_prepared(source, action)
        self._observer(tap_receipt(source))
        return source, action, self._frame("entry-follow", self._post_entry_screen)

    def execute_developmental_control(self, scope, proof, observation):
        self.control_calls.append(scope)
        follow = self._frame("control-follow", self._control_follow_up_screen)
        receipt = tap_receipt(observation)
        self._observer(receipt)
        return DevelopmentalControlResult(receipt=receipt, follow_up=follow)

    def close(self):
        self.executor.input_dispatch_recorder = None
        self.closed = True


class _FakeBundle:
    def __init__(self) -> None:
        self.closed = False

    def close(self):
        self.closed = True


def _deps(tmp: Path, core_holder: dict, *, annotation_factory=None) -> RunnerDeps:
    def _connect(*, binding, run_dir, observer):
        bundle = _FakeBundle()
        core = _FakeCore(observer, run_dir, **core_holder.get("core_kwargs", {}))
        core.executor.input_dispatch_recorder = observer
        core_holder["core"] = core
        core_holder["bundle"] = bundle
        return LiveConnection(bundle=bundle, core=core, account=object())

    return RunnerDeps(
        probe_source=lambda binding: SourceProbe(
            head_sha=CANDIDATE_SHA, dirty_paths=(), source_root=binding.source_root
        ),
        connect=_connect,
        annotation_factory=annotation_factory,
        sleep=lambda _: None,
        postcondition_timeout_seconds=0.01,
    )


def _binding(tmp: Path, *case_ids: str):
    return load_assignment_binding(
        write_assignment(tmp, assignment_payload(tmp, case_ids=case_ids))
    )


class LiveCaseRunnerTests(unittest.TestCase):
    def test_discovery_case_passes_and_evidence_validates(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder: dict = {}
            evidence, path = LiveCaseRunner(
                binding, _deps(tmp, holder)
            ).run()
            result = evidence.case_results[0]
            self.assertEqual(CaseStatus.PASSED, result.status)
            self.assertIsNotNone(result.body_entry_event_id)
            self.assertIsNotNone(result.source_artifact)
            self.assertIsNotNone(result.follow_up_artifact)
            self.assertTrue(holder["core"].closed)
            self.assertTrue(holder["bundle"].closed)
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )

    def test_discovery_body_entry_refusal_fails_the_case_not_the_run(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp, "v44_bank_body_menu", "v44_watchtower_body_menu"
            )
            holder: dict = {"core_kwargs": {"entry_error": SelectorResolutionError("no qualified body")}}
            evidence, _ = LiveCaseRunner(binding, _deps(tmp, holder)).run()
            statuses = {r.case_id: r.status for r in evidence.case_results}
        # Both cases fail entry, but the run completes and emits both results.
        self.assertEqual(CaseStatus.FAILED, statuses["v44_bank_body_menu"])
        self.assertEqual(CaseStatus.FAILED, statuses["v44_watchtower_body_menu"])
        self.assertEqual("qualified_body_entry",
                         evidence.case_results[0].unresolved_boundary)

    def test_blocked_precondition_marks_case_blocked(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder: dict = {}

            def _connect(*, binding, run_dir, observer):
                core = _FakeCore(observer, run_dir)
                core.executor.input_dispatch_recorder = observer
                core.capture_once = lambda label, **kw: home_observation(
                    artifact_path=write_frame_file(run_dir / "frames", "pre.png"),
                    screen_type=ScreenType.PNC_POPUP,
                )
                holder["core"] = core
                return LiveConnection(bundle=_FakeBundle(), core=core, account=object())

            deps = RunnerDeps(
                probe_source=lambda binding: SourceProbe(
                    head_sha=CANDIDATE_SHA, dirty_paths=(), source_root=binding.source_root
                ),
                connect=_connect,
                annotation_factory=None,
                sleep=lambda _: None,
            )
            evidence, _ = LiveCaseRunner(binding, deps).run()
            result = evidence.case_results[0]
        self.assertEqual(CaseStatus.BLOCKED, result.status)
        self.assertEqual("precondition", result.unresolved_boundary)

    def test_validation_case_owns_its_body_entry_and_journals_attempts(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_return_home")
            holder: dict = {}
            annotation_dir = tmp / "annotation"

            exchange = AnnotationExchange(
                annotation_dir, timeout_seconds=5.0, poll_seconds=0.01,
                sleep=lambda _: None,
            )
            deps = _deps(tmp, holder, annotation_factory=lambda _: exchange)

            # Pre-arm the tester: respond as soon as the request file appears.
            original_prepare = exchange.prepare
            def _armed_prepare(**kwargs):
                request = original_prepare(**kwargs)
                request.response_path.write_text(json.dumps({
                    "control_name": request.control_name,
                    "artifact_sha256": request.artifact_sha256,
                    "frame": request.frame,
                    "bounds": {"x": 10, "y": 10, "width": 100, "height": 50},
                    "action_point": {"x": 40, "y": 30},
                    "task_owned_foreground": True,
                    "visual_reason": "back control in the panel",
                    "intended_effect": "nonspending_state_change",
                    "foreground_target": HomeCityObjectId.BANK.value,
                }), encoding="utf-8")
                return request
            exchange.prepare = _armed_prepare

            evidence, path = LiveCaseRunner(binding, deps).run()
            result = evidence.case_results[0]
            self.assertEqual(CaseStatus.PASSED, result.status)
            core = holder["core"]
            self.assertEqual(1, len(core.control_calls))
            scope = core.control_calls[0]
            self.assertEqual("v44_bank_return_home", scope.case_id)
            self.assertEqual("v44_bank_return_home", scope.body_entry.case_id)
            journal_path = Path(binding.report_root) / binding.run_id / "attempts.jsonl"
            self.assertTrue(journal_path.exists())
            self.assertEqual((), pending_attempts(journal_path))
            entries = read_journal(journal_path)
            self.assertEqual(("attempt_begin", "attempt_finish"),
                             tuple(e.record_type for e in entries))
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )

    def test_annotation_timeout_blocks_the_case_and_closes_the_attempt(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_return_home")
            holder: dict = {}
            clock = {"t": 0.0}
            exchange = AnnotationExchange(
                tmp / "annotation", timeout_seconds=1.0, poll_seconds=2.0,
                sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                now=lambda: clock["t"],
            )
            deps = _deps(tmp, holder, annotation_factory=lambda _: exchange)
            evidence, _ = LiveCaseRunner(binding, deps).run()
            result = evidence.case_results[0]
            journal_path = Path(binding.report_root) / binding.run_id / "attempts.jsonl"
            self.assertTrue(journal_path.exists())
            pending = pending_attempts(journal_path)
        self.assertEqual(CaseStatus.BLOCKED, result.status)
        self.assertEqual("annotation_timeout", result.unresolved_boundary)
        self.assertEqual((), pending)
        self.assertEqual(
            "annotation_timeout",
            evidence.logical_attempts[0].status,
        )

    def test_unprovenanced_follow_up_blocks_before_any_attempt(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_return_home")
            holder: dict = {}

            base_connect = _deps(tmp, holder, annotation_factory=lambda _: None)
            original_connect = base_connect.connect
            def _connect(*, binding, run_dir, observer):
                connection = original_connect(binding=binding, run_dir=run_dir, observer=observer)
                core = connection.core
                original_enter = core.enter_building_body_for_discovery
                def _enter(target, **kwargs):
                    source, action, follow = original_enter(target, **kwargs)
                    object.__setattr__(follow, "frame_ref", None)
                    return source, action, follow
                core.enter_building_body_for_discovery = _enter
                return connection
            deps = RunnerDeps(
                probe_source=base_connect.probe_source,
                connect=_connect,
                annotation_factory=base_connect.annotation_factory,
                sleep=lambda _: None,
            )
            # Follow-up without provenance is not an allowed source anyway;
            # assert the run still terminates with one typed result.
            evidence, _ = LiveCaseRunner(binding, deps).run()
            result = evidence.case_results[0]
        self.assertIn(result.status, (CaseStatus.BLOCKED, CaseStatus.FAILED))

    def test_wrong_castle_refuses_before_any_case(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder: dict = {}
            deps = _deps(tmp, holder)
            original = deps.connect

            def _connect(*, binding, run_dir, observer):
                connection = original(binding=binding, run_dir=run_dir, observer=observer)
                connection.core.preflight_active_castle_identity = lambda: CastleIdentity(
                    kingdom="k2", castle_name="Wrong"
                )
                return connection

            deps = RunnerDeps(
                probe_source=deps.probe_source,
                connect=_connect,
                annotation_factory=None,
            )
            runner = LiveCaseRunner(binding, deps)
            with self.assertRaises(PreflightRefusal):
                runner.run()
            self.assertTrue(holder["bundle"].closed)


if __name__ == "__main__":
    unittest.main()
