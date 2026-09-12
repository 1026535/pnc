"""Helpers for adding canonical runtime OCR fields to reduced registries."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry


def _with_runtime_text_fields(registry: SelectorRegistry) -> SelectorRegistry:
    """Add canonical runtime OCR fields to a purpose-built selector fixture."""

    if any(selector.id == UiElementId.PNC_CHAT_INPUT_FIELD for selector in registry.all()):
        return registry
    canonical = build_default_selector_registry()
    return SelectorRegistry(
        selectors=(*registry.all(), canonical.require(UiElementId.PNC_CHAT_INPUT_FIELD)),
    )
