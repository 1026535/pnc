"""Exercise timer lifecycle and anomaly detection without model or app requests."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import devin_monitor as monitor


class MonitorTests(unittest.TestCase):
    """Keep timer and health decisions independent of paid inference."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rollout = self.root / "rollout.jsonl"
        self.rollout.write_text(json.dumps({"type": "session_meta", "payload": {"id": "lead"}}) + "\n")
        self.config = {"thread_id": "lead", "automation_id": "timer", "name": "Keepalive", "rollout": str(self.rollout)}
        monitor.write_json(self.root / "config.json", self.config)

    def event(self, kind, turn):
        """Append only synthetic lifecycle metadata."""
        with self.rollout.open("a") as stream:
            stream.write(json.dumps({"type": "event_msg", "timestamp": "now", "payload": {"type": kind, "turn_id": turn}}) + "\n")

    def snapshot(self, **kwargs):
        """Build a live worker sample with a stable last call."""
        value = {"state": "running", "turn": 1, "supervisor_alive": True, "heartbeat_at": 0,
                 "fingerprint": [1, 10, 20, 0], "in_flight": False}
        value.update(kwargs)
        return value

    def test_identity_and_incremental_partial_lines(self):
        self.assertEqual(monitor.rollout_path("lead", self.rollout), self.rollout)
        with self.assertRaises(ValueError):
            monitor.rollout_path("wrong", self.rollout)
        self.event("task_complete", "historical")
        offset = self.rollout.stat().st_size
        self.event("task_complete", "new")
        with self.rollout.open("ab") as stream:
            stream.write(b'{"type":')
        events, cursor = monitor.read_events(self.rollout, offset)
        self.assertEqual([e["turn_id"] for e in events], ["new"])
        self.assertEqual(monitor.read_events(self.rollout, cursor), ([], cursor))
        self.rollout.write_bytes(b"")
        with self.assertRaises(ValueError):
            monitor.read_events(self.rollout, cursor)

    def test_completion_deduplication_and_active_turn(self):
        state = {}
        monitor.observe_events(state, [{"type": "task_complete", "turn_id": "one"}])
        self.assertTrue(state["rearm_pending"])
        state["rearm_pending"] = False
        monitor.observe_events(state, [{"type": "task_complete", "turn_id": "one"},
                                      {"type": "task_started", "turn_id": "two"},
                                      {"type": "task_complete", "turn_id": "stale"}])
        self.assertFalse(state["rearm_pending"])
        self.assertEqual(state["active_turn"], "two")

    def test_heartbeat_requires_matching_receipt(self):
        response = {"content": [{"type": "text", "text": json.dumps({"automationId": "timer", "status": "ACTIVE"})}]}
        with patch.object(monitor, "call_app_tool", AsyncMock(return_value=response)) as call:
            asyncio.run(monitor.set_heartbeat(self.config, "ACTIVE", self.root / "err"))
            self.assertEqual(call.call_args.args[2]["prompt"], monitor.PROMPT)
            self.assertEqual(call.call_args.args[2]["rrule"], "FREQ=MINUTELY;INTERVAL=27")
            with self.assertRaises(monitor.AppToolError):
                asyncio.run(monitor.set_heartbeat(self.config, "PAUSED", self.root / "err"))

    def test_same_tool_with_new_activity_is_progress(self):
        prior = {"snapshot": self.snapshot(), "checked_at": 0}
        result = monitor.classify_activity(prior, self.snapshot(fingerprint=[1, 11, 20, 1], heartbeat_at=900), 900)
        self.assertIsNone(result["alert"])
        self.assertIsNone(result["quiet_since"])

    def test_sustained_inactivity_but_long_tool_is_not_stall(self):
        prior = {"snapshot": self.snapshot(), "checked_at": 0}
        first = monitor.classify_activity(prior, self.snapshot(heartbeat_at=900), 900)
        first["checked_at"] = 900
        self.assertIsNone(first["alert"])
        second = monitor.classify_activity(first, self.snapshot(heartbeat_at=1800), 1800)
        self.assertEqual(second["alert"], "possible-inactivity:turn-1")
        live = monitor.classify_activity(first, self.snapshot(heartbeat_at=7200, in_flight=True), 7200)
        self.assertIsNone(live["alert"])

    def test_dead_and_stale_supervisors_are_actionable(self):
        for sample in (self.snapshot(supervisor_alive=False), self.snapshot()):
            self.assertEqual(monitor.classify_activity({}, sample, 200)["alert"], "supervisor-unhealthy:turn-1")

    def test_health_alert_is_latched(self):
        (self.root / "runs").mkdir()
        monitor.write_json(self.root / "runs/one.json", {"run_dir": "worker"})
        state = {}
        with patch.object(monitor, "activity_snapshot", return_value=self.snapshot(supervisor_alive=False)), \
                patch.object(monitor, "checked_delivery", return_value={"status": "delivered"}) as delivery:
            monitor.health_check(self.root, self.config, state, 0)
            monitor.health_check(self.root, self.config, state, 900)
            delivery.assert_called_once()

    def test_ambiguous_callback_is_not_retried(self):
        (self.root / "runs").mkdir()
        monitor.write_json(self.root / "runs/one.json", {"run_dir": "worker"})
        monitor.write_json(self.root / "notification.json", {"status": "pending", "uncertain": True, "at": 0})
        with patch.object(monitor, "activity_snapshot", return_value={"state": "terminal", "turn": 1, "turn_dir": str(self.root)}), \
                patch.object(monitor, "checked_delivery") as delivery:
            monitor.health_check(self.root, self.config, {}, 900)
            delivery.assert_not_called()

    def test_definite_callback_failure_is_retried_once_after_delivery(self):
        (self.root / "runs").mkdir()
        monitor.write_json(self.root / "runs/one.json", {"run_dir": "worker"})
        monitor.write_json(self.root / "notification.json", {"status": "pending", "uncertain": False, "at": 0})
        with patch.object(monitor, "activity_snapshot", return_value={"state": "terminal", "turn": 1, "turn_dir": str(self.root)}), \
                patch.object(monitor, "checked_delivery", return_value={"status": "delivered", "at": 900}) as delivery:
            state = {}
            monitor.health_check(self.root, self.config, state, 900)
            monitor.health_check(self.root, self.config, state, 1800)
            delivery.assert_called_once()

    def test_stop_during_rearm_wins(self):
        async def update(config, status, error_path):
            if status == "ACTIVE":
                (self.root / "stop.request").touch()
        with patch.object(monitor, "monitor_lock"), patch.object(monitor, "set_heartbeat", side_effect=update) as call, \
                patch.object(monitor, "health_check") as health:
            monitor.run_monitor(self.root)
        self.assertEqual([c.args[1] for c in call.call_args_list], ["ACTIVE", "PAUSED"])
        health.assert_not_called()
        self.assertEqual(monitor.read_json(self.root / "state.json")["status"], "stopped")

    def test_completion_rearms_without_health_or_model_queries(self):
        ticks = 0
        def tick(seconds):
            nonlocal ticks
            ticks += 1
            if ticks == 1:
                self.event("task_complete", "fresh")
            else:
                (self.root / "stop.request").touch()
        with patch.object(monitor, "monitor_lock"), patch.object(monitor, "set_heartbeat", AsyncMock()) as call, \
                patch.object(monitor, "health_check") as health, patch.object(monitor.time, "sleep", side_effect=tick):
            monitor.run_monitor(self.root)
        self.assertEqual([c.args[1] for c in call.call_args_list], ["ACTIVE", "ACTIVE", "PAUSED"])
        health.assert_called_once()

    def test_restart_rearms_stopped_timer(self):
        monitor.write_json(self.root / "state.json", {"status": "stopped", "offset": self.rollout.stat().st_size,
                           "active_turn": None, "rearm_pending": False})
        self.test_stop_during_rearm_wins()

    def test_snapshot_tolerates_partial_tool_record(self):
        turn = self.root / "turn"
        turn.mkdir()
        monitor.write_json(self.root / "state.json", {"status": "running", "turn": 1, "turn_dir": str(turn), "supervisor_pid": 1})
        (turn / "identity.jsonl").write_text('{"hook_event_name":"PreToolUse","tool_name":"shell","at":1}\n{"part":')
        snapshot = monitor.activity_snapshot(self.root, alive=lambda pid: True)
        self.assertTrue(snapshot["in_flight"])
        self.assertEqual(snapshot["last_tool_at"], 1)

    def test_snapshot_preserves_tool_state_across_damaged_hook_line(self):
        turn = self.root / "turn"
        turn.mkdir()
        monitor.write_json(self.root / "state.json", {
            "status": "running", "turn": 1, "turn_dir": str(turn), "supervisor_pid": 1,
        })
        identity = turn / "identity.jsonl"
        identity.write_text(
            '{"hook_event_name":"PostToolUse","tool_name":"shell","at":1}\n'
            'e_up"}\n'
            '{"hook_event_name":"PreToolUse","tool_name":"tests","at":2}\n',
            encoding="utf-8",
        )
        snapshot = monitor.activity_snapshot(self.root, alive=lambda pid: True)
        self.assertTrue(snapshot["in_flight"])
        self.assertEqual(snapshot["tool"], "tests")
        self.assertEqual(snapshot["last_tool_at"], 2)
        self.assertEqual(snapshot["unreadable_event_lines"], 1)
        self.assertEqual(snapshot["fingerprint"][1], identity.stat().st_size)

    def test_rearm_failure_backoff_and_single_alert(self):
        clock = [1000]
        attempts = []
        async def update(config, status, error_path):
            if status == "ACTIVE":
                attempts.append(clock[0])
                if len(attempts) <= 3:
                    raise monitor.AppToolError("offline")
                (self.root / "stop.request").touch()
        def tick(seconds):
            clock[0] += seconds
            if clock[0] > 1100:
                self.fail("Retry loop failed to converge")
        with patch.object(monitor, "monitor_lock"), patch.object(monitor, "set_heartbeat", side_effect=update), \
                patch.object(monitor, "health_check"), patch.object(monitor, "checked_delivery") as alert, \
                patch.object(monitor.time, "time", side_effect=lambda: clock[0]), \
                patch.object(monitor.time, "sleep", side_effect=tick):
            monitor.run_monitor(self.root)
        self.assertEqual(attempts, [1000, 1010, 1030, 1070])
        alert.assert_called_once()

    def test_only_one_monitor_can_own_lead(self):
        with patch.object(monitor, "codex_home", return_value=self.root):
            with monitor.monitor_lock("lead"):
                with self.assertRaises(OSError):
                    with monitor.monitor_lock("lead"):
                        self.fail("Duplicate monitor acquired the same lead")
            with monitor.monitor_lock("lead"):
                pass


if __name__ == "__main__":
    unittest.main()
