"""Exercise worker boundaries offline; no test authenticates or calls a model."""

import argparse
import ctypes
from ctypes import wintypes as wt
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import devin_worker as worker


def process_running(pid):
    """Independently check a retained descendant PID without trusting runner state."""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    api.OpenProcess.restype = wt.HANDLE
    api.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    api.WaitForSingleObject.restype = wt.DWORD
    api.CloseHandle.argtypes = [wt.HANDLE]
    api.CloseHandle.restype = wt.BOOL
    handle = api.OpenProcess(0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            return False
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        result = api.WaitForSingleObject(handle, 0)
        if result not in (0, 258):
            raise ctypes.WinError(ctypes.get_last_error())
        return result == 258
    finally:
        api.CloseHandle(handle)


class ExportTests(unittest.TestCase):
    """Check exported evidence with small files, without Git or worker processes."""

    def setUp(self):
        """Give each export check its own artifact directory and valid seed response."""
        temporary = tempfile.TemporaryDirectory(prefix="devin export ")
        self.addCleanup(temporary.cleanup)
        self.export = Path(temporary.name) / "export.json"
        self.data = {"session_id": "fixture-session", "agent": {"tool_definitions": []},
                     "steps": [{"source": "agent", "model_name": worker.MODEL, "message": "Done"}]}

    def test_stale_resumed_response_is_incomplete(self):
        """An old completion in a resumed export cannot satisfy a new prompt."""
        worker.write_json(self.export, self.data)
        result = worker.export_evidence(self.export, "fixture-session", previous_agent_steps=1)
        self.assertFalse(result["has_final_response"])
        self.assertFalse(self.export.with_name("handoff.md").exists())

    def test_nested_tools_and_generation_mismatch_are_rejected(self):
        """Model selection cannot conceal nested tooling or conflicting serving telemetry."""
        self.data["agent"]["tool_definitions"] = [{"function": {"name": "run_subagent"}}]
        worker.write_json(self.export, self.data)
        with self.assertRaisesRegex(RuntimeError, "Nested subagent"):
            worker.export_evidence(self.export)
        self.data["agent"]["tool_definitions"] = []
        self.data["steps"][0]["extra"] = {"generation_model": "different-provider"}
        worker.write_json(self.export, self.data)
        with self.assertRaisesRegex(RuntimeError, "generation-model"):
            worker.export_evidence(self.export)


class MonitorTests(unittest.TestCase):
    """Verify bounded diagnostics and notification failure without model calls or real waits."""

    def setUp(self):
        """Create a minimal durable turn without repository or process setup."""
        temporary = tempfile.TemporaryDirectory(prefix="devin monitor ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = {"turn": 1, "run_dir": str(self.root), "turn_dir": str(self.root),
                      "status": "running", "started_at": time.time() - 43200,
                      "heartbeat_at": time.time() - 180, "session_id": None}
        worker.write_json(self.root / "state.json", self.state)

    def test_status_excludes_content_and_bounds_diagnostics(self):
        """Normal checks expose metadata only; requested excerpts ignore incomplete event writes."""
        event = {"hook_event_name": "PostToolUse", "session_id": "session", "tool_name": "exec",
                 "tool_input": {"command": "PRIVATE_COMMAND" * 1000},
                 "tool_response": {"success": False, "error": "PRIVATE_ERROR" * 1000}}
        with patch.dict(os.environ, {"DEVIN_IMPLEMENT_TURN_DIR": str(self.root)}), \
             patch("sys.stdin", io.StringIO(json.dumps(event))):
            worker.hook()
        with (self.root / "identity.jsonl").open("a", encoding="utf-8") as stream:
            stream.write('{"unfinished":')
        (self.root / "stdout.log").write_text("PRIVATE_OUTPUT\n" * 1000)
        (self.root / "stderr.log").write_text("PRIVATE_STDERR\n" * 1000)
        result = worker.status(self.root)
        self.assertNotIn("PRIVATE_", json.dumps(result))
        self.assertEqual(result["supervisor_check"], "stale: inspect supervisor")
        self.assertEqual(result["session_id"], "session")
        self.assertEqual(result["status"], "running")
        detailed = worker.status(self.root, recent=True)
        self.assertEqual(len(detailed["recent_activity"]), 1)
        self.assertLessEqual(len(detailed["recent_activity"][0]["input_excerpt"]), 400)
        self.assertLessEqual(len(detailed["recent_activity"][0]["error_excerpt"]), 400)
        self.assertLessEqual(len(detailed["stdout_tail"].encode()), 2048)
        self.assertLessEqual(len(detailed["stderr_tail"].encode()), 1024)
        self.assertEqual(worker.read_json(self.root / "state.json"), self.state)

    def test_notification_preserves_results_on_delivery_failure(self):
        """A messaging failure leaves results available for the scheduled fallback."""
        self.state["status"] = "exited"
        worker.write_json(self.root / "result.json", self.state)
        with patch.object(worker, "send_notification", new_callable=AsyncMock, side_effect=TimeoutError("Messaging timed out")):
            worker.notify_completion(self.state, "test-task")
        self.assertEqual(worker.read_json(self.root / "notification.json")["status"], "pending")
        self.assertEqual(worker.read_json(self.root / "result.json"), self.state)
        with patch.object(worker, "send_notification", new_callable=AsyncMock) as send:
            worker.notify_completion(self.state, "test-task")
        self.assertEqual(worker.read_json(self.root / "notification.json")["status"], "delivered")
        self.assertEqual(send.call_args.args[0], "test-task")
        self.assertIn(str(self.root / "result.json"), send.call_args.args[1])

    def test_cancellation_grace_is_bounded_and_old_adapters_fall_back(self):
        """Native exit gets its grace; unresponsive and older adapters reach process cleanup."""
        (self.root / "cancel.request").touch()
        for controls, exit_at, expected in [(["cancel"], 3, "requested"), (["cancel"], None, "forced"), ([], None, "forced")]:
            with self.subTest(controls=controls, exit_at=exit_at):
                worker.write_json(self.root / "acp-session.json", {"controls": controls})
                self.state.pop("cancellation", None)
                tick = [0]

                def wait(timeout):
                    """Advance only the supervisor clock, preserving the real grace contract."""
                    tick[0] += timeout
                    if tick[0] == exit_at:
                        return 0
                    raise subprocess.TimeoutExpired("fixture", timeout)

                with patch.object(worker.time, "monotonic", side_effect=lambda: tick[0]):
                    worker.wait_for_exit(SimpleNamespace(wait=wait), self.state, self.root)
                self.assertEqual(self.state["cancellation"], expected)
                self.assertEqual(tick[0], exit_at or (worker.CANCEL_GRACE_SECONDS + 1 if controls else 1))


class WorkerTests(unittest.TestCase):
    """Use real Git and contained child processes with a deterministic fake Devin."""

    @classmethod
    def setUpClass(cls):
        """Prepare one isolated repository; tests restore only their own fixture files."""
        cls.temporary = tempfile.TemporaryDirectory(prefix="devin adapter ")
        cls.root = Path(cls.temporary.name)
        cls.repo = cls.root / "repo"
        cls.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(cls.repo)], check=True)
        (cls.repo / "existing.txt").write_text("initial\n")
        subprocess.run(["git", "-C", str(cls.repo), "add", "existing.txt"], check=True)
        subprocess.run(["git", "-C", str(cls.repo), "-c", "user.name=Adapter test", "-c",
                        "user.email=test@localhost", "commit", "-qm", "Seed adapter test"], check=True)
        cls.head = worker.git(cls.repo, "rev-parse", "HEAD")
        cls.git_dir = Path(worker.git(cls.repo, "rev-parse", "--absolute-git-dir"))
        cls.brief = cls.root / "brief.md"
        cls.brief.write_text("Implement the bounded fixture.")
        cls.fake = cls.root / "fake_devin.py"
        cls.fake.write_text('''"""Deterministic CLI fixture, never a real model."""
import json, os, pathlib, subprocess, sys, time
args = sys.argv[1:]
export = pathlib.Path(args[args.index('--export') + 1])
config = json.loads(pathlib.Path(args[args.index('--config') + 1]).read_text())
assert config['subagents_enabled'] is False
assert config['attribution'] is False
assert config['agent']['compaction_threshold_tokens'] == 100_000
assert os.environ['DEVIN_IMPLEMENT_ROLE'] == 'worker'
assert args[args.index('--model') + 1] == 'swe-2-max'
permission = args[args.index('--permission-mode') + 1]
assert permission == os.environ['DEVIN_ADAPTER_EXPECTED_PERMISSION']
assert args[args.index('--respect-workspace-trust') + 1] == ('false' if permission == 'dangerous' else 'true')
behavior = os.environ.get('DEVIN_ADAPTER_TEST', 'success')
if behavior == 'console':
    import ctypes
    assert ctypes.windll.kernel32.GetConsoleCP() != 0, 'CLI has no attached console'
    sys.stdout.buffer.write('visible stdout: caf\\u00e9\\n'.encode('utf-8'))
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write('visible stderr: caf\\u00e9\\n'.encode('utf-8'))
    sys.stderr.buffer.flush()
if behavior in ('sleep', 'graceful-cancel'):
    export.with_name('acp-session.json').write_text(json.dumps({'session_id':'fixture-session','controls':['cancel']}))
    export.write_text(json.dumps({'nodes':[], 'main_chain_id':None, 'tools':[]}))
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)'])
    export.with_name('descendant.pid').write_text(str(child.pid))
    if behavior == 'graceful-cancel':
        while not export.with_name('cancel.request').exists():
            time.sleep(0.02)
        child.terminate()
        child.wait(timeout=5)
        export.with_name('cancel-native.json').write_text(json.dumps({'status':'acknowledged'}))
        sys.exit(0)
    time.sleep(90)
if behavior == 'failure':
    pathlib.Path('partial.txt').write_text('preserve partial result')
    sys.exit(7)
model = 'wrong-model' if behavior == 'model-mismatch' else 'swe-2-max'
step = {'source':'agent','model_name':model,'message':'READY_FOR_REVIEW: fixture complete.'}
if behavior == 'denied':
    step.update(message='', tool_calls=[{'function_name':'exec'}])
export.write_text(json.dumps({'session_id':'fixture-session','agent':{'tool_definitions':[]},
                             'steps':[step] * (2 if '--resume' in args else 1),
                             'final_metrics':{'total_prompt_tokens':12}}))
''', encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        """Remove only the isolated temporary fixture after contained processes stop."""
        cls.temporary.cleanup()

    def setUp(self):
        """Give each test unique evidence and no previous writer record."""
        self.run_dir = self.root / self.id().split(".")[-1]
        self.args = argparse.Namespace(repo=str(self.repo), expected_head=self.head,
            run_dir=str(self.run_dir), brief=str(self.brief), resume=False,
            allow_rule=[], permission_mode="accept-edits", notify_thread=None, console=False)
        (self.repo / "existing.txt").write_text("user's uncommitted work\n")
        lock = self.git_dir / "devin-implement.lock"
        lock.unlink(missing_ok=True)

    def invoke(self, behavior="success", through_cli=False):
        """Run real transport via explicit test settings or the public CLI defaults."""
        original_output = subprocess.check_output
        original_popen = subprocess.Popen

        def output(command, **kwargs):
            """Return account/version fixtures while preserving actual Git subprocesses."""
            if command[0] == "fake-devin.exe":
                return "fixture-version" if command[1] == "--version" else json.dumps({
                    "families": [{"variants": [{"model_uid": worker.MODEL}]}]})
            return original_output(command, **kwargs)

        def popen(command, **kwargs):
            """Substitute a deterministic CLI inside the real Windows job bootstrap."""
            if len(command) > 6 and command[6] == "fake-devin.exe":
                # Supervisor fixtures isolate lifetime; ACP has separate protocol tests.
                self.assertEqual(Path(command[5]).name, "devin_acp.py")
                command = [*command[:4], sys.executable, str(self.fake), *command[7:]]
            return original_popen(command, **kwargs)

        with patch.object(worker, "executable", return_value="fake-devin.exe"), \
             patch.object(subprocess, "check_output", side_effect=output), \
             patch.object(subprocess, "Popen", side_effect=popen), \
             patch.dict(os.environ, {"DEVIN_ADAPTER_TEST": behavior,
                                     "CODEX_THREAD_ID": "",
                                     "DEVIN_ADAPTER_EXPECTED_PERMISSION": "dangerous" if through_cli else self.args.permission_mode}), \
             redirect_stdout(io.StringIO()):
            if not through_cli:
                return worker.run(self.args)
            arguments = ["run", "--repo", self.args.repo, "--expected-head", self.args.expected_head,
                         "--run-dir", self.args.run_dir, "--brief", self.args.brief]
            if getattr(self.args, "preamble_file", None):
                arguments.extend(["--preamble-file", self.args.preamble_file])
            if self.args.resume:
                arguments.append("--resume")
            if not self.args.console:
                arguments.append("--no-console")
            return worker.main(arguments)

    def test_visible_console_preserves_both_logs(self):
        """The public default attaches a real console and retains Unicode stdout/stderr."""
        self.args.console = True
        self.assertEqual(self.invoke("console", through_cli=True), 0)
        turn = self.run_dir / "turn-001"
        self.assertEqual((turn / "stdout.log").read_text(encoding="utf-8"), "visible stdout: café\n")
        self.assertEqual((turn / "stderr.log").read_text(encoding="utf-8"), "visible stderr: café\n")
        self.assertTrue(worker.read_json(self.run_dir / "state.json")["writers_stopped"])

    def test_fresh_and_resume_preserve_state(self):
        """Public fresh/resume defaults grant full access and preserve unrelated work/identity."""
        self.assertEqual(self.invoke(through_cli=True), 0)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["session_id"], "fixture-session")
        self.assertEqual(state["permission_mode"], "dangerous")
        self.assertFalse(state["respect_workspace_trust"])
        self.args.resume = True
        self.assertEqual(self.invoke(through_cli=True), 0)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["turn"], 2)
        self.assertEqual(state["permission_mode"], "dangerous")
        self.assertFalse(state["respect_workspace_trust"])
        self.assertEqual(state["command"][-2:], ["--resume", "fixture-session"])
        self.assertTrue((self.run_dir / "turn-001/handoff.md").is_file())
        self.assertEqual((self.repo / "existing.txt").read_text(), "user's uncommitted work\n")
        self.assertTrue(state["writers_stopped"])

    def test_custom_preamble_replaces_implementation_role(self):
        """A specialized worker can replace the default implementation reporting contract."""
        preamble = self.root / "live-test-preamble.md"
        preamble.write_text("Return BLOCKED only for required user intervention.", encoding="utf-8")
        self.args.preamble_file = str(preamble)
        self.assertEqual(self.invoke(through_cli=True), 0)
        prompt = (self.run_dir / "turn-001" / "prompt.md").read_text(encoding="utf-8")
        self.assertTrue(prompt.startswith("Return BLOCKED only for required user intervention.\n\n"))
        self.assertNotIn("NEEDS_LEAD", prompt)
        self.args.resume = True
        self.args.preamble_file = None
        self.assertEqual(self.invoke(through_cli=True), 0)
        resumed = (self.run_dir / "turn-002" / "prompt.md").read_text(encoding="utf-8")
        self.assertTrue(resumed.startswith("Return BLOCKED only for required user intervention.\n\n"))
        self.assertNotIn("NEEDS_LEAD", resumed)

    def test_zero_exit_without_handoff_is_incomplete(self):
        """A rejected final tool call cannot masquerade as completed transport."""
        self.assertEqual(self.invoke("denied"), 1)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["status"], "incomplete")
        self.assertFalse((self.run_dir / "turn-001/handoff.md").exists())

    def test_model_mismatch_preserves_evidence(self):
        """Refuse acceptance evidence from a different serving model without retrying."""
        with self.assertRaisesRegex(RuntimeError, "exclusively"):
            self.invoke("model-mismatch")
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["writers_stopped"])
        self.assertTrue((self.run_dir / "turn-001/export.json").exists())

    def test_failure_preserves_partial_edits(self):
        """A nonzero CLI exit retains useful source work and records failure."""
        self.assertEqual(self.invoke("failure"), 1)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["exit_code"], 7)
        self.assertEqual(state["status"], "failed")
        self.assertEqual((self.repo / "partial.txt").read_text(), "preserve partial result")

    def test_wrong_baseline_prevents_launch(self):
        """Fail before creating a run for a stale revision."""
        self.args.expected_head = "0" * 40
        with self.assertRaisesRegex(RuntimeError, "Revision changed"):
            worker.run(self.args)
        self.assertFalse(self.run_dir.exists())

    def test_wrong_directory_prevents_launch(self):
        """Reject a nested directory instead of accepting Git's ancestor discovery."""
        nested = self.repo / "nested"
        nested.mkdir(exist_ok=True)
        self.args.repo = str(nested)
        with self.assertRaisesRegex(RuntimeError, "exact Git"):
            worker.run(self.args)

    def test_recursive_worker_prevents_launch(self):
        """An inherited worker marker prevents nested delegation before any discovery."""
        with patch.dict(os.environ, {worker.ROLE_VARIABLE: "worker"}):
            with self.assertRaisesRegex(RuntimeError, "cannot launch another"):
                worker.run(self.args)

    def test_concurrent_writer_is_rejected(self):
        """Only one helper may own a checkout even with distinct run directories."""
        with worker.writer_lock(self.repo, self.root / "other-run"):
            with self.assertRaisesRegex(RuntimeError, "owns this checkout"):
                with worker.writer_lock(self.repo, self.run_dir):
                    self.fail("second writer acquired the lock")

    def test_interrupted_writer_requires_reconciliation(self):
        """An OS-released lock does not make an unresolved prior run safe to replace."""
        previous = self.root / "interrupted"
        previous.mkdir()
        worker.write_json(previous / "state.json", {"status": "running"})
        with worker.writer_lock(self.repo, previous):
            pass
        with self.assertRaisesRegex(RuntimeError, "reconciliation"):
            with worker.writer_lock(self.repo, self.run_dir):
                self.fail("unreconciled writer was replaced")

    def test_resume_cannot_change_repository(self):
        """A valid HEAD in another task cannot redirect a persistent conversation."""
        self.run_dir.mkdir()
        worker.write_json(self.run_dir / "state.json", {"repo": str(self.root), "session_id": "fixture-session"})
        self.args.resume = True
        with self.assertRaisesRegex(RuntimeError, "Resume repository differs"):
            worker.run(self.args)

    def test_long_running_worker_survives_until_explicit_cancellation(self):
        """Advance twelve hours, then verify an unresponsive native cancel falls back to tree cleanup."""
        shift = [0]
        observations = []
        turn_dir = self.run_dir / "turn-001"

        def request_cancel():
            """Observe a refreshed heartbeat after the clock jump before requesting cancellation."""
            try:
                deadline = time.monotonic() + 8
                while not (turn_dir / "descendant.pid").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                shift[0] = 43200
                while time.monotonic() < deadline:
                    state = worker.read_json(self.run_dir / "state.json")
                    if state["heartbeat_at"] - state["started_at"] >= 43200:
                        observations.append((worker.status(self.run_dir),
                                             process_running(int((turn_dir / "descendant.pid").read_text()))))
                        break
                    time.sleep(0.02)
            finally:
                (turn_dir / "cancel.request").touch()

        signal = threading.Thread(target=request_cancel)
        signal.start()
        try:
            clock = SimpleNamespace(time=lambda: time.time() + shift[0],
                                    monotonic=lambda: time.monotonic() + shift[0], sleep=time.sleep)
            with patch.object(worker, "snapshot", return_value={"head": self.head, "status": " M existing.txt"}), \
                 patch.object(worker, "time", clock), patch.object(worker, "CANCEL_GRACE_SECONDS", 0.1):
                self.assertEqual(self.invoke("sleep", through_cli=True), 1)
        finally:
            signal.join(timeout=12)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(len(observations), 1, "worker did not survive the twelve-hour clock advance")
        self.assertEqual(observations[0][0]["status"], "running")
        self.assertGreaterEqual(observations[0][0]["elapsed_seconds"], 43200)
        self.assertTrue(observations[0][1], "descendant stopped without explicit cancellation")
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(state["cancellation"], "forced")
        self.assertEqual(state["session_id"], "fixture-session")
        self.assertTrue(state["writers_stopped"])
        self.assertFalse(process_running(int((self.run_dir / "turn-001/descendant.pid").read_text())))

    def test_graceful_cancel_releases_descendants_and_preserves_session(self):
        """A cooperative native stop exits without job termination and retains resume identity."""
        turn = self.run_dir / "turn-001"

        def cancel_when_ready():
            """Request cancellation only after the contained fixture child is observable."""
            deadline = time.monotonic() + 8
            while not (turn / "descendant.pid").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            if (turn / "descendant.pid").exists():
                with redirect_stdout(io.StringIO()):
                    worker.main(["cancel", "--run-dir", str(self.run_dir)])

        signal = threading.Thread(target=cancel_when_ready)
        signal.start()
        try:
            with patch.object(worker, "snapshot", return_value={"head": self.head, "status": " M existing.txt"}), \
                 patch.object(worker.Job, "stop", side_effect=AssertionError("Graceful cancellation must not terminate the job")):
                self.assertEqual(self.invoke("graceful-cancel"), 1)
        finally:
            signal.join(timeout=10)
        state = worker.read_json(self.run_dir / "state.json")
        self.assertEqual(state["status"], "cancelled")
        self.assertEqual(state["cancellation"], "graceful")
        self.assertEqual(state["session_id"], "fixture-session")
        self.assertTrue(state["writers_stopped"])
        self.assertFalse(process_running(int((turn / "descendant.pid").read_text())))

    def test_supervisor_death_stops_descendants(self):
        """Abrupt host loss closes the job even when normal cleanup never executes."""
        import windows_job
        supervisor_script = self.root / "supervisor.py"
        child_marker = self.root / "orphan.pid"
        script_directory = str(Path(worker.__file__).parent)
        supervisor_script.write_text(
            "import subprocess, sys, time\n"
            f"sys.path.insert(0, {script_directory!r})\n"
            "from windows_job import Job\n"
            "job = Job()\n"
            f"subprocess.Popen([sys.executable, {str(Path(windows_job.__file__))!r}, job.name, "
            f"{str(self.repo)!r}, sys.executable, '-c', "
            f"{('import os, pathlib, time; pathlib.Path(' + repr(str(child_marker)) + ').write_text(str(os.getpid())); time.sleep(90)')!r}])\n"
            "time.sleep(90)\n", encoding="utf-8")
        supervisor = subprocess.Popen([sys.executable, str(supervisor_script)], creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 5
            while not child_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(child_marker.exists(), "contained child did not start")
            child_pid = int(child_marker.read_text())
            self.assertTrue(process_running(child_pid))
            supervisor.kill()
            supervisor.wait(timeout=5)
            deadline = time.monotonic() + 3
            while process_running(child_pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(process_running(child_pid))
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
            supervisor.wait(timeout=5)


class TimedResult(unittest.TextTestResult):
    """Expose actual per-test costs for the repository's completion notices."""

    def startTest(self, test):
        """Start timing execution after shared suite preparation."""
        self.started = time.monotonic()
        super().startTest(test)

    def stopTest(self, test):
        """Print a machine-readable duration alongside ordinary unittest evidence."""
        self.stream.writeln(f"COST {test.id()} {time.monotonic() - self.started:.3f}s")
        super().stopTest(test)


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, resultclass=TimedResult))
