"""Synthetic materialize_chat_region fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import Region, SelectorRegistry



def _materialize_chat_region(
    registry: SelectorRegistry,
    selector_id: UiElementId,
    *,
    image_size: tuple[int, int],
) -> Region:
    """Returns one materialized chat region from the canonical selector registry."""

    selector = registry.require(selector_id)
    if selector.relative_bounds is None:
        raise AssertionError(f"Expected relative bounds for selector '{selector_id.value}'.")
    return selector.relative_bounds.materialize_region(image_size=image_size)
