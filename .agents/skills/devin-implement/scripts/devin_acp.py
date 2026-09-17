"""Own Devin's main work, steering, side questions and native cancellation.

Runs inside the existing Windows job. Requests/results are atomic, turn-local
files, not a network service. Native exports remain the supervisor's authority.
"""

import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid

from devin_worker import MODEL, configure_output, read_json, write_json

ANSWER_LIMIT = 2400
QUESTION_LIMIT = 2000


def result_path(turn_dir, request_id, kind="questions"):
    """Validate an opaque request ID before resolving a turn-local result."""
    identifier = str(uuid.UUID(request_id))
    return Path(turn_dir) / kind / (identifier + ".result.json")


def ask(run_dir, question=None, request_id=None, wait_seconds=45):
    """Submit once or retrieve one answer without reading worker output/history."""
    return submit_request(run_dir, "questions", "question", question, request_id, wait_seconds)


def steer(run_dir, message=None, request_id=None, wait_seconds=5):
    """Deliver a delta to main work; receipts require no model acknowledgement or replay."""
    return submit_request(run_dir, "steering", "message", message, request_id, wait_seconds)


def submit_request(run_dir, kind, field, text, request_id, wait_seconds):
    """Share turn-local submission/retrieval; uncertain delivery is never retried automatically."""
    state = read_json(Path(run_dir) / "state.json")
    turn_dir = Path(state["turn_dir"])
    if text is not None:
        if not text.strip() or len(text) > QUESTION_LIMIT:
            raise ValueError(f"Request must contain 1–{QUESTION_LIMIT} characters.")
        if state["status"] != "running" or state.get("transport") != "acp":
            raise RuntimeError("This turn has no live owned ACP connection; do not attach a second session.")
        if not (turn_dir / "acp-ready.json").is_file():
            raise RuntimeError("ACP is not ready; retry submission after startup.")
        if (turn_dir / "cancel.request").exists():
            raise RuntimeError("Cancellation is pending; no new request submitted.")
        if kind == "steering" and "steer" not in read_json(turn_dir / "acp-ready.json").get("controls", []):
            raise RuntimeError("This adapter predates steering; use its normal handback/resume.")
        request_id = str(uuid.uuid4())
        directory = turn_dir / kind
        directory.mkdir(exist_ok=True)
        write_json(directory / (request_id + ".request.json"),
                   {"request_id": request_id, field: text, "created_at": time.time()})
    elif not request_id:
        raise ValueError(f"Supply --{field} or --request-id.")
    path = result_path(turn_dir, request_id, kind)
    if text is None:
        matches = list(Path(run_dir).glob("turn-*/" + kind + "/" + str(uuid.UUID(request_id)) + ".request.json"))
        if len(matches) == 1:
            path = matches[0].with_name(str(uuid.UUID(request_id)) + ".result.json")
        else:
            raise ValueError("Unknown request ID for this run.")
    deadline = time.monotonic() + wait_seconds
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.1)
    if path.is_file():
        return read_json(path)
    current = read_json(Path(run_dir) / "state.json")
    if current["status"] != "running" or Path(current["turn_dir"]) != path.parent.parent:
        if path.is_file():
            return read_json(path)  # Shutdown may have published the receipt after our first check.
        return {"status": "not_sent" if kind == "steering" else "failed", "request_id": request_id,
                "error": "Owning turn ended before this request was dispatched." if kind == "steering" else
                         "Owning turn ended before an answer was saved."}
    return {"status": "pending", "request_id": request_id, "turn_dir": str(turn_dir),
            "note": "Retrieve this ID; do not resubmit. Waiting does not cancel either chain."}


class ProtocolError(RuntimeError):
    """Carry the peer's JSON-RPC error object so the turn records a structured diagnosis."""

    def __init__(self, error):
        super().__init__(str(error)[:600])
        self.detail = error


def record_failure(turn_dir, failure):
    """Persist a bounded machine-readable diagnosis for the supervisor's result."""
    if turn_dir is None:
        return
    record = {"at": time.time(), "error": str(failure)[:800]}
    detail = getattr(failure, "detail", None)
    if isinstance(detail, dict):
        record["acp_error"] = detail
    try:
        write_json(Path(turn_dir) / "acp-error.json", record)
    except Exception:
        pass  # Diagnosis must never mask the original failure.


class Connection:
    """Multiplex standard JSON-RPC and Devin's main/side chain extension."""

    def __init__(self, command, cwd, turn_dir, permission_mode="normal"):
        """Start a contained server and drain protocol output continuously."""
        self.directory = Path(turn_dir)
        self.events = queue.Queue()
        self.responses = {}
        self.next_id = 0
        self.session = None
        self.live = False
        self.side = None
        self.stopping = False
        self.steering_requests = {}
        self.settled_steering = set()
        self.main_text = False
        self.permission_mode = permission_mode
        self.main_tools = set()
        self.reset_main_response()
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=sys.stderr,
                                        text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self.drain, daemon=True)
        self.reader.start()

    def drain(self):
        """Retain raw evidence on disk; never send it to the lead or output console."""
        try:
            with (self.directory / "acp.jsonl").open("w", encoding="utf-8") as log:
                for line in self.process.stdout:
                    log.write(line)
                    log.flush()
                    self.events.put(json.loads(line))
        except Exception as error:
            self.events.put(error)
        finally:
            self.events.put(EOFError("Devin ACP connection closed."))

    def send(self, method, params, notification=False):
        """Write from the event-loop owner only, keeping request IDs distinct."""
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            self.next_id += 1
            message["id"] = self.next_id
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        return message.get("id")

    def reset_main_response(self):
        """Fingerprint only the latest live main answer, without retaining its text."""
        self.main_response_digest = hashlib.sha256()
        self.main_response_bytes = 0

    def receive(self, timeout=0.1):
        """Route side content by native metadata, never by timing or text markers."""
        try:
            message = self.events.get(timeout=timeout)
        except queue.Empty:
            return
        if isinstance(message, Exception):
            raise message
        if "method" not in message:
            self.responses[message["id"]] = message
            return
        params = message.get("params", {})
        if "id" in message:
            response = {"jsonrpc": "2.0", "id": message["id"]}
            if message["method"] == "session/request_permission":
                # Preserve the supervisor's explicit authority without persisting grants.
                authorized = (not self.stopping and not (self.directory / "cancel.request").exists()
                              and self.permission_mode == "dangerous" and params.get("sessionId") == self.session
                              and params.get("toolCall", {}).get("toolCallId") in self.main_tools)
                option = next((item for item in params.get("options", [])
                               if item.get("kind") == "allow_once"), None) if authorized else None
                response["result"] = {"outcome": {"outcome": "selected", "optionId": option["optionId"]}
                                      if option else {"outcome": "cancelled"}}
                if not option:
                    print("ACP permission denied under configured authority; inspect the handback.", file=sys.stderr)
            else:
                response["error"] = {"code": -32601, "message": "Unattended client operation unsupported; return a handback."}
            self.process.stdin.write(json.dumps(response) + "\n")
            self.process.stdin.flush()
            return
        if not self.live or params.get("sessionId") != self.session:
            return  # Includes session/load history replay.
        chain = params.get("_meta", {}).get("cognition.ai/chain", "main")
        update = params.get("update", {})
        kind = update.get("sessionUpdate")
        if chain == "side":
            if self.side and kind == "agent_message_chunk":
                fragment = update.get("content", {}).get("text", "")
                self.side["characters"] += len(fragment)
                self.side["answer"] += fragment[:max(0, ANSWER_LIMIT - len(self.side["answer"]))]
            elif self.side and kind in ("tool_call", "tool_call_update"):
                self.side["error"] = "Side question unexpectedly attempted a tool; answer is not accepted."
                self.send("session/cancel", {"sessionId": self.session,
                          "_meta": {"cognition.ai/chain": "side"}}, notification=True)
            return
        if chain != "main":
            raise RuntimeError("Unknown Devin chain identity; refusing ambiguous routing.")
        if kind in ("agent_message_chunk", "agent_thought_chunk"):
            content = update.get("content", {}).get("text", "")
            if kind == "agent_thought_chunk":
                self.reset_main_response()
            else:
                encoded = content.encode("utf-8")
                self.main_response_digest.update(encoded)
                self.main_response_bytes += len(encoded)
            if kind == "agent_message_chunk" and content.strip():
                self.main_text = True
            print(content, end="", flush=True)
        elif kind == "tool_call":
            self.reset_main_response()
            self.main_text = True
            self.main_tools.add(update.get("toolCallId"))
            print("\n[tool] " + update.get("title", "tool")[:400], flush=True)

    def result(self, identifier):
        """Consume exactly one correlated response, preserving native errors."""
        response = self.responses.pop(identifier)
        if "error" in response:
            raise ProtocolError(response["error"])
        return response["result"]

    def request(self, method, params, timeout=60):
        """Bound setup operations; this deadline never applies to implementation."""
        identifier = self.send(method, params)
        deadline = time.monotonic() + timeout
        while identifier not in self.responses:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"ACP setup did not finish: {method}")
            self.receive()
        return self.result(identifier)

    def finish_side(self, error=None):
        """Publish one bounded answer before admitting another side request."""
        side = self.side
        error = error or side.get("error")
        result = {"request_id": side["request_id"], "status": "failed" if error else "answered",
                  "answer": "" if error else side["answer"], "truncated": side["characters"] > ANSWER_LIMIT,
                  "session_id": self.session, "completed_at": time.time()}
        if error:
            result["error"] = str(error)[:600]
        write_json(result_path(self.directory, side["request_id"]), result)
        self.side = None

    def questions(self, main_done=False):
        """Serialize side requests because native Devin exposes one side chain."""
        if self.side and self.side["rpc_id"] in self.responses:
            try:
                result = self.result(self.side["rpc_id"])
                error = None if result.get("stopReason") == "end_turn" and self.side["answer"].strip() else "Side chain returned no completed answer."
            except Exception as failure:
                error = str(failure)
            self.finish_side(error)
        if self.side:
            return
        for path in sorted((self.directory / "questions").glob("*.request.json")):
            item = read_json(path)
            if result_path(self.directory, item["request_id"]).exists():
                continue
            self.side = {**item, "answer": "", "characters": 0}
            if main_done or self.stopping:
                self.finish_side("Main turn has finished; read its handoff.")
                continue
            if not self.main_text:
                self.side = None
                return  # Native /btw needs an initial main response for context.
            text = ("/btw Answer in at most 150 words. Do not use tools or change the main task. "
                    "Distinguish observed results from assumptions. " + item["question"])
            self.side["rpc_id"] = self.send("session/prompt", {"sessionId": self.session,
                "prompt": [{"type": "text", "text": text}], "_meta": {"cognition.ai/chain": "side"}})
            return

    def steering(self, main_done=False):
        """Send each correction once on main; receipts describe transport, never compliance."""
        for rpc_id, request_id in self.steering_requests.items():
            if rpc_id in self.responses and rpc_id not in self.settled_steering:
                response = self.responses[rpc_id]
                receipt = {"request_id": request_id, "session_id": self.session, "status": "sent"}
                if "error" in response:
                    receipt.update(status="failed", error=str(response["error"])[:600])
                else:
                    receipt["stop_reason"] = response["result"].get("stopReason")
                write_json(result_path(self.directory, request_id, "steering"), receipt)
                self.settled_steering.add(rpc_id)
        for path in sorted((self.directory / "steering").glob("*.request.json"),
                           key=lambda path: read_json(path)["created_at"]):
            item = read_json(path)
            result = result_path(self.directory, item["request_id"], "steering")
            if result.exists():
                continue
            receipt = {"request_id": item["request_id"], "session_id": self.session}
            if main_done or self.stopping:
                write_json(result, {**receipt, "status": "not_sent"})
                continue
            # A crash around the pipe write must not be mistaken for safe resubmission.
            write_json(result, {**receipt, "status": "uncertain"})
            rpc_id = self.send("session/prompt", {"sessionId": self.session,
                "prompt": [{"type": "text", "text": item["message"]}]})
            self.steering_requests[rpc_id] = item["request_id"]
            write_json(result, {**receipt, "status": "sent"})

    def main_done(self, main):
        """Await every submitted main prompt, including a correction racing native completion."""
        return main in self.responses and all(rpc in self.responses for rpc in self.steering_requests)

    def cancel(self, main_done):
        """Request native interruption once and stop admitting work or permission grants."""
        if self.stopping or not (self.directory / "cancel.request").exists():
            return
        self.stopping = True
        (self.directory / "acp-ready.json").unlink(missing_ok=True)
        if not main_done:
            self.send("session/cancel", {"sessionId": self.session}, notification=True)
        if self.side:
            self.send("session/cancel", {"sessionId": self.session,
                      "_meta": {"cognition.ai/chain": "side"}}, notification=True)
        write_json(self.directory / "cancel-native.json", {"status": "requested"})

    def work(self, main):
        """Pump all owned chains; control handling adds no acknowledgement prompts or retries."""
        last_check = 0
        main_finished_at = None
        while not self.main_done(main) or self.side:
            self.receive()
            done = self.main_done(main)
            self.cancel(done)
            if done and main_finished_at is None:
                main_finished_at = time.monotonic()
            if self.side and main_finished_at is not None and time.monotonic() - main_finished_at >= 60:
                self.send("session/cancel", {"sessionId": self.session,
                          "_meta": {"cognition.ai/chain": "side"}}, notification=True)
                self.finish_side("Main turn finished; side answer did not finish during its 60-second completion grace.")
                break
            if time.monotonic() - last_check >= 0.2:
                self.steering(done)
                self.questions(done)
                last_check = time.monotonic()
        (self.directory / "acp-ready.json").unlink(missing_ok=True)
        self.steering(main_done=True)
        self.questions(main_done=True)
        if self.stopping:
            write_json(self.directory / "cancel-native.json", {"status": "acknowledged"})
        # Overlapping native prompts may share a completion/usage record. Never sum them.
        latest = next(reversed(self.steering_requests)) if self.steering_requests else main
        return self.result(latest)

    def close(self):
        """Close only this connection; the existing outer job contains all descendants."""
        self.live = False
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.reader.join(timeout=5)


def run(command):
    """Adapt existing launcher arguments while preserving its native export checks."""
    def argument(name):
        """Read a required value from the supervisor-authored invocation."""
        return command[command.index(name) + 1]

    turn_dir = Path(os.environ["DEVIN_IMPLEMENT_TURN_DIR"])
    prompt = Path(argument("--prompt-file")).read_text(encoding="utf-8-sig")
    export = argument("--export")
    resume = argument("--resume") if "--resume" in command else None
    native = command[:command.index("--prompt-file")] + ["acp", "--model", MODEL]
    connection = Connection(native, os.getcwd(), turn_dir, argument("--permission-mode"))
    try:
        result = connection.request("initialize", {"protocolVersion": 1,
            "clientCapabilities": {"_meta": {"cognition.ai/chains": True}},
            "clientInfo": {"name": "devin-implement", "version": "2"}})
        if not result.get("agentCapabilities", {}).get("_meta", {}).get("cognition.ai/chains"):
            raise RuntimeError("Installed Devin does not advertise chain support.")
        params = {"cwd": os.getcwd(), "mcpServers": [], "_meta": {
            "cognition.ai/conversationExports": [{"path": export, "format": "forest"}]}}
        if resume:
            params["sessionId"] = resume
        session = connection.request("session/load" if resume else "session/new", params)
        connection.session = resume or session["sessionId"]
        options = session.get("configOptions", [])
        model = next((item for item in options if item.get("id") == "model"), None)
        if model is None:
            raise RuntimeError("Devin did not expose verifiable model selection.")
        if model.get("currentValue") != MODEL:
            changed = connection.request("session/set_config_option", {"sessionId": connection.session,
                                         "configId": "model", "value": MODEL})
            if not any(item.get("id") == "model" and item.get("currentValue") == MODEL
                       for item in changed.get("configOptions", [])):
                raise RuntimeError("Devin did not select SWE-2 Max.")
        connection.live = True
        write_json(turn_dir / "acp-session.json", {"session_id": connection.session, "model": MODEL,
                                                 "controls": ["steer", "cancel"]})
        write_json(turn_dir / "acp-ready.json", {"session_id": connection.session, "model": MODEL,
                                               "controls": ["steer", "cancel"]})
        main = connection.send("session/prompt", {"sessionId": connection.session,
            "prompt": [{"type": "text", "text": prompt}]})
        result = connection.work(main)
        print(flush=True)
        if result.get("_meta", {}).get("cognition.ai/exportFailures"):
            raise RuntimeError("Native ACP reported an export failure; prior exports are not completion evidence.")
        write_json(turn_dir / "acp-result.json", {"session_id": connection.session,
                   "main_result": result, "live_main_response": {
                       "sha256": connection.main_response_digest.hexdigest(),
                       "bytes": connection.main_response_bytes}})
        if result.get("stopReason") == "cancelled" and connection.stopping:
            return 0
        if result.get("stopReason") != "end_turn":
            raise RuntimeError("Main ACP turn did not complete: " + str(result.get("stopReason")))
        if not Path(export).is_file():
            raise RuntimeError("Native ACP conversation export is missing.")
        return 0
    finally:
        (turn_dir / "acp-ready.json").unlink(missing_ok=True)
        connection.steering(main_done=True)
        if connection.side:
            connection.finish_side("ACP connection ended before this answer completed.")
        connection.close()


if __name__ == "__main__":
    configure_output()
    try:
        sys.exit(run(sys.argv[1:]))
    except Exception as failure:
        print("ACP ERROR: " + str(failure)[:800], file=sys.stderr)
        record_failure(os.environ.get("DEVIN_IMPLEMENT_TURN_DIR"), failure)
        sys.exit(1)
