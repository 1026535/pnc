"""Synthetic CLI and isolated repository fixture for worker process tests."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType
from typing import Any
from unittest.mock import patch


class WorkerFixture:
    """Provide a fake CLI and disposable Git task for worker end-to-end tests."""

    def __init__(self, worker: ModuleType) -> None:
        self.worker = worker
        self.temporary = tempfile.TemporaryDirectory(prefix="agent runtime worker ")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "existing.txt").write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "existing.txt"], check=True)
        subprocess.run([
            "git", "-C", str(self.repo), "-c", "user.name=Adapter test", "-c",
            "user.email=test@localhost", "commit", "-qm", "Seed adapter test",
        ], check=True)
        self.head = worker.git(self.repo, "rev-parse", "HEAD")
        self.git_dir = Path(worker.git(self.repo, "rev-parse", "--absolute-git-dir"))
        self.brief = self.root / "brief.md"
        self.brief.write_text("Implement the bounded fixture.", encoding="utf-8")
        self.fake = self.root / "fake_devin.py"
        self.fake.write_text(_FAKE_DEVIN, encoding="utf-8")
        self.args: argparse.Namespace | None = None
        self.run_dir: Path | None = None

    def close(self) -> None:
        """Remove the isolated repository after its child processes have stopped."""
        self.temporary.cleanup()

    def prepare(self, test_id: str) -> argparse.Namespace:
        """Return fresh worker arguments and reset the fixture checkout."""
        self.run_dir = self.root / test_id.rsplit(".", 1)[-1]
        self.args = argparse.Namespace(
            repo=str(self.repo), expected_head=self.head, run_dir=str(self.run_dir),
            brief=str(self.brief), resume=False, allow_rule=[],
            permission_mode="accept-edits", notify_thread=None, console=False,
        )
        (self.repo / "existing.txt").write_text("user's uncommitted work\n", encoding="utf-8")
        (self.git_dir / "devin-implement.lock").unlink(missing_ok=True)
        return self.args

    def invoke(
        self,
        behavior: str = "success",
        *,
        through_cli: bool = False,
        allow_native_console: bool = False,
    ) -> int:
        """Invoke the real worker against a deterministic fake CLI process."""
        if self.args is None:
            raise RuntimeError("Call prepare() before invoking the worker fixture.")
        worker = self.worker
        original_output = subprocess.check_output
        original_popen = subprocess.Popen

        def output(command: list[str], **kwargs: Any) -> str:
            """Return account/version fixtures while preserving actual Git subprocesses."""
            if command[0] == "fake-devin.exe":
                return "fixture-version" if command[1] == "--version" else json.dumps({
                    "families": [{"variants": [{"model_uid": worker.MODEL}]}],
                })
            return original_output(command, **kwargs)

        def popen(command: list[str], **kwargs: Any) -> subprocess.Popen:
            """Substitute the deterministic CLI inside the real Windows job bootstrap."""
            new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", None)
            flags = kwargs.get("creationflags") or 0
            if new_console is not None and flags & new_console and not allow_native_console:
                raise AssertionError("Portable worker fixtures may not request CREATE_NEW_CONSOLE.")
            if len(command) > 1 and Path(command[1]).name == "windows_job.py":
                flag_name = "CREATE_NEW_CONSOLE" if self.args.console else "CREATE_NO_WINDOW"
                expected_flag = getattr(subprocess, flag_name, None)
                if expected_flag is None or not flags & expected_flag:
                    raise AssertionError(f"Worker bootstrap must request {flag_name}.")
            if len(command) > 6 and command[6] == "fake-devin.exe":
                # The process supervisor owns lifetime; ACP has separate protocol tests.
                if Path(command[5]).name != "devin_acp.py":
                    raise AssertionError(f"Unexpected ACP launcher: {command[5]}")
                command = [*command[:4], sys.executable, str(self.fake), *command[7:]]
            return original_popen(command, **kwargs)

        with patch.object(worker, "executable", return_value="fake-devin.exe"), \
                patch.object(subprocess, "check_output", side_effect=output), \
                patch.object(subprocess, "Popen", side_effect=popen), \
                patch.dict(os.environ, {
                    "DEVIN_ADAPTER_TEST": behavior,
                    "CODEX_THREAD_ID": "",
                    "DEVIN_ADAPTER_EXPECTED_PERMISSION": (
                        "dangerous" if through_cli else self.args.permission_mode
                    ),
                }), redirect_stdout(io.StringIO()):
            if not through_cli:
                return worker.run(self.args)
            arguments = [
                "run", "--repo", self.args.repo, "--expected-head", self.args.expected_head,
                "--run-dir", self.args.run_dir, "--brief", self.args.brief,
            ]
            if getattr(self.args, "preamble_file", None):
                arguments.extend(["--preamble-file", self.args.preamble_file])
            if self.args.resume:
                arguments.append("--resume")
            if not self.args.console:
                arguments.append("--no-console")
            return worker.main(arguments)


_FAKE_DEVIN = '''"""Deterministic CLI fixture, never a real model."""
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
export.with_name('context.json').write_text(json.dumps({
    'used_tokens':36425, 'peak_used_tokens':130770,
    'window_tokens':262000, 'compactions_completed':1}))
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
if behavior == 'acp-error':
    pathlib.Path(os.environ['DEVIN_IMPLEMENT_TURN_DIR'], 'acp-error.json').write_text(
        json.dumps({'error': 'protocol invalid_argument (trace ID: t1)',
                    'acp_error': {'code': -32013, 'data': {'cognition.ai/retryable': True}}}))
    sys.exit(1)
model = 'wrong-model' if behavior == 'model-mismatch' else 'swe-2-max'
step = {'source':'agent','model_name':model,'message':'READY_FOR_REVIEW: fixture complete.'}
if behavior == 'denied':
    step.update(message='', tool_calls=[{'function_name':'exec'}])
export.write_text(json.dumps({'session_id':'fixture-session','agent':{'tool_definitions':[]},
                             'steps':[step] * (2 if '--resume' in args else 1),
                             'final_metrics':{'total_prompt_tokens':12}}))
'''
