"""BlueStacks runtime instance resolver tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from pnc_automation.app.authoring.config.models import BlueStacksInstanceConfig
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
    _parse_running_instances_json,
)
from pnc_automation.core.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class _FakeRunningInstanceSource:
    """Returns one deterministic set of running BlueStacks instances for resolver tests."""

    running_instances: tuple[BlueStacksRunningInstance, ...] = ()

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the seeded running-instance snapshot."""

        return self.running_instances


class _FailingRunningInstanceSource:
    """Models Windows denying access to process command-line metadata."""

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Raises the canonical process-enumeration failure."""

        raise ConfigurationError("process metadata unavailable")


@dataclass(frozen=True, slots=True)
class _FakePortProbe:
    """Returns one deterministic ADB-port reachability result."""

    reachable: bool

    def is_reachable(self, host: str, port: int) -> bool:
        """Returns the seeded result after validating the requested endpoint."""

        if host != "127.0.0.1" or port <= 0:
            raise AssertionError("Resolver supplied an invalid local ADB endpoint.")
        return self.reachable


@dataclass(slots=True)
class _SequencedRunningInstanceSource:
    """Returns a deterministic sequence of running-instance snapshots."""

    snapshots: tuple[tuple[BlueStacksRunningInstance, ...], ...]
    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the next seeded snapshot, repeating the final value once exhausted."""

        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


@dataclass(slots=True)
class _FakeInstanceLauncher:
    """Records requested BlueStacks launches without starting local processes."""

    launched_instance_keys: list[str] = field(default_factory=list)

    def launch_instance(self, instance_key: str) -> None:
        """Records one requested instance startup."""

        self.launched_instance_keys.append(instance_key)


class BlueStacksInstanceResolverTests(unittest.TestCase):
    """Validates runtime BlueStacks port discovery from the authoritative host config."""

    def test_resolve_returns_runtime_device_id_for_matching_display_name(self) -> None:
        """Resolves the live ADB endpoint from the matching BlueStacks display name."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Nougat32_1.display_name="testing"
                bst.instance.Nougat32_1.status.adb_port="5566"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32"),),
                ),
            )

            instance = resolver.resolve(_make_instance_config(display_name="serious_stuff"))

            self.assertEqual(instance.id, "bs-main")
            self.assertEqual(instance.display_name, "serious_stuff")
            self.assertEqual(instance.device_id, "127.0.0.1:5555")
            self.assertEqual(instance.app_package, "com.global.tmslg")

    def test_resolve_rejects_missing_host_config_file(self) -> None:
        """Fails fast when the configured BlueStacks host metadata file does not exist."""

        resolver = BlueStacksInstanceResolver(config_path=Path("missing_bluestacks.conf").resolve())

        with self.assertRaises(ConfigurationError):
            resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_rejects_unknown_display_name(self) -> None:
        """Fails fast when the configured BlueStacks display name is absent from the host metadata."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="testing"
                bst.instance.Nougat32.status.adb_port="5566"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32"),),
                ),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_rejects_duplicate_display_names(self) -> None:
        """Fails fast when the host metadata exposes the same display name more than once."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Nougat32_1.display_name="serious_stuff"
                bst.instance.Nougat32_1.status.adb_port="5566"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_rejects_missing_runtime_port(self) -> None:
        """Fails fast when the matched BlueStacks instance does not expose a runtime ADB port."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32"),),
                ),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_rejects_non_numeric_runtime_port(self) -> None:
        """Fails fast when the matched BlueStacks instance exposes an invalid runtime port."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="not-a-port"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32"),),
                ),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_launches_matching_display_name_when_instance_is_not_running(self) -> None:
        """Starts the configured BlueStacks instance before resolving its ADB endpoint."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Nougat32_1.display_name="testing"
                bst.instance.Nougat32_1.status.adb_port="5566"
                """,
            )
            running_source = _SequencedRunningInstanceSource(
                snapshots=(
                    (_make_running_instance(instance_key="Nougat32_1"),),
                    (
                        _make_running_instance(instance_key="Nougat32_1"),
                        _make_running_instance(instance_key="Nougat32", process_id=102),
                    ),
                ),
            )
            launcher = _FakeInstanceLauncher()
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=running_source,
                instance_launcher=launcher,
                launch_poll_interval_seconds=0,
            )

            instance = resolver.resolve(_make_instance_config(display_name="serious_stuff"))

            self.assertEqual(instance.device_id, "127.0.0.1:5555")
            self.assertEqual(launcher.launched_instance_keys, ["Nougat32"])
            self.assertEqual(running_source.calls, 2)

    def test_resolve_rejects_matching_display_name_when_launch_does_not_start_instance(self) -> None:
        """Fails fast when BlueStacks launch returns but process metadata never exposes the target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Nougat32_1.display_name="testing"
                bst.instance.Nougat32_1.status.adb_port="5566"
                """,
            )
            launcher = _FakeInstanceLauncher()
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32_1"),),
                ),
                instance_launcher=launcher,
                launch_poll_attempts=2,
                launch_poll_interval_seconds=0,
            )

            with self.assertRaisesRegex(ConfigurationError, "did not start"):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

            self.assertEqual(launcher.launched_instance_keys, ["Nougat32"])

    def test_resolve_uses_unique_reachable_adb_port_when_process_metadata_is_denied(self) -> None:
        """Falls back to the authored local endpoint only for explicit process-enumeration failure."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Rvc64.display_name="157_farm"
                bst.instance.Rvc64.status.adb_port="5556"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FailingRunningInstanceSource(),
                port_probe=_FakePortProbe(reachable=True),
            )

            instance = resolver.resolve(_make_instance_config(display_name="157_farm"))

            self.assertEqual(instance.device_id, "127.0.0.1:5556")

    def test_resolve_preserves_process_error_when_fallback_port_is_unreachable(self) -> None:
        """Does not misclassify an inaccessible process snapshot as a running emulator."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Rvc64.display_name="157_farm"
                bst.instance.Rvc64.status.adb_port="5556"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FailingRunningInstanceSource(),
                port_probe=_FakePortProbe(reachable=False),
            )

            with self.assertRaisesRegex(ConfigurationError, "process metadata unavailable"):
                resolver.resolve(_make_instance_config(display_name="157_farm"))

    def test_resolve_rejects_shared_port_claimed_by_multiple_running_instances(self) -> None:
        """Fails fast when multiple active BlueStacks instances claim the same runtime ADB port."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Pie64.display_name="mega_old_acc"
                bst.instance.Pie64.status.adb_port="5555"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(
                        _make_running_instance(instance_key="Nougat32"),
                        _make_running_instance(instance_key="Pie64", process_id=102),
                    ),
                ),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

    def test_resolve_allows_stale_inactive_port_claim_when_target_instance_is_the_only_running_owner(self) -> None:
        """Ignores stale inactive metadata records that reuse the target port but are not currently running."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = _write_bluestacks_config(
                Path(temp_directory),
                """
                bst.instance.Nougat32.display_name="serious_stuff"
                bst.instance.Nougat32.status.adb_port="5555"
                bst.instance.Pie64.display_name="mega_old_acc"
                bst.instance.Pie64.status.adb_port="5555"
                """,
            )
            resolver = BlueStacksInstanceResolver(
                config_path=config_path,
                running_instance_source=_FakeRunningInstanceSource(
                    running_instances=(_make_running_instance(instance_key="Nougat32"),),
                ),
            )

            instance = resolver.resolve(_make_instance_config(display_name="serious_stuff"))

            self.assertEqual(instance.device_id, "127.0.0.1:5555")

    def test_parse_running_instances_json_accepts_one_single_process_object(self) -> None:
        """Accepts PowerShell's single-row JSON object shape instead of requiring an array wrapper."""

        running_instances = _parse_running_instances_json(
            '{"ProcessId":101,"CommandLine":"\\"C:\\\\Program Files\\\\BlueStacks_nxt\\\\HD-Player.exe\\" \\"--instance\\" \\"Nougat32_1\\""}'
        )

        self.assertEqual(
            running_instances,
            (_make_running_instance(instance_key="Nougat32_1"),),
        )


def _write_bluestacks_config(root: Path, content: str) -> Path:
    """Writes one deterministic BlueStacks host-config fixture and returns its path."""

    config_path = root / "bluestacks.conf"
    config_path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return config_path


def _make_instance_config(*, display_name: str) -> BlueStacksInstanceConfig:
    """Builds one authored BlueStacks instance config for resolver tests."""

    return BlueStacksInstanceConfig(
        id="bs-main",
        display_name=display_name,
        app_package="com.global.tmslg",
    )


def _make_running_instance(*, instance_key: str, process_id: int = 101) -> BlueStacksRunningInstance:
    """Builds one running BlueStacks process snapshot for resolver tests."""

    return BlueStacksRunningInstance(
        process_id=process_id,
        instance_key=instance_key,
        command_line=f'"C:\\Program Files\\BlueStacks_nxt\\HD-Player.exe" "--instance" "{instance_key}"',
    )


if __name__ == "__main__":
    unittest.main()
