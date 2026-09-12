"""P&C-specific screenshot interpretation services."""

from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionFailurePolicy,
    OcrRegionPlan,
    OcrRegionPurpose,
)

__all__ = [
    "OcrRegionFailurePolicy",
    "OcrRegionPlan",
    "OcrRegionPurpose",
    "SelectorMatch",
]

