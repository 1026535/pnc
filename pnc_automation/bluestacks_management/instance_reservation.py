"""Agent-scoped long reservations over configured BlueStacks display names.

One atomic JSON snapshot under the shared host lease root holds every long
reservation record; a single short-held native metadata mutex serializes its
updates. Native per-display-name task locks in ``instance_lease`` remain the
physical execution exclusion. The private capability issued per claim is
authority: only its SHA-256 digest is persisted, and the capability never
appears in snapshots, status, logs, or errors.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pnc_automation.core.errors import ConfigurationError, InstanceReservedError
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes
from pnc_automation.core.infra.storage.native_locking import (
    ensure_lock_byte,
    lock_file_nonblocking,
    unlock_file,
)

RESERVATION_RECEIPT_ENV = "PNC_INSTANCE_RESERVATION_RECEIPT"
DEFAULT_RESERVATION_IDLE_SECONDS = 2.0 * 60.0 * 60.0
MAX_RESERVATION_LABEL_LENGTH = 128

_SNAPSHOT_NAME = "long-reservations.json"
_METADATA_MUTEX_NAME = "long-reservations.mutex"
_RECEIPTS_DIR_NAME = "long-reservation-receipts"
_RECORD_FIELDS = frozenset(
    {
        "scope_id",
        "owner_label",
        "generation",
        "capability_digest",
        "instances",
        "claimed_at",
        "expires_at",
        "pid",
    }
)
_RECEIPT_FIELDS = frozenset({"version", "scope_id", "generation", "capability"})


class InstanceReservationError(RuntimeError):
    """Rejects one reservation operation without exposing capability material."""


@dataclass(frozen=True, slots=True)
class InstanceReservation:
    """One authoritative all-or-none agent claim over normalized display names."""

    scope_id: str
    owner_label: str
    generation: str
    capability_digest: str
    instances: tuple[str, ...]
    claimed_at: float
    expires_at: float
    pid: int

    def __post_init__(self) -> None:
        """Validates the authoritative record strictly and fails closed."""

        require_safe_label(self.scope_id, "scope_id")
        require_safe_label(self.owner_label, "owner_label")
        if not isinstance(self.generation, str) or not self.generation:
            raise ValueError("Reservation generation must be a non-empty string.")
        if (
            not isinstance(self.capability_digest, str)
            or len(self.capability_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.capability_digest)
        ):
            raise ValueError("Reservation capability digest must be a lowercase SHA-256 hex string.")
        if (
            not isinstance(self.instances, tuple)
            or not self.instances
            or any(not isinstance(name, str) or not name.strip() for name in self.instances)
        ):
            raise ValueError("Reservation instances must be a non-empty tuple of display names.")
        if len(self.instance_keys) != len(self.instances):
            raise ValueError("Reservation instances cannot contain duplicate display names.")
        for label, value in (("claimed_at", self.claimed_at), ("expires_at", self.expires_at)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Reservation {label} must be finite and non-negative.")
        if self.expires_at <= self.claimed_at:
            raise ValueError("Reservation expiry must be after its claim time.")
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or self.pid <= 0:
            raise ValueError("Reservation pid must be a positive integer.")

    @property
    def instance_keys(self) -> frozenset[str]:
        """Returns the casefolded lease keys this claim covers."""

        return frozenset(name.strip().casefold() for name in self.instances)

    def is_active(self, now: float) -> bool:
        """Returns whether the claim still rejects new foreign work."""

        return now < self.expires_at

    def covers_any(self, lease_keys: Iterable[str]) -> bool:
        """Returns whether this claim intersects any normalized lease key."""

        return bool(self.instance_keys & frozenset(lease_keys))


@dataclass(frozen=True, slots=True)
class ReservationReceipt:
    """Private capability material issued once per claim and stored per file."""

    scope_id: str
    generation: str
    capability: str = field(repr=False)

    def __post_init__(self) -> None:
        """Rejects empty receipt authority fields."""

        for label, value in (
            ("scope_id", self.scope_id),
            ("generation", self.generation),
            ("capability", self.capability),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"Reservation receipt {label} must be a non-empty string.")

    @property
    def capability_digest(self) -> str:
        """Returns the SHA-256 digest persisted instead of the capability."""

        return hashlib.sha256(self.capability.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class InstanceReservationClaim:
    """Pairs one published reservation with its private receipt location."""

    reservation: InstanceReservation
    receipt_path: Path


@dataclass(frozen=True, slots=True)
class InstanceReservationStatus:
    """Secret-free status for one configured instance."""

    display_name: str
    reservation_state: str  # "none" | "active" | "expired"
    task_lock_state: str  # "idle" | "busy" | "unknown"
    claimable: bool
    scope_id: str | None = None
    owner_label: str | None = None
    expires_at: float | None = None


@dataclass(slots=True)
class InstanceReservationStore:
    """Persists and validates the authoritative reservation snapshot."""

    lease_root: Path
    now: Callable[[], float] = time.time
    mutex_timeout_seconds: float = 5.0
    mutex_poll_seconds: float = 0.01
    sleep: Callable[[float], None] = time.sleep

    @property
    def snapshot_path(self) -> Path:
        """Returns the single atomic snapshot path under the shared lease root."""

        return self.lease_root / _SNAPSHOT_NAME

    @property
    def mutex_path(self) -> Path:
        """Returns the short-held native metadata mutex path."""

        return self.lease_root / _METADATA_MUTEX_NAME

    @property
    def receipts_dir(self) -> Path:
        """Returns the directory holding private per-claim receipt files."""

        return self.lease_root / _RECEIPTS_DIR_NAME

    def load(self) -> tuple[InstanceReservation, ...]:
        """Reads the authoritative snapshot strictly and fails closed on malformed state."""

        try:
            payload = json.loads(self.snapshot_path.read_bytes())
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigurationError(
                "BlueStacks long-reservation state is malformed; refusing to rely on it.",
                state_file=self.snapshot_path.name,
            ) from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"version", "reservations"}
            or payload["version"] != 1
            or not isinstance(payload["reservations"], list)
        ):
            raise ConfigurationError(
                "BlueStacks long-reservation state schema is invalid; refusing to rely on it.",
                state_file=self.snapshot_path.name,
            )
        records: list[InstanceReservation] = []
        for item in payload["reservations"]:
            records.append(_parse_record(item, state_file=self.snapshot_path.name))
        covered: set[str] = set()
        for record in records:
            overlap = covered & record.instance_keys
            if overlap:
                raise ConfigurationError(
                    "BlueStacks long-reservation state contains overlapping claims.",
                    state_file=self.snapshot_path.name,
                )
            covered |= record.instance_keys
        return tuple(records)

    def save(self, records: tuple[InstanceReservation, ...]) -> None:
        """Atomically publishes the snapshot; the caller must hold ``metadata_lock``."""

        payload = json.dumps(
            {
                "version": 1,
                "reservations": [_serialize_record(record) for record in records],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        atomic_write_bytes(
            self.snapshot_path,
            payload.encode("utf-8"),
            prefix="reservations-",
            suffix=".tmp",
        )

    @contextmanager
    def metadata_lock(self) -> Iterator[None]:
        """Serializes snapshot reads and writes across processes for a bounded hold."""

        self.lease_root.mkdir(parents=True, exist_ok=True)
        self.mutex_path.touch(exist_ok=True)
        handle = self.mutex_path.open("r+b", buffering=0)
        try:
            ensure_lock_byte(handle)
        except BaseException:
            handle.close()
            raise
        deadline = time.monotonic() + self.mutex_timeout_seconds
        while True:
            try:
                lock_file_nonblocking(handle)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise InstanceReservationError(
                        "BlueStacks reservation metadata stayed busy beyond its bounded wait."
                    ) from error
                self.sleep(self.mutex_poll_seconds)
        try:
            yield
        finally:
            try:
                unlock_file(handle)
            finally:
                handle.close()

    def issue_receipt(self, *, scope_id: str) -> tuple[ReservationReceipt, Path]:
        """Writes one private receipt file before its claim is published."""

        receipt = ReservationReceipt(
            scope_id=scope_id,
            generation=uuid.uuid4().hex,
            capability=secrets.token_hex(32),
        )
        path = self.receipts_dir / f"{_safe_file_token(scope_id)}.{receipt.generation}.json"
        payload = json.dumps(
            {
                "version": 1,
                "scope_id": receipt.scope_id,
                "generation": receipt.generation,
                "capability": receipt.capability,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, payload.encode("utf-8"), prefix="receipt-", suffix=".tmp")
        return receipt, path

    def read_receipt(self, path: Path) -> ReservationReceipt:
        """Parses a caller-presented receipt strictly without logging its capability."""

        try:
            payload = json.loads(Path(path).read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstanceReservationError("The reservation receipt is unreadable or malformed.") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != _RECEIPT_FIELDS
            or payload["version"] != 1
        ):
            raise InstanceReservationError("The reservation receipt schema is invalid.")
        try:
            return ReservationReceipt(
                scope_id=payload["scope_id"],
                generation=payload["generation"],
                capability=payload["capability"],
            )
        except (TypeError, ValueError) as error:
            raise InstanceReservationError("The reservation receipt content is invalid.") from error

    def remove_receipt(self, path: Path) -> None:
        """Deletes a receipt inside the receipts directory on a best-effort basis."""

        try:
            resolved = Path(path).resolve()
            if resolved.parent != self.receipts_dir.resolve():
                return
            resolved.unlink(missing_ok=True)
        except OSError:
            return

    def publish_claim(
        self,
        *,
        receipt: ReservationReceipt,
        owner_label: str,
        instances: tuple[str, ...],
        duration_seconds: float,
    ) -> InstanceReservation:
        """Publishes one all-or-none claim under the metadata mutex.

        Expired records are pruned on publish. An active record covering the same
        scope or intersecting the bundle rejects the whole claim. The caller must
        already hold the native task locks proving every target is idle.
        """

        now = self.now()
        with self.metadata_lock():
            kept = [record for record in self.load() if record.is_active(now)]
            if any(record.scope_id == receipt.scope_id for record in kept):
                raise InstanceReservationError(
                    "Reservation scope is already claimed; release it before reclaiming."
                )
            instance_keys = frozenset(name.strip().casefold() for name in instances)
            conflicts = [record for record in kept if record.covers_any(instance_keys)]
            if conflicts:
                raise _foreign_reservation_error(conflicts)
            record = InstanceReservation(
                scope_id=receipt.scope_id,
                owner_label=owner_label,
                generation=receipt.generation,
                capability_digest=receipt.capability_digest,
                instances=instances,
                claimed_at=now,
                expires_at=now + duration_seconds,
                pid=os.getpid(),
            )
            kept.append(record)
            self.save(tuple(kept))
            return record

    def renew(
        self,
        receipt_path: Path,
        *,
        duration_seconds: float | None = None,
    ) -> InstanceReservation:
        """Extends the idle deadline for a live matching generation and capability."""

        duration = resolve_reservation_duration(duration_seconds)
        receipt = self.read_receipt(receipt_path)
        now = self.now()
        with self.metadata_lock():
            records = list(self.load())
            index, record = _find_scope_record(records, receipt.scope_id)
            if record is None:
                raise InstanceReservationError("No reservation exists for this scope.")
            _require_matching_capability(record, receipt)
            if not record.is_active(now):
                raise InstanceReservationError(
                    "The reservation expired; a late renewal cannot revive it."
                )
            renewed = replace(record, expires_at=now + duration)
            records[index] = renewed
            self.save(tuple(records))
            return renewed

    def release(self, receipt_path: Path) -> InstanceReservation | None:
        """Removes the caller's whole scope claim; repeated release is harmless.

        A stale generation or capability never deletes a replacement claim.
        """

        receipt = self.read_receipt(receipt_path)
        with self.metadata_lock():
            records = list(self.load())
            index, record = _find_scope_record(records, receipt.scope_id)
            if record is None:
                return None
            _require_matching_capability(record, receipt)
            records.pop(index)
            self.save(tuple(records))
            return record


def require_safe_label(value: str, field_name: str) -> str:
    """Validates a short printable diagnostic label such as scope or owner."""

    if not isinstance(value, str):
        raise ValueError(f"Reservation {field_name} must be a string.")
    label = value.strip()
    if not label or len(label) > MAX_RESERVATION_LABEL_LENGTH or not label.isprintable():
        raise ValueError(
            f"Reservation {field_name} must be printable and at most "
            f"{MAX_RESERVATION_LABEL_LENGTH} characters."
        )
    return label


def resolve_reservation_duration(duration_seconds: float | None) -> float:
    """Applies the default idle deadline and rejects unbounded or non-positive durations."""

    duration = DEFAULT_RESERVATION_IDLE_SECONDS if duration_seconds is None else duration_seconds
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("Reservation duration must be finite and positive.")
    return float(duration)


def _find_scope_record(
    records: list[InstanceReservation], scope_id: str
) -> tuple[int, InstanceReservation | None]:
    """Locates the unique record for one scope, if any."""

    for index, record in enumerate(records):
        if record.scope_id == scope_id:
            return index, record
    return -1, None


def _require_matching_capability(record: InstanceReservation, receipt: ReservationReceipt) -> None:
    """Rejects stale credentials that cannot mutate a different generation."""

    if (
        record.generation != receipt.generation
        or record.capability_digest != receipt.capability_digest
    ):
        raise InstanceReservationError(
            "The reservation credentials do not match the recorded claim."
        )


def _foreign_reservation_error(conflicts: list[InstanceReservation]) -> InstanceReservedError:
    """Builds a non-retryable conflict with safe diagnostics only."""

    first = conflicts[0]
    return InstanceReservedError(
        "BlueStacks instance is covered by an active long reservation.",
        scope_id=first.scope_id,
        owner_label=first.owner_label,
        expires_at=first.expires_at,
        reserved_instances=first.instances,
    )


def _safe_file_token(scope_id: str) -> str:
    """Reduces a scope label to a bounded filename-safe token."""

    token = "".join(
        character if character.isalnum() or character in "._-" else "_"
        for character in scope_id
    )[:40].strip("._")
    return token or "scope"


def _parse_record(item: object, *, state_file: str) -> InstanceReservation:
    """Strictly validates one persisted record and fails closed."""

    def fail() -> ConfigurationError:
        return ConfigurationError(
            "BlueStacks long-reservation record is malformed; refusing to rely on it.",
            state_file=state_file,
        )

    if not isinstance(item, dict) or set(item) != _RECORD_FIELDS:
        raise fail()
    try:
        instances = tuple(item["instances"])
        return InstanceReservation(
            scope_id=item["scope_id"],
            owner_label=item["owner_label"],
            generation=item["generation"],
            capability_digest=item["capability_digest"],
            instances=instances,
            claimed_at=item["claimed_at"],
            expires_at=item["expires_at"],
            pid=item["pid"],
        )
    except (TypeError, ValueError) as error:
        raise fail() from error


def _serialize_record(record: InstanceReservation) -> dict[str, Any]:
    """Serializes one record; the capability digest already replaced the secret."""

    return {
        "scope_id": record.scope_id,
        "owner_label": record.owner_label,
        "generation": record.generation,
        "capability_digest": record.capability_digest,
        "instances": list(record.instances),
        "claimed_at": record.claimed_at,
        "expires_at": record.expires_at,
        "pid": record.pid,
    }
