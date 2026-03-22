"""Shared test helpers for the automation platform."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pnc_automation.config.models import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.mail import MailboxType
from pnc_automation.pnc.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_request import ObservationRequest


def build_png_bytes(*, size: tuple[int, int] = (20, 20), color: tuple[int, int, int, int] = (255, 255, 255, 255)) -> bytes:
    """Builds a small PNG image payload for tests."""

    image = Image.new("RGBA", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def make_visible(
    selector_id: UiElementId,
    *,
    x: int = 0,
    y: int = 0,
    width: int = 10,
    height: int = 10,
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    action_point: tuple[int, int] | None = None,
) -> VisibleElement:
    """Builds a visible selector with deterministic bounds."""

    return VisibleElement(
        selector_id=selector_id,
        bounds=Bounds(x=x, y=y, width=width, height=height),
        confidence=1.0,
        source_kind=source_kind,
        action_point=action_point,
    )


def make_entry(
    kind: ListEntryKind,
    *,
    title: str,
    metadata: dict[str, Any] | None = None,
    selected: bool = False,
    action_point: tuple[int, int] = (50, 50),
) -> DetectedListEntry:
    """Builds a dynamic list entry for tests."""

    return DetectedListEntry(
        kind=kind,
        bounds=Bounds(x=40, y=40, width=20, height=20),
        title_text=title,
        selected=selected,
        action_point=action_point,
        metadata=metadata or {},
    )


def make_observation(
    screen_type: ScreenType,
    *,
    visible_ids: tuple[UiElementId, ...] = (),
    source_kinds: dict[UiElementId, VisibleElementSourceKind] | None = None,
    list_entries: tuple[DetectedListEntry, ...] = (),
    blocking_popup: bool = False,
    current_castle_name: str | None = None,
    current_castle: CastleIdentity | None = None,
    current_castle_evidence: CurrentCastleEvidenceKind | None = None,
    current_pnc_account_id: str | None = None,
    verified_pnc_account_id: str | None = None,
    castle_roster_snapshot: PncAccountCastleRosterConfig | None = None,
    available_march_slots: int | None = None,
    active_chat_channel: ChatChannel | None = None,
    profile_player_name: str | None = None,
    mailbox_type: MailboxType | None = None,
    mailbox_empty: bool | None = None,
    text_field_states: dict[UiElementId, ObservedTextFieldState] | None = None,
    chat_draft_empty: bool | None = None,
    chat_draft_text: str | None = None,
    artifact_path: Path | None = None,
) -> Observation:
    """Builds a typed observation with synthetic visible elements."""

    visible_elements = {
        selector_id: make_visible(
            selector_id,
            x=index * 15,
            y=index * 15,
            source_kind=(source_kinds or {}).get(selector_id, VisibleElementSourceKind.TEMPLATE),
        )
        for index, selector_id in enumerate(visible_ids)
    }
    return Observation(
        screen_type=screen_type,
        visible_elements=visible_elements,
        list_entries=list_entries,
        blocking_popup=blocking_popup,
        current_castle=current_castle or _make_current_castle(current_castle_name),
        current_castle_evidence=_resolve_current_castle_evidence(
            current_castle=current_castle,
            current_castle_name=current_castle_name,
            current_castle_evidence=current_castle_evidence,
        ),
        current_pnc_account_id=current_pnc_account_id,
        verified_pnc_account_id=verified_pnc_account_id,
        castle_roster_snapshot=castle_roster_snapshot,
        available_march_slots=available_march_slots,
        active_chat_channel=active_chat_channel,
        profile_player_name=profile_player_name,
        mailbox_type=mailbox_type,
        mailbox_empty=mailbox_empty,
        text_field_states={} if text_field_states is None else text_field_states,
        chat_draft_empty=chat_draft_empty,
        chat_draft_text=chat_draft_text,
        artifact_path=artifact_path,
        image_size=(200, 100),
    )


def _make_current_castle(current_castle_name: str | None) -> CastleIdentity | None:
    """Builds a minimal current-castle identity for legacy test fixtures that only provide the name."""

    if current_castle_name is None:
        return None
    return CastleIdentity(kingdom="", castle_name=current_castle_name)


def _resolve_current_castle_evidence(
    *,
    current_castle: CastleIdentity | None,
    current_castle_name: str | None,
    current_castle_evidence: CurrentCastleEvidenceKind | None,
) -> CurrentCastleEvidenceKind | None:
    """Returns the matching evidence kind for synthetic current-castle fixtures."""

    if current_castle_evidence is not None:
        return current_castle_evidence
    if current_castle is not None:
        return CurrentCastleEvidenceKind.NAME_ONLY if current_castle.kingdom == "" else CurrentCastleEvidenceKind.EXACT
    if current_castle_name is not None:
        return CurrentCastleEvidenceKind.NAME_ONLY
    return None


@dataclass
class FakeSession:
    """Captures action-executor calls without talking to ADB."""

    taps: list[tuple[int, int]] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)
    launches: int = 0
    swipes: list[tuple[int, int, int, int, int]] = field(default_factory=list)

    def tap_point(self, x: int, y: int) -> None:
        """Records one tap."""

        self.taps.append((x, y))

    def input_text(self, text: str) -> None:
        """Records one text input."""

        self.texts.append(text)

    def press_key(self, key_code: str) -> None:
        """Records one key event."""

        self.key_events.append(key_code)

    def launch_app(self) -> None:
        """Records one app launch request."""

        self.launches += 1

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, *, duration_ms: int = 300) -> None:
        """Records one swipe gesture."""

        self.swipes.append((start_x, start_y, end_x, end_y, duration_ms))


@dataclass
class FakeObservationService:
    """Returns a pre-seeded sequence of observations."""

    observations: list[Observation]
    labels: list[str] = field(default_factory=list)
    requests: list[ObservationRequest | None] = field(default_factory=list)

    def observe(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Returns the next queued observation."""

        self.labels.append(label)
        self.requests.append(request)
        if not self.observations:
            raise AssertionError(f"No observation queued for label '{label}'.")
        return self.observations.pop(0)


def build_logger() -> logging.LoggerAdapter:
    """Builds a quiet logger adapter for tests."""

    logger = logging.getLogger("pnc_automation.tests")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logging.LoggerAdapter(logger, extra={})
