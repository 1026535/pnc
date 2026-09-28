"""Shared core chat doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


def chat_frame(
    active_channel: ChatChannel | None,
    *,
    selector: UiElementId | None = None,
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    captured_at: datetime | None = None,
    blocked: bool = False,
    screen: ScreenType = ScreenType.PNC_CHAT,
) -> Observation:
    """Build one typed Chat frame with optional current-frame tab evidence."""

    visible_elements = {}
    if selector is not None:
        visible_elements[selector] = VisibleElement(
            selector,
            Bounds(10, 20, 40, 40),
            1.0,
            source_kind=source_kind,
        )
    return Observation(
        screen_type=screen,
        visible_elements=visible_elements,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
        active_chat_channel=active_channel,
    )
