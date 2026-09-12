"""Synthetic paint_synthetic_world_overview_map fixture."""

from __future__ import annotations

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import Bounds



def _paint_synthetic_world_overview_map(image: Image.Image, *, map_region_bounds: Bounds) -> None:
    """Paints one simple parchment-like overview map body inside the calibrated selector bounds."""

    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (
            map_region_bounds.x,
            map_region_bounds.y,
            map_region_bounds.x + map_region_bounds.width,
            map_region_bounds.y + map_region_bounds.height,
        ),
        fill=(156, 138, 101),
    )
    draw.rectangle(
        (
            map_region_bounds.x + 2,
            map_region_bounds.y + 2,
            map_region_bounds.x + map_region_bounds.width - 2,
            map_region_bounds.y + map_region_bounds.height - 2,
        ),
        outline=(86, 74, 56),
        width=2,
    )
