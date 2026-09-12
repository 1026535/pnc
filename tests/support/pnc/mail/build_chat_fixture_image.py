"""Synthetic build_chat_fixture_image fixture."""

from __future__ import annotations

from PIL import Image



def _build_chat_fixture_image(*, image_size: tuple[int, int] = (900, 1600)) -> Image.Image:
    """Builds the shared dark chat-surface image used by OCR-only and icon-placeholder tests."""

    return Image.new("RGB", image_size, (18, 30, 72))
