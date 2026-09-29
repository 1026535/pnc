"""Pet Workshop board, cell, header, and selection recognition."""

from __future__ import annotations

from PIL import Image

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCell,
    WorkshopCellAccess,
    WorkshopEnergy,
    WorkshopItemStatus,
    WorkshopProductionMode,
    WorkshopOccupancy,
    WorkshopSelection,
    WorkshopSelectionKind,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog

from . import geometry, matching, ocr
from .constants import *  # noqa: F403 - measured constants are the data contract


def read_cells(
    *,
    image: Image.Image,
    prepared: PreparedFrame,
    matcher: OpenCvTemplateMatcher,
    catalog: PetWorkshopCatalog,
) -> tuple[tuple[WorkshopCell, ...], dict[int, Bounds]]:
    """Read every board cell and return cells plus image-space bounds."""

    cells: list[WorkshopCell] = []
    cell_bounds: dict[int, Bounds] = {}
    board = catalog.board
    for row in range(1, board.rows + 1):
        for column in range(1, board.columns + 1):
            cell_id = board.cell_id(row, column)
            region = geometry.cell_region(row, column)
            cell_bounds[cell_id] = geometry.scaled_region(region, image)
            cells.append(
                read_cell(
                    matcher,
                    cell_id=cell_id,
                    row=row,
                    column=column,
                    prepared=prepared,
                    region=region,
                )
            )
    return tuple(cells), cell_bounds


def read_cell(
    matcher: OpenCvTemplateMatcher,
    *,
    cell_id: int,
    row: int,
    column: int,
    prepared: PreparedFrame,
    region: Bounds,
) -> WorkshopCell:
    """Classify one cell from independent access, occupancy and state evidence."""

    if matching.best(matcher,
        prepared, _BADGE_TEMPLATES, region, _CELL_OVERLAY_THRESHOLD
    ) is not None:
        return WorkshopCell(
            cell_id=cell_id,
            row=row,
            column=column,
            access=WorkshopCellAccess.LOCKED,
            occupancy=WorkshopOccupancy.EMPTY,
        )
    if matching.best(matcher,
        prepared,
        (_GRASS_TEMPLATE,),
        region,
        _CELL_OVERLAY_THRESHOLD,
    ) is not None:
        return WorkshopCell(
            cell_id=cell_id,
            row=row,
            column=column,
            access=WorkshopCellAccess.LOCKED,
            occupancy=WorkshopOccupancy.UNKNOWN,
        )
    match = matching.best(matcher,
        prepared,
        tuple(_DATA_DIR / name for name, _item_id in _ITEM_TEMPLATES),
        geometry.inflate_region(region, 5),
        _CELL_ITEM_THRESHOLD,
    )
    if match is not None:
        return WorkshopCell(
            cell_id=cell_id,
            row=row,
            column=column,
            access=WorkshopCellAccess.USABLE,
            occupancy=WorkshopOccupancy.OCCUPIED,
            item_id=_ITEM_TEMPLATES[match[1]][1],
            item_status=read_piece_status(matcher, prepared, region),
        )
    if matching.best(matcher,
        prepared,
        (_EMPTY_CELL_TEMPLATE,),
        geometry.cell_center_region(region),
        _CELL_EMPTY_THRESHOLD,
    ) is not None:
        return WorkshopCell(
            cell_id=cell_id,
            row=row,
            column=column,
            access=WorkshopCellAccess.USABLE,
            occupancy=WorkshopOccupancy.EMPTY,
        )
    return WorkshopCell(
        cell_id=cell_id,
        row=row,
        column=column,
        access=WorkshopCellAccess.USABLE,
        occupancy=WorkshopOccupancy.OCCUPIED,
        item_status=read_piece_status(matcher, prepared, region),
    )


def read_piece_status(
    matcher: OpenCvTemplateMatcher, prepared: PreparedFrame, region: Bounds
) -> WorkshopItemStatus:
    """Qualify a supported full-cell appearance without guessing from color."""

    states = {
        status
        for status, level, cells in _CELL_STATE_TEMPLATES
        if matching.best(matcher,
            prepared,
            tuple(
                _DATA_DIR / f"pet_workshop_state_{status.value}_{level}_{cell}.png"
                for cell in cells
            ),
            region,
            _CELL_STATE_THRESHOLD,
        )
        is not None
    }
    return states.pop() if len(states) == 1 else WorkshopItemStatus.UNKNOWN


def read_header(
    *, image: Image.Image, ocr_context: ObservationOcrContext
) -> tuple[int | None, int | None, WorkshopEnergy]:
    """Read Workshop level, EXP, and energy through bounded OCR regions."""

    level_text = ocr.read_region_text(
        image=image,
        ocr_context=ocr_context,
        region=_LEVEL_REGION,
        detail="workshop_level",
    )
    level_match = _LEVEL_SEARCH.search(level_text)
    exp_text = ocr.read_region_text(
        image=image,
        ocr_context=ocr_context,
        region=_EXP_REGION,
        detail="workshop_exp",
    )
    exp_match = _GAUGE_SEARCH.search(exp_text)
    energy_text = ocr.read_region_text(
        image=image,
        ocr_context=ocr_context,
        region=_ENERGY_REGION,
        detail="workshop_energy",
    )
    energy_match = _GAUGE_SEARCH.search(energy_text)
    energy_capacity = int(energy_match.group(2)) if energy_match else None
    energy_current = int(energy_match.group(1)) if energy_match else None
    if energy_capacity is not None and energy_capacity <= 0:
        energy_current = energy_capacity = None
    return (
        int(level_match.group(1)) if level_match else None,
        int(exp_match.group(1)) if exp_match else None,
        WorkshopEnergy(current=energy_current, capacity=energy_capacity),
    )


def read_production_mode(
    matcher: OpenCvTemplateMatcher, prepared: PreparedFrame
) -> WorkshopProductionMode:
    """Report ordinary production only when the measured bolt is visible."""

    if matching.control(matcher,
        prepared, _BOLT_TEMPLATE, _BOARD_REGION, _BOLT_THRESHOLD
    ) is not None:
        return WorkshopProductionMode.ORDINARY
    return WorkshopProductionMode.UNKNOWN


def read_selection(
    *,
    prepared: PreparedFrame,
    matcher: OpenCvTemplateMatcher,
    catalog: PetWorkshopCatalog,
) -> WorkshopSelection:
    """Resolve selected cell by corner majority and measured empty-bar evidence."""

    votes: dict[int, tuple[int, float]] = {}
    accepted: list[tuple[int, int]] = []
    for template in _SEL_CORNER_TEMPLATES:
        for match in matcher.find_matches(
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
            cell_id = cell_id_at(catalog, prepared=prepared, point=center)
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
            return WorkshopSelection(kind=WorkshopSelectionKind.SELECTED, cell_id=cell_id)
        return WorkshopSelection(kind=WorkshopSelectionKind.UNKNOWN)
    return WorkshopSelection(
        kind=(
            WorkshopSelectionKind.NONE
            if geometry.bar_empty(prepared.pixels)
            else WorkshopSelectionKind.UNKNOWN
        )
    )


def cell_id_at(
    catalog: PetWorkshopCatalog,
    *,
    prepared: PreparedFrame,
    point: tuple[int, int],
) -> int | None:
    """Map an image-space point to its containing board cell."""

    scale_x = prepared.reference_size[0] / prepared.original_size[0]
    scale_y = prepared.reference_size[1] / prepared.original_size[1]
    x_ref = point[0] * scale_x
    y_ref = point[1] * scale_y
    column = int((x_ref - _CELL_X0) // _CELL_W) + 1
    row = catalog.board.rows - int((y_ref - _CELL_Y0) // _CELL_H)
    if not catalog.board.contains_position(row, column):
        return None
    return catalog.board.cell_id(row, column)
