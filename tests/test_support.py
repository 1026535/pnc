"""Shared test helpers for the automation platform."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactRecord
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.app.authoring.config.models import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.action_requests import SwipeInputSource
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactKind,
    ObservationArtifactSelection,
    resolve_observation_artifact_selection,
)
from pnc_automation.app.runtime.observation_mode import ObservationMode


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


def make_spatial_object(
    kind: SpatialObjectKind,
    *,
    name_text: str | None = None,
    relationship: SpatialObjectRelationship = SpatialObjectRelationship.UNKNOWN,
    kingdom: str | None = None,
    level: int | None = None,
    metadata: dict[str, Any] | None = None,
    action_point: tuple[int, int] = (50, 50),
    viewport_offset: tuple[int, int] | None = None,
    viewport_offset_ratio: tuple[float, float] | None = None,
    estimated_world_coordinate: tuple[int, int] | None = None,
    confirmed_world_coordinate: tuple[int, int] | None = None,
) -> DetectedSpatialObject:
    """Builds a spatial object with deterministic bounds for tests."""

    return DetectedSpatialObject(
        kind=kind,
        bounds=Bounds(x=40, y=40, width=20, height=20),
        relationship=relationship,
        name_text=name_text,
        kingdom=kingdom,
        level=level,
        action_point=action_point,
        viewport_offset=viewport_offset,
        viewport_offset_ratio=viewport_offset_ratio,
        estimated_world_coordinate=estimated_world_coordinate,
        confirmed_world_coordinate=confirmed_world_coordinate,
        metadata=metadata or {},
    )


def make_spatial_surface(
    surface_type: SpatialSurfaceType,
    *,
    objects: tuple[DetectedSpatialObject, ...] = (),
    x: int | None = None,
    y: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> SpatialSurfaceObservation:
    """Builds a spatial surface with deterministic viewport defaults for tests."""

    if surface_type == SpatialSurfaceType.WORLD_MAP:
        return SpatialSurfaceObservation(
            surface_type=surface_type,
            viewport=SpatialViewport(
                addressing_kind=SpatialViewportAddressingKind.COORDINATE_BAR,
                x=0 if x is None else x,
                y=0 if y is None else y,
            ),
            objects=objects,
            metadata={} if metadata is None else metadata,
        )
    return SpatialSurfaceObservation(
        surface_type=surface_type,
        viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
        objects=objects,
        metadata={} if metadata is None else metadata,
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
    return Observation(
        screen_type=screen_type,
        visible_elements=visible_elements,
        list_entries=list_entries,
        spatial_surface=spatial_surface,
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
        image_size=image_size,
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
    swipe_input_sources: list[SwipeInputSource] = field(default_factory=list)

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

    def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        duration_ms: int = 300,
        input_source: str = SwipeInputSource.TOUCHSCREEN.value,
    ) -> None:
        """Records one swipe gesture."""

        self.swipes.append((start_x, start_y, end_x, end_y, duration_ms))
        self.swipe_input_sources.append(SwipeInputSource(input_source))


@dataclass
class FakeObservationService:
    """Returns a pre-seeded sequence of observations."""

    observations: list[Observation]
    mode: ObservationMode = ObservationMode.DEBUG
    labels: list[str] = field(default_factory=list)
    requests: list[ObservationRequest | None] = field(default_factory=list)
    artifact_selections: list[ObservationArtifactSelection | None] = field(default_factory=list)

    def observe(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> Observation:
        """Returns the next queued observation."""

        self.labels.append(label)
        self.requests.append(request)
        self.artifact_selections.append(artifact_selection)
        if not self.observations:
            raise AssertionError(f"No observation queued for label '{label}'.")
        return self.observations.pop(0)

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> CapturedObservation:
        """Returns the next queued observation wrapped in a synthetic captured screenshot."""

        observation = self.observe(label, request=request, artifact_selection=artifact_selection)
        resolved_artifact_selection = resolve_observation_artifact_selection(
            mode=self.mode,
            request_selection=None if request is None else request.artifact_selection,
            override_selection=artifact_selection,
        )
        artifact = (
            ArtifactRecord(
                path=observation.artifact_path or Path(f"{label}.png"),
                label=label,
                captured_at=observation.captured_at,
                size_bytes=0,
                sha256="0" * 64,
            )
            if ObservationArtifactKind.SCREENSHOT in resolved_artifact_selection
            else None
        )
        return CapturedObservation(
            screenshot=CapturedScreenshot(
                artifact=artifact,
                image=Image.new("RGB", observation.image_size or (10, 10), (0, 0, 0)),
                image_format="PNG",
                payload=build_png_bytes(size=observation.image_size or (10, 10)),
                ephemeral_captured_at=None if artifact is not None else datetime.now(tz=UTC),
            ),
            observation=observation,
        )


def build_logger() -> logging.LoggerAdapter:
    """Builds a quiet logger adapter for tests."""

    logger = logging.getLogger("pnc_automation.tests")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logging.LoggerAdapter(logger, extra={})
