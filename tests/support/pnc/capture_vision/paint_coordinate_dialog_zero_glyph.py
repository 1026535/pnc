"""Synthetic paint_coordinate_dialog_zero_glyph fixture."""

from __future__ import annotations

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import Bounds



def _paint_coordinate_dialog_zero_glyph(image: Image.Image, *, bounds: Bounds) -> None:
    """Paints the compact zero glyph shape seen in live coordinate-dialog field crops."""

    pattern = (
        "...####...",
        "..######..",
        ".##....##.",
        ".##....+#.",
        "##......#+",
        "##......##",
        "##......##",
        "##......##",
        "##......##",
        "##......##",
        "##......#+",
        "##......#+",
        ".#+....##.",
        ".##....#+.",
        "..######..",
        "...+#+....",
    )
    draw = ImageDraw.Draw(image)
    glyph_width = len(pattern[0])
    glyph_height = len(pattern)
    left = bounds.x + (bounds.width - glyph_width) // 2
    top = bounds.y + (bounds.height - glyph_height) // 2
    for row_index, row in enumerate(pattern):
        for column_index, marker in enumerate(row):
            if marker == ".":
                continue
            brightness = 220 if marker == "#" else 160
            draw.point((left + column_index, top + row_index), fill=(brightness, brightness, brightness))
