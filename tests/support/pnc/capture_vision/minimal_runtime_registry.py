"""Selector registries for runtime-default OCR fixture tests."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry


def _minimal_runtime_registry() -> SelectorRegistry:
    """Provide the explicitly registered OCR field needed by runtime-default fakes."""

    canonical = build_default_selector_registry()
    return SelectorRegistry(selectors=(canonical.require(UiElementId.PNC_CHAT_INPUT_FIELD),))
