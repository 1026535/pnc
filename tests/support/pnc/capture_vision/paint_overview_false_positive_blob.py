"""Synthetic paint_overview_false_positive_blob fixture."""

from __future__ import annotations

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import Bounds



def _paint_overview_false_positive_blob(image: Image.Image, *, bounds: Bounds) -> None:
    """Paints one unrelated warm blob that the detector must ignore when a better marker candidate exists."""

    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (
            bounds.x,
            bounds.y,
            bounds.x + bounds.width,
            bounds.y + bounds.height,
        ),
        fill=(198, 115, 34),
    )
