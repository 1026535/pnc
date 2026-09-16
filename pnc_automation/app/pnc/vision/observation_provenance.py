"""Bind measured observation content to its owning capture and screen decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraProof
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    DetectedSpatialObject,
    SpatialSurfaceObservation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef


def select_content_labels(
    elements: Mapping[UiElementId, VisibleElement],
    *,
    selector_registry: SelectorRegistry | None,
) -> dict[UiElementId, VisibleElement]:
    """Selects registry-declared labels and strips any accidental action proof."""

    if selector_registry is None:
        return {}
    label_selector_ids = {
        selector.id
        for selector in selector_registry.all()
        if selector.interaction_kind == SelectorInteractionKind.LABEL
    }
    selected: dict[UiElementId, VisibleElement] = {}
    for selector_id, element in elements.items():
        if selector_id not in label_selector_ids or element.source_kind != VisibleElementSourceKind.OCR:
            continue
        if element.selector_id != selector_id:
            raise SelectorResolutionError(
                "Content label mapping key does not match its visible selector proof.",
                selector_id=selector_id,
                element_selector_id=element.selector_id,
            )
        selected[selector_id] = replace(
            element,
            action_point=None,
            identity_evidence=False,
        )
    return selected


def bind_visible_elements(
    elements: Mapping[UiElementId, VisibleElement],
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> dict[UiElementId, VisibleElement]:
    """Stamps published selector geometry with the observation provenance and source."""

    return {
        selector_id: bind_visible_element(
            element,
            frame_ref=frame_ref,
            source_screen=source_screen,
            source_layout_id=source_layout_id,
        )
        for selector_id, element in elements.items()
    }


def bind_visible_element(
    element: VisibleElement,
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> VisibleElement:
    """Adds missing publication provenance while rejecting contradictory existing proof."""

    if element.frame_ref is not None and element.frame_ref != frame_ref:
        raise SelectorResolutionError(
            "Visible selector proof belongs to a different capture frame.",
            selector_id=element.selector_id,
        )
    if element.source_screen is not None and element.source_screen != source_screen:
        raise SelectorResolutionError(
            "Visible selector proof belongs to a different source screen.",
            selector_id=element.selector_id,
            source_screen=element.source_screen,
            effective_screen=source_screen,
        )
    if element.source_layout_id is not None and element.source_layout_id != source_layout_id:
        raise SelectorResolutionError(
            "Visible selector proof belongs to a different source layout.",
            selector_id=element.selector_id,
            source_layout_id=element.source_layout_id,
            effective_layout_id=source_layout_id,
        )
    return replace(
        element,
        frame_ref=element.frame_ref or frame_ref,
        source_screen=element.source_screen or source_screen,
        source_layout_id=element.source_layout_id if element.source_layout_id is not None else source_layout_id,
    )

def bind_list_entry(
    entry: DetectedListEntry,
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> DetectedListEntry:
    """Adds missing list-row provenance while rejecting contradictory proof."""

    if entry.frame_ref is not None and entry.frame_ref != frame_ref:
        raise SelectorResolutionError("List entry proof belongs to a different capture frame.", entry_kind=entry.kind)
    if entry.source_screen is not None and entry.source_screen != source_screen:
        raise SelectorResolutionError("List entry proof belongs to a different source screen.", entry_kind=entry.kind)
    if entry.source_layout_id is not None and entry.source_layout_id != source_layout_id:
        raise SelectorResolutionError("List entry proof belongs to a different source layout.", entry_kind=entry.kind)
    return replace(
        entry,
        frame_ref=entry.frame_ref or frame_ref,
        source_screen=entry.source_screen or source_screen,
        source_layout_id=entry.source_layout_id if entry.source_layout_id is not None else source_layout_id,
    )


def bind_spatial_surface(
    surface: SpatialSurfaceObservation | None,
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> SpatialSurfaceObservation | None:
    """Binds a spatial surface's objects and camera proof to the publishing context."""

    if surface is None:
        return None
    return replace(
        surface,
        objects=tuple(
            bind_spatial_object(
                object_,
                frame_ref=frame_ref,
                source_screen=source_screen,
                source_layout_id=source_layout_id,
            )
            for object_ in surface.objects
        ),
        camera_proof=bind_camera_proof(
            surface.camera_proof,
            frame_ref=frame_ref,
            source_screen=source_screen,
            source_layout_id=source_layout_id,
        ),
    )


def bind_spatial_object(
    object_: DetectedSpatialObject,
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> DetectedSpatialObject:
    """Adds missing spatial-object provenance while rejecting contradictory proof."""

    if object_.frame_ref is not None and object_.frame_ref != frame_ref:
        raise SelectorResolutionError("Spatial object proof belongs to a different capture frame.", object_kind=object_.kind)
    if object_.source_screen is not None and object_.source_screen != source_screen:
        raise SelectorResolutionError("Spatial object proof belongs to a different source screen.", object_kind=object_.kind)
    if object_.source_layout_id is not None and object_.source_layout_id != source_layout_id:
        raise SelectorResolutionError("Spatial object proof belongs to a different source layout.", object_kind=object_.kind)
    return replace(
        object_,
        frame_ref=object_.frame_ref or frame_ref,
        source_screen=object_.source_screen or source_screen,
        source_layout_id=object_.source_layout_id if object_.source_layout_id is not None else source_layout_id,
    )


def bind_camera_proof(
    proof: HomeCityCameraProof | None,
    *,
    frame_ref: FrameRef | None,
    source_screen: ScreenType,
    source_layout_id: str | None,
) -> HomeCityCameraProof | None:
    """Adds missing camera-proof provenance while rejecting contradictory proof."""

    if proof is None:
        return None
    if proof.frame_ref is not None and proof.frame_ref != frame_ref:
        raise SelectorResolutionError("Camera proof belongs to a different capture frame.")
    if proof.source_screen is not None and proof.source_screen != source_screen:
        raise SelectorResolutionError("Camera proof belongs to a different source screen.")
    if proof.source_layout_id is not None and proof.source_layout_id != source_layout_id:
        raise SelectorResolutionError("Camera proof belongs to a different source layout.")
    return replace(
        proof,
        frame_ref=proof.frame_ref or frame_ref,
        source_screen=proof.source_screen or source_screen,
        source_layout_id=proof.source_layout_id if proof.source_layout_id is not None else source_layout_id,
    )
