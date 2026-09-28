"""Reviewed scrcpy 4.0 control-only wheel transport.

One transport owns one bounded scrcpy-server lifecycle for a single session
epoch. Setup pushes the pinned ``scrcpy-server-v4.0`` asset to a unique remote
path, installs an explicit ``adb forward`` to the server's local abstract
socket, spawns ``app_process`` with control-only options, and awaits the
single dummy 0x00 handshake byte. Each send serializes exactly one upstream
``INJECT_SCROLL_EVENT`` control message producing an Android ``ACTION_SCROLL``
with ``AXIS_VSCROLL == +/-1.0``.

Pinned upstream semantics (tag v4.0):
  - control_msg.c: scroll message type 3, 21 bytes:
      u8 type | s32be x | s32be y | u16be w | u16be h |
      s16be hscroll | s16be vscroll | u32be buttons
    hscroll/vscroll are signed 16-bit fixed-point of (scroll / 16), so a pure
    +/-1 detent is wire +/-0x0800.
  - With video=false there is no display mapper: coordinates MUST be real
    on-device display pixels targeting display_id 0. The session re-reads and
    requires the live native display mapping before every send.
  - The server opens ``LocalServerSocket("scrcpy_<scid:%08x>")``, accepts the
    single control socket, and writes the dummy 0x00 byte.
  - argv[0] must equal the server version ("4.0"); the option pairs below
    disable every mirroring, clipboard, power, settings, and meta path while
    keeping cleanup=true so the server self-unlinks only its own jar.
"""

from __future__ import annotations

import hashlib
import re
import socket
import struct
import subprocess
import time
import zlib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable

from pnc_automation.core.errors import DeviceConnectionError
from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.lifecycle import close_preserving_error

SCRCPY_SERVER_VERSION = "4.0"
SCRCPY_SERVER_ASSET_NAME = "scrcpy-server-v4.0"
SCRCPY_SERVER_SIZE_BYTES = 732226
SCRCPY_SERVER_SHA256 = "84924bd564a1eb6089c872c7521f968058977f91f5ff02514a8c74aff3210f3a"
SCROLL_TRANSPORT_NAME = "scrcpy_control_v4"

_SCROLL_MESSAGE_TYPE = 0x03
_SCROLL_PACKET_SIZE = 21
_SCROLL_I16FP_ONE_DETENT = 0x0800  # (1/16) * 2^15; upstream binary.h sc_float_to_i16fp

_REMOTE_PATH_TEMPLATE = "/data/local/tmp/pnc-scrcpy-control-{run_id}.jar"
_SOCKET_NAME_TEMPLATE = "scrcpy_{scid:08x}"  # DesktopConnection.getSocketName
_SERVER_MAIN_CLASS = "com.genymobile.scrcpy.Server"
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,31}$")
_ASSET_PACKAGE = "pnc_automation.core.infra.emulator"

# Control-only server options: everything except the control channel is off.
# cleanup=true is deliberate: CleanUp.unlinkSelf() deletes only its own
# classpath jar (our unique remote path) and every restore action is disabled.
_SERVER_OPTION_PAIRS = (
    "log_level=warn",
    "tunnel_forward=true",
    "control=true",
    "video=false",
    "audio=false",
    "display_id=0",
    "show_touches=false",
    "stay_awake=false",
    "power_off_on_close=false",
    "clipboard_autosync=false",
    "cleanup=true",
    "power_on=false",
    "keep_active=false",
    "send_device_meta=false",
    "send_frame_meta=false",
    "send_stream_meta=false",
    "send_dummy_byte=true",
)

_PUSH_TIMEOUT_SECONDS = 30.0
_DISPLAY_MAPPING_TIMEOUT_SECONDS = 10.0

DEFAULT_STARTUP_TIMEOUT_SECONDS = 10.0
DEFAULT_SEND_TIMEOUT_SECONDS = 2.0
DEFAULT_CONNECT_RETRY_SECONDS = 0.1
DEFAULT_PROCESS_EXIT_TIMEOUT_SECONDS = 5.0
DEFAULT_PROCESS_TERMINATE_TIMEOUT_SECONDS = 2.0

_DISPLAY_REAL_PATTERN = re.compile(r"real (\d+) x (\d+)")
_DISPLAY_ROTATION_PATTERN = re.compile(r"rotation (\d)")


def choose_local_port() -> int:
    """Selects an unused local port; adb --no-rebind protects the handoff race.

    The configured BlueStacks adb 1.0.36 does not allocate/report tcp:0.
    This local socket performs no device access or game input.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return reservation.getsockname()[1]


def verify_server_asset(path: Path) -> None:
    """Verifies the pinned scrcpy-server-v4.0 asset before any remote setup."""

    try:
        data = path.read_bytes()
    except OSError as error:
        raise DeviceConnectionError(
            "Packaged scrcpy server asset could not be read.",
            failure_phase="setup",
            asset_path=str(path),
        ) from error
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != SCRCPY_SERVER_SIZE_BYTES or digest != SCRCPY_SERVER_SHA256:
        raise DeviceConnectionError(
            "scrcpy server asset failed pinned verification.",
            failure_phase="setup",
            asset_path=str(path),
            size=len(data),
            expected_size=SCRCPY_SERVER_SIZE_BYTES,
            sha256=digest,
            expected_sha256=SCRCPY_SERVER_SHA256,
        )


def _require_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, got {value!r}.")
    return value


def build_scroll_packet(*, x: int, y: int, width: int, height: int, vscroll_detent: int) -> bytes:
    """Serializes one upstream-exact INJECT_SCROLL_EVENT control message.

    Only a pure vertical single-detent wheel is supported: hscroll and buttons
    are always zero and vscroll_detent must be exactly +1 or -1. Invalid inputs
    are rejected, never clipped into range.
    """

    width = _require_int("width", width)
    height = _require_int("height", height)
    x = _require_int("x", x)
    y = _require_int("y", y)
    vscroll_detent = _require_int("vscroll_detent", vscroll_detent)
    if not 1 <= width <= 0xFFFF or not 1 <= height <= 0xFFFF:
        raise ValueError(f"Display dimensions must be within 1..65535, got {width}x{height}.")
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError(f"Cursor ({x}, {y}) is outside display {width}x{height}.")
    if vscroll_detent not in (-1, 1):
        raise ValueError(f"vscroll_detent must be exactly +1 or -1, got {vscroll_detent!r}.")
    packet = struct.pack(
        ">BiiHHhhI",
        _SCROLL_MESSAGE_TYPE,
        x,
        y,
        width,
        height,
        0,
        vscroll_detent * _SCROLL_I16FP_ONE_DETENT,
        0,
    )
    assert len(packet) == _SCROLL_PACKET_SIZE
    return packet


def verify_native_display_mapping(
    *,
    frame_size: tuple[int, int],
    dumpsys_output: str,
    device_id: str,
) -> None:
    """Requires display-0 native geometry to equal the authorized frame's pixel grid.

    With video=false the control channel has no display mapper: a nonzero
    rotation or a native size different from the captured frame would silently
    misplace injected wheel coordinates, so both are rejected outright.
    """

    real = _DISPLAY_REAL_PATTERN.search(dumpsys_output)
    rotation = _DISPLAY_ROTATION_PATTERN.search(dumpsys_output)
    if real is None:
        raise DeviceConnectionError(
            "Could not resolve the native display geometry for wheel dispatch.",
            device_id=device_id,
            failure_phase="mapping",
        )
    if rotation is not None and rotation.group(1) != "0":
        raise DeviceConnectionError(
            "Native display rotation is nonzero; wheel pixels would not map 1:1.",
            device_id=device_id,
            failure_phase="mapping",
            rotation=rotation.group(1),
        )
    native_size = (int(real.group(1)), int(real.group(2)))
    if native_size != tuple(frame_size):
        raise DeviceConnectionError(
            "Native display size does not equal the authorized frame size.",
            device_id=device_id,
            failure_phase="mapping",
            native_width=native_size[0],
            native_height=native_size[1],
            frame_width=frame_size[0],
            frame_height=frame_size[1],
        )


def require_native_display_mapping(
    adb_client: AdbClient,
    *,
    device_id: str,
    frame_size: tuple[int, int],
) -> None:
    """Reads and requires the live display-0 mapping before one wheel dispatch."""

    result = adb_client.shell(
        device_id,
        "dumpsys",
        "display",
        timeout_seconds=_DISPLAY_MAPPING_TIMEOUT_SECONDS,
    )
    if not result.succeeded:
        raise DeviceConnectionError(
            "Failed to read the native display mapping before wheel dispatch.",
            device_id=device_id,
            stderr=result.stderr_text,
            failure_phase="mapping",
        )
    verify_native_display_mapping(
        frame_size=frame_size,
        dumpsys_output=result.stdout_text,
        device_id=device_id,
    )


@dataclass(slots=True)
class ScrcpyControlTransport:
    """Owns one bounded control-only scrcpy-server lifecycle for one session epoch.

    The owning BlueStacksSession supplies its canonical AdbClient and device id
    after the lease and input role are already active; this transport never
    creates sessions, leases, devices, or ambient adb state. ``close()`` is
    idempotent and never raises: unresolved remote cleanup is reported through
    ``cleanup_report``.
    """

    adb_client: AdbClient
    device_id: str
    run_id: str
    server_asset: Path | None = None
    startup_timeout_seconds: float = DEFAULT_STARTUP_TIMEOUT_SECONDS
    send_timeout_seconds: float = DEFAULT_SEND_TIMEOUT_SECONDS
    connect_retry_seconds: float = DEFAULT_CONNECT_RETRY_SECONDS
    process_exit_timeout_seconds: float = DEFAULT_PROCESS_EXIT_TIMEOUT_SECONDS
    process_terminate_timeout_seconds: float = DEFAULT_PROCESS_TERMINATE_TIMEOUT_SECONDS
    connect_factory: Callable[..., socket.socket] = socket.create_connection
    popen_factory: Callable[..., subprocess.Popen] = subprocess.Popen
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    port_allocator: Callable[[], int] = choose_local_port

    _remote_path: str = field(default="", init=False)
    _socket_name: str = field(default="", init=False)
    _scid: int = field(default=0, init=False)
    _local_port: int | None = field(default=None, init=False)
    _process: subprocess.Popen | None = field(default=None, init=False)
    _control_socket: socket.socket | None = field(default=None, init=False)
    _closed: bool = field(default=False, init=False)
    cleanup_report: dict[str, object] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        """Derives the unique remote path, socket name, and SCID for this run."""

        if not _RUN_ID_PATTERN.match(self.run_id):
            raise ValueError(f"run_id must match {_RUN_ID_PATTERN.pattern}, got {self.run_id!r}.")
        self._scid = zlib.crc32(self.run_id.encode("utf-8")) & 0x7FFFFFFF
        self._remote_path = _REMOTE_PATH_TEMPLATE.format(run_id=self.run_id)
        self._socket_name = _SOCKET_NAME_TEMPLATE.format(scid=self._scid)

    @property
    def ready(self) -> bool:
        """Returns whether the control socket completed its handshake."""

        return self._control_socket is not None

    @property
    def remote_path(self) -> str:
        """Returns the unique remote jar path this transport owns."""

        return self._remote_path

    @property
    def socket_name(self) -> str:
        """Returns the server local abstract socket name derived from the SCID."""

        return self._socket_name

    @property
    def local_port(self) -> int | None:
        """Returns the owned local forward port, or None when none is installed."""

        return self._local_port

    def _adb(self, *arguments: str, timeout_seconds: float | None = 10):
        """Runs one bounded device-scoped adb command through the session client."""

        return self.adb_client.run_device(
            self.device_id,
            *arguments,
            timeout_seconds=timeout_seconds,
        )

    def start(self) -> None:
        """Pushes the pinned asset, installs the forward, and awaits the handshake.

        Preparation is idempotent: a ready transport is reused, and a failed
        start performs the same owned cleanup as ``close()`` before raising.
        Every setup phase shares one monotonic deadline, so blocking work early
        in the sequence consumes the same ``startup_timeout_seconds`` budget as
        the connection and handshake wait.
        """

        if self._control_socket is not None:
            return
        self._closed = False
        deadline = self.monotonic() + self.startup_timeout_seconds
        try:
            if self.server_asset is not None:
                self._start_with_asset(self.server_asset, deadline)
            else:
                with resources.as_file(
                    resources.files(_ASSET_PACKAGE).joinpath("data", SCRCPY_SERVER_ASSET_NAME)
                ) as asset_path:
                    self._start_with_asset(Path(asset_path), deadline)
        except BaseException as error:
            close_preserving_error(
                self.close,
                error,
                message="scrcpy control transport setup and cleanup both failed.",
            )
            raise

    def _setup_remaining_seconds(self, deadline: float) -> float:
        """Returns the remaining whole-setup budget, failing once it is spent."""

        remaining = deadline - self.monotonic()
        if remaining <= 0:
            raise DeviceConnectionError(
                "scrcpy control transport setup exceeded its bounded startup deadline.",
                device_id=self.device_id,
                failure_phase="setup",
                startup_timeout_seconds=self.startup_timeout_seconds,
            )
        return remaining

    def _start_with_asset(self, asset_path: Path, deadline: float) -> None:
        """Runs the setup sequence against one asset inside the shared deadline."""

        verify_server_asset(asset_path)
        self._push(asset_path, deadline)
        self._forward(deadline)
        self._setup_remaining_seconds(deadline)
        self._start_server()
        self._await_control_socket(deadline)

    def _push(self, asset_path: Path, deadline: float) -> None:
        """Pushes the verified jar to this transport's unique remote path."""

        result = self._adb(
            "push",
            str(asset_path),
            self._remote_path,
            timeout_seconds=min(_PUSH_TIMEOUT_SECONDS, self._setup_remaining_seconds(deadline)),
        )
        if not result.succeeded:
            raise DeviceConnectionError(
                "adb push of the scrcpy server failed.",
                device_id=self.device_id,
                stderr=result.stderr_text,
                failure_phase="setup",
            )

    def _forward(self, deadline: float) -> None:
        """Installs one explicit forward and proves ownership by exact listing."""

        port = _require_int("local_port", self.port_allocator())
        if not 1 <= port <= 65535:
            raise ValueError("local_port must be within 1..65535.")
        # Remember the attempted port even on an uncertain command result.
        # Cleanup removes only a listing with our exact device and socket name.
        self._local_port = port
        result = self._adb(
            "forward",
            "--no-rebind",
            f"tcp:{port}",
            f"localabstract:{self._socket_name}",
            timeout_seconds=self._setup_remaining_seconds(deadline),
        )
        if not result.succeeded:
            raise DeviceConnectionError(
                "adb explicit forward for the scrcpy control socket failed.",
                device_id=self.device_id,
                stderr=result.stderr_text,
                failure_phase="setup",
            )
        # Legacy adb succeeds with empty stdout. Exact listing, not stdout or
        # exit code alone, proves which resource this transport owns.
        if f"tcp:{port}" not in self._owned_forward_endpoints(
            timeout_seconds=self._setup_remaining_seconds(deadline)
        ):
            raise DeviceConnectionError(
                "adb did not publish the exact requested device/port/socket forward.",
                device_id=self.device_id,
                failure_phase="setup",
            )

    def _owned_forward_endpoints(self, *, timeout_seconds: float | None = 10) -> tuple[str, ...]:
        """Finds only forwards for this session device and unique remote socket."""

        result = self._adb("forward", "--list", timeout_seconds=timeout_seconds)
        if not result.succeeded:
            raise DeviceConnectionError(
                "Could not verify owned adb forwards.",
                device_id=self.device_id,
                stderr=result.stderr_text,
                failure_phase="setup",
            )
        endpoints = []
        for line in result.stdout_text.splitlines():
            fields = line.split()
            if (
                len(fields) == 3
                and fields[0] == self.device_id
                and fields[2] == f"localabstract:{self._socket_name}"
                and fields[1].startswith("tcp:")
                and fields[1][4:].isdigit()
            ):
                endpoints.append(fields[1])
        return tuple(endpoints)

    def _server_command(self) -> str:
        """Builds the control-only app_process command with the derived SCID."""

        options = " ".join(_SERVER_OPTION_PAIRS + (f"scid={self._scid:x}",))
        return (
            f"CLASSPATH={self._remote_path} app_process / "
            f"{_SERVER_MAIN_CLASS} {SCRCPY_SERVER_VERSION} {options}"
        )

    def _start_server(self) -> None:
        """Spawns the one owned foreground adb shell app_process."""

        argv = [
            self.adb_client.adb_path,
            "-s",
            self.device_id,
            "shell",
            self._server_command(),
        ]
        self._process = self.popen_factory(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def _await_control_socket(self, deadline: float) -> None:
        """Waits for the control socket inside the shared setup deadline."""

        assert self._process is not None and self._local_port is not None
        last_error: object = None
        while self.monotonic() < deadline:
            returncode = self._process.poll()
            if returncode is not None:
                stderr = (
                    self._process.stderr.read().decode("utf-8", errors="replace")
                    if self._process.stderr
                    else ""
                )
                raise DeviceConnectionError(
                    "scrcpy server exited during control transport startup.",
                    device_id=self.device_id,
                    returncode=returncode,
                    stderr=stderr.strip(),
                    failure_phase="setup",
                )
            candidate = None
            try:
                candidate = self.connect_factory(
                    ("127.0.0.1", self._local_port),
                    timeout=min(1.0, self._setup_remaining_seconds(deadline)),
                )
                candidate.settimeout(min(1.0, self._setup_remaining_seconds(deadline)))
                byte = candidate.recv(1)
                self._setup_remaining_seconds(deadline)
                if byte == b"\x00":
                    candidate.settimeout(self.send_timeout_seconds)
                    self._control_socket = candidate
                    return
                last_error = f"unexpected handshake byte {byte!r}"
            except OSError as exc:
                last_error = exc
            finally:
                if candidate is not None and candidate is not self._control_socket:
                    try:
                        candidate.close()
                    except OSError:
                        pass
            self.sleep(min(self.connect_retry_seconds, max(0.0, deadline - self.monotonic())))
        raise DeviceConnectionError(
            "Timed out waiting for the scrcpy control socket dummy byte.",
            device_id=self.device_id,
            last_error=repr(last_error),
            failure_phase="setup",
        )

    def send_packet(self, packet: bytes) -> None:
        """Sends one prebuilt scroll control packet through the ready socket.

        Packet construction and validation happen in ``build_scroll_packet``
        before the session's dispatch boundary; this send performs no retry on
        an uncertain outcome.
        """

        if self._control_socket is None:
            raise DeviceConnectionError(
                "scrcpy control socket is not ready; the transport must be started first.",
                device_id=self.device_id,
                failure_phase="send",
            )
        if len(packet) != _SCROLL_PACKET_SIZE:
            raise ValueError(f"A scroll control packet must be exactly {_SCROLL_PACKET_SIZE} bytes.")
        try:
            self._control_socket.sendall(packet)
        except OSError as error:
            raise DeviceConnectionError(
                "Failed to send the wheel control packet.",
                device_id=self.device_id,
                failure_phase="send",
            ) from error

    def close(self) -> None:
        """Closes owned resources and surfaces unresolved cleanup at every caller."""

        if self._closed:
            return
        self._closed = True
        unresolved: list[str] = []

        if self._control_socket is not None:
            try:
                self._control_socket.close()
            except OSError:
                pass
            self._control_socket = None

        if self._process is not None:
            try:
                self._process.wait(timeout=self.process_exit_timeout_seconds)
            except subprocess.TimeoutExpired:
                try:
                    self._process.terminate()  # only the process this transport owns
                except OSError:
                    pass
                try:
                    self._process.wait(timeout=self.process_terminate_timeout_seconds)
                except subprocess.TimeoutExpired:
                    unresolved.append("server_process")
            self._process = None

        if self._local_port is not None:
            try:
                for endpoint in self._owned_forward_endpoints():
                    self._adb("forward", "--remove", endpoint)
                if self._owned_forward_endpoints():
                    unresolved.append("adb_forward")
            except Exception:
                unresolved.append("adb_forward")
            self._local_port = None

        try:
            result = self._adb("shell", "rm", "-f", self._remote_path)
            if not result.succeeded:
                unresolved.append("remote_file")
        except Exception:
            unresolved.append("remote_file")

        self.cleanup_report = {
            "remote_path": self._remote_path,
            "socket_name": self._socket_name,
            "unresolved": unresolved,
        }
        if unresolved:
            raise DeviceConnectionError(
                "scrcpy control transport cleanup left unresolved remote resources.",
                device_id=self.device_id,
                failure_phase="cleanup",
                transport=SCROLL_TRANSPORT_NAME,
                **self.cleanup_report,
            )
