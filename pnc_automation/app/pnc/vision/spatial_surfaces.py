"""Shared spatial-surface parsing helpers for world-map and home-city observations."""

from __future__ import annotations

import re
from dataclasses import replace

from PIL import Image

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.building_catalog import (
    build_home_city_object_metadata,
    home_city_object_definition_for_label,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, SurfaceDefinition
from pnc_automation.app.pnc.vision.world_map_coordinates import (
    ParsedWorldViewport,
    is_world_map_blue_family_pixel,
    parse_world_viewport,
)

_WORLD_UI_CHROME_TEXTS = frozenset({"HOME", "HERO", "QUEST", "MAIL", "ALLIANCE", "MORE", "SEARCH"})
_WORLD_NEUTRAL_OBJECT_TOKENS = frozenset({"DRAGONIA", "ALTAR", "HELLFORTRESS"})
_WORLD_ALLIANCE_BUILDING_TOKENS = frozenset({"FORTRESS", "TOWER", "HIVE", "MINE", "CAMP"})
_WORLD_RESOURCE_TYPE_BY_TOKEN = {
    "FOOD": "food",
    "FARM": "food",
    "WOOD": "wood",
    "LUMBER": "wood",
    "STONE": "stone",
    "QUARRY": "stone",
    "IRON": "iron",
}
_ALLIANCE_TAG_PATTERN = re.compile(r"^\[(?P<tag>[A-Z0-9]{2,5})\]\s*(?P<name>.+)$")
_WORLD_CASTLE_LABEL_PATTERN = re.compile(r"^K(?P<kingdom>\d{3})(?P<identifier>[A-Z0-9]{5,})$")
_MONSTER_LEVEL_PATTERN = re.compile(r"^(?:LV\.?|LEVEL)\s*(?P<level>\d{1,3})\s*(?P<name>.+)$", re.IGNORECASE)
_HOME_CITY_TIMER_PATTERN = re.compile(r"(?<!\d)(?P<timer>\d{1,2}:\d{2}:\d{2})(?!\d)")
_HOME_CITY_LEVEL_PATTERN = re.compile(r"^(?:LV\.?|LEVEL)?\s*(?P<level>\d{1,3})$", re.IGNORECASE)
_WORLD_MAP_ESTIMATED_VIEWPORT_WIDTH_UNITS = 900
_WORLD_MAP_ESTIMATED_VIEWPORT_HEIGHT_UNITS = 1184
_WORLD_MAP_VISIBLE_SCAN_TOP_RATIO = 0.1
_WORLD_MAP_VISIBLE_SCAN_BOTTOM_RATIO = 0.84
_HOME_EMPTY_SLOT_TEXTS = frozenset({"BUILD", "EMPTY"})


def estimated_world_map_visible_scan_footprint_units() -> tuple[int, int]:
    """Returns the modeled world-coordinate footprint used by full-viewport world-map object scans."""

    return (
        _WORLD_MAP_ESTIMATED_VIEWPORT_WIDTH_UNITS,
        int(
            round(
                _WORLD_MAP_ESTIMATED_VIEWPORT_HEIGHT_UNITS
                * (_WORLD_MAP_VISIBLE_SCAN_BOTTOM_RATIO - _WORLD_MAP_VISIBLE_SCAN_TOP_RATIO)
            )
        ),
    )


def build_world_map_surface_observation(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    selector_registry: SelectorRegistry | None,
) -> ParsedWorldViewport | None:
    """Returns the strict world-map viewport proof when OCR exposes the coordinate bar."""

    del selector_registry
    return parse_world_viewport(image=image, lines=lines)


def build_world_map_spatial_surface(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    selector_registry: SelectorRegistry | None,
    object_scan_bounds: Bounds | None = None,
    parsed_viewport: ParsedWorldViewport | None = None,
    include_objects: bool = True,
) -> SpatialSurfaceObservation | None:
    """Builds the canonical world-map spatial surface from the full viewport or one requested subsection."""

    viewport = parsed_viewport if parsed_viewport is not None else parse_world_viewport(image=image, lines=lines)
    if viewport is None:
        return None
    surface_definition = None if selector_registry is None else selector_registry.surface_for_screen(ScreenType.PNC_WORLD_MAP)
    viewport_bounds = _resolve_world_map_scan_bounds(image=image, requested_bounds=None)
    scan_bounds = _resolve_world_map_scan_bounds(image=image, requested_bounds=object_scan_bounds)
    objects = (
        _parse_world_map_objects(
            image=image,
            lines=lines,
            surface_definition=surface_definition,
            scan_bounds=scan_bounds,
            viewport_bounds=viewport_bounds,
            viewport_coordinate=viewport.viewport.coordinate,
        )
        if include_objects
        else ()
    )
    return SpatialSurfaceObservation(
        surface_type=SpatialSurfaceType.WORLD_MAP,
        viewport=viewport.viewport,
        objects=objects,
        metadata={
            "coordinate_text": viewport.coordinate_text,
            "scan_bounds": scan_bounds,
            "scan_scope": "coordinate_only"
            if not include_objects
            else "section"
            if object_scan_bounds is not None
            else "full_viewport",
            **({} if surface_definition is None else {"surface_id": surface_definition.id}),
        },
    )


def build_home_city_spatial_surface(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    selector_registry: SelectorRegistry | None,
) -> SpatialSurfaceObservation:
    """Builds the canonical home-city spatial surface using camera-relative building parsing."""

    surface_definition = None if selector_registry is None else selector_registry.surface_for_screen(ScreenType.PNC_HOME_CITY)
    objects = _attach_home_city_building_levels(
        image=image,
        lines=lines,
        objects=_parse_home_city_objects(
            image=image,
            lines=lines,
            surface_definition=surface_definition,
        ),
    )
    metadata = {} if surface_definition is None else {"surface_id": surface_definition.id}
    active_build_timer_text = _find_home_city_active_build_timer_text(image=image, lines=lines)
    if active_build_timer_text is not None:
        metadata["active_build_timer_text"] = active_build_timer_text
    anchor_buildings = tuple(sorted(object_.name_text for object_ in objects if object_.name_text is not None))
    return SpatialSurfaceObservation(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        viewport=SpatialViewport(
            addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE,
            metadata={"anchor_buildings": anchor_buildings},
        ),
        objects=objects,
        metadata=metadata,
    )


def _find_home_city_active_build_timer_text(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> str | None:
    """Returns the strongest visible home-city construction timer when OCR proves one is on-screen."""

    min_y = int(image.height * 0.4)
    max_y = int(image.height * 0.95)
    min_x = int(image.width * 0.08)
    best_timer: str | None = None
    best_score: tuple[int, int, int] | None = None
    for line in lines:
        if line.bounds.y < min_y or line.bounds.y > max_y or line.bounds.x < min_x:
            continue
        match = _HOME_CITY_TIMER_PATTERN.search(line.text.strip())
        if match is None:
            continue
        surrounding_text = line.text.replace(match.group("timer"), "", 1).strip()
        score = (
            1 if surrounding_text != "" else 0,
            line.bounds.y,
            line.bounds.width,
        )
        if best_score is not None and score <= best_score:
            continue
        best_score = score
        best_timer = match.group("timer")
    return best_timer


def _parse_world_map_objects(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    surface_definition: SurfaceDefinition | None,
    scan_bounds: Bounds,
    viewport_bounds: Bounds,
    viewport_coordinate: tuple[int, int] | None,
) -> tuple[DetectedSpatialObject, ...]:
    """Extracts typed world-map objects from OCR-visible labels inside the map viewport."""

    supported_kinds = None if surface_definition is None else frozenset(surface_definition.object_kinds)
    relationship_rules = None if surface_definition is None else surface_definition.relationship_rules
    parsed_objects: list[DetectedSpatialObject] = []
    seen_keys: set[tuple[object, ...]] = set()
    candidate_lines = _visible_world_map_candidate_lines(lines=lines, scan_bounds=scan_bounds)
    index = 0
    while index < len(candidate_lines):
        line, consumed_count = _resolve_world_map_label_line(
            image=image,
            lines=candidate_lines,
            start_index=index,
            relationship_rules=relationship_rules,
            viewport_bounds=viewport_bounds,
            viewport_coordinate=viewport_coordinate,
        )
        object_ = _classify_world_map_object(
            image=image,
            line=line,
            relationship_rules=relationship_rules,
            viewport_bounds=viewport_bounds,
            viewport_coordinate=viewport_coordinate,
        )
        index += consumed_count
        if object_ is None:
            continue
        if supported_kinds is not None and object_.kind not in supported_kinds:
            continue
        key = (object_.kind, object_.relationship, object_.name_text, object_.level, line.bounds.x, line.bounds.y)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        parsed_objects.append(object_)
    return tuple(parsed_objects)


def _visible_world_map_candidate_lines(
    *,
    lines: tuple[OcrLine, ...],
    scan_bounds: Bounds,
) -> tuple[OcrLine, ...]:
    """Returns only OCR lines that can plausibly describe visible world-map scene objects."""

    return tuple(
        line
        for line in lines
        if _bounds_center_within_region(bounds=line.bounds, region=scan_bounds)
        and (normalized_text := normalize_ocr_text(line.text)) != ""
        and normalized_text not in _WORLD_UI_CHROME_TEXTS
        and not _looks_like_coordinate_overlay(normalized_text)
    )


def _resolve_world_map_label_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    start_index: int,
    relationship_rules: object | None,
    viewport_bounds: Bounds,
    viewport_coordinate: tuple[int, int] | None,
) -> tuple[OcrLine, int]:
    """Returns the strongest canonical label line for one world-map object, merging wrapped OCR rows when helpful."""

    best_line = lines[start_index]
    best_object = _classify_world_map_object(
        image=image,
        line=best_line,
        relationship_rules=relationship_rules,
        viewport_bounds=viewport_bounds,
        viewport_coordinate=viewport_coordinate,
    )
    last_consumed_index = start_index
    max_index = min(len(lines), start_index + 3)
    for next_index in range(start_index + 1, max_index):
        next_line = lines[next_index]
        if not _can_merge_world_map_label_lines(upper_line=best_line, lower_line=next_line):
            break
        merged_line = merge_ocr_lines(best_line, next_line)
        merged_object = _classify_world_map_object(
            image=image,
            line=merged_line,
            relationship_rules=relationship_rules,
            viewport_bounds=viewport_bounds,
            viewport_coordinate=viewport_coordinate,
        )
        if not _merged_world_map_object_is_stronger(current_object=best_object, merged_object=merged_object):
            break
        best_line = merged_line
        best_object = merged_object
        last_consumed_index = next_index
    return best_line, last_consumed_index - start_index + 1


def _can_merge_world_map_label_lines(
    *,
    upper_line: OcrLine,
    lower_line: OcrLine,
) -> bool:
    """Returns whether two vertically stacked OCR lines plausibly belong to the same world-map label."""

    upper_bottom = upper_line.bounds.y + upper_line.bounds.height
    vertical_gap = lower_line.bounds.y - upper_bottom
    if vertical_gap < -max(upper_line.bounds.height, lower_line.bounds.height) * 0.35:
        return False
    if vertical_gap > max(upper_line.bounds.height, lower_line.bounds.height) * 1.2:
        return False
    upper_center_x = upper_line.bounds.x + (upper_line.bounds.width // 2)
    lower_center_x = lower_line.bounds.x + (lower_line.bounds.width // 2)
    allowed_center_delta = max(upper_line.bounds.width, lower_line.bounds.width) * 0.6
    return abs(upper_center_x - lower_center_x) <= allowed_center_delta


def _merged_world_map_object_is_stronger(
    *,
    current_object: DetectedSpatialObject | None,
    merged_object: DetectedSpatialObject | None,
) -> bool:
    """Returns whether a merged label carries meaningfully better world-object evidence than the current line."""

    if merged_object is None:
        return False
    if current_object is None:
        return True
    if merged_object.kind != current_object.kind:
        return True
    current_name = normalize_ocr_text(current_object.name_text or "")
    merged_name = normalize_ocr_text(merged_object.name_text or "")
    if len(merged_name) > len(current_name):
        return True
    if current_object.level is None and merged_object.level is not None:
        return True
    if current_object.alliance_tag is None and merged_object.alliance_tag is not None:
        return True
    if current_object.kingdom is None and merged_object.kingdom is not None:
        return True
    return len(merged_object.metadata) > len(current_object.metadata)


def _classify_world_map_object(
    *,
    image: Image.Image,
    line: OcrLine,
    relationship_rules: object | None,
    viewport_bounds: Bounds,
    viewport_coordinate: tuple[int, int] | None,
) -> DetectedSpatialObject | None:
    """Classifies one OCR line into a typed world-map spatial object when the evidence is strong enough."""

    raw_text = line.text.strip()
    normalized_text = normalize_ocr_text(raw_text)
    if normalized_text == "":
        return None
    alliance_tag, stripped_name = _extract_alliance_tag(raw_text)
    kind = _classify_world_map_object_kind(normalized_text, raw_text=raw_text, alliance_tag=alliance_tag)
    if kind is None:
        return None
    color_family = _classify_color_family(image=image, bounds=line.bounds)
    relationship = _classify_world_map_relationship(
        kind=kind,
        normalized_text=normalized_text,
        alliance_tag=alliance_tag,
        color_family=color_family,
        relationship_rules=relationship_rules,
    )
    level, resolved_name = _extract_level_and_name(raw_text, fallback_name=stripped_name)
    kingdom = _extract_world_object_kingdom(normalized_text)
    metadata: dict[str, object] = {}
    if color_family is not None:
        metadata["color_family"] = color_family
    if kind == SpatialObjectKind.CASTLE and _looks_like_world_castle_label(normalized_text):
        metadata["castle_label"] = raw_text
        metadata["castle_identifier"] = normalized_text[4:]
    if kind == SpatialObjectKind.RESOURCE_NODE:
        resource_type = _resolve_resource_type(normalized_text)
        if resource_type is not None:
            metadata["resource_type"] = resource_type
    bounds = Bounds(
        x=line.bounds.x,
        y=line.bounds.y,
        width=line.bounds.width,
        height=line.bounds.height,
    )
    viewport_offset = _bounds_center_offset(bounds=bounds, origin=viewport_bounds.center())
    viewport_offset_ratio = _bounds_center_offset_ratio(bounds=bounds, viewport_bounds=viewport_bounds)
    return DetectedSpatialObject(
        kind=kind,
        bounds=bounds,
        relationship=relationship,
        name_text=resolved_name,
        alliance_tag=alliance_tag,
        level=level,
        kingdom=kingdom,
        action_point=bounds.center(),
        viewport_offset=viewport_offset,
        viewport_offset_ratio=viewport_offset_ratio,
        estimated_world_coordinate=_estimate_world_coordinate(
            viewport_coordinate=viewport_coordinate,
            viewport_offset_ratio=viewport_offset_ratio,
        ),
        metadata=metadata,
    )


def _classify_world_map_object_kind(
    normalized_text: str,
    *,
    raw_text: str,
    alliance_tag: str | None,
) -> SpatialObjectKind | None:
    """Returns the typed world-map object kind implied by one OCR label."""

    if normalized_text == "MYTERRITORY" or "TERRITORY" in normalized_text:
        return SpatialObjectKind.CASTLE
    if _looks_like_world_castle_label(normalized_text):
        return SpatialObjectKind.CASTLE
    if "DRAGONIA" in normalized_text:
        return SpatialObjectKind.DRAGONIA
    if "ALTAR" in normalized_text:
        return SpatialObjectKind.ALTAR
    if "HELLFORTRESS" in normalized_text:
        return SpatialObjectKind.HELL_FORTRESS
    if _resolve_resource_type(normalized_text) is not None:
        return SpatialObjectKind.RESOURCE_NODE
    if _MONSTER_LEVEL_PATTERN.match(raw_text.strip()) is not None:
        return SpatialObjectKind.MONSTER
    if alliance_tag is not None:
        if any(token in normalized_text for token in _WORLD_ALLIANCE_BUILDING_TOKENS):
            return SpatialObjectKind.ALLIANCE_BUILDING
        return SpatialObjectKind.CASTLE
    if any(token in normalized_text for token in _WORLD_NEUTRAL_OBJECT_TOKENS):
        return SpatialObjectKind.ALTAR if "ALTAR" in normalized_text else SpatialObjectKind.DRAGONIA
    return None


def _classify_world_map_relationship(
    *,
    kind: SpatialObjectKind,
    normalized_text: str,
    alliance_tag: str | None,
    color_family: str | None,
    relationship_rules: object | None,
) -> SpatialObjectRelationship:
    """Returns the semantic ownership relationship for one typed world-map object."""

    del alliance_tag
    if kind in {
        SpatialObjectKind.MONSTER,
        SpatialObjectKind.HELL_FORTRESS,
        SpatialObjectKind.RESOURCE_NODE,
        SpatialObjectKind.ALTAR,
        SpatialObjectKind.DRAGONIA,
    }:
        return SpatialObjectRelationship.NEUTRAL
    self_castle_label = normalize_ocr_text(getattr(relationship_rules, "self_castle_label", "My Territory"))
    if normalized_text == self_castle_label:
        return SpatialObjectRelationship.SELF
    if color_family == getattr(relationship_rules, "self_color_family", "deep_blue"):
        return SpatialObjectRelationship.SELF
    if color_family == getattr(relationship_rules, "ally_name_color_family", "light_blue"):
        return SpatialObjectRelationship.ALLY
    if color_family == getattr(relationship_rules, "other_alliance_color_family", "yellow"):
        return SpatialObjectRelationship.OTHER
    return SpatialObjectRelationship.UNKNOWN


def _attach_home_city_building_levels(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    objects: tuple[DetectedSpatialObject, ...],
) -> tuple[DetectedSpatialObject, ...]:
    """Associates visible home-city building level badges with the nearest parsed building labels."""

    updated_objects = list(objects)
    candidate_levels = [
        (line, level)
        for line in lines
        if (level := _parse_home_city_level(line.text)) is not None
    ]
    for line, level in candidate_levels:
        best_index: int | None = None
        best_distance: int | None = None
        for index, object_ in enumerate(updated_objects):
            if object_.kind != SpatialObjectKind.HOME_BUILDING or object_.level is not None:
                continue
            if not _home_city_level_line_matches_object(image=image, line=line, object_=object_):
                continue
            object_center_x, object_center_y = object_.bounds.center()
            line_center_x = line.bounds.x + (line.bounds.width // 2)
            line_center_y = line.bounds.y + (line.bounds.height // 2)
            distance = abs(line_center_x - object_center_x) + abs(line_center_y - object_center_y)
            if best_distance is not None and distance >= best_distance:
                continue
            best_distance = distance
            best_index = index
        if best_index is None:
            continue
        updated_objects[best_index] = replace(updated_objects[best_index], level=level)
    return tuple(updated_objects)


def _parse_home_city_level(raw_text: str) -> int | None:
    """Returns one visible home-city building level badge value when the OCR text is level-shaped."""

    match = _HOME_CITY_LEVEL_PATTERN.match(raw_text.strip())
    if match is None:
        return None
    level = int(match.group("level"))
    if level <= 0:
        return None
    return level


def _home_city_level_line_matches_object(
    *,
    image: Image.Image,
    line: OcrLine,
    object_: DetectedSpatialObject,
) -> bool:
    """Returns whether one OCR level badge sits where the parsed building would display it."""

    max_horizontal_gap = max(64, int(image.width * 0.12))
    max_vertical_gap = max(72, int(image.height * 0.1))
    if line.bounds.y < object_.bounds.y - max(24, object_.bounds.height):
        return False
    if line.bounds.y > object_.bounds.y + max_vertical_gap:
        return False
    line_center_x = line.bounds.x + (line.bounds.width // 2)
    object_center_x = object_.bounds.x + (object_.bounds.width // 2)
    return abs(line_center_x - object_center_x) <= max_horizontal_gap


def _parse_home_city_objects(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    surface_definition: SurfaceDefinition | None,
) -> tuple[DetectedSpatialObject, ...]:
    """Extracts typed home-city buildings and empty slots from OCR-visible scene labels."""

    supported_kinds = None if surface_definition is None else frozenset(surface_definition.object_kinds)
    parsed_objects: list[DetectedSpatialObject] = []
    min_y = int(image.height * 0.12)
    max_y = int(image.height * 0.82)
    for line in lines:
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text == "":
            continue
        object_ = _classify_home_city_object(image=image, line=line, normalized_text=normalized_text)
        if object_ is None:
            continue
        if supported_kinds is not None and object_.kind not in supported_kinds:
            continue
        parsed_objects.append(object_)
    return tuple(parsed_objects)


def _classify_home_city_object(
    *,
    image: Image.Image,
    line: OcrLine,
    normalized_text: str,
) -> DetectedSpatialObject | None:
    """Returns one typed home-city spatial object when the OCR line describes scene content."""

    viewport_bounds = Bounds(x=0, y=0, width=image.width, height=image.height)
    bounds = Bounds(x=line.bounds.x, y=line.bounds.y, width=line.bounds.width, height=line.bounds.height)
    viewport_offset = _bounds_center_offset(bounds=bounds, origin=viewport_bounds.center())
    viewport_offset_ratio = _bounds_center_offset_ratio(bounds=bounds, viewport_bounds=viewport_bounds)
    object_definition = home_city_object_definition_for_label(line.text)
    if object_definition is not None:
        metadata = build_home_city_object_metadata(object_definition.id)
        metadata["home_city_label"] = line.text.strip()
        return DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=bounds,
            relationship=SpatialObjectRelationship.SELF,
            name_text=line.text.strip(),
            action_point=bounds.center(),
            viewport_offset=viewport_offset,
            viewport_offset_ratio=viewport_offset_ratio,
            metadata=metadata,
        )
    if normalized_text in _HOME_EMPTY_SLOT_TEXTS and not _looks_like_home_action_label(image=image, line=line):
        return DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_EMPTY_SLOT,
            bounds=bounds,
            relationship=SpatialObjectRelationship.SELF,
            name_text=line.text.strip(),
            action_point=bounds.center(),
            viewport_offset=viewport_offset,
            viewport_offset_ratio=viewport_offset_ratio,
        )
    return None


def _extract_alliance_tag(raw_text: str) -> tuple[str | None, str | None]:
    """Returns the alliance tag and stripped name when the label uses the supported `[TAG] Name` form."""

    match = _ALLIANCE_TAG_PATTERN.match(raw_text.strip())
    if match is None:
        return None, raw_text.strip()
    return match.group("tag"), match.group("name").strip()


def _extract_level_and_name(raw_text: str, *, fallback_name: str | None) -> tuple[int | None, str | None]:
    """Extracts a leading world-object level token while preserving the remaining display name."""

    match = _MONSTER_LEVEL_PATTERN.match(raw_text.strip())
    if match is None:
        return None, fallback_name
    return int(match.group("level")), match.group("name").strip()


def _looks_like_world_castle_label(normalized_text: str) -> bool:
    """Returns whether one OCR label matches the live kingdom/castle label form shown on the world map."""

    match = _WORLD_CASTLE_LABEL_PATTERN.match(normalized_text)
    if match is None:
        return False
    return sum(character.isdigit() for character in normalized_text) >= 8


def _extract_world_object_kingdom(normalized_text: str) -> str | None:
    """Returns the canonical kingdom token from one world-map castle label when OCR proves it."""

    if not _looks_like_world_castle_label(normalized_text):
        return None
    return f"K{normalized_text[1:4]}"


def _resolve_resource_type(normalized_text: str) -> str | None:
    """Returns the canonical resource type string implied by one world-node label."""

    for token, resource_type in _WORLD_RESOURCE_TYPE_BY_TOKEN.items():
        if token in normalized_text:
            return resource_type
    return None


def _looks_like_coordinate_overlay(normalized_text: str) -> bool:
    """Returns whether one OCR label looks like the fixed world-coordinate overlay instead of a scene object."""

    return normalized_text.startswith("X") or normalized_text.startswith("Y")


def _looks_like_home_action_label(*, image: Image.Image, line: OcrLine) -> bool:
    """Returns whether one `Build` OCR line sits in the fixed home-action area instead of the scene."""

    return (
        line.bounds.x <= int(image.width * 0.18)
        and line.bounds.y >= int(image.height * 0.15)
        and line.bounds.y <= int(image.height * 0.85)
    )


def _classify_color_family(*, image: Image.Image, bounds: object) -> str | None:
    """Returns the coarse label color family used by world-map relationship classification."""

    crop = image.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height)).convert("RGB")
    red_total = 0
    green_total = 0
    blue_total = 0
    pixels = crop.load()
    pixel_count = max(1, crop.width * crop.height)
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = pixels[x, y]
            red_total += red
            green_total += green
            blue_total += blue
    red = red_total / pixel_count
    green = green_total / pixel_count
    blue = blue_total / pixel_count
    if is_world_map_blue_family_pixel(red=red, green=green, blue=blue):
        if green >= 90 and green >= red:
            return "light_blue"
        return "deep_blue"
    if red >= 120 and green >= 120 and blue <= 140:
        return "yellow"
    return None


def _resolve_world_map_scan_bounds(*, image: Image.Image, requested_bounds: Bounds | None) -> Bounds:
    """Returns the visible world-map scan area, optionally narrowed to one requested subsection."""

    full_viewport_bounds = Bounds(
        x=0,
        y=int(image.height * _WORLD_MAP_VISIBLE_SCAN_TOP_RATIO),
        width=image.width,
        height=max(
            1,
            int(image.height * _WORLD_MAP_VISIBLE_SCAN_BOTTOM_RATIO)
            - int(image.height * _WORLD_MAP_VISIBLE_SCAN_TOP_RATIO),
        ),
    )
    if requested_bounds is None:
        return full_viewport_bounds
    left = max(full_viewport_bounds.x, requested_bounds.x)
    top = max(full_viewport_bounds.y, requested_bounds.y)
    right = min(full_viewport_bounds.x + full_viewport_bounds.width, requested_bounds.x + requested_bounds.width)
    bottom = min(full_viewport_bounds.y + full_viewport_bounds.height, requested_bounds.y + requested_bounds.height)
    if right <= left or bottom <= top:
        raise SelectorResolutionError(
            "Requested world-map scan bounds do not intersect the visible world viewport.",
            requested_bounds=requested_bounds,
            viewport_bounds=full_viewport_bounds,
        )
    return Bounds(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
    )


def _bounds_center_within_region(*, bounds: object, region: Bounds) -> bool:
    """Returns whether one OCR label is centered inside the requested scan region."""

    center_x = bounds.x + (bounds.width // 2)
    center_y = bounds.y + (bounds.height // 2)
    return (
        center_x >= region.x
        and center_x <= region.x + region.width
        and center_y >= region.y
        and center_y <= region.y + region.height
    )


def _bounds_center_offset(*, bounds: Bounds, origin: tuple[int, int]) -> tuple[int, int]:
    """Returns one bounds-center offset from the provided viewport-center origin."""

    center_x, center_y = bounds.center()
    return center_x - origin[0], center_y - origin[1]


def _bounds_center_offset_ratio(*, bounds: Bounds, viewport_bounds: Bounds) -> tuple[float, float]:
    """Returns one normalized bounds-center offset relative to the visible world viewport dimensions."""

    offset_x, offset_y = _bounds_center_offset(bounds=bounds, origin=viewport_bounds.center())
    return (
        offset_x / max(viewport_bounds.width, 1),
        offset_y / max(viewport_bounds.height, 1),
    )


def _estimate_world_coordinate(
    *,
    viewport_coordinate: tuple[int, int] | None,
    viewport_offset_ratio: tuple[float, float] | None,
) -> tuple[int, int] | None:
    """Returns a calibrated normalized world-coordinate estimate without mixing in raw screenshot pixels."""

    if viewport_coordinate is None or viewport_offset_ratio is None:
        return None
    return (
        viewport_coordinate[0] + int(round(viewport_offset_ratio[0] * _WORLD_MAP_ESTIMATED_VIEWPORT_WIDTH_UNITS)),
        viewport_coordinate[1] + int(round(viewport_offset_ratio[1] * _WORLD_MAP_ESTIMATED_VIEWPORT_HEIGHT_UNITS)),
    )
