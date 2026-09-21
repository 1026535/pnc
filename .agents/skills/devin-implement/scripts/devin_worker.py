"""Run/resume one SWE-2 Max turn with bounded output and durable local evidence.

The skill owns engineering decisions and acceptance. This script owns only native
process lifetime, one-writer exclusion, session identity, and transport evidence.
It never approves changes, retries a model, publishes Git state, or cleans sources.
"""

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from windows_job import Job

MODEL = "swe-2-max"
ROLE_VARIABLE = "DEVIN_IMPLEMENT_ROLE"
CANCEL_GRACE_SECONDS = 15
CATALOG_MAX_ATTEMPTS = 3
DEFAULT_PREAMBLE = (
    "You are the SWE-2 implementation worker. Do not delegate, invoke orchestration skills, "
    "change model/configuration, or start detached processes. Execute the concrete package "
    "and its checks; make routine implementation choices within the lead's decisions. Return "
    "NEEDS_LEAD with evidence when the approach is challenged, complex reasoning or a material "
    "decision is needed, or repeated attempts yield no useful new evidence. Preserve partial "
    "work and return at the package boundary rather than expanding into open-ended problem-solving. "
    "Use the requested compact handoff instead of interactive question tools."
)


def read_json(path):
    """Read CLI and local JSON, tolerating the UTF-8 BOM emitted by PowerShell."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    """Replace a record atomically, allowing a short Windows reader-lock interval.

    Windows can deny replacement while a status reader has the destination
    open. Retry only that replace operation for at most 350 ms; persistent
    denial and other filesystem errors still fail without discarding evidence.
    """
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    for attempt in range(4):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in (5, 32) or attempt == 3:
                raise
            time.sleep(0.05 * (2 ** attempt))


def git(repo, *arguments):
    """Run Git without a shell; preserve command failures as transport failures."""
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True, encoding="utf-8").strip()


def executable():
    """Reuse PATH or the existing Windows install even when Codex has an older PATH."""
    found = shutil.which("devin")
    if found:
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "devin/cli/bin/devin.exe"
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError("Devin CLI not found. Install/authenticate once using the runtime reference.")


def model_catalog(binary: str, turn_dir: Path) -> dict:
    """Retry only the observed catalog transport failure, never an agent prompt."""
    command = [binary, "models", "list", "--format", "json"]
    for attempt in range(1, CATALOG_MAX_ATTEMPTS + 1):
        try:
            output = subprocess.check_output(
                command, text=True, encoding="utf-8", stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as error:
            stderr = error.stderr or ""
            evidence = turn_dir / f"catalog-attempt-{attempt}.stderr.log"
            evidence.write_text(stderr, encoding="utf-8")
            retryable = any(
                line.startswith("Error: Connection failed: Connect HTTP error:")
                and "error sending request for url" in line
                and "/exa.api_server_pb.ApiServerService/GetCliModelConfigs" in line
                for line in stderr.splitlines()
            )
            if not retryable or attempt == CATALOG_MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Devin model catalog failed after {attempt} attempt(s) "
                    f"(exit {error.returncode}); see {evidence}."
                ) from error
            delay = 2 * attempt
            print(
                f"Devin catalog connection attempt {attempt}/{CATALOG_MAX_ATTEMPTS} "
                f"failed; retrying in {delay}s. Evidence: {evidence}",
                file=sys.stderr, flush=True,
            )
            time.sleep(delay)
        else:
            return json.loads(output)
    raise AssertionError("Catalog attempt limit must be positive.")


def repository(path, expected_head):
    """Reject a fallback CWD, nested directory, or unexpected revision before launch."""
    repo = Path(path).resolve(strict=True)
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo:
        raise RuntimeError("--repo must name the exact Git working-tree root.")
    actual = git(repo, "rev-parse", "HEAD")
    if actual != expected_head:
        raise RuntimeError(f"Revision changed: expected {expected_head}, found {actual}.")
    return repo


@contextmanager
def writer_lock(repo, run_dir):
    """Use an OS-released lock per Git worktree; it is not an engineering ledger."""
    import msvcrt
    lock_path = Path(git(repo, "rev-parse", "--absolute-git-dir")) / "devin-implement.lock"
    with lock_path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b" ")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError("Another devin-implement worker owns this checkout.") from error
        try:
            stream.seek(1)
            previous_path = stream.read().decode("utf-8")
            previous_state = Path(previous_path) / "state.json" if previous_path else None
            if previous_state and previous_state.is_file():
                previous = read_json(previous_state)
                if previous.get("status") == "running" or not previous.get("writers_stopped", False):
                    raise RuntimeError(f"Previous writer needs process/resource reconciliation: {previous_state}")
            stream.seek(1)
            stream.truncate()
            stream.write(str(run_dir).encode("utf-8"))
            stream.flush()
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def snapshot(repo, directory, name):
    """Retain tracked diffs plus untracked content hashes without copying user files."""
    details = {"head": git(repo, "rev-parse", "HEAD"),
               "branch": git(repo, "branch", "--show-current"),
               "status": git(repo, "status", "--porcelain=v1", "-uall"), "untracked": {}}
    paths = subprocess.check_output(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "-z"])
    for item in paths.decode("utf-8").split("\0"):
        if item:
            path = repo / item
            details["untracked"][item] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "non-file"
    write_json(directory / f"{name}.json", details)
    for suffix, arguments in [("unstaged", []), ("staged", ["--cached"])]:
        with (directory / f"{name}-{suffix}.patch").open("wb") as output:
            subprocess.run(["git", "-C", str(repo), "diff", "--binary", *arguments], stdout=output, check=True)
    return details


def hook():
    """Record bounded native activity without influencing tools or adding paid turns."""
    event = json.load(sys.stdin)
    turn_dir = Path(os.environ["DEVIN_IMPLEMENT_TURN_DIR"])
    payload = {key: event.get(key) for key in ("hook_event_name", "session_id", "prompt_id", "tool_name")}
    payload["at"] = time.time()
    if "tool_input" in event:
        payload["input_excerpt"] = json.dumps(event["tool_input"], ensure_ascii=False)[:400]
    response = event.get("tool_response")
    if isinstance(response, dict):
        payload["success"] = response.get("success")
        if response.get("error"):
            payload["error_excerpt"] = str(response["error"])[:400]
    with (turn_dir / "identity.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(payload) + "\n")


def tail(path, limit):
    """Read bounded complete trailing lines, tolerating a writer's unfinished last line."""
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        size = stream.seek(0, 2)
        start = max(0, size - limit)
        stream.seek(start)
        data = stream.read(limit)
    if start:
        data = data.partition(b"\n")[2]
    return data[:data.rfind(b"\n") + 1].decode("utf-8", errors="replace")


def status(run_dir, recent=False):
    """Summarize transport and activity; silence is evidence for diagnosis, never a kill signal."""
    state = read_json(Path(run_dir) / "state.json")
    turn_dir = Path(state["turn_dir"])
    result = {key: state.get(key) for key in ("status", "transport", "session_id", "turn", "writers_stopped",
              "supervisor_pid", "bootstrap_pid", "turn_dir", "error", "cancellation",
              "compaction_threshold_tokens")}
    context = turn_dir / "context.json"
    result["context"] = read_json(context) if context.is_file() else None
    now = time.time()
    result["elapsed_seconds"] = state.get("elapsed_seconds", round(now - state["started_at"]))
    if state["status"] == "running":
        heartbeat = state.get("heartbeat_at")
        result["supervisor_heartbeat_age_seconds"] = round(now - heartbeat) if heartbeat else None
        result["supervisor_check"] = ("unavailable" if heartbeat is None else
                                      "stale: inspect supervisor" if now - heartbeat > 120 else "responding")
    events = [json.loads(line) for line in tail(turn_dir / "identity.jsonl", 16384).splitlines()]
    if events:
        result["latest_activity"] = {key: events[-1].get(key) for key in ("at", "hook_event_name", "tool_name", "success")}
        result["activity_age_seconds"] = round(now - events[-1]["at"]) if "at" in events[-1] else None
        result["session_id"] = result["session_id"] or events[-1].get("session_id")
    ready = turn_dir / "acp-ready.json"
    if not result["session_id"] and ready.is_file():
        result["session_id"] = read_json(ready).get("session_id")
    notification = turn_dir / "notification.json"
    if notification.is_file():
        result["notification"] = read_json(notification)
    if recent:
        result["recent_activity"] = events[-8:]
        result["stdout_tail"] = tail(turn_dir / "stdout.log", 2048)
        result["stderr_tail"] = tail(turn_dir / "stderr.log", 1024)
    return result


class AppToolError(RuntimeError):
    """Distinguish confirmed non-delivery from a lost acknowledgement after submission."""

    def __init__(self, message, uncertain=False):
        """Keep the delivery state available to code-only retry policies."""
        super().__init__(message)
        self.uncertain = uncertain


def is_unknown_app_tool_error(error, name):
    """Recognize the native bridge's rejection before it invokes the host tool."""
    return (isinstance(error, dict) and error.get("code") == -32602
            and str(error.get("message", "")).endswith(f"Unknown Codex app tool: {name}"))


async def call_app_tool(thread_id, name, arguments, error_path):
    """Call the existing native MCP bridge without invoking a model or changing its settings."""
    plugin_root = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "plugins/cache/openai-bundled/codex-app-tools"
    servers = list(plugin_root.glob("*/server.mjs"))
    node = os.environ.get("CODEX_MCP_NODE_PATH") or shutil.which("node")
    if not servers or not node or not os.environ.get("CODEX_APP_TOOLS_PIPE_PATH"):
        raise AppToolError("Codex app runtime unavailable; result remains pending for recovery.")
    server = max(servers, key=lambda path: path.stat().st_mtime)
    error_path = Path(error_path)
    error_path.parent.mkdir(parents=True, exist_ok=True)
    submitted = False
    with error_path.open("wb") as errors:
        process = await asyncio.create_subprocess_exec(node, str(server), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=errors, creationflags=subprocess.CREATE_NO_WINDOW)

        async def request(identifier, method, params):
            """Return only the matching MCP response, never conversation or notification streams."""
            process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": identifier,
                                            "method": method, "params": params}) + "\n").encode())
            await process.stdin.drain()
            while line := await process.stdout.readline():
                response = json.loads(line)
                if response.get("id") == identifier:
                    if "error" in response:
                        error = response["error"]
                        # The native bridge rejects an unknown tool before forwarding
                        # it to the host, so retrying cannot duplicate delivery.
                        if method == "tools/call" and is_unknown_app_tool_error(error, name):
                            raise AppToolError(str(error)[:500], uncertain=False)
                        raise RuntimeError(str(error)[:500])
                    return response["result"]
            raise RuntimeError("App messaging connection closed before acknowledgement.")

        async def deliver():
            """Initialize MCP and submit exactly one operation on the originating task."""
            nonlocal submitted
            await request(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                          "clientInfo": {"name": "devin_implement", "version": "1"}})
            process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await process.stdin.drain()
            submitted = True
            response = await request(2, "tools/call", {"name": name,
                                     "_meta": {"threadId": thread_id},
                                     "arguments": arguments})
            if response.get("isError"):
                # A server error after submission does not prove that no message was sent.
                raise AppToolError(str(response.get("content"))[:500], uncertain=True)
            return response

        try:
            return await asyncio.wait_for(deliver(), timeout=30)
        except AppToolError:
            raise
        except Exception as error:
            raise AppToolError(str(error) or type(error).__name__, uncertain=submitted) from error
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def send_notification(thread_id, message, error_path):
    """Steer an active lead or wake an idle one through the shared native bridge."""
    return await call_app_tool(thread_id, "send_message_to_thread",
                               {"threadId": thread_id, "prompt": message}, error_path)


def notify_completion(state, thread_id):
    """Send one compact result wake; preserve failed delivery for the Python monitor."""
    if not thread_id:
        return
    turn_dir = Path(state["turn_dir"])
    record = {"thread_id": thread_id, "status": "pending", "at": time.time()}
    path = turn_dir / "notification.json"
    write_json(path, record)
    try:
        message = (f"Devin worker turn {state['turn']} is {state['status']}. "
                   f"Run: {state['run_dir']}. Read the compact result at {turn_dir / 'result.json'} "
                   "and its handoff, then continue this task through review, corrections, or recovery. "
                   "Do not read the full conversation/export or repeat an already handled turn. "
                   "After completing the follow-up or recording its concrete wait/blocker, "
                   "record this turn with the registered monitor's resolve command; receipt alone is not resolution.")
        if state["status"] == "failed" and state.get("error"):
            message += " Diagnosis: " + str(state["error"])[:300]
        asyncio.run(send_notification(thread_id, message, turn_dir / "notification.stderr.log"))
        record["status"] = "delivered"
    except Exception as error:
        record["uncertain"] = getattr(error, "uncertain", True)
        record["error"] = (str(error) or type(error).__name__)[-500:]
    write_json(path, record)


def export_evidence(path, expected_session=None, previous_agent_steps=0):
    """Check actual agent turns/tool definitions; the selected model alone is insufficient."""
    data = read_json(path)
    if "nodes" in data:
        return forest_evidence(path, data, expected_session)
    turns = [step for step in data.get("steps", []) if step.get("source") == "agent"]
    models = sorted({step.get("model_name", "") for step in turns})
    generation_models = {step.get("extra", {}).get("generation_model") for step in turns}
    generation_models.discard(None)
    definitions = data.get("agent", {}).get("tool_definitions")
    if not isinstance(definitions, list):
        raise RuntimeError("Export has no tool-definition evidence for nested-agent verification.")
    tools = {entry.get("function", {}).get("name") for entry in definitions}
    if not turns or models != [MODEL]:
        raise RuntimeError(f"Export does not prove exclusively {MODEL} agent turns: {models}.")
    if generation_models and generation_models != {MODEL}:
        raise RuntimeError(f"Export generation-model telemetry differs: {generation_models}.")
    if tools.intersection({"run_subagent", "read_subagent"}):
        raise RuntimeError("Nested subagent tools are present despite the worker configuration.")
    session = data.get("session_id")
    if not session or (expected_session and session != expected_session):
        raise RuntimeError("Export session identity is missing or differs from the resumed session.")
    final_message = turns[-1].get("message", "")
    has_final_response = (len(turns) > previous_agent_steps and isinstance(final_message, str)
                          and bool(final_message.strip()) and not turns[-1].get("tool_calls"))
    if has_final_response:
        Path(path).with_name("handoff.md").write_text(final_message + "\n", encoding="utf-8")
    return {"session_id": session, "served_models": models, "metrics": data.get("final_metrics", {}),
            "agent_steps": len(turns), "has_final_response": has_final_response}


def forest_evidence(path, data, expected_session):
    """Validate the native ACP main ancestry; side answers cannot become handoffs."""
    completion = read_json(Path(path).with_name("acp-result.json"))
    session = completion.get("session_id")
    if not session or (expected_session and session != expected_session):
        raise RuntimeError("ACP session identity differs from the requested session.")
    nodes = {node["id"]: node for node in data["nodes"]}
    chain = []
    current = data["main_chain_id"]
    seen = set()
    while current is not None:
        if current in seen or current not in nodes:
            raise RuntimeError("Invalid ACP main ancestry.")
        seen.add(current)
        node = nodes[current]
        chain.append(node["message"])
        current = node.get("parent_id")
    chain.reverse()
    turns = [message for message in chain if message.get("role") == "assistant"
             and message.get("metadata", {}).get("generation_model")]
    models = sorted({message["metadata"]["generation_model"] for message in turns})
    if models != [MODEL]:
        raise RuntimeError(f"ACP export serving models differ: {models}.")
    definitions = data.get("tools")
    if not isinstance(definitions, list) or any(item.get("name") in ("run_subagent", "read_subagent") for item in definitions):
        raise RuntimeError("ACP export has invalid or nested subagent tool definitions.")
    user_id = completion["main_result"].get("_meta", {}).get("cognition.ai/userMessageId")
    current_users = [index for index, message in enumerate(chain)
                     if message.get("message_id") == user_id and message.get("role") == "user"]
    final = chain[-1] if chain else {}
    content = final.get("content")
    # Native compaction can remove the user ancestor and omit userMessageId. Match
    # the final main node against this owned connection's live answer fingerprint.
    live = completion.get("live_main_response", {})
    encoded = content.encode("utf-8") if isinstance(content, str) else b""
    streamed_final = bool(encoded and completion["main_result"].get("stopReason") == "end_turn"
                          and live.get("bytes") == len(encoded)
                          and live.get("sha256") == hashlib.sha256(encoded).hexdigest())
    current_final = bool(current_users and current_users[-1] < len(chain) - 1)
    has_final = bool(completion["main_result"].get("stopReason") == "end_turn"
                     and (current_final or streamed_final)
                     and final.get("role") == "assistant" and not final.get("tool_calls")
                     and final.get("metadata", {}).get("generation_model") == MODEL
                     and isinstance(content, str) and content.strip())
    if has_final:
        Path(path).with_name("handoff.md").write_text(content + "\n", encoding="utf-8")
    return {"session_id": session, "served_models": models, "agent_steps": len(turns),
            "has_final_response": has_final, "metrics": completion["main_result"].get("usage", {})}


def wait_for_exit(process, state, turn_dir):
    """Allow native cancellation a bounded grace; only explicit cancellation has a deadline."""
    last_heartbeat = time.monotonic()
    cancel_started = None
    while True:
        try:
            state["exit_code"] = process.wait(timeout=1)
            return
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            if (turn_dir / "cancel.request").exists():
                if cancel_started is None:
                    cancel_started = now
                    state["cancellation"] = "requested"
                    write_json(Path(state["run_dir"]) / "state.json", state)
                identity = turn_dir / "acp-session.json"
                supports_cancel = not identity.exists() or "cancel" in read_json(identity).get("controls", [])
                if not supports_cancel or now - cancel_started >= CANCEL_GRACE_SECONDS:
                    state["cancellation"] = "forced"
                    return
            if now - last_heartbeat >= 30:
                state["heartbeat_at"] = time.time()
                write_json(Path(state["run_dir"]) / "state.json", state)
                last_heartbeat = now


def run(args):
    """Run until CLI exit or explicit cancellation; preserve results for lead-owned recovery."""
    if os.environ.get(ROLE_VARIABLE):
        raise RuntimeError("A Devin implementation worker cannot launch another worker.")
    if os.name != "nt":
        raise RuntimeError("The bundled launcher currently supports native Windows only.")
    repo = repository(args.repo, args.expected_head)
    run_dir = Path(args.run_dir).resolve()
    brief = Path(args.brief).resolve(strict=True)
    prior = read_json(run_dir / "state.json") if args.resume else None
    if prior and Path(prior["repo"]).resolve() != repo:
        raise RuntimeError("Resume repository differs from the original task.")
    retrying_startup = bool(prior and prior.get("phase") == "preflight"
                           and prior.get("status") == "failed" and prior.get("writers_stopped"))
    if prior and not prior.get("session_id") and not retrying_startup:
        raise RuntimeError("No verified session identity. Reconcile saved identity events before recovery.")
    if not args.resume and run_dir.exists():
        raise RuntimeError("A fresh --run-dir must not exist; this prevents accidental evidence overwrite.")
    preamble_file = getattr(args, "preamble_file", None)
    requested_preamble = (Path(preamble_file).resolve(strict=True).read_text(encoding="utf-8-sig")
                          if preamble_file else None)
    saved_preamble = run_dir / "worker-preamble.md"
    retain_preamble = bool(prior and saved_preamble.exists())
    if retain_preamble:
        preamble = saved_preamble.read_text(encoding="utf-8")
        if requested_preamble is not None and requested_preamble.rstrip() != preamble.rstrip():
            raise RuntimeError("Resume preamble differs from the original worker role.")
    else:
        preamble = requested_preamble if requested_preamble is not None else DEFAULT_PREAMBLE
    run_dir.mkdir(parents=True, exist_ok=True)
    with writer_lock(repo, run_dir):
        if prior and prior.get("status") == "running":
            raise RuntimeError("Previous run has no terminal record. Reconcile its process/job before resuming.")
        turn = (prior.get("turn", 0) if prior else 0) + 1
        turn_dir = run_dir / f"turn-{turn:03d}"
        turn_dir.mkdir()
        preflight = {"repo": str(repo), "run_dir": str(run_dir), "turn": turn,
                     "turn_dir": str(turn_dir), "status": "running", "phase": "preflight",
                     "session_id": prior.get("session_id") if prior else None,
                     "agent_steps": prior.get("agent_steps", 0) if prior else 0,
                     "expected_head": args.expected_head, "supervisor_pid": os.getpid(),
                     "started_at": time.time(), "heartbeat_at": time.time(), "model": MODEL}
        try:
            binary = executable()
            version = subprocess.check_output([binary, "--version"], text=True).strip()
            catalog = model_catalog(binary, turn_dir)
            variants = [variant for family in catalog["families"] for variant in family["variants"]]
            selected = [variant for variant in variants if variant["model_uid"] == MODEL]
            if len(selected) != 1:
                raise RuntimeError(f"Account does not expose the exact {MODEL} variant.")
        except Exception as error:
            preflight.update(status="failed", writers_stopped=True,
                             error=str(error) or type(error).__name__,
                             elapsed_seconds=round(time.time() - preflight["started_at"], 2))
            write_json(run_dir / "state.json", preflight)
            write_json(turn_dir / "result.json", preflight)
            notify_completion(preflight, args.notify_thread)
            print(preflight["error"], file=sys.stderr, flush=True)
            return 1
        write_json(turn_dir / "model.json", {"version": version, "model": selected[0]})
        before = snapshot(repo, turn_dir, "before")
        if not retain_preamble:
            saved_preamble.write_text(preamble.rstrip() + "\n", encoding="utf-8")
        prompt = turn_dir / "prompt.md"
        prompt.write_text(preamble.rstrip() + "\n\n" + brief.read_text(encoding="utf-8-sig"), encoding="utf-8")
        hook_command = 'python "' + Path(__file__).resolve().as_posix() + '" hook'
        # Compact before the observed SWE-2 failure boundary near 131k tokens.
        config = {"agent": {"model": MODEL, "show_history_on_continue": False,
                            "compaction_threshold_tokens": 100_000},
                  "attribution": False,
                  "subagents_enabled": False, "auto_update": False, "notify": "never",
                  "theme_mode": "nocolor", "shell": {"setup_complete": True},
                  "read_config_from": {"claude": False, "cursor": False, "windsurf": False},
                  "permissions": {"allow": args.allow_rule},
                  "hooks": {event: [{"hooks": [{"type": "command", "command": hook_command, "timeout": 10}]}]
                            for event in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Stop")}}
        write_json(turn_dir / "config.json", config)
        respect_workspace_trust = args.permission_mode != "dangerous"
        command = [binary, "--config", str(turn_dir / "config.json"), "--model", MODEL,
                   "--permission-mode", args.permission_mode,
                   "--respect-workspace-trust", str(respect_workspace_trust).lower(),
                   "--prompt-file", str(prompt),
                   "--export", str(turn_dir / "export.json")]
        if prior and prior.get("session_id"):
            command += ["--resume", prior["session_id"]]
        command = [sys.executable, str(Path(__file__).with_name("devin_acp.py")), *command]
        state = {"repo": str(repo), "run_dir": str(run_dir), "turn": turn, "turn_dir": str(turn_dir),
                 "status": "running", "transport": "acp", "session_id": prior["session_id"] if prior else None,
                 "expected_head": args.expected_head, "started_at": time.time(), "heartbeat_at": time.time(), "model": MODEL,
                 "supervisor_pid": os.getpid(), "command": command, "permission_mode": args.permission_mode,
                 "respect_workspace_trust": respect_workspace_trust,
                 "compaction_threshold_tokens": config["agent"]["compaction_threshold_tokens"]}
        write_json(run_dir / "state.json", state)
        env = dict(os.environ, DEVIN_IMPLEMENT_ROLE="worker", DEVIN_IMPLEMENT_TURN_DIR=str(turn_dir),
                   DEVIN_IMPLEMENT_CONSOLE="1" if args.console else "0")
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        job = Job()
        state["job_name"] = job.name
        write_json(run_dir / "state.json", state)
        process = None
        started = time.monotonic()
        try:
            with (turn_dir / "stdout.log").open("wb") as stdout, (turn_dir / "stderr.log").open("wb") as stderr:
                process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("windows_job.py")), job.name, str(repo), *command],
                                           cwd=repo, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           creationflags=subprocess.CREATE_NEW_CONSOLE if args.console else subprocess.CREATE_NO_WINDOW)
                state["bootstrap_pid"] = process.pid
                write_json(run_dir / "state.json", state)
                wait_for_exit(process, state, turn_dir)
            if (turn_dir / "cancel.request").exists():
                state["status"] = "cancelled"
                native = turn_dir / "cancel-native.json"
                if native.exists() and read_json(native).get("status") == "acknowledged":
                    state["cancellation"] = "graceful"
                elif state.get("cancellation") != "forced":
                    state["cancellation"] = "process_exit"
            if job.active():
                if state["status"] == "cancelled":
                    state["cancellation"] = "forced"
                job.stop()
            if process:
                process.wait(timeout=10)
            state["writers_stopped"] = True
            if state["status"] == "running":
                state["status"] = "exited" if state["exit_code"] == 0 else "failed"
            identity = turn_dir / "acp-session.json"
            if identity.is_file():
                state["session_id"] = read_json(identity)["session_id"]
            if (turn_dir / "export.json").is_file() and (
                    (turn_dir / "acp-result.json").is_file() or not identity.is_file()):
                state.update(export_evidence(turn_dir / "export.json", prior["session_id"] if prior else None,
                                             prior.get("agent_steps", 0) if prior else 0))
                if state["status"] == "exited" and not state["has_final_response"]:
                    state["status"] = "incomplete"
            elif state["status"] == "exited":
                raise RuntimeError("Successful CLI exit has no export; model/session evidence is unavailable.")
            after = snapshot(repo, turn_dir, "after")
            state["final_head"] = after["head"]
            state["initially_dirty"] = bool(before["status"])
            if state["status"] == "failed" and not state.get("error"):
                record = turn_dir / "acp-error.json"
                try:
                    detail = read_json(record) if record.is_file() else None
                except (OSError, ValueError):
                    detail = None  # A damaged record must not hide the exit diagnosis.
                if detail:
                    state["error"] = "Devin ACP failure: " + str(detail.get("error", ""))[:600]
                else:
                    state["error"] = f"Worker exited {state.get('exit_code')} without a recorded diagnosis."
                stderr_tail = tail(turn_dir / "stderr.log", 2048)
                if stderr_tail:
                    state["stderr_tail"] = stderr_tail
        except BaseException as error:
            state["status"] = "failed"
            state["error"] = str(error) or type(error).__name__
            try:
                job.stop()
                if process:
                    process.wait(timeout=10)
                state["writers_stopped"] = True
            except Exception as cleanup_error:
                state["cleanup_error"] = str(cleanup_error)
            raise
        finally:
            job.close()
            state["elapsed_seconds"] = round(time.monotonic() - started, 2)
            context = turn_dir / "context.json"
            state["context"] = read_json(context) if context.is_file() else None
            write_json(run_dir / "state.json", state)
            write_json(turn_dir / "result.json", state)
            notify_completion(state, args.notify_thread)
        print(json.dumps({key: state.get(key) for key in ("status", "session_id", "turn", "elapsed_seconds", "served_models", "writers_stopped", "run_dir")}))
        return 0 if state["status"] == "exited" else 1


def main(argv=None):
    """Default runs/resumes to authorized full access; allow explicit narrower overrides."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action", required=True)
    subcommands.add_parser("hook")
    for name in ("status", "cancel"):
        action = subcommands.add_parser(name)
        action.add_argument("--run-dir", required=True)
        if name == "status":
            action.add_argument("--recent", action="store_true", help="Include bounded recent activity and log excerpts.")
    for name, field, wait in (("ask", "question", 45), ("steer", "message", 5)):
        action = subcommands.add_parser(name)
        action.add_argument("--run-dir", required=True)
        request = action.add_mutually_exclusive_group(required=True)
        request.add_argument("--" + field, help="Submit once; maximum 2,000 characters.")
        request.add_argument("--request-id", help="Retrieve this request without resubmission.")
        action.add_argument("--wait-seconds", type=float, default=wait)
    action = subcommands.add_parser("run")
    action.add_argument("--repo", required=True)
    action.add_argument("--expected-head", required=True)
    action.add_argument("--run-dir", required=True)
    action.add_argument("--brief", required=True)
    action.add_argument("--preamble-file",
                        help="Optional role preamble, retained across resumes; defaults to implementation.")
    action.add_argument("--resume", action="store_true")
    action.add_argument("--no-console", dest="console", action="store_false",
                        help="Hide the live Devin output console (shown by default).")
    action.add_argument("--notify-thread", default=os.environ.get("CODEX_THREAD_ID"),
                        help="Codex task to wake on completion/failure; defaults to the calling Codex task.")
    action.add_argument("--permission-mode", choices=("normal", "accept-edits", "dangerous"), default="dangerous")
    action.add_argument("--allow-rule", action="append", default=[])
    args = parser.parse_args(argv)
    if args.action in ("ask", "steer"):
        from devin_acp import ask, steer
        if not 0 <= args.wait_seconds <= 60:
            raise ValueError("--wait-seconds must be between 0 and 60; a pending request remains retrievable.")
        operation = ask if args.action == "ask" else steer
        text = args.question if args.action == "ask" else args.message
        print(json.dumps(operation(args.run_dir, text, args.request_id, args.wait_seconds), ensure_ascii=False))
        return 0
    if args.action == "hook":
        hook()
        return 0
    if args.action in ("status", "cancel"):
        state = read_json(Path(args.run_dir) / "state.json")
        if args.action == "cancel":
            if state["status"] != "running":
                raise RuntimeError("Run is already terminal; no cancellation sent.")
            (Path(state["turn_dir"]) / "cancel.request").touch(exist_ok=False)
            print("Cancellation requested. Await terminal state and writers_stopped before reuse.")
        else:
            print(json.dumps(status(args.run_dir, args.recent)))
        return 0
    return run(args)


def configure_output():
    """Keep redirected CLI/log output Unicode-safe regardless of the Windows locale."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")


if __name__ == "__main__":
    configure_output()
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
