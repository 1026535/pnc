"""Canonical Pet Workshop content producer (PW02).

Under the independently proved ``pet_workshop_*`` layouts this producer reads
typed Workshop facts for the measured surfaces: the merge board, the item and
order detail modals, the help overlay and the premium storage drawer (reported
as the excluded-modal surface). The manor hub carries navigation controls only
and yields no content observation.

Board semantics measured on the PW02 fixtures: a badge medallion marks a
level-gated cell, grass cover marks a seeded cell whose contents stay hidden,
a flat tile interior marks an empty usable cell, and any remaining non-empty
piece is reported occupied with ``item_id=None`` rather than guessed. Piece
interaction state is measured independently against full-cell state
references, including the surrounding overlay area. Unmatched appearances
stay UNKNOWN; piece color and identity never imply action eligibility.

The order strip is measured, not slotted: card panels are located by their
cream panel columns (a card cut by the frame edge is CLIPPED but keeps its
partial reads), and each card's requirement tiles are detected as colored
inlay runs independent of icon identity so an unmatched or missed icon makes
the card UNREADABLE instead of silently shrinking the recipe. Reward counts
are OCR'd only inside zones bounded by independently measured foreground
groups. A missed icon leaves an UNKNOWN reward and cannot expand another
icon's count zone. ``production_mode``
is ORDINARY only while a producer bolt overlay is measured; selection NONE
requires the measured empty bar, and split corner votes resolve to UNKNOWN.

Glyph references (``.local-data/pw02`` provenance): cell overlays, selection
brackets and controls, order-strip requirement/reward icons and order-detail
icons were all cropped from the 2026-09-16/17 measurement captures reviewed
for this packet. Match margins on the reference fixtures: item templates
>= .90 vs <= .88 cross-cell noise, badge digits discriminate by argmax
(intended >= .96 vs <= .89), selection bar controls >= .90, bolt overlays
>= .72 vs <= .52.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopObservation,
    WorkshopOrder,
    WorkshopOrderSurvey,
    WorkshopState,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
    WorkshopSurfaceKind,
    WorkshopView,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    load_pet_workshop_catalog,
)
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from . import board as board_reader
from . import geometry, matching
from . import orders as order_reader
from .constants import (
    _BACK_SEARCH,
    _BACK_TEMPLATE,
    _CLOSE_X_TEMPLATE,
    _CONTROL_THRESHOLD,
    _DETAIL_ICON_THRESHOLD,
    _DETAIL_REQUIREMENT_TEMPLATES,
    _DETAIL_REWARD_TEMPLATES,
    _HELP_CLOSE_SEARCH,
    _INSPECT_SEARCH,
    _INSPECT_TEMPLATE,
    _ITEM_DETAIL_CLOSE_SEARCH,
    _OD_PEDESTAL_MERGE_GAP,
    _OD_REQUIREMENT_BAND,
    _OD_REQ_PEDESTAL_BAND,
    _OD_REWARD_BAND,
    _OD_REW_PEDESTAL_BAND,
    _ORDER_DETAIL_CLOSE_SEARCH,
    _RECYCLE_SEARCH,
    _RECYCLE_TEMPLATE,
    _REFERENCE_SIZE,
)

PET_WORKSHOP_BOARD_LAYOUT_ID = "pet_workshop_board"
PET_WORKSHOP_ITEM_DETAIL_LAYOUT_ID = "pet_workshop_item_detail"
PET_WORKSHOP_ORDER_DETAIL_LAYOUT_ID = "pet_workshop_order_detail"
PET_WORKSHOP_HELP_LAYOUT_ID = "pet_workshop_help"
PET_WORKSHOP_STORAGE_LAYOUT_ID = "pet_workshop_storage"


@dataclass(frozen=True, slots=True)
class WorkshopContentProducer:
    """Produce typed Workshop state and measured view facts per surface."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)
    catalog: PetWorkshopCatalog = field(default_factory=load_pet_workshop_catalog)

    def additions_for_screen(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions | None:
        """Dispatch Workshop screen content under its proved visual layout only."""

        if screen_type == ScreenType.PNC_PET_WORKSHOP and layout_id == PET_WORKSHOP_BOARD_LAYOUT_ID:
            return self.board_additions(image=image, ocr_context=ocr_context)
        if (
            screen_type == ScreenType.PNC_PET_WORKSHOP_ITEM_DETAIL
            and layout_id == PET_WORKSHOP_ITEM_DETAIL_LAYOUT_ID
        ):
            return self._surface_additions(
                image=image,
                surface=WorkshopSurfaceKind.ITEM_DETAIL,
                close_search=_ITEM_DETAIL_CLOSE_SEARCH,
            )
        if (
            screen_type == ScreenType.PNC_PET_WORKSHOP_ORDER_DETAIL
            and layout_id == PET_WORKSHOP_ORDER_DETAIL_LAYOUT_ID
        ):
            return self.order_detail_additions(image=image, ocr_context=ocr_context)
        if screen_type == ScreenType.PNC_PET_WORKSHOP_HELP and layout_id == PET_WORKSHOP_HELP_LAYOUT_ID:
            return self._surface_additions(
                image=image,
                surface=WorkshopSurfaceKind.HELP,
                close_search=_HELP_CLOSE_SEARCH,
            )
        if (
            screen_type == ScreenType.PNC_PET_WORKSHOP_STORAGE
            and layout_id == PET_WORKSHOP_STORAGE_LAYOUT_ID
        ):
            return self._surface_additions(
                image=image,
                surface=WorkshopSurfaceKind.EXCLUDED_MODAL,
            )
        return None

    def board_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish the measured board, header and order-strip facts."""

        prepared = self.matcher.prepare_frame(image, reference_size=_REFERENCE_SIZE)
        if prepared is None:
            return self._unread(image=image, surface=WorkshopSurfaceKind.BOARD)
        cells, cell_bounds = board_reader.read_cells(
            image=image, prepared=prepared, matcher=self.matcher, catalog=self.catalog
        )
        level, workshop_exp, energy = board_reader.read_header(
            image=image, ocr_context=ocr_context
        )
        orders, order_views, strip_bounds = order_reader.read_orders(
            image=image,
            prepared=prepared,
            matcher=self.matcher,
            ocr_context=ocr_context,
        )
        state = WorkshopState(
            board=self.catalog.board,
            surface=WorkshopSurfaceKind.BOARD,
            cells=cells,
            energy=energy,
            production_mode=board_reader.read_production_mode(self.matcher, prepared),
            workshop_level=level,
            workshop_exp=workshop_exp,
            selection=board_reader.read_selection(
                prepared=prepared, matcher=self.matcher, catalog=self.catalog
            ),
            order_survey=WorkshopOrderSurvey(
                orders=orders,
                coverage=(
                    WorkshopSurveyCoverage.PARTIAL
                    if strip_bounds is None
                    or any(
                        order.completeness != RowRecognitionStatus.COMPLETE
                        for order in orders
                    )
                    else WorkshopSurveyCoverage.COMPLETE
                ),
                freshness=WorkshopSurveyFreshness.CURRENT,
            ),
        )
        view = WorkshopView(
            cell_bounds=cell_bounds,
            order_views=order_views,
            order_strip_bounds=(
                geometry.scaled_region(strip_bounds, image) if strip_bounds is not None else None
            ),
            detail_control_bounds=matching.control(
                self.matcher,
                prepared, _INSPECT_TEMPLATE, _INSPECT_SEARCH, _CONTROL_THRESHOLD
            ),
            close_control_bounds=matching.control(
                self.matcher,
                prepared, _BACK_TEMPLATE, _BACK_SEARCH, _CONTROL_THRESHOLD
            ),
            recycle_control_bounds=matching.control(
                self.matcher,
                prepared, _RECYCLE_TEMPLATE, _RECYCLE_SEARCH, _CONTROL_THRESHOLD
            ),
            image_size=image.size,
        )
        return ObservationAdditions(workshop=WorkshopObservation(state=state, view=view))

    def order_detail_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish the order detail modal's measured target and reward facts."""

        prepared = self.matcher.prepare_frame(image, reference_size=_REFERENCE_SIZE)
        if prepared is None:
            return self._unread(image=image, surface=WorkshopSurfaceKind.ORDER_DETAIL)
        req_icons = matching.icons(
            self.matcher,
            prepared,
            templates=_DETAIL_REQUIREMENT_TEMPLATES,
            region=_OD_REQUIREMENT_BAND,
            threshold=_DETAIL_ICON_THRESHOLD,
        )
        req_pedestals = geometry.pedestal_runs(prepared.pixels, _OD_REQ_PEDESTAL_BAND)
        rew_icons = matching.icons(
            self.matcher,
            prepared,
            templates=_DETAIL_REWARD_TEMPLATES,
            region=_OD_REWARD_BAND,
            threshold=_DETAIL_ICON_THRESHOLD,
        )
        rew_pedestals = geometry.pedestal_runs(
            prepared.pixels, _OD_REW_PEDESTAL_BAND, merge_gap=_OD_PEDESTAL_MERGE_GAP
        )
        rewards, orphans = order_reader.read_detail_rewards(
            self.matcher,
            image=image,
            prepared=prepared,
            ocr_context=ocr_context,
            icons=rew_icons,
            pedestals=rew_pedestals,
        )
        complete = (
            geometry.pedestals_covered(req_pedestals, req_icons, prepared)
            and geometry.pedestals_covered(rew_pedestals, rew_icons, prepared)
            and not orphans
            and bool(req_icons)
        )
        order = WorkshopOrder(
            order_ref=1,
            requirements=geometry.counted_icons(req_icons),
            rewards=rewards,
            completeness=(
                RowRecognitionStatus.COMPLETE if complete else RowRecognitionStatus.UNREADABLE
            ),
            ready=None,
            source="order_detail",
        )
        state = WorkshopState(
            board=self.catalog.board,
            surface=WorkshopSurfaceKind.ORDER_DETAIL,
            order_survey=WorkshopOrderSurvey(
                orders=(order,),
                coverage=WorkshopSurveyCoverage.PARTIAL,
                freshness=WorkshopSurveyFreshness.CURRENT,
            ),
        )
        view = WorkshopView(
            close_control_bounds=matching.control(
                self.matcher,
                prepared, _CLOSE_X_TEMPLATE, _ORDER_DETAIL_CLOSE_SEARCH, _CONTROL_THRESHOLD
            ),
            image_size=image.size,
        )
        return ObservationAdditions(workshop=WorkshopObservation(state=state, view=view))

    def _surface_additions(
        self,
        *,
        image: Image.Image,
        surface: WorkshopSurfaceKind,
        close_search: Bounds | None = None,
        close_template: Path = _CLOSE_X_TEMPLATE,
    ) -> ObservationAdditions:
        """Publish a control-only modal surface with its measured close control.

        ``close_search=None`` records a surface whose frame exposes no dismiss
        control (the storage sheet is dismissed by tapping outside it).
        """

        prepared = self.matcher.prepare_frame(image, reference_size=_REFERENCE_SIZE)
        view = WorkshopView(
            close_control_bounds=(
                matching.control(
                    self.matcher, prepared, close_template, close_search, _CONTROL_THRESHOLD
                )
                if prepared is not None and close_search is not None
                else None
            ),
            image_size=image.size,
        )
        return ObservationAdditions(
            workshop=WorkshopObservation(
                state=WorkshopState(board=self.catalog.board, surface=surface),
                view=view,
            )
        )

    def _unread(self, *, image: Image.Image, surface: WorkshopSurfaceKind) -> ObservationAdditions:
        """Publish the recognized surface with all readings left unknown."""

        return ObservationAdditions(
            workshop=WorkshopObservation(
                state=WorkshopState(board=self.catalog.board, surface=surface),
                view=WorkshopView(image_size=image.size),
            )
        )
