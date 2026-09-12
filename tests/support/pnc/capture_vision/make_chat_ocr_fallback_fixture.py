"""Synthetic make_chat_ocr_fallback_fixture fixture."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import (
    SelectorRegistry,
    build_default_selector_registry,
)

from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.materialize_chat_region import _materialize_chat_region
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


def _make_chat_ocr_fallback_fixture(
    *,
    active_channel: ChatChannel | None,
    draft_ocr_text: str | None,
    image_size: tuple[int, int] = (900, 1600),
) -> tuple[object, SelectorRegistry, _RecordingOcrService]:
    """Builds a synthetic chat screenshot where geometry misses but OCR still proves chat."""

    registry = build_default_selector_registry()
    image = Image.new("RGB", image_size, (15, 28, 68))
    input_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_INPUT_FIELD, image_size=image_size)
    kingdom_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_KINGDOM, image_size=image_size)
    alliance_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_ALLIANCE, image_size=image_size)
    image.paste((210, 210, 210), (input_region.x, input_region.y, input_region.x + input_region.width, input_region.y + input_region.height))
    warm_color = (228, 178, 48)
    cool_color = (64, 68, 82)
    if active_channel is None:
        neutral_color = (118, 112, 106)
        image.paste(
            neutral_color,
            (kingdom_region.x, kingdom_region.y, kingdom_region.x + kingdom_region.width, kingdom_region.y + kingdom_region.height),
        )
        image.paste(
            neutral_color,
            (alliance_region.x, alliance_region.y, alliance_region.x + alliance_region.width, alliance_region.y + alliance_region.height),
        )
    else:
        active_region = kingdom_region if active_channel == ChatChannel.WORLD else alliance_region
        inactive_region = alliance_region if active_channel == ChatChannel.WORLD else kingdom_region
        image.paste(
            warm_color,
            (active_region.x, active_region.y, active_region.x + active_region.width, active_region.y + active_region.height),
        )
        image.paste(
            cool_color,
            (inactive_region.x, inactive_region.y, inactive_region.x + inactive_region.width, inactive_region.y + inactive_region.height),
        )
    lines = [
        _ocr_line("Chat", x=181, y=20, width=113, height=49),
        _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
        _ocr_line("Alliance", x=652, y=116, width=123, height=39),
    ]
    if draft_ocr_text:
        lines.append(
            _ocr_line(
                draft_ocr_text,
                x=input_region.x + 18,
                y=input_region.y + max(8, input_region.height // 5),
                width=max(40, input_region.width - 36),
                height=max(20, input_region.height // 2),
            )
        )
    screenshot = type(
        "Captured",
        (),
        {
            "image": image,
            "artifact": type("Artifact", (), {"path": Path("synthetic_chat_ocr_fallback.png"), "captured_at": None})(),
        },
    )()
    return screenshot, registry, _RecordingOcrService(lines=tuple(lines))
