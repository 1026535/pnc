"""Synthetic encode_png fixture."""

from __future__ import annotations

import io

from PIL import Image



def _encode_png(image: Image.Image) -> bytes:
    """Encodes one PIL image into PNG bytes for screenshot tests."""

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
