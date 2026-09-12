"""BlueStacks session tests."""

from __future__ import annotations

import shlex
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.session import (
    BlueStacksSession,
    BlueStacksSessionCleanupPolicy,
)
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.policy import BlueStacksCapabilities
from pnc_automation.core.errors import DeviceConnectionError, GameLaunchError, InstanceBusyError


@dataclass(slots=True)
class _FakeAdbClient:
    """Returns deterministic command results for BlueStacks session tests."""

    connect_result: CommandResult
    state_result: CommandResult
    shell_result: CommandResult
    shell_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    exec_out_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Returns the seeded connect result."""

        return self.connect_result

    def get_state(self, device_id: str) -> CommandResult:
        """Returns the seeded device-state result."""

        return self.state_result

    def exec_out(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Records one observation capture and returns a deterministic non-empty payload."""

        del timeout_seconds
        self.exec_out_calls.append((device_id, arguments))
        return _command_result(returncode=0, stdout_text="PNG")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Records one shell call and returns the seeded shell result."""

        del timeout_seconds
        self.shell_calls.append((device_id, arguments))
        return self.shell_result


@dataclass(slots=True)
class _SequencedConnectionAdbClient:
    """Returns deterministic ADB connect/state sequences for session retry tests."""

    connect_results: tuple[CommandResult, ...]
    state_results: tuple[CommandResult, ...]
    connect_calls: list[str] = field(default_factory=list)
    state_calls: list[str] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Returns the next seeded connect result."""

        self.connect_calls.append(device_id)
        index = min(len(self.connect_calls) - 1, len(self.connect_results) - 1)
        return self.connect_results[index]

    def get_state(self, device_id: str) -> CommandResult:
        """Returns the next seeded device-state result."""

        self.state_calls.append(device_id)
        index = min(len(self.state_calls) - 1, len(self.state_results) - 1)
        return self.state_results[index]

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Rejects unexpected shell calls during connection tests."""

        del device_id, arguments, timeout_seconds
        raise AssertionError("Connection retry tests must not run shell commands.")


@dataclass(slots=True)
class _SequencedShellAdbClient:
    """Returns deterministic shell results for responsiveness retry tests."""

    shell_results: tuple[CommandResult, ...]
    shell_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Rejects unexpected connect calls during responsiveness tests."""

        del device_id
        raise AssertionError("Responsiveness retry tests must not run connect.")

    def get_state(self, device_id: str) -> CommandResult:
        """Rejects unexpected state calls during responsiveness tests."""

        del device_id
        raise AssertionError("Responsiveness retry tests must not run get-state.")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Returns the next seeded shell result."""

        del timeout_seconds
        self.shell_calls.append((device_id, arguments))
        index = min(len(self.shell_calls) - 1, len(self.shell_results) - 1)
        return self.shell_results[index]


@dataclass(slots=True)
class _RecordingInstanceCloser:
    """Records phase-end shutdown requests without touching a host process."""

    instances: list[BlueStacksInstance] = field(default_factory=list)
    intents: list[tuple[BlueStacksInstance, float]] = field(default_factory=list)
    canceled: list[BlueStacksInstance] = field(default_factory=list)

    def register_close_intent(
        self,
        instance: BlueStacksInstance,
        *,
        grace_period_seconds: float,
    ) -> str:
        """Records durable-intent registration for the selected process."""

        self.intents.append((instance, grace_period_seconds))
        return f"intent-{len(self.intents)}"

    def cancel_close_intent(self, instance: BlueStacksInstance) -> None:
        """Records a keep-warm claim that cancels pending shutdown."""

        self.canceled.append(instance)

    def finalize_close_intent(self, instance: BlueStacksInstance, *, intent_id: str) -> None:
        """Records the exact resolved instance selected for shutdown."""

        self.assert_intent_id(intent_id)
        self.instances.append(instance)

    @staticmethod
    def assert_intent_id(intent_id: str) -> None:
        """Rejects a finalization detached from its registered intent."""

        if not intent_id.startswith("intent-"):
            raise AssertionError("Unexpected shutdown intent id.")


@dataclass(slots=True)
class _FailingInstanceCloser:
    """Raises during shutdown to verify primary failures remain visible."""

    def register_close_intent(
        self,
        instance: BlueStacksInstance,
        *,
        grace_period_seconds: float,
    ) -> str:
        """Accepts the deterministic test intent."""

        del instance, grace_period_seconds
        return "intent-failing"

    def cancel_close_intent(self, instance: BlueStacksInstance) -> None:
        """Accepts an unused keep-warm cancellation path."""

        del instance

    def finalize_close_intent(self, instance: BlueStacksInstance, *, intent_id: str) -> None:
        """Fails one synthetic phase-end shutdown."""

        del instance, intent_id
        raise RuntimeError("cleanup failed")


class BlueStacksSessionTests(unittest.TestCase):
    """Validates BlueStacks connectivity checks."""

    def setUp(self) -> None:
        """Gives every direct session test a private native-lock registry."""

        self._lease_directory = tempfile.TemporaryDirectory()
        self._lease_registry = InstanceLeaseRegistry(root=Path(self._lease_directory.name))
        self._sessions: list[BlueStacksSession] = []

    def tearDown(self) -> None:
        """Closes every session and releases any test-owned lock references."""

        for session in self._sessions:
            session.close()
        self._lease_registry.release_all()
        self._lease_directory.cleanup()

    def _track(self, session: BlueStacksSession) -> BlueStacksSession:
        """Tracks a session for deterministic cleanup after each test."""

        self._sessions.append(session)
        return session

    def _make_session(self, *, adb_client: object, connect_attempts: int = 30) -> BlueStacksSession:
        """Builds a session against this test case's private lease registry."""

        return self._track(
            _make_session(
                adb_client=adb_client,
                connect_attempts=connect_attempts,
                lease_registry=self._lease_registry,
            )
        )

    def test_connect_retries_until_adb_reports_device_ready(self) -> None:
        """Waits through BlueStacks startup while ADB still reports an offline device."""

        adb_client = _SequencedConnectionAdbClient(
            connect_results=(
                _command_result(returncode=0, stdout_text="connected"),
                _command_result(returncode=0, stdout_text="already connected"),
            ),
            state_results=(
                _command_result(returncode=0, stdout_text="offline"),
                _command_result(returncode=0, stdout_text="device"),
            ),
        )
        session = self._make_session(adb_client=adb_client, connect_attempts=2)

        session.connect()

        self.assertEqual(adb_client.connect_calls, ["127.0.0.1:5555", "127.0.0.1:5555"])
        self.assertEqual(adb_client.state_calls, ["127.0.0.1:5555", "127.0.0.1:5555"])

    def test_keep_warm_policy_does_not_close_a_started_instance(self) -> None:
        """Keeps a short or intermediate live phase warm when the agent selects reuse."""

        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                    started_by_resolver=True,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.keep_warm(),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(closer.instances, [])
        self.assertEqual(len(closer.canceled), 1)

    def test_cleanup_policy_rejects_invalid_shutdown_grace(self) -> None:
        """Requires a bounded numeric quiescence interval."""

        for value in (True, -1, float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    BlueStacksSessionCleanupPolicy.close_at_phase_end(
                        shutdown_grace_seconds=value,
                    )

    def test_phase_end_policy_finalizes_after_releasing_session_lease(self) -> None:
        """Makes the instance claimable before the phase-end finalizer runs."""

        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                    started_by_resolver=True,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(len(closer.instances), 1)
        self.assertEqual(closer.instances[0].process_id, 101)
        self.assertEqual(len(closer.intents), 1)
        self.assertEqual(closer.intents[0][1], 120.0)
        competitor = InstanceLeaseRegistry(root=Path(self._lease_directory.name), wait_timeout_seconds=0)
        try:
            acquired = competitor.acquire(display_name="serious_stuff")
            self.assertEqual(acquired.display_name, "serious_stuff")
        finally:
            competitor.release_all()

    def test_phase_end_policy_can_keep_preexisting_instance_warm_when_requested(self) -> None:
        """Allows an agent to preserve a pre-existing user-opened instance explicitly."""

        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=_make_instance(),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(
                    close_preexisting_instance=False,
                ),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(closer.instances, [])

    def test_phase_end_policy_keeps_preexisting_instance_by_default(self) -> None:
        """Does not treat a manually opened process as phase-owned without an explicit choice."""

        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(closer.instances, [])
        self.assertEqual(closer.intents, [])

    def test_phase_end_policy_can_explicitly_close_preexisting_instance(self) -> None:
        """Closes a selected pre-existing process only when the phase explicitly owns cleanup."""

        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(
                    close_preexisting_instance=True,
                ),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(len(closer.instances), 1)
        self.assertEqual(len(closer.intents), 1)

    def test_phase_end_shutdown_waits_for_outer_task_series_reservation(self) -> None:
        """Defers shutdown until the final same-process reservation reference is released."""

        outer_lease = self._lease_registry.acquire(display_name="serious_stuff", timeout_seconds=0)
        closer = _RecordingInstanceCloser()
        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text="model"),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                    started_by_resolver=True,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(),
                instance_closer=closer,
                lease_registry=self._lease_registry,
            )
        )

        session.connect()
        session.close()

        self.assertEqual(closer.instances, [])
        competitor = InstanceLeaseRegistry(root=Path(self._lease_directory.name), wait_timeout_seconds=0)
        try:
            with self.assertRaises(InstanceBusyError):
                competitor.acquire(display_name="serious_stuff")
        finally:
            competitor.release_all()

        outer_lease.release()
        self.assertEqual(len(closer.instances), 1)

    def test_connect_and_shutdown_failures_are_both_reported(self) -> None:
        """Preserves the connection error when final phase cleanup also fails."""

        session = self._track(
            BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=1, stderr_text="offline"),
                    state_result=_command_result(returncode=1, stdout_text="offline"),
                    shell_result=_command_result(returncode=0, stdout_text=""),
                ),
                instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5555",
                    app_package="com.global.tmslg",
                    host_instance_key="Nougat32",
                    process_id=101,
                    started_by_resolver=True,
                ),
                cleanup_policy=BlueStacksSessionCleanupPolicy.close_at_phase_end(),
                instance_closer=_FailingInstanceCloser(),
                lease_registry=self._lease_registry,
                connect_attempts=1,
            )
        )

        with self.assertRaises(BaseExceptionGroup) as raised:
            session.connect()

        self.assertEqual(
            tuple(type(error) for error in raised.exception.exceptions),
            (DeviceConnectionError, RuntimeError),
        )

    def test_connect_fails_after_bounded_readiness_retries(self) -> None:
        """Fails clearly when ADB never reports the device-ready state."""

        adb_client = _SequencedConnectionAdbClient(
            connect_results=(
                _command_result(returncode=0, stdout_text="connected"),
                _command_result(returncode=0, stdout_text="already connected"),
            ),
            state_results=(
                _command_result(returncode=0, stdout_text="offline"),
                _command_result(returncode=0, stdout_text="offline"),
            ),
        )
        session = self._make_session(adb_client=adb_client, connect_attempts=2)

        with self.assertRaises(DeviceConnectionError):
            session.connect()

        self.assertEqual(adb_client.connect_calls, ["127.0.0.1:5555", "127.0.0.1:5555"])
        self.assertEqual(adb_client.state_calls, ["127.0.0.1:5555", "127.0.0.1:5555"])

    def test_ensure_responsive_uses_getprop_probe(self) -> None:
        """Uses a stable getprop probe instead of shell echo for readiness validation."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text="ONEPLUS A5000"),
        )
        session = self._track(BlueStacksSession(
            adb_client=adb_client,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            lease_registry=self._lease_registry,
        ))

        session.ensure_responsive()

        self.assertEqual(adb_client.shell_calls, [("127.0.0.1:5555", ("getprop", "ro.product.model"))])

    def test_ensure_responsive_fails_when_probe_returns_empty_output(self) -> None:
        """Rejects devices that do not return model information from the readiness probe."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=""),
        )
        session = self._track(BlueStacksSession(
            adb_client=adb_client,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            sleep=lambda _: None,
            connect_attempts=1,
            lease_registry=self._lease_registry,
        ))

        with self.assertRaises(DeviceConnectionError):
            session.ensure_responsive()

    def test_ensure_responsive_retries_until_getprop_returns_model(self) -> None:
        """Waits through early Android boot while shell commands return empty model output."""

        adb_client = _SequencedShellAdbClient(
            shell_results=(
                _command_result(returncode=0, stdout_text=""),
                _command_result(returncode=0, stdout_text="SM-G998B"),
            ),
        )
        session = self._make_session(adb_client=adb_client, connect_attempts=2)

        session.ensure_responsive()

        self.assertEqual(
            adb_client.shell_calls,
            [
                ("127.0.0.1:5555", ("getprop", "ro.product.model")),
                ("127.0.0.1:5555", ("getprop", "ro.product.model")),
            ],
        )

    def test_ensure_responsive_fails_after_bounded_retries(self) -> None:
        """Fails clearly when Android never returns model information."""

        adb_client = _SequencedShellAdbClient(
            shell_results=(
                _command_result(returncode=0, stdout_text=""),
                _command_result(returncode=0, stdout_text=""),
            ),
        )
        session = self._make_session(adb_client=adb_client, connect_attempts=2)

        with self.assertRaises(DeviceConnectionError):
            session.ensure_responsive()

        self.assertEqual(len(adb_client.shell_calls), 2)

    def test_input_text_quotes_android_shell_expansions(self) -> None:
        """Sends shell metacharacters literally, including in credential text."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0),
            state_result=_command_result(returncode=0),
            shell_result=_command_result(returncode=0),
        )
        session = self._make_session(adb_client=adb_client)
        for value in ("$HOME", "`id`", "$(id)", r"path\name", "*?[ab]", "hello\tworld"):
            with self.subTest(value=value):
                session.input_text(value)
                arguments = adb_client.shell_calls[-1][1]
                self.assertEqual(arguments, ("input", "text", f"'{value}'"))

        value = "it's a test & example"
        session.input_text(value)
        self.assertEqual(
            shlex.split(" ".join(adb_client.shell_calls[-1][1])),
            ["input", "text", value.replace(" ", "%s")],
        )

    def test_input_text_rejection_does_not_include_the_input_value(self) -> None:
        """Keeps rejected multiline credentials out of structured diagnostics."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0),
            state_result=_command_result(returncode=0),
            shell_result=_command_result(returncode=0),
        )
        session = self._make_session(adb_client=adb_client)
        with self.assertRaises(DeviceConnectionError) as raised:
            session.input_text("synthetic-sensitive-value\nsecond-line")

        self.assertNotIn("synthetic-sensitive-value", str(raised.exception.details))
        self.assertEqual(adb_client.shell_calls, [])

    def test_swipe_uses_explicit_touchscreen_source(self) -> None:
        """Uses the touchscreen-qualified input command so drag gestures are unambiguous to ADB-backed emulators."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=""),
        )
        session = self._track(BlueStacksSession(
            adb_client=adb_client,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            lease_registry=self._lease_registry,
        ))

        session.swipe(100, 200, 300, 400, duration_ms=750)

        self.assertEqual(
            adb_client.shell_calls,
            [("127.0.0.1:5555", ("input", "touchscreen", "swipe", "100", "200", "300", "400", "750"))],
        )

    def test_swipe_can_use_plain_input_source(self) -> None:
        """Allows callers to request the plain Android swipe entry point when emulator behavior differs by source."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=""),
        )
        session = self._track(BlueStacksSession(
            adb_client=adb_client,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            lease_registry=self._lease_registry,
        ))

        session.swipe(100, 200, 300, 400, duration_ms=750, input_source="default")

        self.assertEqual(
            adb_client.shell_calls,
            [("127.0.0.1:5555", ("input", "swipe", "100", "200", "300", "400", "750"))],
        )

    def test_swipe_can_emit_press_move_release_motion_events(self) -> None:
        """Supports a desktop-like press-drag-release primitive through Android motion events."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=""),
        )
        session = self._track(BlueStacksSession(
            adb_client=adb_client,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="serious_stuff",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            sleep=lambda _: None,
            lease_registry=self._lease_registry,
        ))

        session.swipe(100, 200, 300, 400, duration_ms=750, gesture_primitive="press_move_release")

        self.assertEqual(
            adb_client.shell_calls,
            [
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "DOWN", "100", "200")),
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "MOVE", "150", "250")),
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "MOVE", "200", "300")),
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "MOVE", "250", "350")),
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "MOVE", "300", "400")),
                ("127.0.0.1:5555", ("input", "touchscreen", "motionevent", "UP", "300", "400")),
            ],
        )

    def test_read_only_observation_is_allowed_but_app_launch_and_input_are_rejected(self) -> None:
        """Allows observation of an already-running app while rejecting every control primitive."""

        with tempfile.TemporaryDirectory() as directory:
            registry = InstanceLeaseRegistry(root=Path(directory))
            lease = registry.acquire(display_name="serious_stuff", timeout_seconds=0)
            adb_client = _FakeAdbClient(
                connect_result=_command_result(returncode=0, stdout_text="connected"),
                state_result=_command_result(returncode=0, stdout_text="device"),
                shell_result=_command_result(returncode=0, stdout_text=_launcher_window_dump()),
            )
            session = self._track(BlueStacksSession(
                adb_client=adb_client,
                instance=_make_instance(),
                capabilities=BlueStacksCapabilities(
                    allow_instance_launch=False,
                    allow_app_launch=False,
                    allow_input=False,
                ),
                lease_registry=registry,
                instance_lease=lease,
            ))
            try:
                self.assertFalse(session.is_app_foregrounded())
                self.assertEqual(len(adb_client.shell_calls), 1)
                self.assertEqual(session.capture_screenshot_bytes(), b"PNG")
                with self.assertRaises(PermissionError):
                    session.ensure_app_foregrounded()
                for operation in (
                    lambda: session.launch_app(),
                    lambda: session.tap_point(1, 2),
                    lambda: session.input_text("text"),
                    lambda: session.press_key("KEYCODE_BACK"),
                    lambda: session.swipe(1, 2, 3, 4),
                ):
                    with self.subTest(operation=operation):
                        with self.assertRaises(PermissionError):
                            operation()
            finally:
                session.close()
                registry.release_all()

    def test_ensure_app_foregrounded_reports_false_when_package_is_already_foregrounded(self) -> None:
        """Distinguishes an existing foreground app from a newly started launch."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=_game_window_dump()),
        )
        session = self._make_session(adb_client=adb_client)

        self.assertFalse(session.ensure_app_foregrounded())
        self.assertEqual(1, len(adb_client.shell_calls))

    def test_ensure_app_foregrounded_reports_true_when_it_starts_a_launch(self) -> None:
        """Reports the launch boundary needed by passive post-launch screen settling."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=_launcher_window_dump()),
        )
        session = self._make_session(adb_client=adb_client)

        self.assertTrue(session.ensure_app_foregrounded())
        self.assertEqual(
            [
                ("127.0.0.1:5555", ("dumpsys", "window", "windows")),
                ("127.0.0.1:5555", ("monkey", "-p", "com.global.tmslg", "-c", "android.intent.category.LAUNCHER", "1")),
            ],
            adb_client.shell_calls,
        )

    def test_foreground_detection_ignores_background_game_window_when_launcher_has_focus(self) -> None:
        """Reads only mCurrentFocus instead of treating a background game window as foreground."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=0, stdout_text=_launcher_window_dump(include_background_game=True)),
        )
        session = self._make_session(adb_client=adb_client)

        self.assertFalse(session.is_app_foregrounded())

    def test_foreground_detection_requires_exact_game_component_package(self) -> None:
        """Does not accept a package whose name merely contains the configured package."""

        for dump, expected in (
            (_game_window_dump(), True),
            (_game_window_dump() + "\r\n", True),
            (_window_dump("com.global.tmslg.backup/com.example.MainActivity"), False),
        ):
            with self.subTest(dump=dump):
                adb_client = _FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text=dump),
                )
                session = self._make_session(adb_client=adb_client)
                self.assertEqual(expected, session.is_app_foregrounded())
                session.close()

    def test_foreground_detection_treats_null_or_title_without_component_as_not_game(self) -> None:
        """Returns false when WMS has focus without a proven package component."""

        for dump in (
            "mCurrentFocus=null",
            _window_dump("Starting Window"),
        ):
            with self.subTest(dump=dump):
                adb_client = _FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text=dump),
                )
                session = self._make_session(adb_client=adb_client)
                self.assertFalse(session.is_app_foregrounded())
                session.close()

    def test_foreground_detection_rejects_missing_duplicate_or_malformed_focus(self) -> None:
        """Fails with an actionable launch error instead of guessing from another WMS field."""

        dumps = (
            "mFocusedApp=Window{1 u0 com.global.tmslg/com.example.MainActivity}",
            "mCurrentFocus=null\nmCurrentFocus=null",
            "mCurrentFocus=not-a-window",
            "mCurrentFocus=\nWindow{48fe9e8 u0 com.global.tmslg/com.global.tmslg.MainActivity}",
            "mCurrentFocus=Window{not-hex u0 com.global.tmslg/com.global.tmslg.MainActivity}",
            "mCurrentFocus=Window{48fe9e8 u0 com.global.tmslg/com.example.Main/Activity}",
            "mCurrentFocus=Window{48fe9e8 u0 com.global.tmslg/}",
            "mCurrentFocus=Window{48fe9e8 u0   }",
        )
        for dump in dumps:
            with self.subTest(dump=dump):
                adb_client = _FakeAdbClient(
                    connect_result=_command_result(returncode=0, stdout_text="connected"),
                    state_result=_command_result(returncode=0, stdout_text="device"),
                    shell_result=_command_result(returncode=0, stdout_text=dump),
                )
                session = self._make_session(adb_client=adb_client)
                with self.assertRaisesRegex(GameLaunchError, "mCurrentFocus"):
                    session.is_app_foregrounded()
                session.close()

    def test_launch_error_from_adb_is_still_propagated(self) -> None:
        """Keeps the existing GameLaunchError boundary when the launch command itself fails."""

        adb_client = _FakeAdbClient(
            connect_result=_command_result(returncode=0, stdout_text="connected"),
            state_result=_command_result(returncode=0, stdout_text="device"),
            shell_result=_command_result(returncode=1, stderr_text="monkey failed"),
        )
        session = self._make_session(adb_client=adb_client)

        with self.assertRaises(GameLaunchError):
            session.launch_app()

    def test_connect_failure_releases_the_supplied_operation_lease(self) -> None:
        """Makes a failed ADB connection immediately available to the next process-shaped owner."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = InstanceLeaseRegistry(root=root)
            lease = registry.acquire(display_name="serious_stuff", timeout_seconds=0)
            session = self._track(BlueStacksSession(
                adb_client=_FakeAdbClient(
                    connect_result=_command_result(returncode=1, stderr_text="offline"),
                    state_result=_command_result(returncode=1, stdout_text="offline"),
                    shell_result=_command_result(returncode=0, stdout_text=""),
                ),
                instance=_make_instance(),
                lease_registry=registry,
                instance_lease=lease,
                connect_attempts=1,
            ))

            with self.assertRaises(DeviceConnectionError):
                session.connect()
            competitor = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            try:
                acquired = competitor.acquire(display_name="serious_stuff")
                self.assertEqual(acquired.display_name, "serious_stuff")
            finally:
                competitor.release_all()


def _window_dump(component: str) -> str:
    """Builds one realistic WMS mCurrentFocus line for foreground tests."""

    return f"  mCurrentFocus=Window{{48fe9e8 u0 {component}}}\n"


def _game_window_dump() -> str:
    """Builds a focused P&C WMS window dump."""

    return _window_dump("com.global.tmslg/com.global.tmslg.MainActivity")


def _launcher_window_dump(*, include_background_game: bool = False) -> str:
    """Builds a launcher-focused dump that may also contain a background game window."""

    background = (
        "  Window #1 Window{1234567 u0 com.global.tmslg/com.global.tmslg.MainActivity}\n"
        if include_background_game
        else ""
    )
    return background + "  mFocusedApp=Window{7654321 u0 com.global.tmslg/com.global.tmslg.MainActivity}\n" + _window_dump(
        "com.uncube.launcher3/com.bluestacks.launcher.activity.HomeActivity"
    )


def _make_instance() -> BlueStacksInstance:
    """Builds the canonical test emulator target."""

    return BlueStacksInstance(
        id="bs-main",
        display_name="serious_stuff",
        device_id="127.0.0.1:5555",
        app_package="com.global.tmslg",
    )


def _command_result(*, returncode: int, stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    """Builds one raw ADB command result for tests."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


def _make_session(
    *,
    adb_client: object,
    connect_attempts: int = 30,
    lease_registry: InstanceLeaseRegistry,
) -> BlueStacksSession:
    """Builds one test session over the provided fake ADB client."""

    return BlueStacksSession(
        adb_client=adb_client,
        instance=BlueStacksInstance(
            id="bs-main",
            display_name="serious_stuff",
            device_id="127.0.0.1:5555",
            app_package="com.global.tmslg",
        ),
        sleep=lambda _: None,
        connect_attempts=connect_attempts,
        lease_registry=lease_registry,
    )


if __name__ == "__main__":
    unittest.main()
