"""Canonical BlueStacks runtime discovery based on authoritative host metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pnc_automation.config.models import BlueStacksInstanceConfig
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.errors import ConfigurationError

BLUESTACKS_ADB_HOST = "127.0.0.1"
_BLUESTACKS_INSTANCE_PREFIX = "bst.instance."


@dataclass(frozen=True, slots=True)
class BlueStacksRuntimeInstanceRecord:
    """Represents one BlueStacks host-config instance record relevant to runtime ADB resolution."""

    instance_key: str
    display_name: str | None = None
    adb_port: str | None = None

    def matches_display_name(self, display_name: str) -> bool:
        """Returns whether this runtime record exposes the requested BlueStacks display name."""

        return self.display_name == display_name

    def require_device_id(self, *, config_path: Path, adb_host: str = BLUESTACKS_ADB_HOST) -> str:
        """Builds the resolved ADB device id or fails fast when the runtime port is missing or invalid."""

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
        return f"{adb_host}:{port}"


@dataclass(frozen=True, slots=True)
class BlueStacksInstanceResolver:
    """Resolves authored BlueStacks display names to the live runtime ADB endpoint."""

    config_path: Path
    adb_host: str = BLUESTACKS_ADB_HOST

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

    def resolve(self, config: BlueStacksInstanceConfig) -> BlueStacksInstance:
        """Resolves one authored BlueStacks display name to a live runtime instance target."""

        matches = tuple(
            record
            for record in self.load_runtime_instances()
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

        return BlueStacksInstance.from_config(
            config,
            device_id=matches[0].require_device_id(config_path=self.config_path, adb_host=self.adb_host),
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
