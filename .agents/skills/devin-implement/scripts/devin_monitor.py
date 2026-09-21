"""Code-only timer rearming and conservative liveness checks; anomalies may wake the lead.

The native heartbeat invokes the lead once. This process observes the local
rollout's completion metadata and resets the timer without a lead tool call.
Rollout format is a verified local integration, not a public cache-control API.
"""

import argparse
import ast
import asyncio
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from devin_worker import (
    AppToolError, call_app_tool, is_unknown_app_tool_error,
    read_json, send_notification, tail, write_json,
)

PROMPT = ("Cache keepalive only. Do not call tools, inspect worker progress, or produce commentary. "
          "Return an empty final response.")
HEALTH_INTERVAL = 15 * 60
KEEPALIVE_RULE = "FREQ=MINUTELY;INTERVAL=27"


def codex_home():
    """Locate local Codex state without changing its user configuration."""
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def process_alive(pid):
    """Check a Windows process without terminating it or trusting a recycled status file."""
    if not pid:
        return False
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x100000, False, int(pid))
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


@contextmanager
def monitor_lock(thread_id):
    """Exclude competing monitors for one lead, even across different monitor directories."""
    import msvcrt
    directory = codex_home() / "devin-monitor-locks"
    directory.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(thread_id.encode()).hexdigest()
    with (directory / (name + ".lock")).open("a+b") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b" ")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def rollout_path(thread_id, explicit=None):
    """Resolve exactly one rollout and verify its first-record session identity."""
    matches = [Path(explicit)] if explicit else list((codex_home() / "sessions").rglob(f"*{thread_id}.jsonl"))
    if len(matches) != 1:
        raise ValueError(f"Expected one rollout for {thread_id}; found {len(matches)}")
    path = matches[0].resolve(strict=True)
    with path.open("rb") as stream:
        first = json.loads(stream.readline())
    if first.get("type") != "session_meta" or first["payload"].get("id") != thread_id:
        raise ValueError("Rollout session identity differs from the requested lead.")
    return path


def read_events(path, offset):
    """Read only new complete lines; return lifecycle metadata and retain partial lines for later."""
    path = Path(path)
    if path.stat().st_size < offset:
        raise ValueError("Rollout was truncated; refusing historical replay.")
    events = []
    with path.open("rb") as stream:
        stream.seek(offset)
        while True:
            line = stream.readline()
            if not line or not line.endswith(b"\n"):
                break
            offset = stream.tell()
            if b'"task_complete"' not in line and b'"task_started"' not in line:
                continue
            record = json.loads(line)
            payload = record.get("payload", {})
            if record.get("type") == "event_msg" and payload.get("type") in ("task_started", "task_complete"):
                if not payload.get("turn_id"):
                    raise ValueError("Lifecycle event lacks turn identity.")
                events.append({"type": payload["type"], "turn_id": payload["turn_id"], "at": record["timestamp"]})
    return events, offset


def observe_events(state, events):
    """Collapse completions into one rearm; a newer active turn defers the reset until it finishes."""
    for event in events:
        if event["type"] == "task_started":
            state["active_turn"] = event["turn_id"]
        elif event["turn_id"] != state.get("last_completion"):
            if state.get("active_turn") not in (None, event["turn_id"]):
                continue
            state["active_turn"] = None
            state["last_completion"] = event["turn_id"]
            state["rearm_pending"] = True


async def set_heartbeat(config, status, error_path):
    """Update the existing native timer and require an explicit matching acknowledgement."""
    result = await call_app_tool(config["thread_id"], "automation_update", {
        "id": config["automation_id"], "mode": "update", "kind": "heartbeat", "destination": "thread",
        "targetThreadId": config["thread_id"], "name": config["name"], "prompt": PROMPT,
        "rrule": KEEPALIVE_RULE, "status": status,
    }, error_path)
    for item in result.get("content", []):
        if item.get("type") != "text":
            continue
        try:
            receipt = json.loads(item["text"])
        except json.JSONDecodeError:
            continue
        if isinstance(receipt, dict) and receipt.get("automationId") == config["automation_id"] and receipt.get("status") == status:
            return
    raise AppToolError("Automation response did not acknowledge the requested ID/status.", uncertain=True)


def activity_snapshot(run_dir, alive=process_alive):
    """Inspect bounded tool-event metadata and byte growth, never ask the worker for progress."""
    path = Path(run_dir) / "state.json"
    if not path.exists():
        return {"state": "not-started"}
    worker = read_json(path)
    if worker["status"] != "running":
        return {"state": "terminal", "turn_dir": worker["turn_dir"], "turn": worker["turn"]}
    turn_dir = Path(worker["turn_dir"])
    events = []
    unreadable_event_lines = 0
    for line in tail(turn_dir / "identity.jsonl", 16384).splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # A damaged hook record must not stop monitoring independent workers.
            unreadable_event_lines += 1
    tools = [e for e in events if e.get("hook_event_name") in ("PreToolUse", "PostToolUse")]
    last = tools[-1] if tools else {}
    files = [turn_dir / "identity.jsonl", turn_dir / "stdout.log"]
    return {
        "state": "running", "turn": worker["turn"], "turn_dir": str(turn_dir),
        "supervisor_alive": alive(worker.get("supervisor_pid")), "heartbeat_at": worker.get("heartbeat_at", 0),
        "fingerprint": [worker["turn"], *[p.stat().st_size if p.exists() else 0 for p in files], last.get("at")],
        "in_flight": last.get("hook_event_name") == "PreToolUse", "tool": last.get("tool_name"),
        "last_tool_at": last.get("at"),
        "unreadable_event_lines": unreadable_event_lines,
    }


def classify_activity(previous, current, now):
    """Latch mechanical anomalies; silence and repeated tool names never authorize cancellation."""
    result = {"snapshot": current, "quiet_since": None, "alert": None}
    if current["state"] != "running":
        return result
    if not current["supervisor_alive"] or now - current["heartbeat_at"] > 120:
        result["alert"] = f"supervisor-unhealthy:turn-{current['turn']}"
        return result
    old = previous.get("snapshot", {})
    if old.get("fingerprint") != current["fingerprint"]:
        return result
    result["quiet_since"] = previous.get("quiet_since")
    if result["quiet_since"] is None:
        result["quiet_since"] = previous.get("checked_at", now)
    # A live outstanding operation may legitimately run for hours without new output.
    if not current["in_flight"] and now - result["quiet_since"] >= 2 * HEALTH_INTERVAL:
        result["alert"] = f"possible-inactivity:turn-{current['turn']}"
    return result


def checked_delivery(config, message, path):
    """Send an actionable alert once; persist ambiguity instead of repeating a possibly delivered wake."""
    record = {"status": "pending", "at": time.time()}
    try:
        asyncio.run(send_notification(config["thread_id"], message, path.with_suffix(".stderr.log")))
        record["status"] = "delivered"
    except Exception as error:
        record.update(error=str(error)[-500:], uncertain=getattr(error, "uncertain", True))
    write_json(path, record)
    return record


def resolve_completion(run_dir: Path, turn: int, resolution: str) -> Path:
    """Record the lead's completed follow-up, not merely receipt or worker acceptance."""
    if turn < 1 or not resolution.strip():
        raise ValueError("A positive turn and concrete follow-up resolution are required.")
    turn_dir = run_dir / f"turn-{turn:03d}"
    result = read_json(turn_dir / "result.json")
    if (result.get("turn") != turn or Path(result.get("run_dir", "")) != run_dir
            or result.get("status") not in {"exited", "incomplete", "failed", "cancelled"}
            or result.get("writers_stopped") is not True):
        raise ValueError("Resolve only the exact terminal turn after its writers have stopped.")
    path = turn_dir / "lead-resolution.json"
    write_json(path, {"run_dir": str(run_dir), "turn": turn, "at": time.time(),
                      "resolution": resolution.strip()})
    return path


def completion_is_resolved(run, current):
    """Match completed lead follow-up to this exact run and turn."""
    resolution_path = Path(current["turn_dir"]) / "lead-resolution.json"
    if resolution_path.exists():
        resolution = read_json(resolution_path)
        if (resolution.get("turn") == current["turn"]
                and Path(resolution.get("run_dir", "")) == Path(run)
                and resolution.get("resolution", "").strip()):
            return True
    return False


def check_completion_followup(config, run, current, lead_active, now):
    """Remind an idle lead once about delivered but unresolved work; never resume a worker."""
    if completion_is_resolved(run, current):
        return "resolved"
    turn_dir = Path(current["turn_dir"])
    note_path = turn_dir / "notification.json"
    if not note_path.exists():
        return "notification-unavailable"
    note = read_json(note_path)
    if note.get("status") != "delivered":
        return "notification-unconfirmed"
    if lead_active or now - note.get("at", now) < HEALTH_INTERVAL:
        return "awaiting-lead"
    # A successful/uncertain reminder is not replayed, including after monitor restart.
    reminder_path = turn_dir / "lead-followup.json"
    if reminder_path.exists():
        prior = read_json(reminder_path)
        if prior.get("status") == "delivered" or prior.get("uncertain") is not False:
            return "reminder-sent-or-uncertain"
        if now - prior.get("at", now) < HEALTH_INTERVAL:
            return "reminder-retry-pending"
    message = (
        f"Devin follow-up missing for run {run}, turn {current['turn']}. "
        "The completion notification was delivered, but no lead resolution was recorded. "
        f"Read {turn_dir}/result.json and its compact handoff, reconcile existing review/work, "
        "then finish the next authorized action or record the concrete wait/blocker. "
        "Use devin_monitor.py resolve only after doing that work. "
        "Do not repeat an already handled review, restart Devin blindly, or read full exports."
    )
    checked_delivery(config, message, reminder_path)
    return "reminder-attempted"


def confirmed_nondelivery(notification):
    """Also recognize rejection records from supervisors started before this fix."""
    if notification.get("uncertain") is False:
        return True
    try:
        error = ast.literal_eval(notification.get("error", ""))
    except (SyntaxError, ValueError, TypeError):
        return False
    return is_unknown_app_tool_error(error, "send_message_to_thread")


def health_check(directory, config, state, now):
    """Check registered runs every fifteen minutes and emit only new actionable anomalies."""
    for registration in (directory / "runs").glob("*.json"):
        run = read_json(registration)["run_dir"]
        previous = state.setdefault("workers", {}).get(run, {})
        current = activity_snapshot(run)
        result = classify_activity(previous, current, now)
        result["checked_at"] = now
        result["retry_after"] = previous.get("retry_after", 0)
        alert = result["alert"]
        if alert and alert != previous.get("alert"):
            message = (f"Devin monitor {alert}. Run: {run}. Last tool: {current.get('tool')}; "
                       f"last tool event: {current.get('last_tool_at')}; in-flight: {current.get('in_flight')}. "
                       "Inspect this anomaly as needed. Inactivity alone is not proof of a stall; do not cancel automatically.")
            result["delivery"] = checked_delivery(config, message, directory / (registration.stem + "-alert.json"))
        elif alert:
            result["delivery"] = previous.get("delivery")
        if current["state"] == "terminal":
            # Only retry a conclusively undelivered callback, after the supervisor has had time to finish.
            note = Path(current["turn_dir"]) / "notification.json"
            if note.exists() and not completion_is_resolved(run, current):
                notification = read_json(note)
                if (notification.get("status") == "pending" and confirmed_nondelivery(notification)
                        and now - notification.get("at", now) > 120
                        and now >= previous.get("retry_after", 0)):
                    result["retry_after"] = now + HEALTH_INTERVAL
                    message = (f"Devin result callback retry for run {run}, turn {current['turn']}. "
                               f"Read {current['turn_dir']}/result.json and its handoff; skip if already handled.")
                    delivery = checked_delivery(config, message, directory / (registration.stem + "-callback.json"))
                    notification.update(delivery)
                    write_json(note, notification)
            result["followup"] = check_completion_followup(
                config, run, current, bool(state.get("active_turn")), now,
            )
        state["workers"][run] = result


def run_monitor(directory):
    """Own the event cursor, timer resets and health state until an explicit stop request."""
    config = read_json(directory / "config.json")
    with monitor_lock(config["thread_id"]):
        rollout = rollout_path(config["thread_id"], config["rollout"])
        state_path = directory / "state.json"
        state = read_json(state_path) if state_path.exists() else {
            "offset": rollout.stat().st_size, "active_turn": None, "rearm_pending": True,
        }
        state.update(pid=os.getpid(), status="running", rearm_pending=True)
        write_json(state_path, state)
        next_health = 0
        retry_at = 0
        failures = 0
        startup_pending = True
        try:
            while True:
                now = time.time()
                state["heartbeat_at"] = now
                if (directory / "stop.request").exists():
                    asyncio.run(set_heartbeat(config, "PAUSED", directory / "pause.stderr.log"))
                    state["status"] = "stopped"
                    break
                events, state["offset"] = read_events(rollout, state["offset"])
                observe_events(state, events)
                if (state.get("rearm_pending") and (startup_pending or not state.get("active_turn"))
                        and now >= retry_at):
                    try:
                        asyncio.run(set_heartbeat(config, "ACTIVE", directory / "rearm.stderr.log"))
                        state.update(rearm_pending=False, rearmed_at=time.time(), last_error=None)
                        failures = 0
                        startup_pending = False
                    except Exception as error:
                        failures += 1
                        state["last_error"] = str(error)[-500:]
                        retry_at = now + min(300, 5 * 2 ** min(failures, 6))
                        if failures == 3:
                            checked_delivery(config, "Devin keepalive timer reset failed three times. "
                                             f"Inspect {directory}/state.json; the previous schedule may remain active.",
                                             directory / "rearm-failure.json")
                    # A stop arriving while the update was in flight must win before another active tick.
                    if (directory / "stop.request").exists():
                        continue
                if now >= next_health:
                    health_check(directory, config, state, now)
                    next_health = now + HEALTH_INTERVAL
                write_json(state_path, state)
                time.sleep(2)
        except Exception as error:
            state.update(status="failed", last_error=str(error)[-500:])
            checked_delivery(config, f"Devin Python monitor failed: {state['last_error']}. "
                             f"Inspect {directory}; the native keepalive may still be scheduled.", directory / "failure.json")
            raise
        finally:
            write_json(state_path, state)


def main(argv=None):
    """Register runs, start one hidden monitor, inspect compact state, or stop and pause it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "register", "status", "stop", "run", "resolve"))
    parser.add_argument("--monitor-dir", required=True)
    parser.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    parser.add_argument("--automation-id")
    parser.add_argument("--name", default="Devin cache keepalive")
    parser.add_argument("--rollout")
    parser.add_argument("--run-dir", action="append", default=[])
    parser.add_argument("--turn", type=int)
    parser.add_argument("--resolution")
    args = parser.parse_args(argv)
    directory = Path(args.monitor_dir).resolve()
    if args.action == "resolve":
        if len(args.run_dir) != 1 or args.turn is None or not args.resolution:
            parser.error("resolve requires one --run-dir, --turn and --resolution")
        run = Path(args.run_dir[0]).resolve()
        registered = directory / "runs" / (hashlib.sha256(str(run).lower().encode()).hexdigest() + ".json")
        if not registered.is_file():
            raise ValueError("Resolve requires a run registered with this monitor.")
        path = resolve_completion(run, args.turn, args.resolution)
        print(json.dumps({"status": "resolved", "turn": args.turn, "record": str(path)}))
        return
    if args.action == "run":
        run_monitor(directory)
        return
    if args.action == "start":
        if not args.thread_id or not args.automation_id:
            parser.error("start requires --thread-id and --automation-id")
        rollout = rollout_path(args.thread_id, args.rollout)
        config = {"thread_id": args.thread_id, "automation_id": args.automation_id,
                  "name": args.name, "rollout": str(rollout)}
        directory.mkdir(parents=True, exist_ok=True)
        existing = directory / "config.json"
        if existing.exists() and read_json(existing) != config:
            raise ValueError("Monitor configuration differs; stop/reconcile the existing monitor first.")
        if not existing.exists():
            write_json(existing, config)
    if args.action in ("start", "register"):
        config = read_json(directory / "config.json")
        registrations = directory / "runs"
        registrations.mkdir(exist_ok=True)
        for path in args.run_dir:
            run = str(Path(path).resolve())
            write_json(registrations / (hashlib.sha256(run.lower().encode()).hexdigest() + ".json"), {"run_dir": run})
        if args.action == "register":
            print(json.dumps({"registered": len(args.run_dir)}))
            return
        state_path = directory / "state.json"
        state = read_json(state_path) if state_path.exists() else {}
        if state.get("status") == "running" and process_alive(state.get("pid")):
            print(json.dumps({"status": "already-running", "pid": state["pid"]}))
            return
        (directory / "stop.request").unlink(missing_ok=True)
        with (directory / "stdout.log").open("ab") as stdout, (directory / "stderr.log").open("ab") as stderr:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "run", "--monitor-dir", str(directory)],
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Monitor exited during startup; inspect {directory}/stderr.log")
            state = read_json(state_path) if state_path.exists() else {}
            if state.get("pid") == process.pid and state.get("rearmed_at") and not state.get("rearm_pending"):
                print(json.dumps({"status": "running", "pid": process.pid, "heartbeat": "ACTIVE"}))
                return
            time.sleep(.2)
        raise RuntimeError(f"Monitor has not acknowledged startup; inspect {directory}/state.json before waiting.")
    elif args.action == "status":
        state = read_json(directory / "state.json")
        if state.get("status") == "running" and not process_alive(state.get("pid")):
            state["status"] = "dead"
        print(json.dumps({k: state.get(k) for k in ("status", "pid", "heartbeat_at", "rearmed_at", "rearm_pending", "last_error")}))
    elif args.action == "stop":
        (directory / "stop.request").touch()
        config = read_json(directory / "config.json")
        state_path = directory / "state.json"
        state = read_json(state_path) if state_path.exists() else {}
        if state.get("status") == "running" and process_alive(state.get("pid")):
            deadline = time.monotonic() + 40
            while process_alive(state["pid"]) and time.monotonic() < deadline:
                time.sleep(.2)
            if process_alive(state["pid"]):
                raise RuntimeError("Stop remains pending; refusing to race the live monitor's timer update.")
        # Also recover a dead monitor or a failed pause, using the same timer ID.
        asyncio.run(set_heartbeat(config, "PAUSED", directory / "pause.stderr.log"))
        state = read_json(state_path) if state_path.exists() else state
        state.update(status="stopped")
        write_json(state_path, state)
        print(json.dumps({"status": "stopped", "heartbeat": "PAUSED"}))


if __name__ == "__main__":
    main()
