"""Canonical BlueStacks runtime discovery based on authoritative host metadata."""

from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pnc_automation.config.models import BlueStacksInstanceConfig
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.errors import ConfigurationError

BLUESTACKS_ADB_HOST = "127.0.0.1"
_BLUESTACKS_INSTANCE_PREFIX = "bst.instance."
_HD_PLAYER_PROCESS_NAME = "HD-Player.exe"
_HD_PLAYER_INSTANCE_ARGUMENT = "--instance"
_LIST_HD_PLAYER_PROCESSES_SCRIPT = rf"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
@(
    Get-CimInstance Win32_Process -Filter "Name = '{_HD_PLAYER_PROCESS_NAME}'" |
    Select-Object ProcessId, CommandLine
) | ConvertTo-Json -Compress
""".strip()


class BlueStacksRunningInstanceSource(Protocol):
    """Lists the currently running BlueStacks player processes with their instance identities."""

    def list_running_instances(self) -> tuple["BlueStacksRunningInstance", ...]:
        """Returns all running BlueStacks instances visible to the current user."""


@dataclass(frozen=True, slots=True)
class BlueStacksRunningInstance:
    """Represents one currently running `HD-Player.exe --instance <instance_key>` process."""

    process_id: int
    instance_key: str
    command_line: str


@dataclass(slots=True)
class PowerShellBlueStacksRunningInstanceSource:
    """Queries Windows process metadata for the authoritative set of running BlueStacks instances."""

    powershell_path: str = "powershell"

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the running BlueStacks player processes discovered through PowerShell CIM."""

        completed = subprocess.run(
            [self.powershell_path, "-NoProfile", "-Command", _LIST_HD_PLAYER_PROCESSES_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode != 0:
            raise ConfigurationError(
                "Failed to enumerate running BlueStacks player processes.",
                command=(self.powershell_path, "-NoProfile", "-Command", _LIST_HD_PLAYER_PROCESSES_SCRIPT),
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
            )
        return _parse_running_instances_json(completed.stdout)


@dataclass(frozen=True, slots=True)
class BlueStacksRuntimeInstanceRecord:
    """Represents one BlueStacks host-config instance record relevant to runtime ADB resolution."""

    instance_key: str
    display_name: str | None = None
    adb_port: str | None = None

    def matches_display_name(self, display_name: str) -> bool:
        """Returns whether this runtime record exposes the requested BlueStacks display name."""

        return self.display_name == display_name

    def require_adb_port(self, *, config_path: Path) -> int:
        """Returns the validated runtime ADB port or fails fast when the host metadata is unusable."""

        if self.adb_port is None or self.adb_port.strip() == "":
            raise ConfigurationError(
                f"BlueStacks instance '{self.display_name}' does not expose status.adb_port in '{config_path}'.",
                display_name=self.display_name,
                instance_key=self.instance_key,
                bluestacks_config_path=str(config_path),
            )
        if not self.adb_port.isdecimal():
            raise ConfigurationError(
                f"BlueStacks instance '{self.display_name}' exposes a non-numeric status.adb_port.",
                display_name=self.display_name,
                instance_key=self.instance_key,
                adb_port=self.adb_port,
                bluestacks_config_path=str(config_path),
            )
        port = int(self.adb_port)
        if port < 1 or port > 65535:
            raise ConfigurationError(
                f"BlueStacks instance '{self.display_name}' exposes an out-of-range status.adb_port.",
                display_name=self.display_name,
                instance_key=self.instance_key,
                adb_port=self.adb_port,
                bluestacks_config_path=str(config_path),
            )
        return port

    def require_device_id(self, *, config_path: Path, adb_host: str = BLUESTACKS_ADB_HOST) -> str:
        """Builds the resolved ADB device id or fails fast when the runtime port is missing or invalid."""

        return f"{adb_host}:{self.require_adb_port(config_path=config_path)}"


@dataclass(frozen=True, slots=True)
class BlueStacksRuntimeCatalog:
    """Combines authored host metadata with the authoritative set of currently running BlueStacks instances."""

    records: tuple[BlueStacksRuntimeInstanceRecord, ...]
    running_instances: tuple[BlueStacksRunningInstance, ...]

    def find_records_by_display_name(self, display_name: str) -> tuple[BlueStacksRuntimeInstanceRecord, ...]:
        """Returns every host-config record authored with the requested BlueStacks display name."""

        return tuple(record for record in self.records if record.matches_display_name(display_name))

    def running_instance_keys(self) -> frozenset[str]:
        """Returns the canonical set of instance keys currently backed by live player processes."""

        return frozenset(instance.instance_key for instance in self.running_instances)

    def running_records(self) -> tuple[BlueStacksRuntimeInstanceRecord, ...]:
        """Returns the host-config records whose instance keys are currently running."""

        running_keys = self.running_instance_keys()
        return tuple(record for record in self.records if record.instance_key in running_keys)


@dataclass(frozen=True, slots=True)
class BlueStacksInstanceResolver:
    """Resolves authored BlueStacks display names to the live runtime ADB endpoint."""

    config_path: Path
    adb_host: str = BLUESTACKS_ADB_HOST
    running_instance_source: BlueStacksRunningInstanceSource = field(
        default_factory=PowerShellBlueStacksRunningInstanceSource,
    )

    def load_runtime_instances(self) -> tuple[BlueStacksRuntimeInstanceRecord, ...]:
        """Parses the BlueStacks host metadata file into typed runtime instance records."""

        if not self.config_path.is_file():
            raise ConfigurationError(
                f"BlueStacks host config '{self.config_path}' does not exist.",
                bluestacks_config_path=str(self.config_path),
            )

        raw_records: dict[str, dict[str, str]] = {}
        with self.config_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                parsed = _parse_key_value_line(raw_line, line_number=line_number, config_path=self.config_path)
                if parsed is None:
                    continue
                key, value = parsed
                if not key.startswith(_BLUESTACKS_INSTANCE_PREFIX):
                    continue
                instance_key, property_name = _split_instance_property(
                    key,
                    line_number=line_number,
                    config_path=self.config_path,
                )
                properties = raw_records.setdefault(instance_key, {})
                existing_value = properties.get(property_name)
                if existing_value is not None and existing_value != value:
                    raise ConfigurationError(
                        "BlueStacks host config contains conflicting duplicate instance properties.",
                        bluestacks_config_path=str(self.config_path),
                        line_number=line_number,
                        instance_key=instance_key,
                        property_name=property_name,
                        existing_value=existing_value,
                        duplicate_value=value,
                    )
                properties[property_name] = value

        return tuple(
            BlueStacksRuntimeInstanceRecord(
                instance_key=instance_key,
                display_name=properties.get("display_name"),
                adb_port=properties.get("status.adb_port"),
            )
            for instance_key, properties in raw_records.items()
        )

    def load_runtime_catalog(
        self,
        *,
        records: tuple[BlueStacksRuntimeInstanceRecord, ...] | None = None,
    ) -> BlueStacksRuntimeCatalog:
        """Loads the full runtime catalog including host metadata and the authoritative running-instance set."""

        return BlueStacksRuntimeCatalog(
            records=self.load_runtime_instances() if records is None else records,
            running_instances=self.running_instance_source.list_running_instances(),
        )

    def resolve(self, config: BlueStacksInstanceConfig) -> BlueStacksInstance:
        """Resolves one authored BlueStacks display name to a live runtime instance target."""

        records = self.load_runtime_instances()
        matches = tuple(
            record
            for record in records
            if record.matches_display_name(config.display_name)
        )
        if not matches:
            raise ConfigurationError(
                f"BlueStacks display_name '{config.display_name}' was not found in '{self.config_path}'.",
                display_name=config.display_name,
                instance_id=config.id,
                bluestacks_config_path=str(self.config_path),
            )
        if len(matches) > 1:
            raise ConfigurationError(
                f"BlueStacks display_name '{config.display_name}' is ambiguous in '{self.config_path}'.",
                display_name=config.display_name,
                instance_id=config.id,
                bluestacks_config_path=str(self.config_path),
                instance_keys=tuple(record.instance_key for record in matches),
            )
        catalog = self.load_runtime_catalog(records=records)
        match = matches[0]
        running_instance_keys = catalog.running_instance_keys()
        if match.instance_key not in running_instance_keys:
            raise ConfigurationError(
                f"BlueStacks display_name '{config.display_name}' maps to instance_key '{match.instance_key}', but that instance is not currently running.",
                display_name=config.display_name,
                instance_id=config.id,
                instance_key=match.instance_key,
                running_instance_keys=tuple(sorted(running_instance_keys)),
                bluestacks_config_path=str(self.config_path),
            )
        matched_port = match.require_adb_port(config_path=self.config_path)
        matching_running_port_claims = tuple(
            record
            for record in catalog.running_records()
            if record.require_adb_port(config_path=self.config_path) == matched_port
        )
        if len(matching_running_port_claims) > 1:
            raise ConfigurationError(
                f"BlueStacks runtime port '{matched_port}' is ambiguously claimed by multiple running instances.",
                display_name=config.display_name,
                instance_id=config.id,
                instance_key=match.instance_key,
                adb_port=str(matched_port),
                instance_keys=tuple(record.instance_key for record in matching_running_port_claims),
                bluestacks_config_path=str(self.config_path),
            )

        return BlueStacksInstance.from_config(
            config,
            device_id=match.require_device_id(config_path=self.config_path, adb_host=self.adb_host),
        )


def _parse_key_value_line(raw_line: str, *, line_number: int, config_path: Path) -> tuple[str, str] | None:
    """Parses one `key=value` BlueStacks host-config line and ignores blank lines."""

    line = raw_line.strip()
    if line == "":
        return None
    key, separator, raw_value = line.partition("=")
    if separator == "":
        raise ConfigurationError(
            "BlueStacks host config contains a malformed line without '='.",
            bluestacks_config_path=str(config_path),
            line_number=line_number,
            line=line,
        )
    normalized_key = key.strip()
    if normalized_key == "":
        raise ConfigurationError(
            "BlueStacks host config contains an empty property name.",
            bluestacks_config_path=str(config_path),
            line_number=line_number,
            line=line,
        )
    return normalized_key, _normalize_bluestacks_value(raw_value)


def _split_instance_property(key: str, *, line_number: int, config_path: Path) -> tuple[str, str]:
    """Splits one BlueStacks instance property key into the instance key and the property name."""

    suffix = key.removeprefix(_BLUESTACKS_INSTANCE_PREFIX)
    instance_key, separator, property_name = suffix.partition(".")
    if separator == "" or instance_key == "" or property_name == "":
        raise ConfigurationError(
            "BlueStacks host config contains an invalid instance property key.",
            bluestacks_config_path=str(config_path),
            line_number=line_number,
            key=key,
        )
    return instance_key, property_name


def _normalize_bluestacks_value(raw_value: str) -> str:
    """Normalizes one BlueStacks host-config value by trimming whitespace and outer quotes."""

    value = raw_value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_running_instances_json(raw_output: str) -> tuple[BlueStacksRunningInstance, ...]:
    """Parses the PowerShell JSON payload describing running `HD-Player.exe` processes."""

    payload = raw_output.strip()
    if payload == "":
        return ()
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            "BlueStacks process enumeration returned invalid JSON.",
            raw_output=raw_output,
        ) from error
    if isinstance(parsed, Mapping):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise ConfigurationError(
            "BlueStacks process enumeration did not return a JSON object or array.",
            raw_output=raw_output,
        )
    running_instances = tuple(
        _parse_running_instance(raw_instance, process_index=index)
        for index, raw_instance in enumerate(parsed, start=1)
    )
    _reject_duplicate_running_instance_keys(running_instances)
    return running_instances


def _parse_running_instance(raw_instance: object, *, process_index: int) -> BlueStacksRunningInstance:
    """Parses one PowerShell process row into a typed running-instance record."""

    if not isinstance(raw_instance, Mapping):
        raise ConfigurationError(
            "BlueStacks process enumeration returned a non-object row.",
            process_index=process_index,
            raw_instance=raw_instance,
        )
    process_id = raw_instance.get("ProcessId")
    command_line = raw_instance.get("CommandLine")
    if not isinstance(process_id, int):
        raise ConfigurationError(
            "BlueStacks process enumeration returned a process without an integer ProcessId.",
            process_index=process_index,
            raw_instance=raw_instance,
        )
    if not isinstance(command_line, str) or command_line.strip() == "":
        raise ConfigurationError(
            "BlueStacks process enumeration returned a process without a command line.",
            process_id=process_id,
            process_index=process_index,
            raw_instance=raw_instance,
        )
    return BlueStacksRunningInstance(
        process_id=process_id,
        instance_key=_parse_running_instance_key(command_line=command_line, process_id=process_id),
        command_line=command_line,
    )


def _parse_running_instance_key(*, command_line: str, process_id: int) -> str:
    """Extracts the authoritative BlueStacks `--instance <instance_key>` argument from one process command line."""

    try:
        tokens = shlex.split(command_line, posix=True)
    except ValueError as error:
        raise ConfigurationError(
            "Failed to parse a running BlueStacks process command line.",
            process_id=process_id,
            command_line=command_line,
        ) from error
    for index, token in enumerate(tokens[:-1]):
        if token != _HD_PLAYER_INSTANCE_ARGUMENT:
            continue
        instance_key = tokens[index + 1].strip()
        if instance_key == "":
            break
        return instance_key
    raise ConfigurationError(
        "Running BlueStacks process does not expose '--instance <instance_key>'.",
        process_id=process_id,
        command_line=command_line,
    )


def _reject_duplicate_running_instance_keys(running_instances: tuple[BlueStacksRunningInstance, ...]) -> None:
    """Rejects process snapshots that claim the same BlueStacks instance key more than once."""

    processes_by_instance_key: dict[str, list[int]] = {}
    for instance in running_instances:
        processes_by_instance_key.setdefault(instance.instance_key, []).append(instance.process_id)
    duplicates = {
        instance_key: tuple(process_ids)
        for instance_key, process_ids in processes_by_instance_key.items()
        if len(process_ids) > 1
    }
    if not duplicates:
        return
    raise ConfigurationError(
        "BlueStacks process enumeration returned duplicate running instance keys.",
        duplicate_processes=duplicates,
    )
