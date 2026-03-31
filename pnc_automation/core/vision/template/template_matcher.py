"""Baseline Pillow-backed template matching."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch


class PillowTemplateMatcher:
    """Performs conservative exact-image template matching using Pillow."""

    def find_best_match(self, image: Image.Image, template_path: Path, *, threshold: float) -> TemplateMatch | None:
        """Returns the best template hit above the requested confidence threshold."""

        template = _load_template(template_path)
        if template.width > image.width or template.height > image.height:
            return None

        best_match: TemplateMatch | None = None
        rgba_image = image.convert("RGBA")
        for y in range(0, rgba_image.height - template.height + 1):
            for x in range(0, rgba_image.width - template.width + 1):
                crop = rgba_image.crop((x, y, x + template.width, y + template.height))
                confidence = _calculate_confidence(crop, template)
                if confidence < threshold:
                    continue
                match = TemplateMatch(bounds=Bounds(x=x, y=y, width=template.width, height=template.height), confidence=confidence)
                if best_match is None or match.confidence > best_match.confidence:
                    best_match = match
                    if confidence >= 0.9999:
                        return best_match
        return best_match


@lru_cache(maxsize=256)
def _load_template(path: Path) -> Image.Image:
    """Loads one template image and caches it by absolute path."""

    with Image.open(path) as image:
        return image.convert("RGBA")


def _calculate_confidence(candidate: Image.Image, template: Image.Image) -> float:
    """Calculates a normalized confidence score for one template candidate."""

    difference = ImageChops.difference(candidate, template)
    stats = ImageStat.Stat(difference)
    mean_delta = sum(stats.mean) / len(stats.mean)
    return max(0.0, 1.0 - (mean_delta / 255.0))
