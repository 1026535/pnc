"""Public Bag vision API.

The package keeps the historical ``pnc_automation.app.pnc.vision.bag_items``
import path while internal ownership is split between card production, pure
OCR parsing, measured geometry and preview publication.
"""

from pnc_automation.app.pnc.vision.bag_items.producer import BagItemContentProducer

BAG_LAYOUT_ID = "bag"

__all__ = ["BAG_LAYOUT_ID", "BagItemContentProducer"]
