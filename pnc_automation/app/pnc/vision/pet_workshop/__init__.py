"""Pet Workshop visual content recognition.

The package keeps the historical ``vision.pet_workshop`` import path while
grouping the producer's board, order, and OCR responsibilities internally.
"""

from .producer import (
    PET_WORKSHOP_BOARD_LAYOUT_ID,
    PET_WORKSHOP_HELP_LAYOUT_ID,
    PET_WORKSHOP_ITEM_DETAIL_LAYOUT_ID,
    PET_WORKSHOP_ORDER_DETAIL_LAYOUT_ID,
    PET_WORKSHOP_STORAGE_LAYOUT_ID,
    WorkshopContentProducer,
)

__all__ = [
    "PET_WORKSHOP_BOARD_LAYOUT_ID",
    "PET_WORKSHOP_HELP_LAYOUT_ID",
    "PET_WORKSHOP_ITEM_DETAIL_LAYOUT_ID",
    "PET_WORKSHOP_ORDER_DETAIL_LAYOUT_ID",
    "PET_WORKSHOP_STORAGE_LAYOUT_ID",
    "WorkshopContentProducer",
]
