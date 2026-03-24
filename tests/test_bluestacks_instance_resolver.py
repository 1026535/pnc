"""BlueStacks runtime instance resolver tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.config.models import BlueStacksInstanceConfig
from pnc_automation.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
)
from pnc_automation.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class _FakeRunningInstanceSource:
    """Returns one deterministic set of running BlueStacks instances for resolver tests."""

    running_instances: tuple[BlueStacksRunningInstance, ...] = ()

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the seeded running-instance snapshot."""

        return self.running_instances


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

    def test_resolve_rejects_matching_display_name_when_instance_is_not_running(self) -> None:
        """Fails fast when the authored display name exists in host metadata but its instance key is inactive."""

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
                    running_instances=(_make_running_instance(instance_key="Nougat32_1"),),
                ),
            )

            with self.assertRaises(ConfigurationError):
                resolver.resolve(_make_instance_config(display_name="serious_stuff"))

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
