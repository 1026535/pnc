"""Scrcpy control-only wheel transport tests."""

from __future__ import annotations

import hashlib
import io
import re
import struct
import tempfile
import unittest
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from pnc_automation.core.errors import DeviceConnectionError
from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.emulator.scroll_transport import (
    SCRCPY_SERVER_ASSET_NAME,
    SCRCPY_SERVER_SIZE_BYTES,
    ScrcpyControlTransport,
    build_scroll_packet,
    verify_native_display_mapping,
    verify_server_asset,
)

_ASSET_PACKAGE = "pnc_automation.core.infra.emulator"
_DEVICE_ID = "127.0.0.1:5555"


def _command_result(*, returncode: int, stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    """Builds one raw ADB command result for transport tests."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


@dataclass
class _FakeTransportAdbClient:
    """Scripts the device-scoped adb calls one transport lifecycle performs."""

    forwards: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    removed_forwards: list[str] = field(default_factory=list)
    adb_path: str = "adb"
    push_ok: bool = True
    forward_ok: bool = True
    publish_forward: bool = True
    shell_ok: bool = True
    on_call: Callable[[tuple[str, ...]], None] | None = None

    def run_device(
        self,
        device_id: str,
        *arguments: str,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        """Answers the bounded push/forward/list/remove/shell sequence."""

        del timeout_seconds
        self.calls.append(arguments)
        if self.on_call is not None:
            self.on_call(arguments)
        if arguments[0] == "push":
            return _command_result(returncode=0 if self.push_ok else 1, stderr_text="push failed")
        if arguments[:2] == ("forward", "--no-rebind"):
            if not self.forward_ok:
                return _command_result(returncode=1, stderr_text="forward failed")
            if self.publish_forward:
                self.forwards[arguments[2]] = arguments[3]
            return _command_result(returncode=0)
        if arguments[:2] == ("forward", "--list"):
            listing = "".join(
                f"{device_id} {endpoint} {name}\n" for endpoint, name in self.forwards.items()
            )
            return _command_result(returncode=0, stdout_text=listing)
        if arguments[:2] == ("forward", "--remove"):
            self.removed_forwards.append(arguments[2])
            self.forwards.pop(arguments[2], None)
            return _command_result(returncode=0)
        if arguments[0] == "shell":
            return _command_result(returncode=0 if self.shell_ok else 1, stderr_text="shell failed")
        return _command_result(returncode=0)


class _FakeServerProcess:
    """Stands in for the owned foreground adb shell app_process."""

    def __init__(self) -> None:
        self.stderr = io.BytesIO(b"")
        self.wait_calls: list[float | None] = []
        self.terminated = False

    def poll(self) -> int | None:
        """Reports a live server process."""

        return None

    def wait(self, timeout: float | None = None) -> int:
        """Reports a clean process exit."""

        self.wait_calls.append(timeout)
        return 0

    def terminate(self) -> None:
        """Records termination of the owned process."""

        self.terminated = True


class _SetupClock:
    """Advances a deterministic monotonic clock for shared-deadline tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Reports the current fake monotonic time."""

        return self.now

    def advance(self, seconds: float) -> None:
        """Moves the fake monotonic time forward."""

        self.now += seconds


class _FakeControlSocket:
    """Stands in for the connected scrcpy control socket."""

    def __init__(self, handshake: bytes = b"\x00") -> None:
        self.handshake = handshake
        self.sent = bytearray()
        self.closed = False

    def settimeout(self, _value: float | None) -> None:
        """Accepts socket timeout configuration."""

    def recv(self, _size: int) -> bytes:
        """Returns the configured handshake byte."""

        return self.handshake

    def sendall(self, data: bytes) -> None:
        """Records dispatched packet bytes."""

        self.sent += data

    def close(self) -> None:
        """Records socket shutdown."""

        self.closed = True


def _make_transport(
    adb_client: _FakeTransportAdbClient,
    *,
    socket: _FakeControlSocket,
    process: _FakeServerProcess,
    popen_calls: list[list[str]],
) -> ScrcpyControlTransport:
    """Builds a transport wired to offline lifecycle fakes."""

    def _spawn(argv: list[str], **_kwargs: object) -> _FakeServerProcess:
        popen_calls.append(list(argv))
        return process

    return ScrcpyControlTransport(
        adb_client=adb_client,
        device_id=_DEVICE_ID,
        run_id="s1-abcdef123456",
        startup_timeout_seconds=5.0,
        connect_retry_seconds=0.0,
        connect_factory=lambda _address, timeout=None: socket,
        popen_factory=_spawn,
        sleep=lambda _: None,
        port_allocator=lambda: 41234,
    )


class ScrollPacketTests(unittest.TestCase):
    """Proves the exact 21-byte upstream scroll control message."""

    def test_build_scroll_packet_serializes_the_upstream_wire_layout(self) -> None:
        """Encodes type 3, native pixels, unsigned display size, zero hscroll/buttons."""

        packet = build_scroll_packet(x=640, y=360, width=1280, height=720, vscroll_detent=1)

        self.assertEqual(len(packet), 21)
        self.assertEqual(packet, struct.pack(">BiiHHhhI", 0x03, 640, 360, 1280, 720, 0, 0x0800, 0))
        negative = build_scroll_packet(x=1, y=2, width=3, height=4, vscroll_detent=-1)
        self.assertEqual(negative, struct.pack(">BiiHHhhI", 0x03, 1, 2, 3, 4, 0, -0x0800, 0))

    def test_build_scroll_packet_rejects_invalid_inputs(self) -> None:
        """Rejects non-detents, non-integers, bad dimensions, and out-of-display points."""

        cases = (
            {"x": -1, "y": 0, "width": 10, "height": 10, "vscroll_detent": 1},
            {"x": 10, "y": 0, "width": 10, "height": 10, "vscroll_detent": 1},
            {"x": 0, "y": 10, "width": 10, "height": 10, "vscroll_detent": 1},
            {"x": 0, "y": 0, "width": 0, "height": 10, "vscroll_detent": 1},
            {"x": 0, "y": 0, "width": 70000, "height": 10, "vscroll_detent": 1},
            {"x": 0, "y": 0, "width": 10, "height": 10, "vscroll_detent": 0},
            {"x": 0, "y": 0, "width": 10, "height": 10, "vscroll_detent": 2},
            {"x": 0, "y": 0, "width": 10, "height": 10, "vscroll_detent": True},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_scroll_packet(**kwargs)


class NativeDisplayMappingTests(unittest.TestCase):
    """Proves wheel coordinates require identity-mapped native display pixels."""

    def test_verify_native_display_mapping_accepts_identity_display_zero_geometry(self) -> None:
        """Accepts real display-0 geometry equal to the authorized frame size."""

        verify_native_display_mapping(
            frame_size=(1280, 720),
            dumpsys_output="Display 0: real 1280 x 720, rotation 0",
            device_id=_DEVICE_ID,
        )

    def test_verify_native_display_mapping_rejects_unmappable_displays(self) -> None:
        """Rejects missing geometry, nonzero rotation, and scaled native size."""

        for output in (
            "no display info",
            "Display 0: real 1280 x 720, rotation 1",
            "Display 0: real 640 x 360, rotation 0",
        ):
            with self.subTest(output=output), self.assertRaises(DeviceConnectionError) as context:
                verify_native_display_mapping(
                    frame_size=(1280, 720),
                    dumpsys_output=output,
                    device_id=_DEVICE_ID,
                )
            self.assertEqual(context.exception.details["failure_phase"], "mapping")


class ScrcpyServerAssetTests(unittest.TestCase):
    """Proves the pinned server asset resolves through installed package data."""

    def test_packaged_server_asset_and_notice_match_the_pinned_digest(self) -> None:
        """Resolves the packaged jar and upstream v4.0 license content offline."""

        package = resources.files(_ASSET_PACKAGE)
        notice = package.joinpath("data", "scrcpy-server-v4.0.LICENSE-Apache-2.0.txt")
        self.assertTrue(notice.is_file())
        # Retrieved 2026-09-27 from the upstream v4.0 tag source:
        # https://raw.githubusercontent.com/Genymobile/scrcpy/v4.0/LICENSE
        with resources.as_file(notice) as notice_path:
            notice_bytes = notice_path.read_bytes()
        self.assertEqual(
            # Git may check text out as CRLF; upstream content uses LF.
            hashlib.sha256(notice_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            "01c12035bf35af37241298dc7ad538eb2a07e5c940437bc6876feeaa9d1951d0",
        )
        notice_text = notice_bytes.decode("utf-8")
        self.assertIn("Copyright (C) 2018 Genymobile", notice_text)
        self.assertIn("Copyright (C) 2018-2026 Romain Vimont", notice_text)
        self.assertIn("END OF TERMS AND CONDITIONS", notice_text)
        with resources.as_file(package.joinpath("data", SCRCPY_SERVER_ASSET_NAME)) as asset:
            self.assertEqual(asset.stat().st_size, SCRCPY_SERVER_SIZE_BYTES)
            verify_server_asset(asset)

    def test_verify_server_asset_rejects_missing_or_mismatched_assets(self) -> None:
        """Fails before remote setup when the pinned jar cannot be proven."""

        with self.assertRaises(DeviceConnectionError) as missing:
            verify_server_asset(Path("does-not-exist.jar"))
        self.assertEqual(missing.exception.details["failure_phase"], "setup")

        with tempfile.TemporaryDirectory() as directory:
            mismatch = Path(directory) / "scrcpy-server-v4.0"
            mismatch.write_bytes(b"not the pinned server")
            with self.assertRaises(DeviceConnectionError) as context:
                verify_server_asset(mismatch)
        self.assertEqual(context.exception.details["failure_phase"], "setup")


class ScrcpyControlTransportTests(unittest.TestCase):
    """Proves the bounded control-only transport lifecycle."""

    def test_start_runs_the_control_only_setup_and_derives_unique_endpoints(self) -> None:
        """Pushes the pinned jar, installs one owned forward, and awaits the dummy byte."""

        adb_client = _FakeTransportAdbClient()
        socket = _FakeControlSocket()
        process = _FakeServerProcess()
        popen_calls: list[list[str]] = []
        transport = _make_transport(
            adb_client,
            socket=socket,
            process=process,
            popen_calls=popen_calls,
        )

        transport.start()

        self.assertTrue(transport.ready)
        self.assertEqual(
            transport.remote_path,
            "/data/local/tmp/pnc-scrcpy-control-s1-abcdef123456.jar",
        )
        self.assertTrue(re.fullmatch(r"scrcpy_[0-9a-f]{8}", transport.socket_name))
        push_call = adb_client.calls[0]
        self.assertEqual(push_call[0], "push")
        self.assertEqual(push_call[2], transport.remote_path)
        self.assertEqual(
            adb_client.calls[1:3],
            [
                ("forward", "--no-rebind", "tcp:41234", f"localabstract:{transport.socket_name}"),
                ("forward", "--list"),
            ],
        )
        self.assertEqual(len(popen_calls), 1)
        command = popen_calls[0][-1]
        expected_scid = zlib.crc32(b"s1-abcdef123456") & 0x7FFFFFFF
        for option in (
            "control=true",
            "video=false",
            "audio=false",
            "clipboard_autosync=false",
            "power_off_on_close=false",
            "power_on=false",
            "cleanup=true",
            "send_dummy_byte=true",
            "display_id=0",
            f"scid={expected_scid:x}",
        ):
            self.assertIn(option, command)
        transport.close()

    def test_send_packet_dispatches_through_the_ready_socket(self) -> None:
        """Sends one prebuilt packet as-is through the connected control socket."""

        adb_client = _FakeTransportAdbClient()
        socket = _FakeControlSocket()
        transport = _make_transport(
            adb_client,
            socket=socket,
            process=_FakeServerProcess(),
            popen_calls=[],
        )
        transport.start()
        packet = build_scroll_packet(x=640, y=360, width=1280, height=720, vscroll_detent=-1)

        transport.send_packet(packet)

        self.assertEqual(bytes(socket.sent), packet)
        transport.close()

    def test_send_packet_requires_a_ready_socket_and_exact_size(self) -> None:
        """Refuses sends before startup and packets that are not 21 bytes."""

        adb_client = _FakeTransportAdbClient()
        socket = _FakeControlSocket()
        transport = _make_transport(
            adb_client,
            socket=socket,
            process=_FakeServerProcess(),
            popen_calls=[],
        )
        packet = build_scroll_packet(x=1, y=1, width=1280, height=720, vscroll_detent=1)

        with self.assertRaises(DeviceConnectionError) as context:
            transport.send_packet(packet)
        self.assertEqual(context.exception.details["failure_phase"], "send")

        transport.start()
        with self.assertRaises(ValueError):
            transport.send_packet(packet[:-1])
        transport.close()

    def test_start_rejects_a_forward_the_listing_does_not_own(self) -> None:
        """Fails setup when adb does not publish this transport's exact forward."""

        adb_client = _FakeTransportAdbClient(publish_forward=False)
        transport = _make_transport(
            adb_client,
            socket=_FakeControlSocket(),
            process=_FakeServerProcess(),
            popen_calls=[],
        )

        with self.assertRaises(DeviceConnectionError) as context:
            transport.start()

        self.assertEqual(context.exception.details["failure_phase"], "setup")
        self.assertFalse(transport.ready)

    def test_start_rejects_an_unexpected_handshake_byte(self) -> None:
        """Requires the single dummy 0x00 byte before the socket is usable."""

        adb_client = _FakeTransportAdbClient()
        transport = ScrcpyControlTransport(
            adb_client=adb_client,
            device_id=_DEVICE_ID,
            run_id="s1-abcdef123456",
            startup_timeout_seconds=0.25,
            connect_retry_seconds=0.0,
            connect_factory=lambda _address, timeout=None: _FakeControlSocket(handshake=b"\x01"),
            popen_factory=lambda _argv, **_kwargs: _FakeServerProcess(),
            sleep=lambda _: None,
            port_allocator=lambda: 41234,
        )

        with self.assertRaises(DeviceConnectionError) as context:
            transport.start()

        self.assertEqual(context.exception.details["failure_phase"], "setup")
        self.assertFalse(transport.ready)

    def test_close_releases_only_owned_endpoints_and_is_idempotent(self) -> None:
        """Closes the socket, reaps the process, removes the owned forward, unlinks the jar."""

        adb_client = _FakeTransportAdbClient()
        socket = _FakeControlSocket()
        process = _FakeServerProcess()
        transport = _make_transport(
            adb_client,
            socket=socket,
            process=process,
            popen_calls=[],
        )
        transport.start()

        transport.close()
        transport.close()

        self.assertTrue(socket.closed)
        self.assertTrue(process.wait_calls)
        self.assertEqual(adb_client.removed_forwards, ["tcp:41234"])
        self.assertEqual(adb_client.forwards, {})
        self.assertIn(("shell", "rm", "-f", transport.remote_path), [tuple(c) for c in adb_client.calls])
        self.assertEqual(transport.cleanup_report["unresolved"], [])

    def test_close_reports_unresolved_remote_cleanup(self) -> None:
        """Surfaces a remote jar unlink that could not be proven."""

        adb_client = _FakeTransportAdbClient(shell_ok=False)
        transport = _make_transport(
            adb_client,
            socket=_FakeControlSocket(),
            process=_FakeServerProcess(),
            popen_calls=[],
        )
        transport.start()

        with self.assertRaises(DeviceConnectionError) as context:
            transport.close()

        self.assertIn("remote_file", transport.cleanup_report["unresolved"])
        self.assertEqual(context.exception.details["failure_phase"], "cleanup")
        self.assertEqual(context.exception.details["unresolved"], ["remote_file"])

    def test_start_enforces_one_total_setup_deadline_across_all_phases(self) -> None:
        """Fails setup once earlier blocking phases spend the whole startup budget."""

        clock = _SetupClock()
        adb_client = _FakeTransportAdbClient(on_call=lambda _arguments: clock.advance(6.0))
        transport = ScrcpyControlTransport(
            adb_client=adb_client,
            device_id=_DEVICE_ID,
            run_id="s1-abcdef123456",
            startup_timeout_seconds=5.0,
            connect_retry_seconds=0.0,
            connect_factory=lambda _address, timeout=None: _FakeControlSocket(),
            popen_factory=lambda _argv, **_kwargs: _FakeServerProcess(),
            sleep=lambda _: None,
            monotonic=clock,
            port_allocator=lambda: 41234,
        )

        with self.assertRaises(DeviceConnectionError) as context:
            transport.start()

        self.assertEqual(context.exception.details["failure_phase"], "setup")
        self.assertEqual(adb_client.calls[0][0], "push")
        self.assertFalse(
            any(call[:2] == ("forward", "--no-rebind") for call in adb_client.calls),
        )
        self.assertFalse(transport.ready)

    def test_connect_and_handshake_share_the_remaining_setup_budget(self) -> None:
        """Connection time reduces the handshake budget and late success is rejected."""

        for handshake_seconds in (0.5, 1.0):
            with self.subTest(handshake_seconds=handshake_seconds):
                clock = _SetupClock()
                timeouts: list[float | None] = []

                class _TimedSocket(_FakeControlSocket):
                    def settimeout(self, value: float | None) -> None:
                        timeouts.append(value)

                    def recv(self, size: int) -> bytes:
                        clock.advance(handshake_seconds)
                        return super().recv(size)

                socket = _TimedSocket()

                def connect(_address: object, timeout: float | None = None) -> _TimedSocket:
                    clock.advance(0.8)
                    return socket

                transport = ScrcpyControlTransport(
                    adb_client=_FakeTransportAdbClient(),
                    device_id=_DEVICE_ID,
                    run_id="s1-abcdef123456",
                    startup_timeout_seconds=1.5,
                    connect_factory=connect,
                    popen_factory=lambda _argv, **_kwargs: _FakeServerProcess(),
                    sleep=clock.advance,
                    monotonic=clock,
                    port_allocator=lambda: 41234,
                )
                if handshake_seconds == 0.5:
                    transport.start()
                    self.assertTrue(transport.ready)
                    transport.close()
                else:
                    with self.assertRaises(DeviceConnectionError):
                        transport.start()
                    self.assertFalse(transport.ready)
                self.assertAlmostEqual(timeouts[0], 0.7)
                self.assertTrue(socket.closed)

    def test_failed_setup_surfaces_unresolved_remote_cleanup(self) -> None:
        """A failed start retains its setup error and the failed jar cleanup."""

        transport = _make_transport(
            _FakeTransportAdbClient(publish_forward=False, shell_ok=False),
            socket=_FakeControlSocket(),
            process=_FakeServerProcess(),
            popen_calls=[],
        )
        with self.assertRaises(BaseExceptionGroup) as context:
            transport.start()
        errors = context.exception.exceptions
        self.assertEqual([error.details["failure_phase"] for error in errors], ["setup", "cleanup"])
        self.assertEqual(errors[1].details["unresolved"], ["remote_file"])
        self.assertFalse(transport.ready)

    def test_start_preserves_the_setup_error_when_cleanup_also_fails(self) -> None:
        """Groups the setup failure with an unexpected cleanup failure."""

        clock = _SetupClock()

        class _UncleanProcess(_FakeServerProcess):
            def wait(self, timeout: float | None = None) -> int:
                raise RuntimeError("process reaping exploded")

        def _refuse(_address: object, timeout: float | None = None) -> _FakeControlSocket:
            raise OSError("connection refused")

        transport = ScrcpyControlTransport(
            adb_client=_FakeTransportAdbClient(),
            device_id=_DEVICE_ID,
            run_id="s1-abcdef123456",
            startup_timeout_seconds=5.0,
            connect_retry_seconds=10.0,
            connect_factory=_refuse,
            popen_factory=lambda _argv, **_kwargs: _UncleanProcess(),
            sleep=clock.advance,
            monotonic=clock,
            port_allocator=lambda: 41234,
        )

        with self.assertRaises(BaseExceptionGroup) as context:
            transport.start()

        types = sorted(type(error).__name__ for error in context.exception.exceptions)
        self.assertEqual(types, ["DeviceConnectionError", "RuntimeError"])
        self.assertFalse(transport.ready)


if __name__ == "__main__":
    unittest.main()
