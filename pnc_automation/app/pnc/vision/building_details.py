"""Bounded typed building-detail production from accepted building-owned frames.

This module owns the building-detail semantic extraction for the shared
``PNC_BUILDING_DETAILS`` surface, the proved named building primaries, the
Institute upgrade detail layout, and the construction surface. It is invoked
only under an independently accepted screen identity: visual profiles and OCR
evidence prove the screen/layout before any fact here is parsed, so this
content can describe the panel but can never establish or override identity.

Facts are observations only. A primary panel's Upgrade control opens an
internal upgrade panel; only the upgrade panel's ordinary Upgrade is the
mutation surface. ``filter_building_detail_controls`` keeps those two
phase-owned selectors distinct at both publisher boundaries, so a primary
frame never advertises the mutation control and an upgrade frame never
advertises the entry control.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_definition_for_label,
    home_city_object_id_for_layout,
    home_city_object_id_for_screen,
    upgrade_entry_selector_for_screen,
)
from pnc_automation.app.pnc.domain.building_details import (
    BuildingDetail,
    BuildingDetailPhase,
    BuildingRequirementRow,
    parse_building_level_pair,
)
from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.resource_cost import ResourceCost
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.numeric_parsing import parse_grouped_integer
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

# The upgrade panel replaces the primary's stat rows with these fixed section
# headers; any one of them proves the UPGRADE phase on layouts that own both.
_UPGRADE_SECTION_TEXTS = frozenset({"TIME", "REQUIREMENT", "MATERIALSREQUIRED", "EFFECT"})
_REQUIREMENT_HEADER_TEXTS = frozenset({"REQUIREMENT"})
_REQUIREMENT_SECTION_TERMINATORS = frozenset({"MATERIALSREQUIRED", "EFFECT"})
# Layouts whose accepted visual identity is itself the upgrade detail panel.
_UPGRADE_DETAIL_LAYOUT_IDS = frozenset({"institute_upgrade_detail"})
# Owned primary-only stats labels in the middle band prove the PRIMARY phase
# on the shared details layout. `Food Output` alone is not proof: related
# wording appears inside upgrade-panel effect text.
_PRIMARY_STATS_LABEL_TEXTS = frozenset({"OVERALLHOURLYOUTPUT"})
# The primary stats band sits between the level/action band and the lower
# effect area on the shared details layout.
_PRIMARY_STATS_BAND_MIN_Y = 0.32
_PRIMARY_STATS_BAND_MAX_Y = 0.63
# Institute primary-only category controls measured on the `institute` layout;
# the upgrade detail shares its title/description identity but has no grid.
_INSTITUTE_CATEGORY_SELECTOR_IDS = frozenset(
    {
        UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
        UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
        UiElementId.PNC_INSTITUTE_MILITARY_BUTTON,
        UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON,
    }
)

_TITLE_TEXTS = frozenset(
    {
        "ACADEMY",
        "BARRACKS",
        "CASTLE",
        "EMBASSY",
        "FARM",
        "HALLOFWAR",
        "HOSPITAL",
        "IRONMINE",
        "LUMBERMILL",
        "LUMBERYARD",
        "QUARRY",
        "SHOOTINGRANGE",
        "STABLE",
        "TRAININGGROUNDS",
        "WALL",
        "WAREHOUSE",
        "WATCHTOWER",
    }
)

_LEVEL_PATTERN = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
_TIME_PATTERN = re.compile(r"^(?:\d+\s*d\s*)?\d{1,3}:\d{2}:\d{2}$", re.IGNORECASE)
_COST_PATTERN = re.compile(r"^(\d[\d,.]*)\s*/\s*(\d[\d,.]*)$")
_PREMIUM_COST_PATTERN = re.compile(r"^(FREE|\d{1,3}(?:,\d{3})*|\d{1,6})$")
_REQUIREMENT_LEVEL_PATTERN = re.compile(r"LV\.?\s*(\d+)", re.IGNORECASE)

# These selectors describe controls whose meaning is owned by the observed
# phase: the mutation surface only exists on a proved UPGRADE panel, and the
# generic entry control only exists on a proved PRIMARY panel.
_UPGRADE_PHASE_SELECTOR_IDS = frozenset(
    {
        UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
        UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
        UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
    }
)
# Named primary entry controls are the building's own Upgrade on its primary
# panel. They stay published while the phase is unproved (many primaries
# cannot read the section band), but a proved UPGRADE frame must not keep
# advertising them: their pixels sit on the spending surface there. The set is
# derived from the canonical catalog mapping so ownership stays single.
_PRIMARY_ENTRY_SELECTOR_IDS = frozenset(
    selector_id
    for selector_id in map(upgrade_entry_selector_for_screen, ScreenType)
    if selector_id is not None
)


def filter_building_detail_controls(
    elements: Mapping[UiElementId, VisibleElement],
    detail: BuildingDetail | None,
) -> dict[UiElementId, VisibleElement]:
    """Publish each phase-owned building control only under its proved phase.

    The same Upgrade button pixels mean "open the upgrade panel" on a primary
    frame and "spend on the upgrade" on an upgrade frame. The typed phase —
    never the button's appearance — decides which selector may publish. The
    mutation selectors require a proved UPGRADE phase, and the generic details
    entry requires a proved PRIMARY phase; an unphased observation advertises
    neither. Named primary entry selectors survive an unproved phase (their
    screens cannot always read the section band) but never a proved UPGRADE.
    """

    phase = None if detail is None else detail.phase
    filtered = dict(elements)
    if phase is not BuildingDetailPhase.UPGRADE:
        for selector_id in _UPGRADE_PHASE_SELECTOR_IDS:
            filtered.pop(selector_id, None)
    else:
        for selector_id in _PRIMARY_ENTRY_SELECTOR_IDS:
            filtered.pop(selector_id, None)
    if phase is not BuildingDetailPhase.PRIMARY:
        filtered.pop(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON, None)
    return filtered


def find_building_requirement_header_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> OcrLine | None:
    """Returns the shared unmet-requirement section header when one upgrade gate is visible."""

    max_x = int(image.width * 0.35)
    min_y = int(image.height * 0.35)
    for line in lines:
        if normalize_ocr_text(line.text) not in _REQUIREMENT_HEADER_TEXTS:
            continue
        if line.bounds.y < min_y or line.bounds.x > max_x:
            continue
        return line
    return None


def find_building_requirement_go_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    header: OcrLine,
) -> OcrLine | None:
    """Returns the right-side `Go` affordance associated with one unmet-requirement row when visible."""

    min_y = header.bounds.y
    max_y = min(image.height, header.bounds.y + header.bounds.height + int(image.height * 0.14))
    min_x = int(image.width * 0.6)
    for line in lines:
        if normalize_ocr_text(line.text) != "GO":
            continue
        if line.bounds.x < min_x:
            continue
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        return line
    return None


def find_building_requirement_target_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    header: OcrLine,
    go_line: OcrLine | None = None,
) -> OcrLine | None:
    """Returns the prerequisite label, aligned with the actionable `Go` row when one exists."""

    candidates = _requirement_target_candidates(image=image, lines=lines, header=header)
    if not candidates:
        return None
    if go_line is None:
        return min(candidates, key=lambda line: (line.bounds.y, line.bounds.x))
    go_center_y = go_line.bounds.y + (go_line.bounds.height // 2)
    return min(
        candidates,
        key=lambda line: abs((line.bounds.y + (line.bounds.height // 2)) - go_center_y),
    )


def _requirement_target_candidates(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    header: OcrLine,
) -> list[OcrLine]:
    """Returns candidate requirement labels below the section header."""

    header_bottom = header.bounds.y + header.bounds.height
    max_y = min(image.height, header_bottom + int(image.height * 0.14))
    max_x = int(image.width * 0.65)
    candidates: list[OcrLine] = []
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text in {"", "GO"} or normalized_text in _REQUIREMENT_SECTION_TERMINATORS:
            continue
        if line.bounds.y <= header_bottom or line.bounds.y > max_y:
            continue
        if line.bounds.x > max_x:
            continue
        candidates.append(line)
    return candidates


def find_building_title_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns a conservative building-title candidate from the screen header."""

    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text not in _TITLE_TEXTS:
            continue
        if line.bounds.y > int(image.height * 0.09):
            continue
        if line.bounds.x > int(image.width * 0.35):
            continue
        return line
    return None


def _requirement_target_building(target_text: str) -> HomeCityObjectId | None:
    """Resolve the prerequisite's named building from its preserved label text."""

    base = re.split(r"LV\.?\s*\d+", target_text, flags=re.IGNORECASE)[0]
    base = base.rstrip(" :").strip()
    if base == "":
        return None
    definition = home_city_object_definition_for_label(base)
    return None if definition is None else definition.id


def _requirement_target_level(target_text: str) -> int | None:
    """Parse the prerequisite's required level from its preserved label text."""

    match = _REQUIREMENT_LEVEL_PATTERN.search(target_text)
    return None if match is None else int(match.group(1))


def _has_upgrade_sections(lines: tuple[OcrLine, ...]) -> bool:
    """Returns whether owned OCR regions contain upgrade-detail section headers."""

    return any(normalize_ocr_text(line.text) in _UPGRADE_SECTION_TEXTS for line in lines)


def _has_primary_phase_proof(
    *,
    image: Image.Image,
    screen_type: ScreenType,
    lines: tuple[OcrLine, ...],
    measured_elements: Mapping[UiElementId, VisibleElement],
) -> bool:
    """Returns whether owned evidence proves the primary stats panel.

    The shared details layout proves PRIMARY through its primary-only stats
    labels in the middle band (the upgrade panel shows section headers there
    instead). The Institute primary proves it through its measured category
    grid — the upgrade detail shares the title identity but has no grid.
    """

    if screen_type is ScreenType.PNC_BUILDING_DETAILS:
        min_y = int(image.height * _PRIMARY_STATS_BAND_MIN_Y)
        max_y = int(image.height * _PRIMARY_STATS_BAND_MAX_Y)
        return any(
            normalize_ocr_text(line.text) in _PRIMARY_STATS_LABEL_TEXTS
            and min_y <= line.bounds.y <= max_y
            for line in lines
        )
    if screen_type is ScreenType.PNC_INSTITUTE:
        categories = {
            selector for selector in _INSTITUTE_CATEGORY_SELECTOR_IDS
            if selector in measured_elements
            and measured_elements[selector].source_kind is VisibleElementSourceKind.TEMPLATE
        }
        return len(categories) >= 2
    return False


def _building_owner(
    *,
    screen_type: ScreenType,
    layout_id: str | None,
    title_text: str | None,
) -> HomeCityObjectId | None:
    """Resolve the owning building from accepted identity, never arbitrary OCR."""

    owner = home_city_object_id_for_screen(screen_type)
    if owner is not None:
        return owner
    owner = home_city_object_id_for_layout(layout_id)
    if owner is not None:
        return owner
    if screen_type is ScreenType.PNC_BUILDING_CONSTRUCTION and title_text is not None:
        # The construction header names the target itself; it is not a label guess.
        definition = home_city_object_definition_for_label(title_text)
        return None if definition is None else definition.id
    return None


@dataclass(frozen=True, slots=True)
class BuildingContentProducer:
    """Produce the typed building-detail fact for one accepted building frame."""

    def phase_for(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        layout_id: str | None,
        lines: tuple[OcrLine, ...],
        measured_elements: Mapping[UiElementId, VisibleElement],
    ) -> BuildingDetailPhase | None:
        """Return the observed panel phase, or None when no owned evidence proves it.

        Every phase requires positive proof: construction/upgrade surfaces are
        proved by their accepted layout or section headers, and the primary
        panel is proved by owned primary-only evidence — never by the absence
        of upgrade sections, which a degraded OCR read could also produce.
        """

        if screen_type is ScreenType.PNC_BUILDING_CONSTRUCTION:
            return BuildingDetailPhase.CONSTRUCTION
        if layout_id in _UPGRADE_DETAIL_LAYOUT_IDS or _has_upgrade_sections(lines):
            return BuildingDetailPhase.UPGRADE
        if _has_primary_phase_proof(
            image=image,
            screen_type=screen_type,
            lines=lines,
            measured_elements=measured_elements,
        ):
            return BuildingDetailPhase.PRIMARY
        return None

    def detail(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        screen_type: ScreenType,
        layout_id: str | None,
        measured_elements: Mapping[UiElementId, VisibleElement],
        content_elements: Mapping[UiElementId, VisibleElement],
    ) -> BuildingDetail | None:
        """Parse one accepted building screen into its typed detail fact.

        ``measured_elements`` carries template-proved controls (for example the
        row-owned Go bound); ``content_elements`` carries the OCR-published
        elements (the shared level label). Facts record what the frame
        actually shows; unknown identity, levels, costs, or Go geometry stay
        unknown rather than inferred.
        """

        phase = self.phase_for(
            image=image,
            screen_type=screen_type,
            layout_id=layout_id,
            lines=lines,
            measured_elements=measured_elements,
        )
        title_line = find_building_title_line(image=image, lines=lines)
        title_text = None if title_line is None else title_line.text.strip()
        building_id = _building_owner(
            screen_type=screen_type,
            layout_id=layout_id,
            title_text=title_text,
        )
        level_element = content_elements.get(UiElementId.PNC_BUILDING_LEVEL_LABEL)
        level_pair = (
            None
            if level_element is None or level_element.extracted_text is None
            else parse_building_level_pair(level_element.extracted_text)
        )
        current_level = None if level_pair is None else level_pair[0]
        max_level = None if level_pair is None else level_pair[1]
        requirement = self._requirement_row(
            image=image,
            lines=lines,
            measured_elements=measured_elements,
        )
        costs = self._resource_costs(image=image, lines=lines)
        original_time, actual_time = self._upgrade_times(image=image, lines=lines)
        premium_bounds, premium_cost = self._premium_upgrade_now(image=image, lines=lines)
        return BuildingDetail(
            building_id=building_id,
            phase=phase,
            title_text=title_text,
            current_level=current_level,
            max_level=max_level,
            level_text=(
                None
                if level_element is None or level_element.extracted_text is None
                else level_element.extracted_text
            ),
            requirement=requirement,
            costs=costs,
            original_time_text=original_time,
            actual_time_text=actual_time,
            premium_button_bounds=premium_bounds,
            premium_cost_text=premium_cost,
        )

    def _requirement_row(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        measured_elements: Mapping[UiElementId, VisibleElement],
    ) -> BuildingRequirementRow | None:
        """Bind the one supported explicit prerequisite row and its own Go geometry.

        ``go_bounds`` is the actionable half of the fact: only the measured
        template Go control associated with the row may fill it. Bare OCR `Go`
        text never manufactures actionability — when the measured control is
        absent the row still reports its target while staying non-actionable.
        """

        header = find_building_requirement_header_line(image=image, lines=lines)
        if header is None:
            return None
        go_line = find_building_requirement_go_line(image=image, lines=lines, header=header)
        target = find_building_requirement_target_line(
            image=image,
            lines=lines,
            header=header,
            go_line=go_line,
        )
        if target is None:
            return None
        go_element = measured_elements.get(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON)
        return BuildingRequirementRow(
            target_text=target.text.strip(),
            target_bounds=target.bounds,
            target_building=_requirement_target_building(target.text),
            target_level=_requirement_target_level(target.text),
            go_bounds=(
                go_element.bounds
                if go_element is not None and go_element.source_kind is VisibleElementSourceKind.TEMPLATE
                else None
            ),
        )

    def _resource_costs(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> tuple[ResourceCost, ...]:
        """Parse ordinary ``available/required`` material rows below the action band."""

        min_y = int(image.height * 0.30)
        costs: list[ResourceCost] = []
        for line in lines:
            if line.bounds.y < min_y:
                continue
            match = _COST_PATTERN.match(line.text.strip())
            if match is None:
                continue
            available = parse_grouped_integer(match.group(1))
            required = parse_grouped_integer(match.group(2))
            # Preserve a readable half when OCR damages the other amount's
            # grouping (observed comma -> decimal point). Never guess it.
            if available is None and required is None:
                continue
            costs.append(
                ResourceCost(
                    resource_type=None,
                    available=available,
                    required=required,
                    text_bounds=line.bounds,
                )
            )
        return tuple(costs)

    def _upgrade_times(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> tuple[str | None, str | None]:
        """Pair the Original/Actual time labels with the time values under each column."""

        time_lines = [
            line for line in lines if _TIME_PATTERN.match(line.text.strip()) is not None
        ]
        if not time_lines:
            return None, None
        original_label = next(
            (
                line
                for line in lines
                if normalize_ocr_text(line.text).startswith("ORIGINALTIME")
            ),
            None,
        )
        actual_label = next(
            (
                line
                for line in lines
                if normalize_ocr_text(line.text).startswith("ACTUALTIME")
            ),
            None,
        )
        return (
            _time_below(original_label, time_lines),
            _time_below(actual_label, time_lines),
        )

    def _premium_upgrade_now(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> tuple[object, str | None]:
        """Read the premium Upgrade Now affordance as a fact, never an action."""

        min_x = int(image.width * 0.4)
        min_y = int(image.height * 0.2)
        max_y = int(image.height * 0.55)
        upgrade_now = next(
            (
                line
                for line in lines
                if normalize_ocr_text(line.text) == "UPGRADENOW"
                and line.bounds.x >= min_x
                and min_y <= line.bounds.y <= max_y
            ),
            None,
        )
        if upgrade_now is None:
            return None, None
        tolerance = max(4, round(image.height * 0.004))
        cost_line = next(
            (
                line
                for line in lines
                if _PREMIUM_COST_PATTERN.match(line.text.strip()) is not None
                and line.bounds.y + line.bounds.height <= upgrade_now.bounds.y + tolerance
                and line.bounds.y >= upgrade_now.bounds.y - int(image.height * 0.08)
                and abs(line.bounds.x - upgrade_now.bounds.x) <= upgrade_now.bounds.width
            ),
            None,
        )
        return (
            upgrade_now.bounds,
            None if cost_line is None else cost_line.text.strip(),
        )


def _time_below(label: OcrLine | None, time_lines: list[OcrLine]) -> str | None:
    """Return the first measured time value under one label column."""

    if label is None:
        return None
    candidates = [
        line for line in time_lines
        if line.bounds.y >= label.bounds.y + label.bounds.height
        and abs(line.bounds.x - label.bounds.x) <= label.bounds.width
    ]
    candidates.sort(key=lambda line: (line.bounds.y, line.bounds.x))
    return candidates[0].text.strip() if candidates else None
