"""Typed chat append transaction records and strict byte-level codecs."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pnc_automation.app.pnc.persistence.chat_archive_state import (
    ChatArchiveSchemaError,
    canonical_json_bytes,
    decode_json_object,
    validate_state_document,
)
from pnc_automation.core.infra.storage.atomic_file import atomic_write_bytes


MAX_PENDING_BYTES = 16 * 1024 * 1024
MAX_APPEND_BYTES = 12 * 1024 * 1024
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ChatArchiveConsistencyError(RuntimeError):
    """Raised when physical archive bytes cannot be classified safely."""


class ChatArchivePublicationError(OSError):
    """Raised when a chat transaction cannot publish one required durability stage."""


@dataclass(frozen=True, slots=True)
class ChatStreamIdentity:
    """Stores the path identity that owns one day-independent chat stream."""

    account_segment: str
    castle_segment: str
    channel: str

    def __post_init__(self) -> None:
        """Normalizes physical path segments so case aliases share one identity."""

        for name, value in (
            ("account_segment", self.account_segment),
            ("castle_segment", self.castle_segment),
            ("channel", self.channel),
        ):
            if not isinstance(value, str) or not value or value in {".", ".."} or any(separator in value for separator in ("/", "\\")):
                raise ChatArchiveSchemaError(f"Chat stream identity field '{name}' is unsafe.")
        object.__setattr__(self, "account_segment", os.path.normcase(self.account_segment))
        object.__setattr__(self, "castle_segment", os.path.normcase(self.castle_segment))
        object.__setattr__(self, "channel", os.path.normcase(self.channel))

    def as_document(self) -> dict[str, str]:
        """Returns the strict JSON identity document."""

        return {
            "account_segment": self.account_segment,
            "castle_segment": self.castle_segment,
            "channel": self.channel,
        }


@dataclass(frozen=True, slots=True)
class PendingChatTransaction:
    """Describes one immutable, replayable transcript append and next state."""

    operation_id: str
    stream_identity: ChatStreamIdentity
    archive_day: str
    captured_at: datetime
    transcript_existed: bool
    previous_offset: int
    prefix_sha256: str
    append_bytes: bytes
    prior_target_state_sha256: str | None
    next_state: dict[str, Any]
    next_state_sha256: str
    screenshot_relative_path: str
    screenshot_length: int
    screenshot_sha256: str

    @property
    def append_length(self) -> int:
        """Returns the exact number of bytes recorded for replay."""

        return len(self.append_bytes)

    @property
    def append_sha256(self) -> str:
        """Returns the digest of the exact append payload."""

        return hashlib.sha256(self.append_bytes).hexdigest()

    def to_document(self) -> dict[str, Any]:
        """Serializes the record including its self-checking record digest."""

        document: dict[str, Any] = {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "stream_identity": self.stream_identity.as_document(),
            "archive_day": self.archive_day,
            "captured_at": self.captured_at.isoformat(),
            "transcript_existed": self.transcript_existed,
            "previous_offset": self.previous_offset,
            "prefix_sha256": self.prefix_sha256,
            "append_bytes_base64": base64.b64encode(self.append_bytes).decode("ascii"),
            "append_length": self.append_length,
            "append_sha256": self.append_sha256,
            "prior_target_state": (
                None
                if self.prior_target_state_sha256 is None
                else {"sha256": self.prior_target_state_sha256}
            ),
            "next_state": self.next_state,
            "next_state_sha256": self.next_state_sha256,
            "screenshot": {
                "path": self.screenshot_relative_path,
                "length": self.screenshot_length,
                "sha256": self.screenshot_sha256,
            },
        }
        document["record_sha256"] = hashlib.sha256(canonical_json_bytes(document)).hexdigest()
        return document

    def to_bytes(self) -> bytes:
        """Returns the canonical durable pending payload."""

        return canonical_json_bytes(self.to_document())


def decode_pending_bytes(payload: bytes) -> PendingChatTransaction:
    """Strictly decodes one version-one pending record without coercion."""

    if len(payload) > MAX_PENDING_BYTES:
        raise ChatArchiveSchemaError("Chat pending record exceeds the maximum supported size.")
    document = decode_json_object(payload, field_name="pending")
    expected_keys = {
        "schema_version",
        "operation_id",
        "stream_identity",
        "archive_day",
        "captured_at",
        "transcript_existed",
        "previous_offset",
        "prefix_sha256",
        "append_bytes_base64",
        "append_length",
        "append_sha256",
        "prior_target_state",
        "next_state",
        "next_state_sha256",
        "screenshot",
        "record_sha256",
    }
    if set(document) != expected_keys:
        raise ChatArchiveSchemaError("Chat pending record has an unsupported or missing field.")
    if document["schema_version"] != 1 or type(document["schema_version"]) is not int:
        raise ChatArchiveSchemaError("Unsupported chat pending schema version.")
    operation_id = _non_empty_string(document["operation_id"], "operation_id")
    identity_document = _mapping(document["stream_identity"], "stream_identity")
    if set(identity_document) != {"account_segment", "castle_segment", "channel"}:
        raise ChatArchiveSchemaError("Chat pending stream_identity has an invalid schema.")
    identity = ChatStreamIdentity(
        account_segment=_non_empty_string(identity_document["account_segment"], "stream_identity.account_segment"),
        castle_segment=_non_empty_string(identity_document["castle_segment"], "stream_identity.castle_segment"),
        channel=_non_empty_string(identity_document["channel"], "stream_identity.channel"),
    )
    archive_day = _non_empty_string(document["archive_day"], "archive_day")
    if _DAY_PATTERN.fullmatch(archive_day) is None:
        raise ChatArchiveSchemaError("Chat pending archive_day must be YYYY-MM-DD.")
    captured_at = _aware_datetime(document["captured_at"], "captured_at")
    if captured_at.astimezone().strftime("%Y-%m-%d") != archive_day:
        raise ChatArchiveSchemaError("Chat pending archive_day does not match captured_at in the local timezone.")
    transcript_existed = _exact_bool(document["transcript_existed"], "transcript_existed")
    previous_offset = _non_negative_int(document["previous_offset"], "previous_offset")
    if not transcript_existed and previous_offset != 0:
        raise ChatArchiveSchemaError("Chat pending absent transcripts must start at byte offset zero.")
    prefix_sha256 = _sha256(document["prefix_sha256"], "prefix_sha256")
    append_encoded = _non_empty_string(document["append_bytes_base64"], "append_bytes_base64")
    try:
        append_bytes = base64.b64decode(append_encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as error:
        raise ChatArchiveSchemaError("Chat pending append_bytes_base64 is not strict base64.") from error
    if len(append_bytes) > MAX_APPEND_BYTES:
        raise ChatArchiveSchemaError("Chat pending append payload exceeds the maximum supported size.")
    append_length = _non_negative_int(document["append_length"], "append_length")
    if append_length != len(append_bytes):
        raise ChatArchiveSchemaError("Chat pending append_length does not match its decoded payload.")
    append_sha256 = _sha256(document["append_sha256"], "append_sha256")
    if append_sha256 != hashlib.sha256(append_bytes).hexdigest():
        raise ChatArchiveSchemaError("Chat pending append_sha256 does not match its payload.")
    prior_state = document["prior_target_state"]
    prior_state_sha256: str | None
    if prior_state is None:
        prior_state_sha256 = None
    else:
        prior_mapping = _mapping(prior_state, "prior_target_state")
        if set(prior_mapping) != {"sha256"}:
            raise ChatArchiveSchemaError("Chat pending prior_target_state has an invalid schema.")
        prior_state_sha256 = _sha256(prior_mapping["sha256"], "prior_target_state.sha256")
    next_state = _mapping(document["next_state"], "next_state")
    decoded_next_state = validate_state_document(next_state, allow_legacy=False)
    if decoded_next_state.transcript_evidence is None:
        raise ChatArchiveSchemaError("Chat pending next_state must identify committed transcript evidence.")
    if decoded_next_state.last_captured_at != captured_at:
        raise ChatArchiveSchemaError("Chat pending next_state timestamp does not match captured_at.")
    next_state_sha256 = _sha256(document["next_state_sha256"], "next_state_sha256")
    if next_state_sha256 != hashlib.sha256(canonical_json_bytes(next_state)).hexdigest():
        raise ChatArchiveSchemaError("Chat pending next_state_sha256 does not match next_state.")
    screenshot = _mapping(document["screenshot"], "screenshot")
    if set(screenshot) != {"path", "length", "sha256"}:
        raise ChatArchiveSchemaError("Chat pending screenshot has an invalid schema.")
    screenshot_path = _relative_path(screenshot["path"], "screenshot.path")
    screenshot_length = _non_negative_int(screenshot["length"], "screenshot.length")
    screenshot_sha256 = _sha256(screenshot["sha256"], "screenshot.sha256")
    record_sha256 = _sha256(document["record_sha256"], "record_sha256")
    unsigned_document = dict(document)
    del unsigned_document["record_sha256"]
    if record_sha256 != hashlib.sha256(canonical_json_bytes(unsigned_document)).hexdigest():
        raise ChatArchiveSchemaError("Chat pending record_sha256 does not match its contents.")
    if not append_bytes:
        raise ChatArchiveSchemaError("Chat pending transactions must contain a non-empty append payload.")
    if screenshot_length <= 0:
        raise ChatArchiveSchemaError("Chat pending transactions require non-empty screenshot evidence.")
    return PendingChatTransaction(
        operation_id=operation_id,
        stream_identity=identity,
        archive_day=archive_day,
        captured_at=captured_at,
        transcript_existed=transcript_existed,
        previous_offset=previous_offset,
        prefix_sha256=prefix_sha256,
        append_bytes=append_bytes,
        prior_target_state_sha256=prior_state_sha256,
        next_state=next_state,
        next_state_sha256=next_state_sha256,
        screenshot_relative_path=screenshot_path,
        screenshot_length=screenshot_length,
        screenshot_sha256=screenshot_sha256,
    )


def load_pending(path: Path) -> PendingChatTransaction:
    """Loads and strictly validates one pending record."""

    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_PENDING_BYTES + 1)
    except OSError as error:
        raise ChatArchiveConsistencyError("Unable to read the chat pending record.") from error
    if len(payload) > MAX_PENDING_BYTES:
        raise ChatArchiveConsistencyError("Chat pending record exceeds the maximum supported size.")
    try:
        return decode_pending_bytes(payload)
    except (ChatArchiveSchemaError, UnicodeError) as error:
        raise ChatArchiveConsistencyError("Chat pending record is malformed.") from error


def write_pending(path: Path, transaction: PendingChatTransaction) -> None:
    """Publishes one complete pending record atomically."""

    payload = transaction.to_bytes()
    decode_pending_bytes(payload)
    atomic_write_bytes(path, payload, prefix="pending-", suffix=".tmp")


def resolve_root_relative(root: Path, relative_path: str) -> Path:
    """Resolves a stored archive path and rejects traversal or absolute aliases."""

    relative = _relative_path(relative_path, "relative_path")
    root_resolved = root.expanduser().absolute()
    candidate = root_resolved / relative
    try:
        candidate.relative_to(root_resolved)
    except ValueError as error:
        raise ChatArchiveConsistencyError("Stored chat path escapes the configured archive root.") from error
    return candidate


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a mapping.")
    return value


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a non-empty string.")
    return value


def _exact_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a boolean.")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a non-negative integer.")
    return value


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a lowercase SHA-256 digest.")
    return value


def _aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be an ISO timestamp.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' is not a valid ISO timestamp.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must include a timezone.")
    return parsed


def _relative_path(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ":" in value or "\x00" in value:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a relative path.")
    normalized = Path(value)
    if any(part in {"", ".", ".."} for part in normalized.parts) or "\\" in value:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' contains an unsafe path.")
    return value
