"""Synthetic paint_overview_viewport_marker fixture."""

from __future__ import annotations

from PIL import Image, ImageDraw



def _paint_overview_viewport_marker(image: Image.Image, *, marker_point: tuple[int, int]) -> None:
    """Paints one stylized orange overview viewport marker around the requested point."""

    draw = ImageDraw.Draw(image)
    warm = (255, 170, 52)
    glow = (218, 118, 30)
    half_width = 18
    half_height = 14
    arm = 10
    thickness = 3
    left = marker_point[0] - half_width
    right = marker_point[0] + half_width
    top = marker_point[1] - half_height
    bottom = marker_point[1] + half_height
    for offset in range(thickness):
        draw.line((left, top + offset, left + arm, top + offset), fill=warm, width=1)
        draw.line((left + offset, top, left + offset, top + arm), fill=warm, width=1)
        draw.line((right - arm, top + offset, right, top + offset), fill=warm, width=1)
        draw.line((right - offset, top, right - offset, top + arm), fill=warm, width=1)
        draw.line((left, bottom - offset, left + arm, bottom - offset), fill=warm, width=1)
        draw.line((left + offset, bottom - arm, left + offset, bottom), fill=warm, width=1)
        draw.line((right - arm, bottom - offset, right, bottom - offset), fill=warm, width=1)
        draw.line((right - offset, bottom - arm, right - offset, bottom), fill=warm, width=1)
    draw.rectangle(
        (
            marker_point[0] - 3,
            marker_point[1] - 3,
            marker_point[0] + 3,
            marker_point[1] + 3,
        ),
        fill=glow,
    )
