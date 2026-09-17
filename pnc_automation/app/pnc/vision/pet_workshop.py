"""Canonical Pet Workshop content producer (PW02).

Under the independently proved ``pet_workshop_*`` layouts this producer reads
typed Workshop facts for the measured surfaces: the merge board, the item and
order detail modals, the help overlay and the premium storage drawer (reported
as the excluded-modal surface). The manor hub carries navigation controls only
and yields no content observation.

Board semantics measured on the PW02 fixtures: a badge medallion marks a
level-gated cell, grass cover marks a seeded cell whose contents stay hidden,
a flat tile interior marks an empty usable cell, and any remaining non-empty
piece is reported occupied with ``item_id=None`` rather than guessed. The
order strip exposes three card slots; a card cut by the frame edge is CLIPPED
but keeps its partial reads. Requirement and reward icons are matched at strip
and detail scale with fixed templates authored from the measurement captures;
dynamic counts remain OCR-owned.

Glyph references (``.local-data/pw02`` provenance): cell overlays, selection
brackets and controls, order-strip requirement/reward icons and order-detail
icons were all cropped from the 2026-09-16/17 measurement captures reviewed
for this packet. Match margins on the reference fixtures: item templates
>= .90 vs <= .88 cross-cell noise, badge digits discriminate by argmax
(intended >= .96 vs <= .89), selection bar controls >= .90.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

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

# Order strip: three card slots at x = 106 + 177 * index; the third card is
# clipped by the right frame edge on the measured fixtures.
_CARD_X0 = 106
_CARD_PITCH = 177
_CARD_SLOTS = 3
_CARD_PANEL_TOP = 141
_CARD_PORTRAIT = Bounds(x=4, y=52, width=96, height=92)
_CARD_SLOT_BAND = Bounds(x=2, y=165, width=166, height=68)
# The reward row is centered in the card panel; single-reward cards place the
# icon near its middle while two-reward rows start at the panel's left edge,
# so the band spans the full row including the icon's slight left overhang.
_CARD_REWARD_BAND = Bounds(x=-8, y=138, width=186, height=36)
_CARD_COMPLETE_SEARCH = Bounds(x=80, y=90, width=96, height=44)

# Selection brackets and the selection-bar controls (bottom bar).
_BOARD_REGION = Bounds(x=15, y=235, width=512, height=615)
_INSPECT_SEARCH = Bounds(x=50, y=865, width=160, height=85)
_RECYCLE_SEARCH = Bounds(x=330, y=858, width=195, height=95)
_BACK_SEARCH = Bounds(x=2, y=2, width=74, height=62)

# Modal close controls sit at each overlay's top-right corner.
_ITEM_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=215, width=95, height=80)
_ORDER_DETAIL_CLOSE_SEARCH = Bounds(x=430, y=185, width=95, height=90)
_HELP_CLOSE_SEARCH = Bounds(x=430, y=100, width=95, height=80)

# Order-detail modal: target-item icons and the reward row.
_OD_REQUIREMENT_BAND = Bounds(x=160, y=285, width=370, height=95)
_OD_REWARD_BAND = Bounds(x=180, y=440, width=360, height=60)
_OD_REWARD_TEXT = Bounds(x=180, y=420, width=360, height=80)

_CELL_OVERLAY_THRESHOLD = 0.90
_CELL_ITEM_THRESHOLD = 0.90
_CELL_EMPTY_THRESHOLD = 0.90
_SELECTION_THRESHOLD = 0.85
_CONTROL_THRESHOLD = 0.85
_STRIP_ICON_THRESHOLD = 0.90
_DETAIL_ICON_THRESHOLD = 0.90

_DATA_DIR = Path(__file__).resolve().parent / "data" / "screen_anchors"

# Board pieces recognized at cell scale. An inactive (greyed) piece keeps its
# catalog identity with an explicit INACTIVE status; unmodeled pieces such as
# bread, bags and bolt-producers stay occupied-with-unknown-id.
_ITEM_TEMPLATES = (
    ("pet_workshop_item_tree_4.png", 20004, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_fruit_1.png", 20101, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_fruit_2.png", 20102, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_fruit_3.png", 20103, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_fruit_5.png", 20105, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_wood_4.png", 20204, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_wood_5.png", 20205, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_wood_7.png", 20207, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_wood_8.png", 20208, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_bowl_5.png", 30105, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_treasure_1.png", 10101, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_treasure_6.png", 10106, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_statue_4.png", 10204, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_clay_2.png", 30002, WorkshopItemStatus.NORMAL),
    ("pet_workshop_item_bowl_1_inactive.png", 30101, WorkshopItemStatus.INACTIVE),
)
_BADGE_TEMPLATES = tuple(
    _DATA_DIR / f"pet_workshop_ov_badge_{level}.png" for level in (7, 8, 9, 10, 11)
)
_GRASS_TEMPLATE = _DATA_DIR / "pet_workshop_ov_grass.png"
_EMPTY_CELL_TEMPLATE = _DATA_DIR / "pet_workshop_cell_empty.png"

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

_SEL_CORNER_TEMPLATE = _DATA_DIR / "pet_workshop_sel_corner.png"
_INSPECT_TEMPLATE = _DATA_DIR / "pet_workshop_sel_inspect.png"
_RECYCLE_TEMPLATE = _DATA_DIR / "pet_workshop_sel_recycle.png"
_COMPLETE_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_complete.png"
_COMPLETE_TEMPLATE_SIZE = (72, 19)
_BACK_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_back.png"
_CLOSE_X_TEMPLATE = _DATA_DIR / "pet_workshop_ctl_close_x.png"

_NUMERIC_TOKEN = re.compile(r"\d+")


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
        orders, order_views = self._read_orders(
            image=image, prepared=prepared, ocr_context=ocr_context
        )
        state = WorkshopState(
            board=self.catalog.board,
            surface=WorkshopSurfaceKind.BOARD,
            cells=cells,
            energy=energy,
            production_mode=WorkshopProductionMode.ORDINARY,
            workshop_level=level,
            workshop_exp=workshop_exp,
            selection=self._read_selection(prepared=prepared),
            order_survey=WorkshopOrderSurvey(
                orders=orders,
                coverage=WorkshopSurveyCoverage.PARTIAL,
                freshness=WorkshopSurveyFreshness.CURRENT,
            ),
        )
        view = WorkshopView(
            cell_bounds=cell_bounds,
            order_views=order_views,
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
        requirements = _counted_icons(
            self._icon_matches(
                prepared,
                templates=_DETAIL_REQUIREMENT_TEMPLATES,
                region=_OD_REQUIREMENT_BAND,
                threshold=_DETAIL_ICON_THRESHOLD,
            )
        )
        rewards = self._read_reward_icons(
            image=image,
            prepared=prepared,
            ocr_context=ocr_context,
            templates=_DETAIL_REWARD_TEMPLATES,
            icon_region=_OD_REWARD_BAND,
            text_region=_OD_REWARD_TEXT,
            detail="workshop_order_detail_rewards",
        )
        order = WorkshopOrder(
            order_ref=1,
            requirements=requirements,
            rewards=rewards,
            completeness=RowRecognitionStatus.COMPLETE,
            ready=False,
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
            tuple(_DATA_DIR / name for name, _item_id, _status in _ITEM_TEMPLATES),
            _inflate_region(region, 5),
            _CELL_ITEM_THRESHOLD,
        )
        if match is not None:
            name, item_id, status = _ITEM_TEMPLATES[match[1]]
            return WorkshopCell(
                cell_id=cell_id, row=row, column=column,
                access=WorkshopCellAccess.USABLE, occupancy=WorkshopOccupancy.OCCUPIED,
                item_id=item_id, item_status=status,
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
            item_status=WorkshopItemStatus.UNKNOWN,
        )

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
        return (
            int(level_match.group(1)) if level_match else None,
            int(exp_match.group(1)) if exp_match else None,
            WorkshopEnergy(
                current=int(energy_match.group(1)) if energy_match else None,
                capacity=int(energy_match.group(2)) if energy_match else None,
            ),
        )

    def _read_selection(self, *, prepared: PreparedFrame) -> WorkshopSelection:
        """Locate the selected cell from its corner brackets, voting by majority."""

        votes: dict[int, tuple[int, float]] = {}
        for match in self.matcher.find_matches(
            prepared,
            _SEL_CORNER_TEMPLATE,
            threshold=_SELECTION_THRESHOLD,
            search_region=_BOARD_REGION,
        ):
            cell_id = self._cell_id_at(prepared=prepared, point=match.bounds.center())
            if cell_id is None:
                continue
            count, confidence = votes.get(cell_id, (0, 0.0))
            votes[cell_id] = (count + 1, max(confidence, match.confidence))
        if not votes:
            return WorkshopSelection(kind=WorkshopSelectionKind.NONE)
        cell_id = max(votes.items(), key=lambda item: (item[1][0], item[1][1]))[0]
        return WorkshopSelection(kind=WorkshopSelectionKind.SELECTED, cell_id=cell_id)

    def _read_orders(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        ocr_context: ObservationOcrContext,
    ) -> tuple[tuple[WorkshopOrder, ...], tuple[WorkshopOrderView, ...]]:
        """Read each order-strip card: requirements, rewards and the ready control."""

        orders: list[WorkshopOrder] = []
        views: list[WorkshopOrderView] = []
        for index in range(_CARD_SLOTS):
            x0 = _CARD_X0 + index * _CARD_PITCH
            if x0 >= _REFERENCE_SIZE[0]:
                break
            order_ref = index + 1
            clipped = x0 + 170 > _REFERENCE_SIZE[0]
            slot_band = _clipped(_offset(_CARD_SLOT_BAND, x0, 0))
            reward_band = _clipped(_offset(_CARD_REWARD_BAND, x0, 0))
            complete_search = _clipped(_offset(_CARD_COMPLETE_SEARCH, x0, 0))
            requirements = (
                _counted_icons(
                    self._icon_matches(
                        prepared,
                        templates=_STRIP_REQUIREMENT_TEMPLATES,
                        region=slot_band,
                        threshold=_STRIP_ICON_THRESHOLD,
                    )
                )
                if slot_band is not None
                else {}
            )
            rewards = (
                self._read_reward_icons(
                    image=image,
                    prepared=prepared,
                    ocr_context=ocr_context,
                    templates=_STRIP_REWARD_TEMPLATES,
                    icon_region=reward_band,
                    text_region=reward_band,
                    detail=f"workshop_order_{order_ref}_rewards",
                )
                if reward_band is not None
                else ()
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
            portrait = _clipped(_offset(_CARD_PORTRAIT, x0, 0))
            orders.append(
                WorkshopOrder(
                    order_ref=order_ref,
                    requirements=requirements,
                    rewards=rewards,
                    completeness=(
                        RowRecognitionStatus.CLIPPED if clipped else RowRecognitionStatus.COMPLETE
                    ),
                    ready=ready,
                    source="order_strip",
                )
            )
            views.append(
                WorkshopOrderView(
                    order_ref=order_ref,
                    portrait_bounds=(
                        _scaled_region(portrait, image) if portrait is not None else None
                    ),
                    submit_bounds=submit_bounds,
                )
            )
        return tuple(orders), tuple(views)

    def _read_reward_icons(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        ocr_context: ObservationOcrContext,
        templates: tuple[tuple[str, WorkshopOrderRewardCategory], ...],
        icon_region: Bounds,
        text_region: Bounds,
        detail: str,
    ) -> tuple[WorkshopOrderReward, ...]:
        """Match reward icons and pair each with its nearest right-side count."""

        icons = self._icon_matches(
            prepared,
            templates=templates,
            region=icon_region,
            threshold=_STRIP_ICON_THRESHOLD,
        )
        if not icons:
            return ()
        tokens = _numeric_tokens(
            self._read_lines(
                image=image, ocr_context=ocr_context, region=text_region, detail=detail
            )
        )
        rewards: list[WorkshopOrderReward] = []
        for category, match in icons:
            quantity = _paired_quantity(match, tokens)
            rewards.append(WorkshopOrderReward(category=category, quantity=quantity))
        return tuple(rewards)

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


def _offset(region: Bounds, dx: int, dy: int) -> Bounds:
    """Translate one reference region."""

    return Bounds(x=region.x + dx, y=region.y + dy, width=region.width, height=region.height)


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


def _numeric_tokens(lines) -> list[tuple[int, Bounds]]:
    """Extract numeric tokens with image-space bounds from OCR lines."""

    tokens: list[tuple[int, Bounds]] = []
    for line in lines:
        for word in line.words:
            digits = _NUMERIC_TOKEN.search(word.text)
            if digits:
                tokens.append((int(digits.group(0)), word.bounds))
        if not line.words:
            digits = _NUMERIC_TOKEN.search(line.text)
            if digits:
                tokens.append((int(digits.group(0)), line.bounds))
    return tokens


def _paired_quantity(icon: TemplateMatch, tokens: list[tuple[int, Bounds]]) -> int | None:
    """Pair an icon with its horizontally nearest count token, or ``None``.

    The count's placement varies by surface: order-strip cards print it right
    of the icon while the detail modal floats it at the slot's top edge, so
    pairing uses the horizontal gap inside the already row-scoped band.
    """

    candidates = [
        (
            max(
                0,
                token_bounds.x - (icon.bounds.x + icon.bounds.width),
                icon.bounds.x - (token_bounds.x + token_bounds.width),
            ),
            value,
        )
        for value, token_bounds in tokens
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]
