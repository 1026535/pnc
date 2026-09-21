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

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from PIL import Image

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopEnergy,
    WorkshopItemStatus,
    WorkshopObservation,
    WorkshopOccupancy,
    WorkshopOrder,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderSurvey,
    WorkshopOrderView,
    WorkshopProductionMode,
    WorkshopSelection,
    WorkshopSelectionKind,
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
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrReadPurpose,
)
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

PET_WORKSHOP_BOARD_LAYOUT_ID = "pet_workshop_board"
PET_WORKSHOP_ITEM_DETAIL_LAYOUT_ID = "pet_workshop_item_detail"
PET_WORKSHOP_ORDER_DETAIL_LAYOUT_ID = "pet_workshop_order_detail"
PET_WORKSHOP_HELP_LAYOUT_ID = "pet_workshop_help"
PET_WORKSHOP_STORAGE_LAYOUT_ID = "pet_workshop_storage"

_REFERENCE_SIZE = (540, 960)

# Measured board grid (540 x 960 reference): 7 columns x 9 rows, cell ids run
# bottom-up so board row 1 is the lowest display row.
_CELL_X0 = 22.2
_CELL_Y0 = 240.6
_CELL_W = 70.98
_CELL_H = 70.8

# Header OCR regions: "Lv.N" label, "N/M" EXP bar and "N/M" energy pill.
_LEVEL_REGION = Bounds(x=140, y=4, width=60, height=38)
_EXP_REGION = Bounds(x=208, y=4, width=175, height=38)
_ENERGY_REGION = Bounds(x=388, y=4, width=150, height=38)
_LEVEL_SEARCH = re.compile(r"LV\.?\s*(\d+)", re.IGNORECASE)
_GAUGE_SEARCH = re.compile(r"(\d+)\s*/\s*(\d+)")

# Order strip: card panels are detected from their non-background columns in
# the union band (reward row + requirement tile row), then the timer-column
# run is rejected by reward-row panel fraction. Card art starts ~y88; the
# panel body ends ~y225 where the wood chrome begins (~y227).
_CARD_UNION_BAND = (144, 228)
_CARD_PANEL_BAND = (147, 187)
_CARD_PANEL_TAIL_SCAN = (150, 228)
_CARD_TOP_SCAN = (60, 146)
_CARD_MIN_WIDTH = 30
# Full panels measure 168/169 px on both qualified Workshop levels. A
# narrower visible fragment cannot prove full requirements, even when it
# touches the timer viewport rather than the physical screenshot edge.
_CARD_FULL_MIN_WIDTH = 160
_CARD_CLIP_RIGHT_X = 532
_CARD_CLIP_LEFT_X = 92
# Requirement tiles sit as a centered group inside the card, each ~48-52 px
# wide with colored inlay interiors that read as non-panel columns.
_CARD_TILE_BAND = (190, 38)
_CARD_REQ_ICON_BAND = (180, 52)
_CARD_TILE_SLOT_PITCH = 52
_TILE_RUN_MIN_WIDTH = 16
# Reward icons sit on the reward row; each count hugs its icon's right edge.
_CARD_REWARD_BAND = (138, 36)
# The uninterrupted cream baseline below the reward glyphs identifies the
# reward panel, including cards whose panel occupies only their right half.
_REWARD_PANEL_BASELINE = 167
_REWARD_INK_BAND = (148, 164)
_REWARD_GROUP_GAP = 8
_CARD_COMPLETE_OFFSET = Bounds(x=80, y=90, width=96, height=44)
# Strip surface: the wood chrome runs along y227-238 across the whole widget;
# the measured top is the first row where the strip span is mostly content.
_STRIP_CHROME_BAND = (227, 242)
_STRIP_TOP_SCAN = (40, 145)
_STRIP_BOTTOM = 240

# Selection brackets and the selection-bar controls (bottom bar).
_BOARD_REGION = Bounds(x=15, y=235, width=512, height=615)
_INSPECT_SEARCH = Bounds(x=50, y=865, width=160, height=85)
_RECYCLE_SEARCH = Bounds(x=330, y=858, width=195, height=95)
_BACK_SEARCH = Bounds(x=2, y=2, width=74, height=62)
# The unselected bottom bar is a flat texture; a populated bar carries the
# portrait card and action controls, which is measurable edge evidence.
_SELECTION_BAR_REGION = Bounds(x=60, y=860, width=420, height=80)
_BAR_EMPTY_EDGE_MAX = 0.08
# Interior cells carry four corner brackets; cells on the board's bottom edge
# lose the lower pair to the selection bar, so two confident corners suffice.
_SELECTION_MIN_CORNERS = 2

# Modal close controls sit at each overlay's top-right corner.
_ITEM_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=215, width=95, height=80)
_ORDER_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=185, width=95, height=90)
_HELP_CLOSE_SEARCH = Bounds(x=430, y=100, width=95, height=80)

# Order-detail modal: requirement and reward icons stand on blue pedestals
# whose lip rows are measurable coverage (an unmatched pedestal preserves an
# unknown requirement/reward rather than vanishing). Reward counts float at
# each icon's top edge.
_OD_REQUIREMENT_BAND = Bounds(x=160, y=285, width=370, height=95)
_OD_REQ_PEDESTAL_BAND = (366, 384)
_OD_REWARD_BAND = Bounds(x=180, y=440, width=360, height=60)
_OD_REW_PEDESTAL_BAND = (508, 522)
_OD_REWARD_TOKEN_BAND = Bounds(x=140, y=424, width=400, height=76)
_OD_PEDESTAL_MIN_WIDTH = 30
_OD_PEDESTAL_PAD_X = 20
_OD_COUNT_ZONE_Y = (-20, 4)
_OD_COUNT_ZONE_RIGHT_PAD = 18

_CELL_OVERLAY_THRESHOLD = 0.90
_CELL_ITEM_THRESHOLD = 0.90
_CELL_EMPTY_THRESHOLD = 0.90
_SELECTION_THRESHOLD = 0.85
_CONTROL_THRESHOLD = 0.85
_STRIP_ICON_THRESHOLD = 0.90
_DETAIL_ICON_THRESHOLD = 0.90
_BOLT_THRESHOLD = 0.70
_CELL_STATE_THRESHOLD = 0.97

_DATA_DIR = Path(__file__).resolve().parent / "data" / "screen_anchors"

# Board pieces recognized at cell scale. Templates carry identity only. Unmodeled
# pieces such as bread, bags and bolt-producers stay occupied-with-unknown-id.
_ITEM_TEMPLATES = (
    ("pet_workshop_item_tree_4.png", 20004),
    ("pet_workshop_item_fruit_1.png", 20101),
    ("pet_workshop_item_fruit_2.png", 20102),
    ("pet_workshop_item_fruit_3.png", 20103),
    ("pet_workshop_item_fruit_5.png", 20105),
    ("pet_workshop_item_wood_4.png", 20204),
    ("pet_workshop_item_wood_5.png", 20205),
    ("pet_workshop_item_wood_7.png", 20207),
    ("pet_workshop_item_wood_8.png", 20208),
    ("pet_workshop_item_bowl_5.png", 30105),
    ("pet_workshop_item_treasure_1.png", 10101),
    ("pet_workshop_item_treasure_6.png", 10106),
    ("pet_workshop_item_statue_4.png", 10204),
    ("pet_workshop_item_clay_2.png", 30002),
    ("pet_workshop_item_bowl_1_inactive.png", 30101),
)
# Independently reviewed full-cell appearances, cropped two pixels inside
# each cell using _cell_region on the normalized tracked board fixtures.
# These include the overlay area omitted by the tight identity glyph crops.
# Unsupported bubble/feed-lock/transition appearances must stay UNKNOWN.
_CELL_STATE_TEMPLATES = (
    (WorkshopItemStatus.NORMAL, "lv8", (1, 2, 4, 5, 7, 8, 12, 15, 17, 20, 24, 36, 46)),
    (WorkshopItemStatus.NORMAL, "lv6", (4, 8, 9)),
    (WorkshopItemStatus.INACTIVE, "lv8", (3, 52, 56)),
    (WorkshopItemStatus.INACTIVE, "lv6", (1,)),
)
_BADGE_TEMPLATES = tuple(
    _DATA_DIR / f"pet_workshop_ov_badge_{level}.png" for level in (7, 8, 9, 10, 11)
)
_GRASS_TEMPLATE = _DATA_DIR / "pet_workshop_ov_grass.png"
_EMPTY_CELL_TEMPLATE = _DATA_DIR / "pet_workshop_cell_empty.png"
# Producer "tap to generate" bolt badge; measured evidence of the ordinary
# per-produce production mode on this frame.
_BOLT_TEMPLATE = _DATA_DIR / "pet_workshop_ov_bolt.png"

# Order-strip requirement icons at slot scale (36 x 42 crops).
_STRIP_REQUIREMENT_TEMPLATES = (
    ("pet_workshop_req_food_9.png", 31109),
    ("pet_workshop_req_fruit_4.png", 20104),
    ("pet_workshop_req_fruit_5.png", 20105),
    ("pet_workshop_req_statue_4.png", 10204),
    ("pet_workshop_req_treasure_6.png", 10106),
    ("pet_workshop_req_treasure_7.png", 10107),
    ("pet_workshop_req_wood_10.png", 20210),
)
_STRIP_REWARD_TEMPLATES = (
    ("pet_workshop_rew_chest.png", WorkshopOrderRewardCategory.CHEST),
    ("pet_workshop_rew_exp.png", WorkshopOrderRewardCategory.WORKSHOP_EXP),
    ("pet_workshop_rew_feed.png", WorkshopOrderRewardCategory.FEED),
    ("pet_workshop_rew_lasso.png", WorkshopOrderRewardCategory.BEAST_LASSO),
)

# Order-detail icons at modal scale (~70 px requirement, ~44 px reward crops).
_DETAIL_REQUIREMENT_TEMPLATES = (
    ("pet_workshop_od_req_fruit_4.png", 20104),
    ("pet_workshop_od_req_treasure_6.png", 10106),
)
_DETAIL_REWARD_TEMPLATES = (
    ("pet_workshop_od_rew_feed.png", WorkshopOrderRewardCategory.FEED),
    ("pet_workshop_od_rew_exp.png", WorkshopOrderRewardCategory.WORKSHOP_EXP),
)

# The selection bracket's four orientations: the authored corner rotated.
_SEL_CORNER_TEMPLATES = tuple(
    _DATA_DIR / f"pet_workshop_sel_corner{suffix}.png"
    for suffix in ("", "_tr", "_br", "_bl")
)
_INSPECT_TEMPLATE = _DATA_DIR / "pet_workshop_sel_inspect.png"
_RECYCLE_TEMPLATE = _DATA_DIR / "pet_workshop_sel_recycle.png"
_COMPLETE_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_complete.png"
_COMPLETE_TEMPLATE_SIZE = (72, 19)
_BACK_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_back.png"
_CLOSE_X_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_close_x.png"

_NUMERIC_TOKEN = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class _CardExtent:
    """Measured reference-space span of one order-strip card."""

    x0: int
    x1: int
    top: int
    bottom: int
    clipped: bool


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
        cells, cell_bounds = self._read_cells(image=image, prepared=prepared)
        level, workshop_exp, energy = self._read_header(image=image, ocr_context=ocr_context)
        orders, order_views, strip_bounds = self._read_orders(
            image=image, prepared=prepared, ocr_context=ocr_context
        )
        state = WorkshopState(
            board=self.catalog.board,
            surface=WorkshopSurfaceKind.BOARD,
            cells=cells,
            energy=energy,
            production_mode=self._read_production_mode(prepared),
            workshop_level=level,
            workshop_exp=workshop_exp,
            selection=self._read_selection(prepared=prepared),
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
                _scaled_region(strip_bounds, image) if strip_bounds is not None else None
            ),
            detail_control_bounds=self._control(
                prepared, _INSPECT_TEMPLATE, _INSPECT_SEARCH, _CONTROL_THRESHOLD
            ),
            close_control_bounds=self._control(
                prepared, _BACK_TEMPLATE, _BACK_SEARCH, _CONTROL_THRESHOLD
            ),
            recycle_control_bounds=self._control(
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
        req_icons = self._icon_matches(
            prepared,
            templates=_DETAIL_REQUIREMENT_TEMPLATES,
            region=_OD_REQUIREMENT_BAND,
            threshold=_DETAIL_ICON_THRESHOLD,
        )
        req_pedestals = _pedestal_runs(prepared.pixels, _OD_REQ_PEDESTAL_BAND)
        rew_icons = self._icon_matches(
            prepared,
            templates=_DETAIL_REWARD_TEMPLATES,
            region=_OD_REWARD_BAND,
            threshold=_DETAIL_ICON_THRESHOLD,
        )
        rew_pedestals = _pedestal_runs(prepared.pixels, _OD_REW_PEDESTAL_BAND)
        rewards, orphans = self._read_detail_rewards(
            image=image,
            prepared=prepared,
            ocr_context=ocr_context,
            icons=rew_icons,
            pedestals=rew_pedestals,
        )
        complete = (
            _pedestals_covered(req_pedestals, req_icons, prepared)
            and _pedestals_covered(rew_pedestals, rew_icons, prepared)
            and not orphans
            and bool(req_icons)
        )
        order = WorkshopOrder(
            order_ref=1,
            requirements=_counted_icons(req_icons),
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
            close_control_bounds=self._control(
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
                self._control(prepared, close_template, close_search, _CONTROL_THRESHOLD)
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

    def _read_cells(
        self, *, image: Image.Image, prepared: PreparedFrame
    ) -> tuple[tuple[WorkshopCell, ...], dict[int, Bounds]]:
        """Classify every board cell from overlay, item and empty evidence."""

        cells: list[WorkshopCell] = []
        cell_bounds: dict[int, Bounds] = {}
        board = self.catalog.board
        for row in range(1, board.rows + 1):
            for column in range(1, board.columns + 1):
                cell_id = board.cell_id(row, column)
                region = _cell_region(row, column)
                cell_bounds[cell_id] = _scaled_region(region, image)
                cells.append(self._read_cell(cell_id=cell_id, row=row, column=column,
                                             prepared=prepared, region=region))
        return tuple(cells), cell_bounds

    def _read_cell(
        self, *, cell_id: int, row: int, column: int, prepared: PreparedFrame, region: Bounds
    ) -> WorkshopCell:
        """Classify one cell: badge gate, grass cover, known piece, empty or unknown."""

        if self._best(prepared, _BADGE_TEMPLATES, region, _CELL_OVERLAY_THRESHOLD) is not None:
            return WorkshopCell(
                cell_id=cell_id, row=row, column=column,
                access=WorkshopCellAccess.LOCKED, occupancy=WorkshopOccupancy.EMPTY,
            )
        if self._best(prepared, (_GRASS_TEMPLATE,), region, _CELL_OVERLAY_THRESHOLD) is not None:
            return WorkshopCell(
                cell_id=cell_id, row=row, column=column,
                access=WorkshopCellAccess.LOCKED, occupancy=WorkshopOccupancy.UNKNOWN,
            )
        match = self._best(
            prepared,
            tuple(_DATA_DIR / name for name, _item_id in _ITEM_TEMPLATES),
            _inflate_region(region, 5),
            _CELL_ITEM_THRESHOLD,
        )
        if match is not None:
            return WorkshopCell(
                cell_id=cell_id, row=row, column=column,
                access=WorkshopCellAccess.USABLE, occupancy=WorkshopOccupancy.OCCUPIED,
                item_id=_ITEM_TEMPLATES[match[1]][1],
                item_status=self._read_piece_status(prepared, region),
            )
        if self._best(
            prepared, (_EMPTY_CELL_TEMPLATE,), _cell_center_region(region), _CELL_EMPTY_THRESHOLD
        ) is not None:
            return WorkshopCell(
                cell_id=cell_id, row=row, column=column,
                access=WorkshopCellAccess.USABLE, occupancy=WorkshopOccupancy.EMPTY,
            )
        return WorkshopCell(
            cell_id=cell_id, row=row, column=column,
            access=WorkshopCellAccess.USABLE, occupancy=WorkshopOccupancy.OCCUPIED,
            item_status=self._read_piece_status(prepared, region),
        )

    def _read_piece_status(self, prepared: PreparedFrame, region: Bounds) -> WorkshopItemStatus:
        """Qualify a state from full-cell appearance independently of sprite identity.

        More than one supported state matching, or no qualified state match,
        yields UNKNOWN. This avoids deriving NORMAL solely from the absence
        of grey pixels when bubble/feed-lock appearances are still unqualified.
        """

        states = {
            status
            for status, level, cells in _CELL_STATE_TEMPLATES
            if self._best(
                prepared,
                tuple(_DATA_DIR / f"pet_workshop_state_{status.value}_{level}_{cell}.png"
                      for cell in cells),
                region,
                _CELL_STATE_THRESHOLD,
            ) is not None
        }
        return states.pop() if len(states) == 1 else WorkshopItemStatus.UNKNOWN

    def _read_header(
        self, *, image: Image.Image, ocr_context: ObservationOcrContext
    ) -> tuple[int | None, int | None, WorkshopEnergy]:
        """Read the header level label, EXP gauge and energy pill."""

        level_text = self._read_region_text(
            image=image, ocr_context=ocr_context, region=_LEVEL_REGION, detail="workshop_level"
        )
        level_match = _LEVEL_SEARCH.search(level_text)
        exp_text = self._read_region_text(
            image=image, ocr_context=ocr_context, region=_EXP_REGION, detail="workshop_exp"
        )
        exp_match = _GAUGE_SEARCH.search(exp_text)
        energy_text = self._read_region_text(
            image=image, ocr_context=ocr_context, region=_ENERGY_REGION, detail="workshop_energy"
        )
        energy_match = _GAUGE_SEARCH.search(energy_text)
        energy_capacity = int(energy_match.group(2)) if energy_match else None
        energy_current = int(energy_match.group(1)) if energy_match else None
        if energy_capacity is not None and energy_capacity <= 0:
            # A nonpositive capacity denominator is OCR noise, not a reading;
            # both gauge fields stay unknown rather than crash the model or
            # publish a false zero.
            energy_current = energy_capacity = None
        return (
            int(level_match.group(1)) if level_match else None,
            int(exp_match.group(1)) if exp_match else None,
            WorkshopEnergy(current=energy_current, capacity=energy_capacity),
        )

    def _read_production_mode(self, prepared: PreparedFrame) -> WorkshopProductionMode:
        """Report ORDINARY only while a producer bolt overlay is measured."""

        if self._control(prepared, _BOLT_TEMPLATE, _BOARD_REGION, _BOLT_THRESHOLD) is not None:
            return WorkshopProductionMode.ORDINARY
        return WorkshopProductionMode.UNKNOWN

    def _read_selection(self, *, prepared: PreparedFrame) -> WorkshopSelection:
        """Locate the selected cell from its corner brackets, voting by majority.

        A selection needs at least two corner votes on one cell with no
        second cell holding two or more; split votes and missing evidence
        resolve to UNKNOWN rather than guessing. NONE is published only when
        the selection bar is additionally measured empty, so a missing corner
        hit on a populated bar still abstains.
        """

        votes: dict[int, tuple[int, float]] = {}
        accepted: list[tuple[int, int]] = []
        for template in _SEL_CORNER_TEMPLATES:
            for match in self.matcher.find_matches(
                prepared,
                template,
                threshold=_SELECTION_THRESHOLD,
                search_region=_BOARD_REGION,
            ):
                center = match.bounds.center()
                if any(
                    abs(center[0] - other[0]) <= 8 and abs(center[1] - other[1]) <= 8
                    for other in accepted
                ):
                    continue
                cell_id = self._cell_id_at(prepared=prepared, point=center)
                if cell_id is None:
                    continue
                accepted.append(center)
                count, confidence = votes.get(cell_id, (0, 0.0))
                votes[cell_id] = (count + 1, max(confidence, match.confidence))
        ranked = sorted(votes.items(), key=lambda item: (-item[1][0], -item[1][1], item[0]))
        if ranked:
            (cell_id, (top_votes, _confidence)), *rest = ranked
            if top_votes >= _SELECTION_MIN_CORNERS and all(
                count <= 1 for _c, (count, _cf) in rest
            ):
                return WorkshopSelection(
                    kind=WorkshopSelectionKind.SELECTED, cell_id=cell_id
                )
            return WorkshopSelection(kind=WorkshopSelectionKind.UNKNOWN)
        return WorkshopSelection(
            kind=(
                WorkshopSelectionKind.NONE
                if _bar_empty(prepared.pixels)
                else WorkshopSelectionKind.UNKNOWN
            )
        )

    def _read_orders(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        ocr_context: ObservationOcrContext,
    ) -> tuple[tuple[WorkshopOrder, ...], tuple[WorkshopOrderView, ...], Bounds | None]:
        """Read each measured order card: coverage-checked requirements and rewards.

        Card panels are detected from pixel evidence rather than assumed slot
        positions; each card's requirement tiles are measured independently of
        icon identity so an unmatched or missed tile marks the card
        UNREADABLE instead of silently shrinking the recipe.
        """

        cards = _detect_card_extents(prepared.pixels)
        strip_bounds = _order_strip_bounds(prepared.pixels)
        orders: list[WorkshopOrder] = []
        views: list[WorkshopOrderView] = []
        for index, card in enumerate(cards):
            order_ref = index + 1
            requirements, covered = self._read_card_requirements(prepared, card)
            rewards, orphan_reward = self._read_strip_rewards(
                image=image,
                prepared=prepared,
                ocr_context=ocr_context,
                card=card,
                order_ref=order_ref,
            )
            complete_search = _clipped(
                Bounds(
                    x=card.x0 + _CARD_COMPLETE_OFFSET.x,
                    y=_CARD_COMPLETE_OFFSET.y,
                    width=_CARD_COMPLETE_OFFSET.width,
                    height=_CARD_COMPLETE_OFFSET.height,
                )
            )
            submit_bounds: Bounds | None = None
            ready: bool | None
            if complete_search is None or not _fits(complete_search, _COMPLETE_TEMPLATE_SIZE):
                ready = None
            else:
                submit_bounds = self._control(
                    prepared, _COMPLETE_TEMPLATE, complete_search, _CONTROL_THRESHOLD
                )
                ready = submit_bounds is not None
            if card.clipped:
                completeness = RowRecognitionStatus.CLIPPED
            elif covered and not orphan_reward:
                completeness = RowRecognitionStatus.COMPLETE
            else:
                completeness = RowRecognitionStatus.UNREADABLE
            orders.append(
                WorkshopOrder(
                    order_ref=order_ref,
                    requirements=requirements,
                    rewards=rewards,
                    completeness=completeness,
                    ready=ready,
                    source="order_strip",
                )
            )
            views.append(
                WorkshopOrderView(
                    order_ref=order_ref,
                    portrait_bounds=_scaled_region(
                        Bounds(
                            x=card.x0,
                            y=card.top,
                            width=card.x1 - card.x0,
                            height=card.bottom - card.top,
                        ),
                        image,
                    ),
                    submit_bounds=submit_bounds,
                )
            )
        return tuple(orders), tuple(views), strip_bounds

    def _read_card_requirements(
        self, prepared: PreparedFrame, card: _CardExtent
    ) -> tuple[dict[int, int], bool]:
        """Match a card's requirement icons and measure tile coverage.

        ``covered`` is True only when every detected tile run holds at least
        one matched icon, every matched icon sits inside a tile run and the
        estimated tile count equals the icon count.
        """

        icon_region = _clipped(
            Bounds(
                x=card.x0,
                y=_CARD_REQ_ICON_BAND[0],
                width=card.x1 - card.x0,
                height=_CARD_REQ_ICON_BAND[1],
            )
        )
        icons = (
            self._icon_matches(
                prepared,
                templates=_STRIP_REQUIREMENT_TEMPLATES,
                region=icon_region,
                threshold=_STRIP_ICON_THRESHOLD,
            )
            if icon_region is not None
            else []
        )
        return _counted_icons(icons), _tile_coverage(
            _tile_runs(prepared.pixels, card), icons, prepared
        )

    def _read_strip_rewards(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        ocr_context: ObservationOcrContext,
        card: _CardExtent,
        order_ref: int,
    ) -> tuple[tuple[WorkshopOrderReward, ...], bool]:
        """Read independently measured reward groups and preserve unknown art.

        Each foreground group contains one icon and its neighboring count.
        A missed icon cannot enlarge its predecessor's count region or make
        a visible reward disappear: that group stays UNKNOWN and the card
        is unreadable. Numeric OCR does not establish group presence.
        """

        band = _clipped(
            Bounds(
                x=card.x0 - 8,
                y=_CARD_REWARD_BAND[0],
                width=card.x1 - card.x0 + 16,
                height=_CARD_REWARD_BAND[1],
            )
        )
        if band is None:
            return (), False
        icons = self._icon_matches(
            prepared,
            templates=_STRIP_REWARD_TEMPLATES,
            region=band,
            threshold=_STRIP_ICON_THRESHOLD,
        )
        icon_refs = sorted(
            (
                (category, _ref_region(match.bounds, prepared))
                for category, match in icons
            ),
            key=lambda item: item[1].x,
        )
        groups = _reward_groups(prepared.pixels, card)
        entries: list[WorkshopOrderReward] = []
        covered_icons: set[int] = set()
        orphan = not groups
        for index, (x0, x1) in enumerate(groups):
            members = [
                (i, category, bounds)
                for i, (category, bounds) in enumerate(icon_refs)
                if x0 <= bounds.center()[0] <= x1
            ]
            if len(members) != 1:
                orphan = True
                label = self._read_region_text(
                    image=image,
                    ocr_context=ocr_context,
                    region=Bounds(x=x0, y=band.y, width=x1 - x0 + 1, height=band.height),
                    detail=f"workshop_order_{order_ref}_unknown_reward_{index}",
                )
                entries.append(WorkshopOrderReward(
                    category=WorkshopOrderRewardCategory.UNKNOWN,
                    label=label or None,
                ))
                continue
            icon_index, category, bounds = members[0]
            covered_icons.add(icon_index)
            right_edge = (
                groups[index + 1][0] - 2 if index + 1 < len(groups)
                else min(card.x1 + 8, _REFERENCE_SIZE[0])
            )
            zone = _clipped(
                Bounds(
                    x=bounds.x + bounds.width,
                    y=max(0, bounds.y - 4),
                    width=max(0, right_edge - (bounds.x + bounds.width)),
                    height=bounds.height + 14,
                )
            )
            entries.append(
                WorkshopOrderReward(
                    category=category,
                    quantity=self._zone_quantity(
                        image=image,
                        ocr_context=ocr_context,
                        region=zone,
                        detail=f"workshop_order_{order_ref}_reward_{index}_count",
                    ),
                )
            )
        if len(covered_icons) != len(icon_refs):
            orphan = True
        return tuple(entries), orphan

    def _read_detail_rewards(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        ocr_context: ObservationOcrContext,
        icons: list[tuple[object, TemplateMatch]],
        pedestals: list[tuple[int, int]],
    ) -> tuple[tuple[WorkshopOrderReward, ...], bool]:
        """Read each detail reward icon's top-edge count; preserve orphans.

        An unmatched pedestal produces an UNKNOWN-category reward so a
        pedestal's presence is never dropped, and a band token that belongs
        to no icon or pedestal stays an UNKNOWN entry as well.
        """

        icon_refs = sorted(
            (
                (category, _ref_region(match.bounds, prepared))
                for category, match in icons
            ),
            key=lambda item: item[1].x,
        )
        ped_spans = [
            (x0 - _OD_PEDESTAL_PAD_X, x1 + _OD_PEDESTAL_PAD_X) for x0, x1 in pedestals
        ]
        entries: list[tuple[int, WorkshopOrderReward]] = []
        consumed: list[Bounds] = []
        for index, (category, bounds) in enumerate(icon_refs):
            right_edge = (
                icon_refs[index + 1][1].x - 2
                if index + 1 < len(icon_refs)
                else bounds.x + bounds.width + _OD_COUNT_ZONE_RIGHT_PAD
            )
            zone = _clipped(
                Bounds(
                    x=bounds.x - 2,
                    y=bounds.y + _OD_COUNT_ZONE_Y[0],
                    width=max(0, min(right_edge, bounds.x + bounds.width + _OD_COUNT_ZONE_RIGHT_PAD) - (bounds.x - 2)),
                    height=_OD_COUNT_ZONE_Y[1] - _OD_COUNT_ZONE_Y[0],
                )
            )
            entries.append(
                (
                    bounds.x,
                    WorkshopOrderReward(
                        category=category,
                        quantity=self._zone_quantity(
                            image=image,
                            ocr_context=ocr_context,
                            region=zone,
                            detail=f"workshop_order_detail_reward_{index}_count",
                        ),
                    ),
                )
            )
            consumed.append(bounds)
            if zone is not None:
                consumed.append(zone)
        orphan = False
        for value, token_bounds, text in _numeric_tokens(
            self._read_lines(
                image=image,
                ocr_context=ocr_context,
                region=_OD_REWARD_TOKEN_BAND,
                detail="workshop_order_detail_rewards",
            )
        ):
            token_ref = _ref_region(token_bounds, prepared)
            if any(_intersects(token_ref, region) for region in consumed):
                continue
            orphan = True
            entries.append(
                (
                    token_ref.x,
                    WorkshopOrderReward(
                        category=WorkshopOrderRewardCategory.UNKNOWN,
                        quantity=value,
                        label=text,
                    ),
                )
            )
        for x0, x1 in ped_spans:
            if any(x0 <= _ref_region(m.bounds, prepared).center()[0] <= x1 for _c, m in icons):
                continue
            orphan = True
            entries.append(
                (
                    x0,
                    WorkshopOrderReward(category=WorkshopOrderRewardCategory.UNKNOWN),
                )
            )
        entries.sort(key=lambda item: item[0])
        return tuple(reward for _x, reward in entries), orphan

    def _zone_quantity(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
        region: Bounds | None,
        detail: str,
    ) -> int | None:
        """OCR one count zone; ``None`` unless exactly one distinct value reads."""

        if region is None or region.width < 8 or region.height < 6:
            return None
        values = {
            value
            for value, _bounds, _text in _numeric_tokens(
                self._read_lines(
                    image=image, ocr_context=ocr_context, region=region, detail=detail
                )
            )
        }
        return values.pop() if len(values) == 1 else None

    def _icon_matches(
        self,
        prepared: PreparedFrame,
        *,
        templates: tuple[tuple[str, object], ...],
        region: Bounds,
        threshold: float,
    ) -> list[tuple[object, TemplateMatch]]:
        """Return deduplicated icon matches across one bounded region."""

        accepted: list[tuple[object, TemplateMatch]] = []
        for entry in templates:
            name, value = entry[0], entry[1]
            for match in self.matcher.find_matches(
                prepared,
                _DATA_DIR / name,
                threshold=threshold,
                search_region=region,
            ):
                if any(
                    other.bounds.contains_point(match.bounds.center())
                    or match.bounds.contains_point(other.bounds.center())
                    for _value, other in accepted
                ):
                    continue
                accepted.append((value, match))
        accepted.sort(key=lambda item: (item[1].bounds.x, item[1].bounds.y))
        return accepted

    def _cell_id_at(self, *, prepared: PreparedFrame, point: tuple[int, int]) -> int | None:
        """Map an image-space point to the containing board cell id."""

        scale_x = prepared.reference_size[0] / prepared.original_size[0]
        scale_y = prepared.reference_size[1] / prepared.original_size[1]
        x_ref = point[0] * scale_x
        y_ref = point[1] * scale_y
        column = int((x_ref - _CELL_X0) // _CELL_W) + 1
        row = self.catalog.board.rows - int((y_ref - _CELL_Y0) // _CELL_H)
        if not self.catalog.board.contains_position(row, column):
            return None
        return self.catalog.board.cell_id(row, column)

    def _best(
        self,
        prepared: PreparedFrame,
        templates: tuple[Path, ...],
        region: Bounds,
        threshold: float,
    ) -> tuple[TemplateMatch, int] | None:
        """Return the highest-confidence match across a template family."""

        best: tuple[TemplateMatch, int] | None = None
        for index, template in enumerate(templates):
            match = self.matcher.find_best_match(
                prepared, template, threshold=threshold, search_region=region
            )
            if match is not None and (best is None or match.confidence > best[0].confidence):
                best = (match, index)
        return best

    def _control(
        self,
        prepared: PreparedFrame,
        template: Path,
        region: Bounds,
        threshold: float,
    ) -> Bounds | None:
        """Return the matched control bounds in image coordinates, or ``None``."""

        match = self.matcher.find_best_match(
            prepared, template, threshold=threshold, search_region=region
        )
        return match.bounds if match is not None else None

    def _read_lines(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
        region: Bounds,
        detail: str,
    ):
        """Read one bounded OCR region scaled into image coordinates."""

        return ocr_context.read_lines(
            image,
            _scaled_region(region, image),
            purpose=OcrReadPurpose.CONTENT,
            detail=detail,
        )

    def _read_region_text(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
        region: Bounds,
        detail: str,
    ) -> str:
        """Read one bounded region and join its raw line text."""

        return " ".join(
            line.text
            for line in self._read_lines(
                image=image, ocr_context=ocr_context, region=region, detail=detail
            )
        )


def _cell_region(row: int, column: int) -> Bounds:
    """Return one cell's reference bounds; row 1 is the bottom display row."""

    return Bounds(
        x=round(_CELL_X0 + (column - 1) * _CELL_W),
        y=round(_CELL_Y0 + (9 - row) * _CELL_H),
        width=71,
        height=71,
    )


def _cell_center_region(region: Bounds) -> Bounds:
    """Return the cell's center window, clear of corner selection brackets."""

    return Bounds(x=region.x + 20, y=region.y + 20, width=32, height=32)


def _inflate_region(region: Bounds, margin: int) -> Bounds:
    """Grow a search region, clamped to the reference frame."""

    clipped = _clipped(
        Bounds(
            x=region.x - margin,
            y=region.y - margin,
            width=region.width + margin * 2,
            height=region.height + margin * 2,
        )
    )
    return clipped if clipped is not None else region


def _clipped(region: Bounds) -> Bounds | None:
    """Clamp a region to the reference frame; ``None`` when fully outside."""

    x2 = min(region.x + region.width, _REFERENCE_SIZE[0])
    y2 = min(region.y + region.height, _REFERENCE_SIZE[1])
    x1 = max(region.x, 0)
    y1 = max(region.y, 0)
    if x2 - x1 <= 0 or y2 - y1 <= 0:
        return None
    return Bounds(x=x1, y=y1, width=x2 - x1, height=y2 - y1)


def _fits(region: Bounds, template_size: tuple[int, int]) -> bool:
    """Check a search region can spatially hold one template."""

    return region.width >= template_size[0] and region.height >= template_size[1]


def _scaled_region(region: Bounds, image: Image.Image) -> Bounds:
    """Scale one fixed reference region into image coordinates."""

    scale_x = image.width / _REFERENCE_SIZE[0]
    scale_y = image.height / _REFERENCE_SIZE[1]
    return Bounds(
        x=round(region.x * scale_x),
        y=round(region.y * scale_y),
        width=round(region.width * scale_x),
        height=round(region.height * scale_y),
    )


def _counted_icons(icons: list[tuple[object, TemplateMatch]]) -> dict[int, int]:
    """Count matched requirement icons per item id."""

    counts: dict[int, int] = {}
    for value, _match in icons:
        counts[int(value)] = counts.get(int(value), 0) + 1
    return counts


def _numeric_tokens(lines) -> list[tuple[int, Bounds, str]]:
    """Extract numeric tokens with image-space bounds and raw text from OCR lines."""

    tokens: list[tuple[int, Bounds, str]] = []
    for line in lines:
        for word in line.words:
            digits = _NUMERIC_TOKEN.search(word.text)
            if digits:
                tokens.append((int(digits.group(0)), word.bounds, word.text))
        if not line.words:
            digits = _NUMERIC_TOKEN.search(line.text)
            if digits:
                tokens.append((int(digits.group(0)), line.bounds, line.text))
    return tokens


def _intersects(first: Bounds, second: Bounds) -> bool:
    """Return whether two bounds rectangles overlap by at least one pixel."""

    return (
        first.x < second.x + second.width
        and second.x < first.x + first.width
        and first.y < second.y + second.height
        and second.y < first.y + first.height
    )


def _ref_region(bounds: Bounds, prepared: PreparedFrame) -> Bounds:
    """Convert image-space match bounds into reference coordinates."""

    scale_x = prepared.reference_size[0] / prepared.original_size[0]
    scale_y = prepared.reference_size[1] / prepared.original_size[1]
    return Bounds(
        x=round(bounds.x * scale_x),
        y=round(bounds.y * scale_y),
        width=max(1, round(bounds.width * scale_x)),
        height=max(1, round(bounds.height * scale_y)),
    )


def _channels(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split RGB pixels into int16 channels for mask arithmetic."""

    return (
        pixels[..., 0].astype(np.int16),
        pixels[..., 1].astype(np.int16),
        pixels[..., 2].astype(np.int16),
    )


def _panel_mask(pixels: np.ndarray) -> np.ndarray:
    """Cream card-panel pixels (the order card body fill)."""

    r, g, b = _channels(pixels)
    return (r >= 235) & (g >= 205) & (b >= 140) & (r > b + 30)


def _strip_bg_mask(pixels: np.ndarray) -> np.ndarray:
    """Strip background pixels: teal scene wash, foliage green and shadow."""

    r, g, b = _channels(pixels)
    teal = (r < 95) & (g > 55) & (g < 125) & (b > 60) & (b < 135) & (b >= g - 15)
    foliage = (g > r + 15) & (g > b + 20) & (g >= 90) & (g < 170) & (r < 140) & (b < 110)
    shadow = (r < 70) & (g < 70) & (b < 70)
    return teal | foliage | shadow


def _chrome_mask(pixels: np.ndarray) -> np.ndarray:
    """Warm wood-tone pixels along the strip's bottom chrome band."""

    r, g, b = _channels(pixels)
    return (r > g + 10) & (g > b) & (r >= 90) & (b < 140) & (r - b >= 40)


def _pedestal_mask(pixels: np.ndarray) -> np.ndarray:
    """Blue detail-modal pedestal pixels (saturated blue on navy modal)."""

    r, g, b = _channels(pixels)
    return (b > 105) & (b - r > 35) & (r < 135)


def _column_runs(mask: np.ndarray, min_width: int) -> list[tuple[int, int]]:
    """Contiguous True-column runs as inclusive ``(x0, x1)`` pairs."""

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, flag in enumerate(mask):
        if flag and start is None:
            start = x
        elif not flag and start is not None:
            if x - start >= min_width:
                runs.append((start, x - 1))
            start = None
    if start is not None and len(mask) - start >= min_width:
        runs.append((start, len(mask) - 1))
    return runs


def _detect_card_extents(pixels: np.ndarray) -> list[_CardExtent]:
    """Locate order-card panels from non-background columns on the strip.

    A horizontal run of mostly-content columns in the union band (reward row
    + tile row) is a card candidate; the left timer column is rejected by its
    missing reward-row panel fraction. Cards touching the frame edges or the
    timer column are marked clipped.
    """

    panel = _panel_mask(pixels)
    nonbg = ~_strip_bg_mask(pixels)
    y0, y1 = _CARD_UNION_BAND
    runs = _column_runs(nonbg[y0:y1].mean(axis=0) >= 0.5, _CARD_MIN_WIDTH)
    cards: list[_CardExtent] = []
    for x0, x1 in runs:
        if panel[_CARD_PANEL_BAND[0] : _CARD_PANEL_BAND[1], x0 : x1 + 1].mean() < 0.25:
            continue
        cards.append(
            _CardExtent(
                x0=x0,
                x1=x1 + 1,
                top=_card_top(nonbg, x0, x1 + 1),
                bottom=_card_bottom(panel, x0, x1 + 1),
                clipped=(
                    x1 - x0 + 1 < _CARD_FULL_MIN_WIDTH
                    or x1 + 1 >= _CARD_CLIP_RIGHT_X
                    or x0 <= _CARD_CLIP_LEFT_X
                ),
            )
        )
    return cards


def _card_top(nonbg: np.ndarray, x0: int, x1: int) -> int:
    """First row of three consecutive mostly-content rows within the card."""

    y0, y1 = _CARD_TOP_SCAN
    frac = nonbg[y0:y1, x0:x1].mean(axis=1)
    for i in range(len(frac) - 2):
        if frac[i] >= 0.5 and frac[i + 1] >= 0.5 and frac[i + 2] >= 0.5:
            return y0 + i
    return _CARD_PANEL_BAND[0]


def _card_bottom(panel: np.ndarray, x0: int, x1: int) -> int:
    """Row just past the card's last mostly-panel row; chrome top as fallback."""

    y0, y1 = _CARD_PANEL_TAIL_SCAN
    frac = panel[y0:y1, x0:x1].mean(axis=1)
    last = None
    for i, value in enumerate(frac):
        if value >= 0.4:
            last = y0 + i
    return (last + 1) if last is not None else _STRIP_CHROME_BAND[0]


def _order_strip_bounds(pixels: np.ndarray) -> Bounds | None:
    """Measure the order-strip surface from its continuous bottom chrome.

    The strip's wood chrome spans the widget horizontally; the top edge is
    the first row where that span reads mostly non-background content.
    ``None`` when no chrome run is measured.
    """

    chrome = _chrome_mask(pixels)
    y0, y1 = _STRIP_CHROME_BAND
    runs = _column_runs(chrome[y0:y1].mean(axis=0) >= 0.5, min_width=8)
    if not runs or max(b - a + 1 for a, b in runs) < 300:
        return None
    x0 = min(run[0] for run in runs)
    x1 = max(run[1] for run in runs) + 1
    nonbg = ~_strip_bg_mask(pixels)
    frac = nonbg[_STRIP_TOP_SCAN[0] : _STRIP_TOP_SCAN[1], x0:x1].mean(axis=1)
    top = None
    for i in range(len(frac) - 2):
        if frac[i] >= 0.45 and frac[i + 1] >= 0.45 and frac[i + 2] >= 0.45:
            top = _STRIP_TOP_SCAN[0] + i
            break
    if top is None:
        return None
    return Bounds(x=x0, y=top, width=x1 - x0, height=_STRIP_BOTTOM - top)


def _tile_runs(pixels: np.ndarray, card: _CardExtent) -> list[tuple[int, int]]:
    """Detect requirement tile columns inside one card's tile band."""

    x0 = card.x0 + 2
    x1 = min(card.x1 - 2, _REFERENCE_SIZE[0])
    if x1 - x0 <= 0:
        return []
    y0, height = _CARD_TILE_BAND
    nonpanel = ~_panel_mask(pixels)
    frac = nonpanel[y0 : y0 + height, x0:x1].mean(axis=0)
    return [(x0 + a, x0 + b) for a, b in _column_runs(frac >= 0.5, _TILE_RUN_MIN_WIDTH)]


def _reward_groups(pixels: np.ndarray, card: _CardExtent) -> list[tuple[int, int]]:
    """Measure reward foreground groups without depending on icon identity.

    On the qualified layout the cream row below the rewards spans their
    panel, including its unused space. Foreground columns above that row
    form icon/count groups; digit gaps are at most eight reference pixels,
    while the two-reward fixtures have larger inter-reward gaps. Ambiguous
    merged groups subsequently fail the one-icon-per-group coverage check.
    """

    panel = _panel_mask(pixels)
    spans = _column_runs(panel[_REWARD_PANEL_BASELINE, card.x0:card.x1], 30)
    if len(spans) != 1:
        return []
    x0, x1 = (card.x0 + value for value in spans[0])
    y0, y1 = _REWARD_INK_BAND
    ink = (~panel[y0:y1, x0:x1 + 1]).mean(axis=0) >= 0.15
    groups: list[tuple[int, int]] = []
    for left, right in _column_runs(ink, 2):
        left, right = x0 + left, x0 + right
        if groups and left - groups[-1][1] - 1 <= _REWARD_GROUP_GAP:
            groups[-1] = (groups[-1][0], right)
        else:
            groups.append((left, right))
    return groups


def _tile_coverage(
    runs: list[tuple[int, int]],
    icons: list[tuple[object, TemplateMatch]],
    prepared: PreparedFrame,
) -> bool:
    """Check tile runs and matched requirement icons agree one-for-one.

    Coverage holds when every run holds at least one icon center, every icon
    sits inside a run, and the run-width slot estimate equals the icon count.
    A card with no measured tiles is never covered.
    """

    if not runs:
        return False
    centers = [_ref_region(match.bounds, prepared).center() for _value, match in icons]
    if any(not any(a <= cx <= b for a, b in runs) for cx, _cy in centers):
        return False
    if any(not any(a <= cx <= b for cx, _cy in centers) for a, b in runs):
        return False
    slots = sum(
        max(1, round((b - a + 1) / _CARD_TILE_SLOT_PITCH)) for a, b in runs
    )
    return slots == len(icons)


def _pedestal_runs(pixels: np.ndarray, band: tuple[int, int]) -> list[tuple[int, int]]:
    """Detect detail-modal pedestal columns from their blue lip rows."""

    ped = _pedestal_mask(pixels)
    y0, y1 = band
    frac = ped[y0:y1, 120:530].mean(axis=0)
    return [(a + 120, b + 120) for a, b in _column_runs(frac >= 0.45, _OD_PEDESTAL_MIN_WIDTH)]


def _pedestals_covered(
    pedestals: list[tuple[int, int]],
    icons: list[tuple[object, TemplateMatch]],
    prepared: PreparedFrame,
) -> bool:
    """Check every pedestal holds a matched icon and every icon sits on one."""

    if not pedestals or len(pedestals) != len(icons):
        return False
    centers = [_ref_region(match.bounds, prepared).center() for _value, match in icons]
    spans = [
        (x0 - _OD_PEDESTAL_PAD_X, x1 + _OD_PEDESTAL_PAD_X) for x0, x1 in pedestals
    ]
    return all(any(a <= cx <= b for a, b in spans) for cx, _cy in centers) and all(
        any(a <= cx <= b for cx, _cy in centers) for a, b in spans
    )


def _bar_empty(pixels: np.ndarray) -> bool:
    """Measure whether the bottom selection bar carries no card/controls."""

    region = _SELECTION_BAR_REGION
    sub = pixels[
        region.y : region.y + region.height, region.x : region.x + region.width
    ].astype(np.float32)
    luminance = sub.mean(axis=2)
    edges = (
        (np.abs(np.diff(luminance, axis=1)) > 28).mean()
        + (np.abs(np.diff(luminance, axis=0)) > 28).mean()
    ) / 2
    return edges < _BAR_EMPTY_EDGE_MAX
