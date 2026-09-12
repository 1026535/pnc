"""Synthetic fixtures owned by core.images."""

from __future__ import annotations

import io

from PIL import Image



def build_png_bytes(*, size: tuple[int, int] = (20, 20), color: tuple[int, int, int, int] = (255, 255, 255, 255)) -> bytes:
    """Builds a small PNG image payload for tests."""

    image = Image.new("RGBA", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
