"""Offline routing regressions; no model calls or paid requests."""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import queue
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import devin_acp as acp
import devin_worker as worker
from test_devin_worker import TimedResult


class AcpTests(unittest.TestCase):
    """Exercise chain identity, queue lifecycle, bounded answers and native evidence."""

    def setUp(self):
        """Build a transport fixture without launching a native process."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.turn = self.root / "turn-001"
        self.turn.mkdir()
        worker.write_json(self.root / "state.json", {"turn_dir": str(self.turn), "status": "running", "transport": "acp"})
        worker.write_json(self.turn / "acp-ready.json", {"session_id": "test", "controls": ["steer", "cancel"]})
        connection = acp.Connection.__new__(acp.Connection)
        connection.directory = self.turn
        connection.events = queue.Queue()
        connection.responses = {}
        connection.next_id = 0
        connection.session = "test"
        connection.live = True
        connection.side = None
        connection.stopping = False
        connection.steering_requests = {}
        connection.settled_steering = set()
        connection.main_text = True
        connection.main_tools = set()
        connection.reset_main_response()
        connection.permission_mode = "dangerous"
        connection.process = SimpleNamespace(stdin=io.StringIO())
        self.connection = connection

    def event(self, text, chain="main", kind="agent_message_chunk", session="test"):
        """Supply interleaved updates with the installed CLI's observed metadata."""
        self.connection.events.put({"method": "session/update", "params": {
            "sessionId": session, "_meta": {"cognition.ai/chain": chain},
            "update": {"sessionUpdate": kind, "content": {"type": "text", "text": text}}}})
        self.connection.receive()

    def test_interleaved_questions_are_serialized_and_answers_bounded(self):
        """Two requests cannot cross-contaminate each other or consume main output."""
        ids = [acp.ask(self.root, question="progress?", wait_seconds=0)["request_id"] for _ in range(2)]
        self.connection.questions()
        first = self.connection.side["request_id"]
        rpc = self.connection.side["rpc_id"]
        with redirect_stdout(io.StringIO()) as output:
            self.event("MAIN")
            self.event("PRIVATE THOUGHT", chain="side", kind="agent_thought_chunk")
            self.event("S" * 4000, chain="side")
            self.event("OTHER SESSION", chain="side", session="unrelated")
        self.assertEqual(output.getvalue(), "MAIN")
        self.connection.questions()
        self.assertEqual(self.connection.side["rpc_id"], rpc)
        self.connection.responses[rpc] = {"result": {"stopReason": "end_turn"}}
        self.connection.questions()
        result = acp.ask(self.root, request_id=first, wait_seconds=0)
        self.assertEqual(result["answer"], "S" * acp.ANSWER_LIMIT)
        self.assertTrue(result["truncated"])
        self.assertNotEqual(self.connection.side["request_id"], first)
        self.event("SECOND", chain="side")
        self.connection.responses[self.connection.side["rpc_id"]] = {"result": {"stopReason": "end_turn"}}
        self.connection.questions(main_done=True)
        other = next(identifier for identifier in ids if identifier != first)
        self.assertEqual(acp.ask(self.root, request_id=other, wait_seconds=0)["answer"], "SECOND")
        self.assertIsNone(self.connection.side)

    def test_unicode_main_output_survives_windows_pipe_encoding(self):
        """A non-ANSI response cannot tear down the live connection when logs use pipes."""
        raw_output, raw_error = io.BytesIO(), io.BytesIO()
        output = io.TextIOWrapper(raw_output, encoding="cp1252")
        errors = io.TextIOWrapper(raw_error, encoding="cp1252")
        with redirect_stdout(output), redirect_stderr(errors):
            worker.configure_output()
            self.event("A \u2192 B; \u4e16\u754c; \U0001f916")
            print("failure \u2192 detail", file=errors, flush=True)
        self.assertEqual(raw_output.getvalue().decode("utf-8"), "A \u2192 B; \u4e16\u754c; \U0001f916")
        self.assertEqual(raw_error.getvalue().decode("utf-8").splitlines(), ["failure \u2192 detail"])

    def test_side_failure_cancels_only_side_and_preserves_main(self):
        """Unexpected side tools fail the question without a main-chain cancellation."""
        identifier = acp.ask(self.root, question="progress?", wait_seconds=0)["request_id"]
        self.connection.questions()
        self.event("", chain="side", kind="tool_call")
        sent = [json.loads(line) for line in self.connection.process.stdin.getvalue().splitlines()]
        cancel = sent[-1]
        self.assertEqual(cancel["method"], "session/cancel")
        self.assertEqual(cancel["params"]["_meta"]["cognition.ai/chain"], "side")
        self.connection.responses[self.connection.side["rpc_id"]] = {"result": {"stopReason": "cancelled"}}
        self.connection.questions()
        self.assertEqual(acp.ask(self.root, request_id=identifier, wait_seconds=0)["status"], "failed")
        with redirect_stdout(io.StringIO()) as output:
            self.event("MAIN CONTINUES")
        self.assertEqual(output.getvalue(), "MAIN CONTINUES")

    def test_replay_and_terminal_queue_do_not_invent_answers(self):
        """History replay is hidden; a completed worker cannot answer a queued question."""
        self.connection.live = False
        with redirect_stdout(io.StringIO()) as output:
            self.event("OLD RESPONSE")
        self.assertEqual(output.getvalue(), "")
        identifier = acp.ask(self.root, question="progress?", wait_seconds=0)["request_id"]
        self.connection.questions(main_done=True)
        result = acp.ask(self.root, request_id=identifier, wait_seconds=0)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["answer"], "")
        with self.assertRaises(ValueError):
            acp.ask(self.root, request_id="../../state", wait_seconds=0)
        with self.assertRaises(ValueError):
            acp.ask(self.root, question="q" * 2001, wait_seconds=0)

    def test_main_export_rejects_stale_completion_and_excludes_side(self):
        """Only a final main response after this prompt is eligible for the handoff."""
        data = {"main_chain_id": 2, "tools": [], "nodes": [
            {"id": 1, "parent_id": None, "message": {"role": "user", "message_id": "current"}},
            {"id": 2, "parent_id": 1, "message": {"role": "assistant", "content": "MAIN FINAL",
               "metadata": {"generation_model": "swe-2-max"}}},
            {"id": 3, "parent_id": 1, "message": {"role": "assistant", "content": "SIDE ANSWER",
               "metadata": {"generation_model": "other-model"}}}]}
        path = self.turn / "export.json"
        worker.write_json(path, data)
        completion = {"session_id": "test", "main_result": {"stopReason": "end_turn",
                      "_meta": {"cognition.ai/userMessageId": "current"}}}
        worker.write_json(self.turn / "acp-result.json", completion)
        self.assertTrue(worker.export_evidence(path, "test")["has_final_response"])
        self.assertEqual((self.turn / "handoff.md").read_text().strip(), "MAIN FINAL")
        completion["main_result"]["stopReason"] = "cancelled"
        worker.write_json(self.turn / "acp-result.json", completion)
        self.assertFalse(worker.export_evidence(path, "test")["has_final_response"])
        completion["main_result"]["stopReason"] = "end_turn"
        completion["main_result"]["_meta"]["cognition.ai/userMessageId"] = "new-prompt"
        worker.write_json(self.turn / "acp-result.json", completion)
        self.assertFalse(worker.export_evidence(path, "test")["has_final_response"])
        data["nodes"][1]["message"]["metadata"]["generation_model"] = "wrong"
        worker.write_json(path, data)
        with self.assertRaisesRegex(RuntimeError, "serving models"):
            worker.export_evidence(path, "test")

    def test_compacted_completion_requires_matching_live_main_fingerprint(self):
        """Compaction may remove the user ancestor; replay, tools and side text prove nothing."""
        with redirect_stdout(io.StringIO()):
            self.connection.live = False
            self.event("REPLAY")
            self.assertEqual(self.connection.main_response_bytes, 0)
            self.connection.live = True
            self.event("EARLIER COMMENT")
            self.event("", kind="tool_call")
            self.assertEqual(self.connection.main_response_bytes, 0)
            self.event("THOUGHT", kind="agent_thought_chunk")
            self.event("MAIN ")
            self.event("FINAL")
            self.event("SIDE", chain="side")
        path = self.turn / "export.json"
        data = {"main_chain_id": 1, "tools": [], "nodes": [{"id": 1, "parent_id": None,
            "message": {"role": "assistant", "content": "MAIN FINAL",
                        "metadata": {"generation_model": "swe-2-max"}}}]}
        completion = {"session_id": "test", "main_result": {"stopReason": "end_turn"},
            "live_main_response": {"sha256": self.connection.main_response_digest.hexdigest(),
                                   "bytes": self.connection.main_response_bytes}}
        worker.write_json(path, data)
        worker.write_json(self.turn / "acp-result.json", completion)
        self.assertTrue(worker.export_evidence(path, "test")["has_final_response"])
        data["nodes"][0]["message"]["content"] = "STALE FINAL"
        worker.write_json(path, data)
        self.assertFalse(worker.export_evidence(path, "test")["has_final_response"])
        data["nodes"][0]["message"]["content"] = "MAIN FINAL"
        completion["main_result"]["stopReason"] = "cancelled"
        worker.write_json(path, data)
        worker.write_json(self.turn / "acp-result.json", completion)
        self.assertFalse(worker.export_evidence(path, "test")["has_final_response"])

    def test_permissions_use_only_authorized_main_tool_once(self):
        """ACP cannot widen narrower access or approve unidentified/side operations."""
        self.connection.main_tools.add("main-tool")
        for tool, mode, allowed in [("main-tool", "dangerous", True),
                                    ("side-tool", "dangerous", False),
                                    ("main-tool", "accept-edits", False)]:
            self.connection.permission_mode = mode
            self.connection.events.put({"id": 7, "method": "session/request_permission", "params": {
                "sessionId": "test", "toolCall": {"toolCallId": tool},
                "options": [{"kind": "allow_once", "optionId": "once"}]}})
            self.connection.receive()
            response = json.loads(self.connection.process.stdin.getvalue().splitlines()[-1])
            self.assertEqual(response["result"]["outcome"]["outcome"], "selected" if allowed else "cancelled")

    def test_steering_uses_main_once_and_returns_only_receipt(self):
        """The public command adds exactly the supplied correction, without acknowledgement inference."""
        with redirect_stdout(io.StringIO()) as output:
            worker.main(["steer", "--run-dir", str(self.root), "--message", "Use canonical owner X.", "--wait-seconds", "0"])
        request_id = json.loads(output.getvalue())["request_id"]
        self.connection.steering()
        self.connection.steering()
        sent = [json.loads(line) for line in self.connection.process.stdin.getvalue().splitlines()]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["method"], "session/prompt")
        self.assertNotIn("_meta", sent[0]["params"])
        self.assertEqual(sent[0]["params"]["prompt"], [{"type": "text", "text": "Use canonical owner X."}])
        self.connection.responses[sent[0]["id"]] = {"result": {"stopReason": "end_turn", "usage": {"totalTokens": 999999}}}
        self.connection.steering(main_done=True)
        receipt = acp.steer(self.root, request_id=request_id, wait_seconds=0)
        self.assertEqual(receipt, {"request_id": request_id, "session_id": "test", "status": "sent", "stop_reason": "end_turn"})
        self.assertEqual(len(self.connection.process.stdin.getvalue().splitlines()), 1)

    def test_steering_missed_turn_and_uncertain_write_are_never_retried(self):
        """Late delivery and a crash around a pipe write remain explicit without replay."""
        missed = acp.steer(self.root, message="Late correction", wait_seconds=0)["request_id"]
        self.connection.steering(main_done=True)
        self.assertEqual(acp.steer(self.root, request_id=missed, wait_seconds=0)["status"], "not_sent")
        uncertain = acp.steer(self.root, message="Uncertain correction", wait_seconds=0)["request_id"]
        with patch.object(self.connection, "send", side_effect=BrokenPipeError):
            with self.assertRaises(BrokenPipeError):
                self.connection.steering()
        self.connection.steering()
        self.assertEqual(acp.steer(self.root, request_id=uncertain, wait_seconds=0)["status"], "uncertain")
        self.assertEqual(self.connection.process.stdin.getvalue(), "")
        orphan = acp.steer(self.root, message="Submitted during shutdown", wait_seconds=0)["request_id"]
        read = acp.read_json
        state_reads = [0]

        def finish_during_status_read(path):
            """Publish delivery as the supervisor switches terminal between the reader's checks."""
            if Path(path).name == "state.json":
                state_reads[0] += 1
                if state_reads[0] == 2:
                    worker.write_json(acp.result_path(self.turn, orphan, "steering"), {"status": "sent", "request_id": orphan})
                    return {"turn_dir": str(self.turn), "status": "exited"}
            return read(path)

        with patch.object(acp, "read_json", side_effect=finish_during_status_read):
            self.assertEqual(acp.steer(self.root, request_id=orphan, wait_seconds=0)["status"], "sent")
        orphan = acp.steer(self.root, message="Undispatched at shutdown", wait_seconds=0)["request_id"]
        worker.write_json(self.root / "state.json", {"turn_dir": str(self.turn), "status": "exited"})
        self.assertEqual(acp.steer(self.root, request_id=orphan, wait_seconds=0)["status"], "not_sent")
        with self.assertRaises(RuntimeError):
            acp.steer(self.root, message="Cannot start another turn", wait_seconds=0)

    def test_work_waits_for_racing_correction_and_uses_latest_completion(self):
        """An earlier main completion cannot end a still-running correction or duplicate usage."""
        main = self.connection.send("session/prompt", {"sessionId": "test", "prompt": []})
        request_id = acp.steer(self.root, message="Correct current work", wait_seconds=0)["request_id"]
        final = {"stopReason": "end_turn", "usage": {"totalTokens": 123}, "_meta": {"cognition.ai/userMessageId": "correction"}}
        self.connection.events.put({"method": "session/update", "params": {"sessionId": "test", "update": {"sessionUpdate": "tool_call"}}})
        self.connection.events.put({"id": main, "result": {"stopReason": "end_turn"}})
        self.connection.events.put({"id": main + 1, "result": final})
        with redirect_stdout(io.StringIO()), patch.object(acp.time, "monotonic", side_effect=[1, 2, 3, 4, 5, 6, 7, 8]):
            result = self.connection.work(main)
        self.assertEqual(result, final)
        self.assertTrue(self.connection.events.empty())
        self.assertEqual(acp.steer(self.root, request_id=request_id, wait_seconds=0)["stop_reason"], "end_turn")
        self.assertFalse((self.turn / "acp-ready.json").exists())

    def test_cancel_stops_both_chains_and_denies_pending_permissions(self):
        """Native cancellation is sent once per active chain and admits no further work."""
        self.connection.main_tools.add("main-tool")
        main = self.connection.send("session/prompt", {"sessionId": "test", "prompt": []})
        question = acp.ask(self.root, question="Progress?", wait_seconds=0)["request_id"]
        self.connection.questions()
        side_rpc = self.connection.side["rpc_id"]
        late = acp.steer(self.root, message="Must not be sent", wait_seconds=0)["request_id"]
        (self.turn / "cancel.request").touch()
        self.connection.events.put({"id": 77, "method": "session/request_permission", "params": {
            "sessionId": "test", "toolCall": {"toolCallId": "main-tool"}, "options": [{"kind": "allow_once", "optionId": "once"}]}})
        self.connection.events.put({"id": main, "result": {"stopReason": "cancelled"}})
        self.connection.events.put({"id": side_rpc, "result": {"stopReason": "cancelled"}})
        with redirect_stderr(io.StringIO()), patch.object(acp.time, "monotonic", side_effect=range(1, 30)):
            self.assertEqual(self.connection.work(main)["stopReason"], "cancelled")
        sent = [json.loads(line) for line in self.connection.process.stdin.getvalue().splitlines()]
        cancellations = [item for item in sent if item.get("method") == "session/cancel"]
        self.assertEqual(len(cancellations), 2)
        self.assertNotIn("_meta", cancellations[0]["params"])
        self.assertEqual(cancellations[1]["params"]["_meta"]["cognition.ai/chain"], "side")
        permission = next(item for item in sent if item.get("id") == 77)
        self.assertEqual(permission["result"]["outcome"]["outcome"], "cancelled")
        self.assertEqual(acp.steer(self.root, request_id=late, wait_seconds=0)["status"], "not_sent")
        self.assertEqual(acp.ask(self.root, request_id=question, wait_seconds=0)["status"], "failed")
        self.assertEqual(worker.read_json(self.turn / "cancel-native.json")["status"], "acknowledged")


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, resultclass=TimedResult))
