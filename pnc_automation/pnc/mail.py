"""Shared mail-domain models and canonical parsing helpers."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pnc_automation.artifact_naming import sanitize_artifact_segment
from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.ui_element_id import UiElementId


class MailboxType(StrEnum):
    """Supported mailbox scopes in the current mail automation slice."""

    PLAYER = "player"
    ALLIANCE = "alliance"


class MailRecipientKind(StrEnum):
    """Supported mail recipient kinds in the current mail automation slice."""

    PLAYER = "player"
    ALLIANCE = "alliance"


class MailArchiveMode(StrEnum):
    """Controls which archive artifacts are persisted for collected mail."""

    SCREENSHOT = "screenshot"
    TEXT = "text"
    BOTH = "both"


class PlayerProfileRouteKind(StrEnum):
    """Supported routes that can reach one remote player profile."""

    PLAYER_TERRITORY = "player_territory"
    CHAT_MESSAGE = "chat_message"
    ALLIANCE_MEMBER = "alliance_member"
    MIGHT_RANK = "might_rank"


@dataclass(frozen=True, slots=True)
class PlayerProfileRoute:
    """Identifies one supported route used to reach a remote player profile."""

    kind: PlayerProfileRouteKind
    player_name: str | None = None


@dataclass(frozen=True, slots=True)
class SendMailParams:
    """Carries the validated canonical send-mail task payload."""

    recipient_kind: MailRecipientKind
    player_name: str | None
    profile_route: PlayerProfileRoute | None
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class CollectMailParams:
    """Carries the validated canonical collect-mail task payload."""

    mailboxes: tuple[MailboxType, ...]
    archive_mode: MailArchiveMode = MailArchiveMode.BOTH
    limit_per_mailbox: int = 25
    only_new: bool = True


@dataclass(frozen=True, slots=True)
class MailThreadFingerprint:
    """Captures one canonical stable mail-thread identity."""

    value: str


@dataclass(frozen=True, slots=True)
class MailArchiveRecord:
    """Describes one canonical archived thread snapshot."""

    account_id: str
    pnc_account_id: str
    active_castle: str
    mailbox_type: MailboxType
    sender_name: str
    thread_timestamp_text: str | None
    fingerprint: MailThreadFingerprint
    captured_at: datetime
    normalized_thread_text: str
    source_artifact_paths: tuple[Path, ...] = ()


def parse_send_mail_params(*, task_label: object, params: Mapping[str, object]) -> SendMailParams:
    """Builds the canonical validated send-mail payload from raw script parameters."""

    recipient_kind = _require_enum_value(
        params.get("recipient_kind"),
        enum_type=MailRecipientKind,
        task_label=task_label,
        field_name="recipient_kind",
    )
    player_name = _optional_non_empty_string(params.get("player_name"))
    profile_route = _parse_profile_route(task_label=task_label, value=params.get("profile_route"))
    subject = _require_trimmed_string(task_label=task_label, field_name="subject", value=params.get("subject"))
    body = _require_trimmed_string(task_label=task_label, field_name="body", value=params.get("body"))
    extra_keys = sorted(
        key
        for key in params.keys()
        if key not in {"recipient_kind", "player_name", "profile_route", "subject", "body"}
    )
    if extra_keys:
        raise ScriptValidationError(
            f"Task '{task_label}' received unsupported send_mail parameters.",
            task_id=task_label,
            extra_keys=extra_keys,
        )
    if recipient_kind == MailRecipientKind.ALLIANCE:
        if player_name is not None or profile_route is not None:
            raise ScriptValidationError(
                "Alliance mail does not accept player_name or profile_route.",
                task_id=task_label,
                recipient_kind=recipient_kind.value,
            )
        return SendMailParams(
            recipient_kind=recipient_kind,
            player_name=None,
            profile_route=None,
            subject=subject,
            body=body,
        )
    if (player_name is None) == (profile_route is None):
        raise ScriptValidationError(
            "Player mail requires exactly one of player_name or profile_route.",
            task_id=task_label,
            recipient_kind=recipient_kind.value,
        )
    return SendMailParams(
        recipient_kind=recipient_kind,
        player_name=player_name,
        profile_route=profile_route,
        subject=subject,
        body=body,
    )


def parse_collect_mail_params(*, task_label: object, params: Mapping[str, object]) -> CollectMailParams:
    """Builds the canonical validated collect-mail payload from raw script parameters."""

    mailboxes = _parse_mailboxes(task_label=task_label, value=params.get("mailboxes"))
    archive_mode = _require_enum_value(
        params.get("archive_mode", MailArchiveMode.BOTH.value),
        enum_type=MailArchiveMode,
        task_label=task_label,
        field_name="archive_mode",
    )
    limit_per_mailbox = params.get("limit_per_mailbox", 25)
    if not isinstance(limit_per_mailbox, int) or isinstance(limit_per_mailbox, bool) or limit_per_mailbox <= 0:
        raise ScriptValidationError(
            "collect_mail requires limit_per_mailbox to be a positive integer.",
            task_id=task_label,
            limit_per_mailbox=limit_per_mailbox,
        )
    only_new = params.get("only_new", True)
    if not isinstance(only_new, bool):
        raise ScriptValidationError(
            "collect_mail requires only_new to be a boolean when provided.",
            task_id=task_label,
            only_new=only_new,
        )
    extra_keys = sorted(
        key
        for key in params.keys()
        if key not in {"mailboxes", "archive_mode", "limit_per_mailbox", "only_new"}
    )
    if extra_keys:
        raise ScriptValidationError(
            "collect_mail received unsupported parameters.",
            task_id=task_label,
            extra_keys=extra_keys,
        )
    return CollectMailParams(
        mailboxes=mailboxes,
        archive_mode=archive_mode,
        limit_per_mailbox=limit_per_mailbox,
        only_new=only_new,
    )


def mailbox_category_selector_id(mailbox: MailboxType) -> UiElementId:
    """Returns the mail-hub category selector for the requested mailbox."""

    if mailbox == MailboxType.PLAYER:
        return UiElementId.PNC_MAIL_ROW_PLAYER_MAIL
    if mailbox == MailboxType.ALLIANCE:
        return UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL
    raise ValueError(f"Unsupported mailbox type '{mailbox}'.")


def mailbox_for_recipient_kind(recipient_kind: MailRecipientKind) -> MailboxType:
    """Returns the mailbox used to verify a successful send for the requested recipient kind."""

    if recipient_kind == MailRecipientKind.PLAYER:
        return MailboxType.PLAYER
    if recipient_kind == MailRecipientKind.ALLIANCE:
        return MailboxType.ALLIANCE
    raise ValueError(f"Unsupported recipient kind '{recipient_kind}'.")


def compose_target_label_for_alliance() -> str:
    """Returns the expected auto-filled compose target for alliance mail."""

    return "Alliance Mail"


def compose_text_field_selector_ids() -> tuple[UiElementId, ...]:
    """Returns the canonical compose text-entry selectors in stable field order."""

    return (
        UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
        UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
        UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
    )


def multiline_text_field_selector_ids() -> frozenset[UiElementId]:
    """Returns the selectors that support multiline text entry."""

    return frozenset({UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD})


def compute_mail_thread_fingerprint(
    *,
    mailbox_type: MailboxType,
    sender_name: str,
    timestamp_text: str | None,
    normalized_thread_text: str,
) -> MailThreadFingerprint:
    """Builds one stable thread fingerprint from canonical normalized mail content."""

    normalized_sender = normalize_mail_text(sender_name)
    normalized_timestamp = normalize_mail_text(timestamp_text or "")
    payload = "\n".join(
        (
            mailbox_type.value,
            normalized_sender,
            normalized_timestamp,
            normalized_thread_text,
        )
    ).encode("utf-8")
    return MailThreadFingerprint(value=hashlib.sha256(payload).hexdigest()[:8])


def normalize_mail_text(value: str) -> str:
    """Normalizes mail text for tolerant comparisons and deterministic fingerprints."""

    collapsed = " ".join(segment for segment in value.replace("\r", "\n").split() if segment != "")
    return re.sub(r"[^A-Z0-9]", "", collapsed.upper())


def normalize_mail_thread_text(lines: Sequence[str]) -> str:
    """Returns deterministic visible thread text from one ordered set of visible lines."""

    normalized_lines = [line.strip() for line in lines if line.strip() != ""]
    return "\n".join(normalized_lines)


def thread_partner_directory_name(sender_name: str) -> str:
    """Returns the canonical sanitized archive directory segment for one sender or thread partner."""

    return sanitize_artifact_segment(sender_name.strip().lower())


def route_requires_player_name(kind: PlayerProfileRouteKind) -> bool:
    """Returns whether the supported route requires a visible player-name target."""

    return kind in {
        PlayerProfileRouteKind.CHAT_MESSAGE,
        PlayerProfileRouteKind.ALLIANCE_MEMBER,
        PlayerProfileRouteKind.MIGHT_RANK,
    }


def _parse_profile_route(*, task_label: object, value: object) -> PlayerProfileRoute | None:
    """Builds the validated player-profile route when the script provided one."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ScriptValidationError(
            "profile_route must be a mapping when provided.",
            task_id=task_label,
            profile_route=value,
        )
    kind = _require_enum_value(
        value.get("kind"),
        enum_type=PlayerProfileRouteKind,
        task_label=task_label,
        field_name="profile_route.kind",
    )
    player_name = _optional_non_empty_string(value.get("player_name"))
    extra_keys = sorted(key for key in value.keys() if key not in {"kind", "player_name"})
    if extra_keys:
        raise ScriptValidationError(
            "profile_route received unsupported keys.",
            task_id=task_label,
            extra_keys=extra_keys,
        )
    if route_requires_player_name(kind) and player_name is None:
        raise ScriptValidationError(
            f"profile_route '{kind.value}' requires player_name.",
            task_id=task_label,
            profile_route_kind=kind.value,
        )
    if not route_requires_player_name(kind) and player_name is not None:
        raise ScriptValidationError(
            f"profile_route '{kind.value}' does not accept player_name.",
            task_id=task_label,
            profile_route_kind=kind.value,
        )
    return PlayerProfileRoute(kind=kind, player_name=player_name)


def _parse_mailboxes(*, task_label: object, value: object) -> tuple[MailboxType, ...]:
    """Builds the canonical deduplicated mailbox tuple from raw script content."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ScriptValidationError(
            "collect_mail requires mailboxes to be a non-empty sequence.",
            task_id=task_label,
            mailboxes=value,
        )
    parsed: list[MailboxType] = []
    seen: set[MailboxType] = set()
    for raw_mailbox in value:
        mailbox = _require_enum_value(
            raw_mailbox,
            enum_type=MailboxType,
            task_label=task_label,
            field_name="mailboxes",
        )
        if mailbox in seen:
            continue
        seen.add(mailbox)
        parsed.append(mailbox)
    if not parsed:
        raise ScriptValidationError(
            "collect_mail requires at least one mailbox.",
            task_id=task_label,
        )
    return tuple(parsed)


def _require_enum_value(
    raw_value: object,
    *,
    enum_type: type[MailboxType] | type[MailRecipientKind] | type[MailArchiveMode] | type[PlayerProfileRouteKind],
    task_label: object,
    field_name: str,
) -> object:
    """Converts one raw string value into the requested canonical enum."""

    if isinstance(raw_value, enum_type):
        return raw_value
    if not isinstance(raw_value, str) or raw_value.strip() == "":
        raise ScriptValidationError(
            f"Task '{task_label}' requires a non-empty string '{field_name}'.",
            task_id=task_label,
            field_name=field_name,
            value=raw_value,
        )
    try:
        return enum_type(raw_value.strip())
    except ValueError as error:
        raise ScriptValidationError(
            f"Task '{task_label}' received unsupported value '{raw_value}' for '{field_name}'.",
            task_id=task_label,
            field_name=field_name,
            value=raw_value,
        ) from error


def _require_trimmed_string(*, task_label: object, field_name: str, value: object) -> str:
    """Returns one required non-empty trimmed string parameter."""

    if not isinstance(value, str) or value.strip() == "":
        raise ScriptValidationError(
            f"Task '{task_label}' requires a non-empty string '{field_name}'.",
            task_id=task_label,
            field_name=field_name,
            value=value,
        )
    return value.strip()


def _optional_non_empty_string(value: object) -> str | None:
    """Returns one optional trimmed string or `None` when the field is absent."""

    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ScriptValidationError(
            "Optional mail string parameters must be non-empty strings when provided.",
            value=value,
        )
    return value.strip()
