"""Canonical chat archive state models and strict codecs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pnc_automation.app.pnc.domain.chat import normalize_chat_text


class ChatArchiveSchemaError(ValueError):
    """Raised when persisted chat state or a nested state value is malformed."""


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{8}$")


@dataclass(frozen=True, slots=True)
class NormalizedPlayerChatEntry:
    """Represents one normalized visible player-chat row."""

    sender_name: str
    message_text: str
    visible_order: int

    def content_key(self) -> tuple[str, str]:
        """Returns the normalized sender/message identity used for overlap."""

        return (normalize_chat_text(self.sender_name), normalize_chat_text(self.message_text))


@dataclass(frozen=True, slots=True)
class VisibleChatSnapshot:
    """Captures one normalized visible-window snapshot."""

    entries: tuple[NormalizedPlayerChatEntry, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ChatTranscriptEvidence:
    """Identifies the complete target-day transcript bytes backing a state."""

    exists: bool
    length: int
    sha256: str

    def __post_init__(self) -> None:
        if type(self.exists) is not bool or not self.exists:
            raise ChatArchiveSchemaError("Chat transcript evidence must identify an existing transcript.")
        if type(self.length) is not int or self.length < 0:
            raise ChatArchiveSchemaError("Chat transcript evidence length must be a non-negative integer.")
        if _SHA256_PATTERN.fullmatch(self.sha256) is None:
            raise ChatArchiveSchemaError("Chat transcript evidence must contain a lowercase SHA-256 digest.")

    def as_document(self) -> dict[str, object]:
        """Returns the strict persisted evidence mapping."""

        return {"exists": self.exists, "length": self.length, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ChatArchiveState:
    """Carries overlap state and explicit target-day transcript evidence."""

    snapshot: VisibleChatSnapshot
    last_captured_at: datetime | None = None
    gap_detected: bool = False
    transcript_evidence: ChatTranscriptEvidence | None = None


@dataclass(frozen=True, slots=True)
class DecodedChatArchiveState:
    """Returns one decoded state and whether it used the legacy schema."""

    state: ChatArchiveState
    legacy: bool


def canonical_json_bytes(document: object) -> bytes:
    """Returns the one canonical JSON byte encoding used by archive state."""

    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise ChatArchiveSchemaError("Chat archive document cannot be canonically encoded.") from error


def decode_json_object(payload: bytes, *, field_name: str) -> dict[str, Any]:
    """Decodes one duplicate-key-free JSON object."""

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ChatArchiveSchemaError) as error:
        raise ChatArchiveSchemaError(f"Chat {field_name} is not valid JSON.") from error
    return _mapping(document, field_name)


def state_document(state: ChatArchiveState) -> dict[str, Any]:
    """Serializes one new version-two state document."""

    return {
        "schema_version": 2,
        "last_captured_at": None if state.last_captured_at is None else state.last_captured_at.isoformat(),
        "gap_detected": state.gap_detected,
        "snapshot": {
            "fingerprint": state.snapshot.fingerprint,
            "entries": [
                {
                    "sender_name": entry.sender_name,
                    "message_text": entry.message_text,
                    "visible_order": entry.visible_order,
                }
                for entry in state.snapshot.entries
            ],
        },
        "transcript_evidence": None if state.transcript_evidence is None else state.transcript_evidence.as_document(),
    }


def state_bytes(state: ChatArchiveState) -> bytes:
    """Returns canonical bytes for one new state."""

    return canonical_json_bytes(state_document(state))


def validate_snapshot(snapshot: object) -> VisibleChatSnapshot:
    """Validates and canonicalizes one caller-supplied visible snapshot."""

    if not isinstance(snapshot, VisibleChatSnapshot):
        raise ChatArchiveSchemaError("Chat snapshot must be a VisibleChatSnapshot.")
    if type(snapshot.entries) is not tuple:
        raise ChatArchiveSchemaError("Chat snapshot entries must be a tuple.")
    entries: list[dict[str, object]] = []
    for index, item in enumerate(snapshot.entries):
        if not isinstance(item, NormalizedPlayerChatEntry):
            raise ChatArchiveSchemaError(f"Chat snapshot entry {index} has an invalid type.")
        entries.append(
            {
                "sender_name": item.sender_name,
                "message_text": item.message_text,
                "visible_order": item.visible_order,
            }
        )
    return _decode_snapshot_document(
        {"fingerprint": snapshot.fingerprint, "entries": entries}
    )


def decode_state_document(document: dict[str, Any], *, allow_legacy: bool = True) -> DecodedChatArchiveState:
    """Strictly decodes version-two state or the supported legacy state shape."""

    document_keys = set(document)
    legacy_keys = {"last_captured_at", "gap_detected", "snapshot"}
    current_keys = {"schema_version", "last_captured_at", "gap_detected", "snapshot", "transcript_evidence"}
    if "schema_version" not in document:
        if not allow_legacy or not document_keys.issubset(legacy_keys) or "snapshot" not in document:
            raise ChatArchiveSchemaError("Chat archive state has an unsupported or missing schema version.")
        legacy = True
    else:
        if document_keys != current_keys or document["schema_version"] != 2 or type(document["schema_version"]) is not int:
            raise ChatArchiveSchemaError("Unsupported chat archive state schema.")
        legacy = False

    snapshot = _decode_snapshot_document(document["snapshot"])
    entries = snapshot.entries
    captured = document.get("last_captured_at")
    if captured is not None and not isinstance(captured, str):
        raise ChatArchiveSchemaError("Chat archive state last_captured_at must be an ISO timestamp or null.")
    last_captured_at = None if captured is None else _aware_datetime(captured, "last_captured_at")
    gap_detected = document.get("gap_detected", False)
    if type(gap_detected) is not bool:
        raise ChatArchiveSchemaError("Chat archive state gap_detected must be a boolean.")
    evidence = None if legacy else _decode_evidence(document["transcript_evidence"])
    if evidence is None and not legacy and entries and last_captured_at is None:
        raise ChatArchiveSchemaError("Chat archive state with visible rows requires a capture timestamp.")
    return DecodedChatArchiveState(
        state=ChatArchiveState(
            snapshot=snapshot,
            last_captured_at=last_captured_at,
            gap_detected=gap_detected,
            transcript_evidence=evidence,
        ),
        legacy=legacy,
    )


def validate_state_document(document: dict[str, Any], *, allow_legacy: bool = False) -> ChatArchiveState:
    """Validates one state mapping and returns its typed value."""

    return decode_state_document(document, allow_legacy=allow_legacy).state


def _decode_snapshot_document(value: object) -> VisibleChatSnapshot:
    snapshot_document = _mapping(value, "snapshot")
    if set(snapshot_document) != {"fingerprint", "entries"} or not isinstance(snapshot_document["entries"], list):
        raise ChatArchiveSchemaError("Chat archive state snapshot has an invalid schema.")
    fingerprint = snapshot_document["fingerprint"]
    if not isinstance(fingerprint, str) or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
        raise ChatArchiveSchemaError("Chat archive state fingerprint must be eight lowercase hexadecimal characters.")
    entries: list[NormalizedPlayerChatEntry] = []
    for index, item in enumerate(snapshot_document["entries"]):
        entry = _mapping(item, f"snapshot.entries[{index}]")
        if set(entry) != {"sender_name", "message_text", "visible_order"}:
            raise ChatArchiveSchemaError(f"Chat archive state snapshot entry {index} has an invalid schema.")
        entries.append(
            NormalizedPlayerChatEntry(
                sender_name=_non_empty_string(entry["sender_name"], f"snapshot.entries[{index}].sender_name"),
                message_text=_non_empty_string(entry["message_text"], f"snapshot.entries[{index}].message_text"),
                visible_order=_non_negative_int(entry["visible_order"], f"snapshot.entries[{index}].visible_order"),
            )
        )
    return VisibleChatSnapshot(entries=tuple(entries), fingerprint=fingerprint)


def _decode_evidence(value: object) -> ChatTranscriptEvidence | None:
    if value is None:
        return None
    document = _mapping(value, "transcript_evidence")
    if set(document) != {"exists", "length", "sha256"}:
        raise ChatArchiveSchemaError("Chat archive transcript evidence has an invalid schema.")
    return ChatTranscriptEvidence(
        exists=_exact_bool(document["exists"], "transcript_evidence.exists"),
        length=_non_negative_int(document["length"], "transcript_evidence.length"),
        sha256=_sha256(document["sha256"], "transcript_evidence.sha256"),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ChatArchiveSchemaError("Duplicate JSON keys are not supported in chat archive data.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ChatArchiveSchemaError(f"JSON constant '{value}' is not supported in chat archive data.")


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a mapping.")
    return value


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a non-empty string.")
    return value.strip()


def _exact_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a boolean.")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a non-negative integer.")
    return value


def _sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must be a lowercase SHA-256 digest.")
    return value


def _aware_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' is not a valid ISO timestamp.") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChatArchiveSchemaError(f"Chat archive field '{field_name}' must include a timezone.")
    return parsed
