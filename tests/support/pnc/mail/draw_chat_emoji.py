"""Synthetic draw_chat_emoji fixture."""

from __future__ import annotations

from PIL import Image, ImageDraw



def _draw_chat_emoji(image: Image.Image, *, top: int, kind: str) -> None:
    """Draws one deterministic non-text chat icon used by the placeholder-classifier tests."""

    draw = ImageDraw.Draw(image)
    if kind == "happy":
        box = (170, top, 230, top + 60)
        draw.ellipse(box, fill=(250, 210, 48))
        draw.ellipse((184, top + 18, 194, top + 28), fill=(20, 20, 20))
        draw.ellipse((206, top + 18, 216, top + 28), fill=(20, 20, 20))
        draw.arc((186, top + 26, 214, top + 48), start=20, end=160, fill=(20, 20, 20), width=3)
        return
    if kind == "eyes":
        draw.ellipse((166, top + 10, 198, top + 42), fill=(245, 245, 245))
        draw.ellipse((202, top + 10, 234, top + 42), fill=(245, 245, 245))
        draw.ellipse((178, top + 20, 188, top + 30), fill=(20, 20, 20))
        draw.ellipse((214, top + 20, 224, top + 30), fill=(20, 20, 20))
        return
    draw.polygon(
        ((180, top + 8), (220, top + 20), (232, top + 54), (200, top + 66), (168, top + 50)),
        fill=(175, 90, 220),
    )
