"""Durable, bounded state for monitor-owned BlueStacks recovery intent."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pnc_automation.core.errors import ConfigurationError

_RECOVERY_FIELDS = frozenset(
    {
        "display_name",
        "instance_key",
        "metadata_path",
        "original_pid",
        "stop_intent",
        "stop_confirmed",
        "launch_attempts",
        "failure_phase",
        "next_retry_at",
    }
)
_FAILURE_PHASES = frozenset(
    {
        "state_write",
        "stop",
        "stop_wait",
        "stop_revalidation",
        "launch",
        "launch_wait",
        "role_revoked",
        "identity_changed",
        "launch_budget_exhausted",
        "recovery",
        "policy_disabled",
    }
)
MAX_PERSISTED_LAUNCH_ATTEMPTS = 9


@dataclass(frozen=True, slots=True)
class InstanceRecoveryRecord:
    """Records one monitor-owned stop/recovery intent without raw process errors."""

    display_name: str
    instance_key: str
    metadata_path: str
    original_pid: int
    stop_intent: bool = False
    stop_confirmed: bool = False
    launch_attempts: int = 0
    failure_phase: str | None = None
    next_retry_at: float | None = None

    def __post_init__(self) -> None:
        """Rejects malformed or unbounded persisted recovery state."""

        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.display_name, self.instance_key, self.metadata_path)
        ):
            raise ValueError("Recovery identity fields must be non-empty.")
        if isinstance(self.original_pid, bool) or not isinstance(self.original_pid, int) or self.original_pid <= 0:
            raise ValueError("Recovery original_pid must be positive.")
        if (
            isinstance(self.launch_attempts, bool)
            or not isinstance(self.launch_attempts, int)
            or not 0 <= self.launch_attempts <= MAX_PERSISTED_LAUNCH_ATTEMPTS
        ):
            raise ValueError("Recovery launch_attempts is outside the bounded range.")
        if not isinstance(self.stop_intent, bool) or not isinstance(self.stop_confirmed, bool):
            raise ValueError("Recovery stop state must be boolean.")
        if self.stop_confirmed and not self.stop_intent:
            raise ValueError("Confirmed stop requires a recorded intent.")
        if self.launch_attempts and not self.stop_confirmed:
            raise ValueError("Launch attempts require a confirmed stop.")
        if self.failure_phase is not None and self.failure_phase not in _FAILURE_PHASES:
            raise ValueError("Recovery failure phase is not recognized.")
        if self.next_retry_at is not None and (
            isinstance(self.next_retry_at, bool)
            or not isinstance(self.next_retry_at, (int, float))
            or not math.isfinite(float(self.next_retry_at))
            or self.next_retry_at < 0
        ):
            raise ValueError("Recovery next_retry_at must be a finite non-negative number.")

    def with_failure(self, *, phase: str, next_retry_at: float | None) -> "InstanceRecoveryRecord":
        """Returns this record with one sanitized failure phase and retry time."""

        return replace(self, failure_phase=phase, next_retry_at=next_retry_at)


@dataclass(frozen=True, slots=True)
class RecoveryStateStore:
    """Persists monitor recovery records atomically under one host state root."""

    root: Path

    def load_all(self) -> tuple[InstanceRecoveryRecord, ...]:
        """Loads every strict recovery record, failing closed on malformed state."""

        if not self.root.exists():
            return ()
        records: list[InstanceRecoveryRecord] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                record = self._load_path(path)
            except FileNotFoundError:
                # Another leased monitor may have completed this record.
                continue
            if path != self.path_for(record):
                raise ConfigurationError("BlueStacks recovery state identity is invalid.")
            records.append(record)
        return tuple(records)

    def save(self, record: InstanceRecoveryRecord) -> None:
        """Writes one record through flush, fsync, and atomic replacement."""

        destination = self.path_for(record)
        payload = json.dumps(_serialize_record(record), sort_keys=True, separators=(",", ":"))
        self._atomic_write(destination, payload)

    @staticmethod
    def _atomic_write(destination: Path, payload: str) -> None:
        """Commits state while its instance lease serializes all writers."""

        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ConfigurationError(
                "BlueStacks recovery state could not be persisted.",
                failure_phase="state_write",
            ) from error

    def remove(self, record: InstanceRecoveryRecord) -> None:
        """Removes one completed record without exposing file contents."""

        try:
            self.path_for(record).unlink(missing_ok=True)
        except OSError as error:
            raise ConfigurationError(
                "BlueStacks recovery state could not be cleared.",
                failure_phase="state_write",
            ) from error

    def path_for(self, record: InstanceRecoveryRecord) -> Path:
        """Returns the stable non-secret file path for one instance identity."""

        key = f"{record.display_name.casefold()}\0{record.instance_key}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def load_cooldown(self, display_name: str) -> float | None:
        """Loads the last successful recovery's wall-clock timestamp."""

        path = self._cooldown_path(display_name)
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError("BlueStacks recovery cooldown state is malformed.") from error
        try:
            value = _require_optional_number(payload)
            if value is None:
                raise ValueError("Missing cooldown timestamp")
            return value
        except ValueError as error:
            raise ConfigurationError("BlueStacks recovery cooldown state fields are invalid.") from error

    def save_cooldown(self, display_name: str, timestamp: float) -> None:
        """Commits one instance's cooldown without racing other instances' writers."""

        value = _require_optional_number(timestamp)
        if value is None:
            raise ValueError("Missing cooldown timestamp")
        self._atomic_write(self._cooldown_path(display_name), json.dumps(value))

    def _cooldown_path(self, display_name: str) -> Path:
        """Keeps cooldown files separate from pending recovery records."""

        digest = hashlib.sha256(display_name.strip().casefold().encode("utf-8")).hexdigest()
        return self.root / "cooldowns" / f"{digest}.json"

    def _load_path(self, path: Path) -> InstanceRecoveryRecord:
        """Parses one record with an allow-list schema and no raw-value echo."""

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError("BlueStacks recovery state is malformed.", state_file=path.name) from error
        if not isinstance(payload, dict) or set(payload) != _RECOVERY_FIELDS:
            raise ConfigurationError("BlueStacks recovery state schema is invalid.", state_file=path.name)
        try:
            return InstanceRecoveryRecord(
                display_name=_require_string(payload["display_name"]),
                instance_key=_require_string(payload["instance_key"]),
                metadata_path=_require_string(payload["metadata_path"]),
                original_pid=_require_positive_int(payload["original_pid"]),
                stop_intent=_require_bool(payload["stop_intent"]),
                stop_confirmed=_require_bool(payload["stop_confirmed"]),
                launch_attempts=_require_nonnegative_int(payload["launch_attempts"]),
                failure_phase=_require_optional_phase(payload["failure_phase"]),
                next_retry_at=_require_optional_number(payload["next_retry_at"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ConfigurationError("BlueStacks recovery state fields are invalid.", state_file=path.name) from error


def _serialize_record(record: InstanceRecoveryRecord) -> dict[str, object]:
    """Builds the strict persisted schema."""

    return {
        "display_name": record.display_name,
        "instance_key": record.instance_key,
        "metadata_path": record.metadata_path,
        "original_pid": record.original_pid,
        "stop_intent": record.stop_intent,
        "stop_confirmed": record.stop_confirmed,
        "launch_attempts": record.launch_attempts,
        "failure_phase": record.failure_phase,
        "next_retry_at": record.next_retry_at,
    }


def _require_string(value: Any) -> str:
    """Validates one persisted string without echoing it."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected string")
    return value


def _require_bool(value: Any) -> bool:
    """Validates one persisted boolean."""

    if not isinstance(value, bool):
        raise ValueError("expected bool")
    return value


def _require_positive_int(value: Any) -> int:
    """Validates one persisted positive integer."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("expected positive int")
    return value


def _require_nonnegative_int(value: Any) -> int:
    """Validates one persisted bounded non-negative integer."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected non-negative int")
    return value


def _require_optional_phase(value: Any) -> str | None:
    """Validates one allow-listed persisted failure phase."""

    if value is None:
        return None
    if not isinstance(value, str) or value not in _FAILURE_PHASES:
        raise ValueError("expected known failure phase")
    return value


def _require_optional_number(value: Any) -> float | None:
    """Validates one persisted retry timestamp."""

    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("expected finite number")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError("expected finite number")
    return numeric
