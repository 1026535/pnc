"""Synthetic fixtures owned by pnc.observations."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from typing import Any

from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    SpatialSurfaceObservation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.emulator.provenance import FrameRef


_SYNTHETIC_FRAME_SEQUENCE = count(1)



def make_visible(
    selector_id: UiElementId,
    *,
    x: int = 0,
    y: int = 0,
    width: int = 10,
    height: int = 10,
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    action_point: tuple[int, int] | None = None,
    extracted_text: str | None = None,
) -> VisibleElement:
    """Builds a visible selector with deterministic bounds."""

    return VisibleElement(
        selector_id=selector_id,
        bounds=Bounds(x=x, y=y, width=width, height=height),
        confidence=1.0,
        source_kind=source_kind,
        extracted_text=extracted_text,
        action_point=action_point,
    )


def make_entry(
    kind: ListEntryKind,
    *,
    title: str,
    subtitle: str | None = None,
    timer_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    selected: bool = False,
    action_point: tuple[int, int] = (50, 50),
) -> DetectedListEntry:
    """Builds a dynamic list entry for tests."""

    return DetectedListEntry(
        kind=kind,
        bounds=Bounds(x=40, y=40, width=20, height=20),
        title_text=title,
        subtitle_text=subtitle,
        timer_text=timer_text,
        selected=selected,
        action_point=action_point,
        metadata=metadata or {},
    )


def make_observation(
    screen_type: ScreenType,
    *,
    visible_ids: tuple[UiElementId, ...] = (),
    source_kinds: dict[UiElementId, VisibleElementSourceKind] | None = None,
    visible_texts: dict[UiElementId, str | None] | None = None,
    list_entries: tuple[DetectedListEntry, ...] = (),
    spatial_surface: SpatialSurfaceObservation | None = None,
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
    image_size: tuple[int, int] = (200, 100),
    frame_fingerprint: str | None = None,
    popup_overlay: PopupOverlayObservation | None = None,
    frame_ref: FrameRef | None = None,
    decision: ScreenDecision | None = None,
) -> Observation:
    """Builds a typed observation with synthetic visible elements."""

    visible_elements = {
        selector_id: make_visible(
            selector_id,
            x=index * 15,
            y=index * 15,
            source_kind=(source_kinds or {}).get(selector_id, VisibleElementSourceKind.TEMPLATE),
            extracted_text=(visible_texts or {}).get(selector_id),
        )
        for index, selector_id in enumerate(visible_ids)
    }
    if popup_overlay is None and UiElementId.PNC_UPDATE_CONFIRM_BUTTON in visible_elements:
        update_element = visible_elements[UiElementId.PNC_UPDATE_CONFIRM_BUTTON]
        popup_overlay = PopupOverlayObservation(
            image_size=image_size,
            layout_id="synthetic_required_update",
            candidates=(
                PopupDismissCandidate(
                    control_kind=PopupControlKind.UPDATE_CONFIRM,
                    bounds=update_element.bounds,
                    action_point=update_element.action_point or update_element.bounds.center(),
                    confidence=update_element.confidence,
                    evidence_kind=PopupEvidenceKind.OCR_TEXT,
                    extracted_text=update_element.extracted_text,
                ),
            ),
        )
    resolved_frame_ref = frame_ref or FrameRef(
        session_id="synthetic-test-session",
        session_epoch=1,
        capture_sequence=next(_SYNTHETIC_FRAME_SEQUENCE),
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )
    resolved_decision = decision or ScreenDecision(
        base_screen=screen_type,
        effective_screen=screen_type,
        guard=GuardVerdict.BLOCKED if blocking_popup else (
            GuardVerdict.UNRESOLVED if screen_type == ScreenType.UNKNOWN else GuardVerdict.CLEAR
        ),
        evidence=(ScreenEvidence(screen_type, "synthetic_fixture"),),
    )
    visible_elements = {
        selector_id: replace(
            element,
            frame_ref=resolved_frame_ref,
            source_screen=resolved_decision.effective_screen,
            source_layout_id=resolved_decision.layout_id,
        )
        for selector_id, element in visible_elements.items()
    }
    resolved_entries = tuple(
        replace(
            entry,
            frame_ref=resolved_frame_ref,
            source_screen=resolved_decision.effective_screen,
            source_layout_id=resolved_decision.layout_id,
        )
        for entry in list_entries
    )
    return Observation(
        decision=resolved_decision,
        visible_elements=visible_elements,
        list_entries=resolved_entries,
        spatial_surface=spatial_surface,
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
        image_size=image_size,
        frame_fingerprint=frame_fingerprint or f"synthetic:{screen_type.value}:{','.join(item.value for item in visible_ids)}",
        popup_overlay=popup_overlay,
        frame_ref=resolved_frame_ref,
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
