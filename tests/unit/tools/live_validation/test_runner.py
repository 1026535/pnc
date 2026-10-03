"""Offline runner orchestration tests with fake connection and core."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalCasePurpose,
    DevelopmentalControlResult,
)
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import (
    HomeCityScanError,
    HomeCityScanState,
    HomeCityScanStopReason,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchFailure,
    InputDispatchRecord,
    SwipeDispatch,
    WheelDispatch,
)

from tools.live_validation.annotation import AnnotationExchange
from tools.live_validation.binding import load_assignment_binding
from tools.live_validation.evidence import CaseStatus
from tools.live_validation.journal import pending_attempts, read_journal
from tools.live_validation.runner import (
    ExecutionIdentity,
    LiveCaseRunner,
    LiveConnection,
    PreflightRefusal,
    RunnerDeps,
    SourceProbe,
    admit_reservation,
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
    """Stateful fake: current screen and input sequence model a real session."""

    def __init__(self, observer, run_dir: Path, *, entry_error=None,
                 post_entry_screens: dict | None = None,
                 control_follow_up_screen: ScreenType | dict = ScreenType.PNC_HOME_CITY) -> None:
        self._observer = observer
        self._dir = run_dir
        self._entry_error = entry_error
        self._post_entry_screens = post_entry_screens or {}
        self._control_follow_up_screen = control_follow_up_screen
        self._screen = ScreenType.PNC_HOME_CITY
        self._input_seq = 0
        self.executor = _FakeExecutor()
        self.runtime = _FakeRuntime(self.executor)
        self._seq = 0
        self.closed = False
        self.entry_calls = []
        self.control_calls = []

    def _frame(self, name: str, screen: ScreenType):
        self._seq += 1
        path = write_frame_file(self._dir / "frames", f"{self._seq:03d}-{name}.png")
        return home_observation(
            artifact_path=path,
            sequence=self._seq,
            screen_type=screen,
            input_sequence=self._input_seq,
        )

    def _send_tap(self, source, *, point=(270, 520)):
        self._input_seq += 1
        receipt = tap_receipt(source, input_sequence=self._input_seq)
        receipt = replace(receipt, dispatch=replace(receipt.dispatch, point=point))
        self._observer(receipt)
        return receipt

    def capture_once(self, label: str, *, include_content: bool = False, request=None):
        return self._frame(label, self._screen)

    def preflight_active_castle_identity(self):
        return CastleIdentity(kingdom="k1", castle_name="Castle")

    def enter_building_body_for_discovery(
        self, target, *, entry_effect, on_body_prepared, home_city_slot=None
    ):
        if self._entry_error is not None:
            raise self._entry_error
        self.entry_calls.append(target)
        source = self._frame("entry-src", ScreenType.PNC_HOME_CITY)
        action = TapSpatialObjectAction(
            target_point=(270, 520),
            reason="developmental_building_body_entry",
        )
        on_body_prepared(source, action)
        self._send_tap(source)
        self._screen = self._post_entry_screens.get(target, ScreenType.UNKNOWN)
        return source, action, self._frame("entry-follow", self._screen)

    def execute_developmental_control(self, scope, proof, observation):
        self.control_calls.append(scope)
        receipt = self._send_tap(observation, point=proof.action_point)
        follow = self._control_follow_up_screen
        if isinstance(follow, dict):
            follow = follow[scope.case_id]
        self._screen = follow
        return DevelopmentalControlResult(
            receipt=receipt,
            follow_up=self._frame("control-follow", self._screen),
        )

    def close(self):
        self.executor.input_dispatch_recorder = None
        self.closed = True


class _FakeBundle:
    def __init__(self) -> None:
        self.closed = False

    def close(self):
        self.closed = True


def _execution_identity(tmp: Path):
    return lambda: ExecutionIdentity(
        entry_point=tmp / "entry.py",
        import_root=tmp,
        tool_root=tmp,
        git_toplevel=tmp,
        entry_tracked=True,
    )


def _deps(tmp: Path, core_holder: dict, *, annotation_factory=None) -> RunnerDeps:
    def _connect(*, binding, run_dir, observer):
        bundle = _FakeBundle()
        core = _FakeCore(observer, run_dir, **core_holder.get("core_kwargs", {}))
        core.executor.input_dispatch_recorder = observer
        core_holder["core"] = core
        core_holder["bundle"] = bundle
        return LiveConnection(bundle=bundle, core=core, account=SimpleNamespace(id="testing", instance_id="bluestacks-1"))

    return RunnerDeps(
        probe_source=lambda binding: SourceProbe(
            head_sha=CANDIDATE_SHA, dirty_paths=(), source_root=binding.source_root
        ),
        connect=_connect,
        annotation_factory=annotation_factory,
        execution_identity=_execution_identity(tmp),
        sleep=lambda _: None,
        postcondition_timeout_seconds=0.01,
    )


def _binding(tmp: Path, *case_ids: str):
    return load_assignment_binding(
        write_assignment(tmp, assignment_payload(tmp, case_ids=case_ids))
    )


def _write_valid_response(request) -> None:
    request.response_path.write_text(json.dumps({
        "request_id": request.request_id,
        "case_id": request.case_id,
        "control_name": request.control_name,
        "foreground_target": request.foreground_target,
        "artifact_path": str(request.artifact_path),
        "artifact_sha256": request.artifact_sha256,
        "frame": request.frame,
        "bounds": {"x": 10, "y": 10, "width": 100, "height": 50},
        "action_point": {"x": 40, "y": 30},
        "task_owned_foreground": True,
        "visual_reason": "back control in the panel",
        "intended_effect": "nonspending_state_change",
    }), encoding="utf-8")


def _armed_exchange(directory: Path) -> AnnotationExchange:
    """An exchange whose tester answers every request immediately."""

    exchange = AnnotationExchange(
        directory, timeout_seconds=5.0, poll_seconds=0.01,
        sleep=lambda _: None,
    )
    original_prepare = exchange.prepare

    def _armed_prepare(**kwargs):
        request = original_prepare(**kwargs)
        _write_valid_response(request)
        return request

    exchange.prepare = _armed_prepare
    return exchange


class LiveCaseRunnerTests(unittest.TestCase):
    def test_recorder_composition_is_preserved_until_core_cleanup(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder = {}
            deps = _deps(tmp, holder)
            original = deps.connect
            def connect(**kwargs):
                connection = original(**kwargs)
                recorder = object()
                connection.core.executor.input_dispatch_recorder = recorder
                capture = connection.core.capture_once
                def checked_capture(*args, **kw):
                    self.assertIs(recorder, connection.core.executor.input_dispatch_recorder)
                    return capture(*args, **kw)
                connection.core.capture_once = checked_capture
                return connection
            evidence, _ = LiveCaseRunner(binding, replace(deps, connect=connect)).run()
            self.assertTrue(evidence.cleanup["observer_restored"])
            self.assertIsNone(evidence.cleanup["instance_preserved"])

    def test_confirmed_control_with_failed_capture_is_not_retried_or_uncertain(self):
        for error in (RuntimeError("capture failed"), SelectorResolutionError("capture failed")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                binding = _binding(tmp, "v44_bank_body_menu", "v44_bank_return_home",
                                   "v44_watchtower_body_menu")
                holder = {}
                deps = _deps(tmp, holder, annotation_factory=_armed_exchange)
                connect = deps.connect
                def failing_connect(**kw):
                    connection = connect(**kw)
                    send = connection.core.execute_developmental_control
                    def fail_after_send(*args):
                        send(*args)
                        raise error
                    connection.core.execute_developmental_control = fail_after_send
                    return connection
                evidence, _ = LiveCaseRunner(binding, replace(deps, connect=failing_connect)).run()
                self.assertEqual(1, len(holder["core"].control_calls))
                self.assertEqual("dispatched", evidence.logical_attempts[-1].status)
                self.assertIsNotNone(evidence.logical_attempts[-1].dispatch_event_id)
                self.assertEqual("follow_up_capture", evidence.case_results[1].unresolved_boundary)
                self.assertEqual(CaseStatus.NOT_RUN, evidence.case_results[2].status)

    def test_offline_proof_for_different_candidate_refuses_before_connection(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder = {}
            deps = _deps(tmp, holder)
            probe = deps.probe_source(binding)
            with self.assertRaises(PreflightRefusal):
                LiveCaseRunner(binding, replace(deps, probe_source=lambda _: replace(
                    probe, source_fingerprint="f" * 64))).run()
            self.assertNotIn("core", holder)

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
            self.assertEqual("v44_bank_body_menu", result.body_case_id)
            self.assertIsNotNone(result.source_artifact)
            self.assertIsNotNone(result.follow_up_artifact)
            self.assertIsNotNone(result.postcondition)
            self.assertTrue(holder["core"].closed)
            self.assertTrue(holder["bundle"].closed)
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )

    def test_raw_discovery_does_not_require_a_menu_screen(self):
        for screen in (ScreenType.PNC_HOME_CITY, ScreenType.PNC_LOADING):
            with self.subTest(screen=screen), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                binding = _binding(tmp, "v44_watchtower_body_menu")
                holder = {"core_kwargs": {"post_entry_screens": {
                    HomeCityObjectId.WATCHTOWER: screen,
                }}}
                evidence, path = LiveCaseRunner(binding, _deps(tmp, holder)).run()
                result = evidence.case_results[0]
                self.assertEqual(CaseStatus.PASSED, result.status)
                self.assertEqual("discovery", result.purpose)
                self.assertEqual(screen.value, result.postcondition["screen_type"])
                self.assertIsNotNone(result.body_entry_event_id)
                self.assertIsNotNone(result.follow_up_artifact)
                self.assertEqual([], holder["core"].control_calls)
                self.assertTrue(validate_live_evidence(binding, path).valid)

    def test_home_discovery_does_not_authorize_a_return_control(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp, "v44_bank_body_menu", "v44_bank_return_home"
            )
            holder = {"core_kwargs": {"post_entry_screens": {
                HomeCityObjectId.BANK: ScreenType.PNC_HOME_CITY,
            }}}
            evidence, _ = LiveCaseRunner(
                binding, _deps(tmp, holder, annotation_factory=lambda _: self.fail(
                    "An unauthorized source must refuse before requesting annotation."
                ))
            ).run()
            discovery, control = evidence.case_results
            self.assertEqual(CaseStatus.PASSED, discovery.status)
            self.assertEqual(CaseStatus.FAILED, control.status)
            self.assertEqual("control_source_screen", control.unresolved_boundary)
            self.assertEqual([], holder["core"].control_calls)

    def test_discovery_body_entry_refusal_fails_the_case_not_the_run(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp, "v44_bank_body_menu", "v44_watchtower_body_menu"
            )
            holder: dict = {"core_kwargs": {"entry_error": SelectorResolutionError("no qualified body")}}
            evidence, _ = LiveCaseRunner(binding, _deps(tmp, holder)).run()
            statuses = {r.case_id: r.status for r in evidence.case_results}
        self.assertEqual(CaseStatus.FAILED, statuses["v44_bank_body_menu"])
        self.assertEqual(CaseStatus.FAILED, statuses["v44_watchtower_body_menu"])
        self.assertEqual("qualified_body_entry",
                         evidence.case_results[0].unresolved_boundary)

    def test_confirmed_camera_scan_failure_keeps_independent_cases_runnable(self):
        errors = (
            SelectorResolutionError("no measured body"),
            HomeCityScanError("no qualified route", HomeCityScanState().result(
                HomeCityScanStopReason.NO_QUALIFIED_ROUTE)),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                binding = _binding(tmp, "v44_bank_body_menu", "v44_bank_return_home",
                                   "v44_watchtower_body_menu", "v44_watchtower_return_home")
                holder = {}
                deps = _deps(tmp, holder, annotation_factory=_armed_exchange)
                connect = deps.connect

                def camera_connect(**kwargs):
                    connection = connect(**kwargs)
                    core = connection.core
                    enter = core.enter_building_body_for_discovery

                    def scan(target, **kw):
                        if target is not HomeCityObjectId.BANK:
                            return enter(target, **kw)
                        for kind in ("wheel", "swipe"):
                            source = core._frame(kind, ScreenType.PNC_HOME_CITY)
                            core._input_seq += 1
                            dispatch = (
                                WheelDispatch((450, 500), (900, 1600), -1,
                                              "test", core._input_seq)
                                if kind == "wheel" else
                                SwipeDispatch((450, 600), (450, 400), 250,
                                              "test", "swipe", core._input_seq)
                            )
                            core._observer(InputDispatchRecord(
                                source.frame_ref, dispatch, source.artifact_path, True))
                        raise error

                    core.enter_building_body_for_discovery = scan
                    return connection

                evidence, path = LiveCaseRunner(
                    binding, replace(deps, connect=camera_connect)).run()
                bank, bank_return, tower, tower_return = evidence.case_results
                self.assertEqual(CaseStatus.FAILED, bank.status)
                self.assertEqual("qualified_body_entry", bank.unresolved_boundary)
                self.assertIsNone(bank.body_entry_event_id)
                self.assertEqual(2, len(bank.receipt_event_ids))
                self.assertEqual("body_dependency", bank_return.unresolved_boundary)
                self.assertEqual(CaseStatus.BLOCKED, bank_return.status)
                self.assertEqual(CaseStatus.PASSED, tower.status)
                self.assertEqual(CaseStatus.PASSED, tower_return.status)
                self.assertFalse(any(a.case_id == bank.case_id
                                     for a in evidence.logical_attempts))
                report = validate_live_evidence(binding, path)
                self.assertTrue(report.valid, report.findings)

    def test_uncertain_acquisition_input_halts_even_without_body_intent(self):
        for failure_event in (True, False):
            with self.subTest(failure_event=failure_event), tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                binding = _binding(tmp, "v44_bank_body_menu", "v44_watchtower_body_menu")
                holder = {}
                deps = _deps(tmp, holder)
                connect = deps.connect

                def uncertain_connect(**kwargs):
                    connection = connect(**kwargs)
                    core = connection.core

                    def scan(*args, **kw):
                        if failure_event:
                            source = core._frame("failed-pan", ScreenType.PNC_HOME_CITY)
                            core._observer(InputDispatchFailure(
                                source.frame_ref, "swipe", "dispatch", "RuntimeError",
                                artifact_path=source.artifact_path, home_city=True))
                            raise SelectorResolutionError("camera dispatch failed")
                        raise HomeCityScanError("input not confirmed", HomeCityScanState().result(
                            HomeCityScanStopReason.INPUT_UNCERTAIN))

                    core.enter_building_body_for_discovery = scan
                    return connection

                evidence, _ = LiveCaseRunner(
                    binding, replace(deps, connect=uncertain_connect)).run()
                self.assertEqual("uncertain_send", evidence.case_results[0].unresolved_boundary)
                self.assertEqual(CaseStatus.NOT_RUN, evidence.case_results[1].status)
                self.assertFalse(evidence.logical_attempts)

    def test_confirmed_body_with_failed_capture_still_halts_later_cases(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu", "v44_watchtower_body_menu")
            holder = {}
            deps = _deps(tmp, holder)
            connect = deps.connect

            def capture_failure_connect(**kwargs):
                connection = connect(**kwargs)
                enter = connection.core.enter_building_body_for_discovery

                def fail_after_body(*args, **kw):
                    enter(*args, **kw)
                    raise SelectorResolutionError("post-body capture failed")

                connection.core.enter_building_body_for_discovery = fail_after_body
                return connection

            evidence, _ = LiveCaseRunner(
                binding, replace(deps, connect=capture_failure_connect)).run()
            self.assertEqual("follow_up_capture", evidence.case_results[0].unresolved_boundary)
            self.assertEqual("dispatched", evidence.logical_attempts[0].status)
            self.assertEqual(CaseStatus.NOT_RUN, evidence.case_results[1].status)
            self.assertEqual(1, len(holder["core"].entry_calls))

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
                return LiveConnection(bundle=_FakeBundle(), core=core, account=SimpleNamespace(id="testing", instance_id="bluestacks-1"))

            deps = RunnerDeps(
                probe_source=lambda binding: SourceProbe(
                    head_sha=CANDIDATE_SHA, dirty_paths=(), source_root=binding.source_root
                ),
                connect=_connect,
                annotation_factory=None,
                execution_identity=_execution_identity(tmp),
                sleep=lambda _: None,
            )
            evidence, _ = LiveCaseRunner(binding, deps).run()
            result = evidence.case_results[0]
        self.assertEqual(CaseStatus.BLOCKED, result.status)
        self.assertEqual("precondition", result.unresolved_boundary)

    def test_four_cases_make_two_body_entries_and_two_returns(self):
        """QR2: two retained-witness returns; the buildings are never reopened."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp,
                "v44_bank_body_menu",
                "v44_bank_return_home",
                "v44_watchtower_body_menu",
                "v44_watchtower_return_home",
            )
            holder: dict = {
                "core_kwargs": {
                    "post_entry_screens": {
                        HomeCityObjectId.BANK: ScreenType.UNKNOWN,
                        HomeCityObjectId.WATCHTOWER: ScreenType.PNC_WATCHTOWER,
                    }
                }
            }
            exchange = _armed_exchange(tmp / "annotation")
            deps = _deps(tmp, holder, annotation_factory=lambda _: exchange)

            evidence, path = LiveCaseRunner(binding, deps).run()
            core = holder["core"]

            statuses = {r.case_id: r.status for r in evidence.case_results}
            self.assertEqual(
                {
                    "v44_bank_body_menu": CaseStatus.PASSED,
                    "v44_bank_return_home": CaseStatus.PASSED,
                    "v44_watchtower_body_menu": CaseStatus.PASSED,
                    "v44_watchtower_return_home": CaseStatus.PASSED,
                },
                statuses,
            )
            # Exactly two body entries — the returns never reopen a building.
            self.assertEqual(
                [HomeCityObjectId.BANK, HomeCityObjectId.WATCHTOWER],
                core.entry_calls,
            )
            self.assertEqual(2, len(core.control_calls))
            bank_scope, tower_scope = core.control_calls
            self.assertEqual("v44_bank_return_home", bank_scope.case_id)
            self.assertEqual("v44_bank_body_menu", bank_scope.body_case_id)
            self.assertEqual("v44_bank_body_menu", bank_scope.body_entry.case_id)
            self.assertEqual("v44_watchtower_return_home", tower_scope.case_id)
            self.assertEqual(
                "v44_watchtower_body_menu", tower_scope.body_entry.case_id
            )
            results = {r.case_id: r for r in evidence.case_results}
            self.assertEqual(
                "v44_bank_body_menu", results["v44_bank_return_home"].body_case_id
            )
            self.assertEqual(
                results["v44_bank_body_menu"].body_entry_event_id,
                results["v44_bank_return_home"].body_entry_event_id,
            )
            journal_path = Path(binding.report_root) / binding.run_id / "attempts.jsonl"
            entries = read_journal(journal_path)
            self.assertEqual((), pending_attempts(journal_path))
            begins = [e for e in entries if e.record_type == "attempt_begin"]
            finishes = [e for e in entries if e.record_type == "attempt_finish"]
            self.assertEqual(
                ["body_entry", "control", "body_entry", "control"],
                [e.payload.get("intent") for e in begins],
            )
            self.assertEqual(4, len(finishes))
            self.assertEqual(
                [e.attempt_id for e in begins],
                [e.attempt_id for e in finishes],
            )
            sequences = [
                e.event.dispatch.input_sequence
                for e in evidence.attributed_dispatches
                if hasattr(e.event, "dispatch")
            ]
            self.assertEqual([1, 2, 3, 4], sequences)
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )
            # The typed finalization overlay exists beside the sealed evidence.
            finalization = Path(binding.report_root) / binding.run_id / "finalization.json"
            self.assertTrue(finalization.exists())
            self.assertEqual(
                "pending_tester_review",
                json.loads(finalization.read_text(encoding="utf-8"))["review_state"],
            )

    def test_chip_discovery_binds_raw_follow_up_and_extends_the_chain(self):
        """body -> chip -> return: one body entry, one continuous receipt chain."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp,
                "v44_watchtower_body_menu",
                "v44_watchtower_selected_control_entry",
                "v44_watchtower_return_home",
            )
            holder: dict = {
                "core_kwargs": {
                    "post_entry_screens": {
                        HomeCityObjectId.WATCHTOWER: ScreenType.PNC_HOME_CITY,
                    },
                    "control_follow_up_screen": {
                        "v44_watchtower_selected_control_entry": ScreenType.PNC_WATCHTOWER,
                        "v44_watchtower_return_home": ScreenType.PNC_HOME_CITY,
                    },
                }
            }
            exchange = _armed_exchange(tmp / "annotation")
            evidence, path = LiveCaseRunner(
                binding, _deps(tmp, holder, annotation_factory=lambda _: exchange)
            ).run()
            core = holder["core"]
            results = {r.case_id: r for r in evidence.case_results}
            self.assertEqual(
                {
                    "v44_watchtower_body_menu": CaseStatus.PASSED,
                    "v44_watchtower_selected_control_entry": CaseStatus.PASSED,
                    "v44_watchtower_return_home": CaseStatus.PASSED,
                },
                {key: r.status for key, r in results.items()},
            )
            chip = results["v44_watchtower_selected_control_entry"]
            self.assertEqual("control_discovery", chip.purpose)
            self.assertEqual(
                "pnc_watchtower", chip.postcondition["screen_type"]
            )
            self.assertEqual(
                str(chip.follow_up_artifact), chip.postcondition["artifact_path"]
            )
            self.assertEqual(
                results["v44_watchtower_body_menu"].body_entry_event_id,
                chip.body_entry_event_id,
            )
            self.assertEqual(
                chip.body_entry_event_id,
                results["v44_watchtower_return_home"].body_entry_event_id,
            )
            # One body entry for the whole chain; the buildings are never reopened.
            self.assertEqual([HomeCityObjectId.WATCHTOWER], core.entry_calls)
            chip_scope, return_scope = core.control_calls
            self.assertEqual(
                "v44_watchtower_selected_control_entry", chip_scope.case_id
            )
            self.assertIs(
                DevelopmentalCasePurpose.CONTROL_DISCOVERY, chip_scope.purpose
            )
            self.assertEqual(
                (chip_scope.body_entry.receipt,), chip_scope.input_chain
            )
            chip_receipt = next(
                entry.event for entry in evidence.attributed_dispatches
                if entry.case_id == "v44_watchtower_selected_control_entry"
                and isinstance(entry.event, InputDispatchRecord)
            )
            # The return case starts from the full recorded chain, not a
            # synthetic tuple containing only the body receipt.
            self.assertEqual(
                (chip_scope.body_entry.receipt, chip_receipt),
                return_scope.input_chain,
            )
            self.assertEqual(
                ScreenType.PNC_WATCHTOWER,
                return_scope.latest_input_follow_up.screen_type,
            )
            begins = [
                entry.payload.get("intent")
                for entry in read_journal(
                    Path(binding.report_root) / binding.run_id / "attempts.jsonl"
                )
                if entry.record_type == "attempt_begin"
            ]
            self.assertEqual(["body_entry", "control", "control"], begins)
            sequences = [
                entry.event.dispatch.input_sequence
                for entry in evidence.attributed_dispatches
                if hasattr(entry.event, "dispatch")
            ]
            self.assertEqual([1, 2, 3], sequences)
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )

    def test_chip_left_on_home_keeps_the_return_pending(self):
        """A chip that stays Home passes raw discovery but cannot source the return."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp,
                "v44_watchtower_body_menu",
                "v44_watchtower_selected_control_entry",
                "v44_watchtower_return_home",
            )
            holder: dict = {
                "core_kwargs": {
                    "post_entry_screens": {
                        HomeCityObjectId.WATCHTOWER: ScreenType.PNC_HOME_CITY,
                    },
                    "control_follow_up_screen": {
                        "v44_watchtower_selected_control_entry": ScreenType.PNC_HOME_CITY,
                    },
                }
            }
            exchange = _armed_exchange(tmp / "annotation")
            evidence, _ = LiveCaseRunner(
                binding, _deps(tmp, holder, annotation_factory=lambda _: exchange)
            ).run()
            results = {r.case_id: r for r in evidence.case_results}
            chip = results["v44_watchtower_selected_control_entry"]
            self.assertEqual(CaseStatus.PASSED, chip.status)
            self.assertEqual("pnc_home_city", chip.postcondition["screen_type"])
            self.assertEqual(
                str(chip.follow_up_artifact), chip.postcondition["artifact_path"]
            )
            returned = results["v44_watchtower_return_home"]
            self.assertEqual(CaseStatus.FAILED, returned.status)
            self.assertEqual(
                "control_source_screen", returned.unresolved_boundary
            )
            self.assertEqual(1, len(holder["core"].control_calls))

    def test_control_case_without_its_body_case_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_return_home")
            holder: dict = {}
            with self.assertRaises(PreflightRefusal):
                LiveCaseRunner(binding, _deps(tmp, holder)).run()
            self.assertNotIn("core", holder)

    def test_annotation_timeout_blocks_the_case_and_closes_the_attempt(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu", "v44_bank_return_home")
            holder: dict = {}
            clock = {"t": 0.0}
            exchange = AnnotationExchange(
                tmp / "annotation", timeout_seconds=1.0, poll_seconds=2.0,
                sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                now=lambda: clock["t"],
            )
            deps = _deps(tmp, holder, annotation_factory=lambda _: exchange)
            evidence, _ = LiveCaseRunner(binding, deps).run()
            results = {r.case_id: r for r in evidence.case_results}
            journal_path = Path(binding.report_root) / binding.run_id / "attempts.jsonl"
            pending = pending_attempts(journal_path)
        self.assertEqual(CaseStatus.PASSED, results["v44_bank_body_menu"].status)
        result = results["v44_bank_return_home"]
        self.assertEqual(CaseStatus.BLOCKED, result.status)
        self.assertEqual("annotation_timeout", result.unresolved_boundary)
        self.assertEqual(
            results["v44_bank_body_menu"].body_entry_event_id,
            result.body_entry_event_id,
        )
        self.assertEqual((), pending)
        self.assertEqual(
            "annotation_timeout",
            evidence.logical_attempts[-1].status,
        )
        self.assertEqual(
            "control", evidence.logical_attempts[-1].intent
        )

    def test_unprovenanced_resume_frame_halts_the_run(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp,
                "v44_bank_body_menu",
                "v44_bank_return_home",
                "v44_watchtower_body_menu",
            )
            holder: dict = {}
            exchange = _armed_exchange(tmp / "annotation")

            base_deps = _deps(tmp, holder, annotation_factory=lambda _: exchange)
            original_connect = base_deps.connect

            def _connect(*, binding, run_dir, observer):
                connection = original_connect(
                    binding=binding, run_dir=run_dir, observer=observer
                )
                core = connection.core
                original_capture = core.capture_once

                def _capture(label, **kwargs):
                    observation = original_capture(label, **kwargs)
                    if "resume_state" in label:
                        object.__setattr__(observation, "frame_ref", None)
                    return observation

                core.capture_once = _capture
                return connection

            deps = RunnerDeps(
                probe_source=base_deps.probe_source,
                connect=_connect,
                annotation_factory=base_deps.annotation_factory,
                execution_identity=base_deps.execution_identity,
                sleep=lambda _: None,
            )
            evidence, _ = LiveCaseRunner(binding, deps).run()
            results = {r.case_id: r for r in evidence.case_results}
        self.assertEqual(CaseStatus.PASSED, results["v44_bank_body_menu"].status)
        self.assertEqual(CaseStatus.FAILED, results["v44_bank_return_home"].status)
        self.assertEqual(
            "resume_provenance", results["v44_bank_return_home"].unresolved_boundary
        )
        self.assertEqual(
            CaseStatus.NOT_RUN, results["v44_watchtower_body_menu"].status
        )

    def test_reused_run_id_refuses_before_connecting(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            (binding.report_root / binding.run_id).mkdir(parents=True)
            holder: dict = {}
            with self.assertRaises(PreflightRefusal):
                LiveCaseRunner(binding, _deps(tmp, holder)).run()
            self.assertNotIn("core", holder)

    def test_execution_identity_mismatch_refuses_before_connecting(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu")
            holder: dict = {}
            deps = RunnerDeps(
                probe_source=lambda binding: SourceProbe(
                    head_sha=CANDIDATE_SHA, dirty_paths=(), source_root=binding.source_root
                ),
                connect=lambda **kw: self.fail("connect must not run"),
                annotation_factory=None,
                execution_identity=lambda: ExecutionIdentity(
                    entry_point=tmp / "elsewhere.py",
                    import_root=tmp,
                    tool_root=tmp,
                    git_toplevel=tmp,
                    entry_tracked=False,
                ),
            )
            with self.assertRaises(PreflightRefusal) as raised:
                LiveCaseRunner(binding, deps).run()
            self.assertTrue(any("entry" in f for f in raised.exception.findings))
            self.assertNotIn("core", holder)

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
                execution_identity=deps.execution_identity,
            )
            runner = LiveCaseRunner(binding, deps)
            with self.assertRaises(PreflightRefusal):
                runner.run()
            self.assertTrue(holder["bundle"].closed)


class AdmitReservationTests(unittest.TestCase):
    def _status(self, state="active", display_name="BS-Testing", scope_id="scope-9"):
        return SimpleNamespace(
            reservation_state=state,
            owner_label="owner",
            scope_id=scope_id,
            display_name=display_name,
        )

    def test_inactive_states_pass_through(self):
        self.assertEqual(
            "none",
            admit_reservation(
                self._status("none"), receipt_path=None, renew=lambda p: None
            ),
        )
        self.assertEqual(
            "expired",
            admit_reservation(
                self._status("expired"), receipt_path=None, renew=lambda p: None
            ),
        )

    def test_foreign_active_reservation_defers_without_a_receipt(self):
        with self.assertRaises(PreflightRefusal) as raised:
            admit_reservation(
                self._status(), receipt_path=None, renew=lambda p: None
            )
        self.assertIn("owner:scope-9", str(raised.exception))

    def test_own_active_reservation_renews_and_admits(self):
        renewed = SimpleNamespace(instance_keys={"bs-testing"}, scope_id="scope-9")
        calls = []
        result = admit_reservation(
            self._status(),
            receipt_path=Path("receipt.json"),
            renew=lambda p: (calls.append(p), renewed)[1],
        )
        self.assertEqual("own", result)
        self.assertEqual([Path("receipt.json")], calls)

    def test_foreign_receipt_that_does_not_renew_defers(self):
        def _deny(path):
            raise RuntimeError("foreign capability")

        with self.assertRaises(PreflightRefusal):
            admit_reservation(
                self._status(), receipt_path=Path("receipt.json"), renew=_deny
            )

    def test_own_receipt_not_covering_the_instance_defers(self):
        renewed = SimpleNamespace(instance_keys={"other-instance"}, scope_id="scope-9")
        with self.assertRaises(PreflightRefusal) as raised:
            admit_reservation(
                self._status(),
                receipt_path=Path("receipt.json"),
                renew=lambda p: renewed,
            )
        self.assertIn("does not cover", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
