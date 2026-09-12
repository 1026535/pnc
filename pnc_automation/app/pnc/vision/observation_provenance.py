"""Bind measured observation content to its owning capture and screen decision."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from pnc_automation.app.pnc.domain.observation import DetectedListEntry, VisibleElement
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
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
