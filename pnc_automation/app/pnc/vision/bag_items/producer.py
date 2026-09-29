"""Bag card producer and public feature orchestration.

Card OCR is deliberately bounded to each measured card. Parsing, geometry and
preview reward publication live in their own modules so direct tests can avoid
constructing the full observation graph while this producer retains the
supported runtime entry point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagItemFacts,
    TreasureIdentity,
    bag_chest_preview_layouts,
    bag_item_facts_metadata,
    bag_item_inspection_supported,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.bag_items.geometry import (
    CARD_NAME_REGION,
    CARD_TEXT_REGION,
    MAGNIFIER_SEARCH,
    MAGNIFIER_TEMPLATE,
    MAGNIFIER_THRESHOLD,
    NAME_MAX_Y,
    REFERENCE_SIZE,
    TEXT_COLUMN_MIN_X,
    clamp_bounds,
    native_offset_region,
    reference_offset_region,
)
from pnc_automation.app.pnc.vision.bag_items.parsing import (
    CardLine,
    identity_for_tab,
    join_lines,
    mark_duplicate_identities,
    owned_count,
)
from pnc_automation.app.pnc.vision.bag_items.preview import preview_additions
from pnc_automation.app.pnc.vision.bag_layout import detect_bag_card_geometry
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame


@dataclass(frozen=True, slots=True)
class BagItemContentProducer:
    """Produce typed Bag item rows and qualified chest-preview content."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)

    def additions_for_screen(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions | None:
        """Dispatch preview content under its qualified visual layout only."""

        if screen_type == ScreenType.PNC_BAG_CHEST_PREVIEW and layout_id in bag_chest_preview_layouts():
            return self.preview_additions(image=image, ocr_context=ocr_context, layout_id=layout_id)
        return None

    def tab_additions(
        self,
        *,
        image: Image.Image,
        tab: BagTab,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish one measured row per detected Bag card."""

        prepared = self.matcher.prepare_frame(image, reference_size=REFERENCE_SIZE)
        if prepared is None:
            return ObservationAdditions()
        entries = tuple(
            self._card_entry(
                image=image,
                prepared=prepared,
                card_bounds=card.bounds,
                card_clipped=card.clipped,
                card_index=index,
                tab=tab,
                ocr_context=ocr_context,
            )
            for index, card in enumerate(detect_bag_card_geometry(image))
        )
        return ObservationAdditions(list_entries=mark_duplicate_identities(entries))

    def preview_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
        layout_id: str,
    ) -> ObservationAdditions:
        """Publish the preview title, source identity and possible rewards."""

        return preview_additions(image=image, ocr_context=ocr_context, layout_id=layout_id)

    def _card_entry(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        card_bounds: Bounds,
        card_clipped: bool,
        card_index: int,
        tab: BagTab,
        ocr_context: ObservationOcrContext,
    ) -> DetectedListEntry:
        """Measure one Bag card into a typed row with explicit unknowns."""

        if card_clipped:
            return DetectedListEntry(
                kind=ListEntryKind.BAG_ITEM,
                bounds=card_bounds,
                row_status=RowRecognitionStatus.CLIPPED,
            )

        lines = ocr_context.read_lines(
            image,
            native_offset_region(CARD_TEXT_REGION, card_bounds, image),
            purpose=OcrReadPurpose.CONTENT,
            detail=f"bag_card_{tab}_{card_index}",
            required_fact="bag_card_fields",
        )
        scale_x = REFERENCE_SIZE[0] / image.width
        scale_y = REFERENCE_SIZE[1] / image.height
        card_lines = [
            CardLine(
                line=line,
                rel_x=round((line.bounds.x - card_bounds.x) * scale_x),
                rel_y=round((line.bounds.y - card_bounds.y) * scale_y),
            )
            for line in lines
        ]
        name_text = join_lines(
            card_line.line
            for card_line in card_lines
            if card_line.rel_x >= TEXT_COLUMN_MIN_X and card_line.rel_y <= NAME_MAX_Y
        )
        description_text = join_lines(
            card_line.line
            for card_line in card_lines
            if card_line.rel_x >= TEXT_COLUMN_MIN_X and card_line.rel_y > NAME_MAX_Y
        )
        owned_value = owned_count(card_lines)
        identity = identity_for_tab(tab, name_text, description_text)
        if identity is None and name_text is not None:
            retry_text = join_lines(
                sorted(
                    ocr_context.read_lines(
                        image,
                        native_offset_region(CARD_NAME_REGION, card_bounds, image),
                        purpose=OcrReadPurpose.CONTENT,
                        detail=f"bag_card_name_{tab}_{card_index}",
                        required_fact="bag_card_fields",
                    ),
                    key=lambda line: line.bounds.x,
                )
            )
            if retry_text is not None:
                retry_identity = identity_for_tab(tab, retry_text, description_text)
                if retry_identity is not None:
                    name_text = retry_text
                    identity = retry_identity

        magnifier = self._glyph_match(
            prepared,
            MAGNIFIER_TEMPLATE,
            reference_offset_region(MAGNIFIER_SEARCH, card_bounds, image),
        )
        facts = BagItemFacts(
            selected_tab=tab,
            identity=identity,
            owned_count=owned_value,
            inspection_glyph_present=magnifier is not None,
        )
        if name_text is None and description_text is None:
            row_status = RowRecognitionStatus.UNREADABLE
        elif tab in {BagTab.MILITARY, BagTab.MISC}:
            row_status = (
                RowRecognitionStatus.NO_ACTION
                if identity is not None
                else RowRecognitionStatus.UNREADABLE
            )
        elif (
            isinstance(identity, TreasureIdentity)
            and bag_item_inspection_supported(identity)
            and magnifier is not None
        ):
            row_status = RowRecognitionStatus.COMPLETE
        else:
            row_status = RowRecognitionStatus.NO_ACTION
        actionable = row_status == RowRecognitionStatus.COMPLETE
        action_bounds = clamp_bounds(magnifier.bounds, card_bounds) if actionable and magnifier else None
        return DetectedListEntry(
            kind=ListEntryKind.BAG_ITEM,
            bounds=card_bounds,
            title_text=name_text,
            subtitle_text=description_text,
            metadata=bag_item_facts_metadata(facts),
            row_status=row_status,
            action_bounds=action_bounds,
            action_point=action_bounds.center() if action_bounds is not None else None,
            bag_item_facts=facts,
        )

    def _glyph_match(
        self,
        prepared: PreparedFrame,
        template: Path,
        search_region: Bounds,
    ) -> TemplateMatch | None:
        """Return the bounded template hit inside one reference region."""

        return self.matcher.find_best_match(
            prepared,
            template,
            threshold=MAGNIFIER_THRESHOLD,
            search_region=search_region,
        )
