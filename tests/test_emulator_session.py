"""BlueStacks session tests."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
import tempfile
from pathlib import Path

from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.policy import BlueStacksCapabilities
from pnc_automation.core.errors import DeviceConnectionError


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
                shell_result=_command_result(returncode=0, stdout_text="other.package"),
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
