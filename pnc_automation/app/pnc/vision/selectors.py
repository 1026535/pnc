"""Canonical selector registry and selector metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds, Region
from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialSurfaceType,
    SpatialViewportAddressingKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_catalog import load_selector_catalog_document
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind


class DetectionKind(StrEnum):
    """Supported selector detection mechanisms."""

    TEMPLATE = "template"
    OCR_REGION = "ocr_region"
    ANCHORED_REGION = "anchored_region"
    COLLECTION = "collection"
    PLANNED = "planned"


class SelectorStatus(StrEnum):
    """Tracks refinement maturity for selectors."""

    PLANNED = "planned"
    SCREENSHOT_SEEDED = "screenshot_seeded"
    CLICK_MAPPED = "click_mapped"
    INTERACTION_VALIDATED = "interaction_validated"
    TASK_VALIDATED = "task_validated"

@dataclass(frozen=True, slots=True)
class ClickDefinition:
    """Defines how a selector should be converted into a click target."""

    anchor: str = "center"


@dataclass(frozen=True, slots=True)
class ClickOutcome:
    """Captures one reviewed selector transition outcome."""

    target_screen: ScreenType | None = None
    verification_selectors: tuple[UiElementId, ...] = ()
    verification_texts: tuple[str, ...] = ()
    safe_to_click: bool = True
    monetized: bool = False
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RelativeBounds:
    """Defines one stable screen-relative selector region from top-left plus size and optional tap point."""

    x_ratio: float
    y_ratio: float
    width_ratio: float
    height_ratio: float
    action_x_ratio: float | None = None
    action_y_ratio: float | None = None

    def __post_init__(self) -> None:
        """Rejects invalid relative geometry before it reaches runtime use."""

        _require_ratio(self.x_ratio, field_name="x_ratio", inclusive_zero=True)
        _require_ratio(self.y_ratio, field_name="y_ratio", inclusive_zero=True)
        _require_ratio(self.width_ratio, field_name="width_ratio", inclusive_zero=False)
        _require_ratio(self.height_ratio, field_name="height_ratio", inclusive_zero=False)
        if self.x_ratio + self.width_ratio > 1:
            raise SelectorResolutionError("Selector relative_bounds x_ratio + width_ratio must not exceed 1.")
        if self.y_ratio + self.height_ratio > 1:
            raise SelectorResolutionError("Selector relative_bounds y_ratio + height_ratio must not exceed 1.")
        if (self.action_x_ratio is None) != (self.action_y_ratio is None):
            raise SelectorResolutionError(
                "Selector relative_bounds must either declare both action ratios or neither one.",
            )
        if self.action_x_ratio is not None:
            _require_ratio(self.action_x_ratio, field_name="action_x_ratio", inclusive_zero=True)
            _require_ratio(self.action_y_ratio, field_name="action_y_ratio", inclusive_zero=True)

    def materialize_region(self, *, image_size: tuple[int, int]) -> Bounds:
        """Builds one concrete screenshot bounds object from normalized selector ratios."""

        image_width, image_height = _require_positive_image_size(image_size)
        x, width = _materialize_axis(start_ratio=self.x_ratio, size_ratio=self.width_ratio, total=image_width)
        y, height = _materialize_axis(start_ratio=self.y_ratio, size_ratio=self.height_ratio, total=image_height)
        return Bounds(x=x, y=y, width=width, height=height)

    def materialize(self, *, selector_id: UiElementId, image_size: tuple[int, int]) -> VisibleElement:
        """Builds one visible selector using normalized top-left/size data for the current screenshot dimensions."""

        image_width, image_height = _require_positive_image_size(image_size)
        bounds = self.materialize_region(image_size=image_size)
        action_point = None
        if self.action_x_ratio is not None and self.action_y_ratio is not None:
            action_point = (
                _clamp_coordinate(int(round(image_width * self.action_x_ratio)), maximum=max(0, image_width - 1)),
                _clamp_coordinate(int(round(image_height * self.action_y_ratio)), maximum=max(0, image_height - 1)),
            )
        return VisibleElement(
            selector_id=selector_id,
            bounds=bounds,
            confidence=1.0,
            source_kind=VisibleElementSourceKind.GEOMETRY,
            action_point=action_point,
        )


@dataclass(frozen=True, slots=True)
class SelectorDefinition:
    """Defines one selector in the canonical registry."""

    id: UiElementId
    screens: tuple[ScreenType, ...]
    detection_kind: DetectionKind
    status: SelectorStatus
    interaction_kind: SelectorInteractionKind = SelectorInteractionKind.UNKNOWN
    template_path: Path | None = None
    threshold: float = 0.98
    click: ClickDefinition | None = field(default_factory=ClickDefinition)
    relative_bounds: RelativeBounds | None = None
    materialize_relative_bounds: bool = True
    click_outcomes: tuple[ClickOutcome, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SurfaceViewportDefinition:
    """Defines the selector-backed viewport controls for one spatial surface."""

    addressing_kind: SpatialViewportAddressingKind
    coordinate_selector: UiElementId | None = None
    home_selector: UiElementId | None = None
    optional_zoom_indicator_selector: UiElementId | None = None


@dataclass(frozen=True, slots=True)
class SurfaceRelationshipRulesDefinition:
    """Defines the canonical relationship heuristics used by one spatial surface parser."""

    self_castle_label: str | None = None
    ally_name_color_family: str | None = None
    other_alliance_color_family: str | None = None
    self_color_family: str | None = None


@dataclass(frozen=True, slots=True)
class SurfaceDefinition:
    """Defines one runtime spatial surface loaded from the canonical catalog."""

    id: str
    surface_type: SpatialSurfaceType
    screen: ScreenType
    viewport: SurfaceViewportDefinition
    object_kinds: tuple[SpatialObjectKind, ...]
    relationship_rules: SurfaceRelationshipRulesDefinition | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorRegistry:
    """Owns canonical selector lookup and validation."""

    selectors: tuple[SelectorDefinition, ...]
    surfaces: tuple[SurfaceDefinition, ...] = ()

    def __post_init__(self) -> None:
        """Ensures selector identifiers remain unique."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed.", duplicates=sorted(duplicates))
        surface_ids = [surface.id for surface in self.surfaces]
        surface_duplicates = {surface_id for surface_id in surface_ids if surface_ids.count(surface_id) > 1}
        if surface_duplicates:
            raise SelectorResolutionError("Duplicate spatial surface ids are not allowed.", duplicates=sorted(surface_duplicates))

    def all(self) -> tuple[SelectorDefinition, ...]:
        """Returns all selector definitions."""

        return self.selectors

    def all_surfaces(self) -> tuple[SurfaceDefinition, ...]:
        """Returns all spatial-surface definitions."""

        return self.surfaces

    def require(self, selector_id: UiElementId) -> SelectorDefinition:
        """Returns one selector definition or fails fast."""

        for selector in self.selectors:
            if selector.id == selector_id:
                return selector
        raise SelectorResolutionError(f"Unknown selector '{selector_id}'.", selector_id=selector_id)

    def for_screen(self, screen_type: ScreenType) -> tuple[SelectorDefinition, ...]:
        """Returns selectors that can appear on the requested screen."""

        return tuple(selector for selector in self.selectors if screen_type in selector.screens)

    def surface_for_screen(self, screen_type: ScreenType) -> SurfaceDefinition | None:
        """Returns the spatial surface bound to the requested screen when one exists."""

        for surface in self.surfaces:
            if surface.screen == screen_type:
                return surface
        return None

    def require_surface(self, surface_type: SpatialSurfaceType) -> SurfaceDefinition:
        """Returns one spatial surface definition or fails fast."""

        for surface in self.surfaces:
            if surface.surface_type == surface_type:
                return surface
        raise SelectorResolutionError("Unknown spatial surface type.", surface_type=surface_type)

    def materialize_for_screen(
        self,
        screen_type: ScreenType,
        *,
        image_size: tuple[int, int],
        exclude_selector_ids: frozenset[UiElementId] = frozenset(),
    ) -> tuple[VisibleElement, ...]:
        """Builds every geometry-backed selector for the requested screen."""

        return tuple(
            selector.relative_bounds.materialize(selector_id=selector.id, image_size=image_size)
            for selector in self.for_screen(screen_type)
            if (
                selector.relative_bounds is not None
                and selector.materialize_relative_bounds
                and selector.detection_kind != DetectionKind.OCR_REGION
                and selector.id not in exclude_selector_ids
            )
        )


def build_default_selector_registry(
    template_root: Path | None = None,
    *,
    catalog_path: Path | None = None,
) -> SelectorRegistry:
    """Builds the static selector registry described by the implementation plan."""

    root = template_root or default_selector_template_root()
    catalog = load_selector_catalog_document(catalog_path)
    return SelectorRegistry(
        selectors=tuple(_create_selector_from_catalog_entry(selector=selector, root=root) for selector in catalog.selectors),
        surfaces=tuple(_create_surface_from_catalog_entry(surface=surface) for surface in catalog.surfaces),
    )


def default_selector_template_root() -> Path:
    """Returns the canonical package-root-relative template directory for selector assets."""

    return Path(__file__).resolve().parents[3] / "templates" / "pnc"


def _create_selector_from_catalog_entry(*, selector: object, root: Path) -> SelectorDefinition:
    """Builds one runtime selector from one raw catalog entry."""

    interaction_kind = _create_interaction_kind(
        getattr(selector, "interaction_kind", None),
        click=getattr(selector, "click", None),
    )
    return _create_selector(
        selector_id=_require_selector_id(selector.id),
        screens=tuple(_require_screen_type(screen) for screen in selector.screens),
        root=root,
        detection_kind=_require_detection_kind(selector.detection_kind),
        status=_require_selector_status(selector.status),
        interaction_kind=interaction_kind,
        click=_create_click_definition(
            interaction_kind=interaction_kind,
            detection_kind_name=selector.detection_kind,
            click=selector.click,
        ),
        relative_bounds=_create_relative_bounds(getattr(selector, "relative_bounds", None)),
        materialize_relative_bounds=getattr(selector, "materialize_relative_bounds", True),
        click_outcomes=tuple(_create_click_outcome(outcome) for outcome in selector.click.outcomes) if selector.click is not None else (),
        notes=selector.notes,
    )


def _create_surface_from_catalog_entry(*, surface: object) -> SurfaceDefinition:
    """Builds one runtime spatial surface from one raw catalog entry."""

    return SurfaceDefinition(
        id=getattr(surface, "id"),
        surface_type=_require_surface_type(getattr(surface, "surface_type")),
        screen=_require_screen_type(getattr(surface, "screen")),
        viewport=_create_surface_viewport(getattr(surface, "viewport")),
        object_kinds=tuple(_require_spatial_object_kind(object_kind) for object_kind in getattr(surface, "object_kinds")),
        relationship_rules=_create_surface_relationship_rules(getattr(surface, "relationship_rules", None)),
        notes=tuple(getattr(surface, "notes", ())),
    )


def _create_selector(
    *,
    selector_id: UiElementId,
    screens: tuple[ScreenType, ...],
    root: Path,
    detection_kind: DetectionKind,
    status: SelectorStatus,
    interaction_kind: SelectorInteractionKind,
    click: ClickDefinition | None,
    relative_bounds: RelativeBounds | None,
    materialize_relative_bounds: bool,
    click_outcomes: tuple[ClickOutcome, ...],
    notes: tuple[str, ...],
) -> SelectorDefinition:
    """Creates one default selector definition with canonical metadata defaults."""

    if status == SelectorStatus.PLANNED:
        return SelectorDefinition(
            id=selector_id,
            screens=screens,
            detection_kind=DetectionKind.PLANNED,
            status=status,
            interaction_kind=interaction_kind,
            template_path=None,
            click=click,
            relative_bounds=relative_bounds,
            materialize_relative_bounds=materialize_relative_bounds,
            click_outcomes=click_outcomes,
            notes=notes,
        )

    if detection_kind == DetectionKind.OCR_REGION:
        return SelectorDefinition(
            id=selector_id,
            screens=screens,
            detection_kind=DetectionKind.OCR_REGION,
            status=status,
            interaction_kind=interaction_kind,
            template_path=None,
            click=click,
            relative_bounds=relative_bounds,
            materialize_relative_bounds=materialize_relative_bounds,
            click_outcomes=click_outcomes,
            notes=notes,
        )

    return SelectorDefinition(
        id=selector_id,
        screens=screens,
        detection_kind=detection_kind,
        status=status,
        interaction_kind=interaction_kind,
        template_path=(root / f"{selector_id.value.lower()}.png") if detection_kind in {DetectionKind.TEMPLATE, DetectionKind.COLLECTION} else None,
        click=click,
        relative_bounds=relative_bounds,
        materialize_relative_bounds=materialize_relative_bounds,
        click_outcomes=click_outcomes,
        notes=notes,
    )


def _require_selector_id(selector_id: str) -> UiElementId:
    """Converts one raw selector identifier into the typed enum value."""

    try:
        return UiElementId[selector_id]
    except KeyError as error:
        raise SelectorResolutionError("Unknown selector id in selector catalog.", selector_id=selector_id) from error


def _require_screen_type(screen_name: str) -> ScreenType:
    """Converts one raw screen identifier into the typed enum value."""

    try:
        return ScreenType[screen_name]
    except KeyError as error:
        raise SelectorResolutionError("Unknown screen type in selector catalog.", screen_type=screen_name) from error


def _require_selector_status(status: str) -> SelectorStatus:
    """Converts one raw selector status into the typed enum value."""

    try:
        return SelectorStatus(status)
    except ValueError as error:
        raise SelectorResolutionError("Unknown selector status in selector catalog.", status=status) from error


def _require_detection_kind(detection_kind: str) -> DetectionKind:
    """Converts one raw detection kind into the typed enum value."""

    try:
        return DetectionKind(detection_kind)
    except ValueError as error:
        raise SelectorResolutionError("Unknown selector detection kind in selector catalog.", detection_kind=detection_kind) from error


def _create_click_definition(
    *,
    interaction_kind: SelectorInteractionKind,
    detection_kind_name: str,
    click: object,
) -> ClickDefinition | None:
    """Builds optional click metadata while preserving canonical defaults."""

    if click is not None:
        anchor = getattr(click, "anchor", None)
        if not isinstance(anchor, str) or anchor == "":
            raise SelectorResolutionError("Selector click anchors must be non-empty strings.", anchor=anchor)
        return ClickDefinition(anchor=anchor)
    if interaction_kind == SelectorInteractionKind.LABEL:
        return None
    detection_kind = _require_detection_kind(detection_kind_name)
    if detection_kind in {DetectionKind.OCR_REGION, DetectionKind.PLANNED}:
        return None
    return ClickDefinition()


def _create_interaction_kind(
    interaction_kind_name: str | None,
    *,
    click: object,
) -> SelectorInteractionKind:
    """Builds one typed interaction kind, falling back to the reviewed click contract when absent."""

    if interaction_kind_name is not None:
        return _require_interaction_kind(interaction_kind_name)
    if click is not None and any(getattr(outcome, "target_screen", None) is not None for outcome in getattr(click, "outcomes", ())):
        return SelectorInteractionKind.NAVIGATION
    return SelectorInteractionKind.UNKNOWN


def _create_relative_bounds(relative_bounds: object | None) -> RelativeBounds | None:
    """Builds optional runtime geometry from the loaded catalog metadata."""

    if relative_bounds is None:
        return None
    return RelativeBounds(
        x_ratio=float(getattr(relative_bounds, "x_ratio")),
        y_ratio=float(getattr(relative_bounds, "y_ratio")),
        width_ratio=float(getattr(relative_bounds, "width_ratio")),
        height_ratio=float(getattr(relative_bounds, "height_ratio")),
        action_x_ratio=None
        if getattr(relative_bounds, "action_x_ratio") is None
        else float(getattr(relative_bounds, "action_x_ratio")),
        action_y_ratio=None
        if getattr(relative_bounds, "action_y_ratio") is None
        else float(getattr(relative_bounds, "action_y_ratio")),
    )


def _create_click_outcome(outcome: object) -> ClickOutcome:
    """Builds one typed click outcome from the raw catalog metadata."""

    target_screen = getattr(outcome, "target_screen")
    verification_selectors = tuple(
        _require_selector_id(selector_id) for selector_id in getattr(outcome, "verification_selectors")
    )
    verification_texts = tuple(getattr(outcome, "verification_texts"))
    if verification_texts:
        raise SelectorResolutionError(
            "Reviewed click outcomes do not support verification_texts at runtime.",
            target_screen=target_screen,
            verification_texts=verification_texts,
        )
    notes = tuple(getattr(outcome, "notes"))
    return ClickOutcome(
        target_screen=None if target_screen is None else _require_screen_type(target_screen),
        verification_selectors=verification_selectors,
        verification_texts=verification_texts,
        safe_to_click=bool(getattr(outcome, "safe_to_click")),
        monetized=bool(getattr(outcome, "monetized")),
        notes=notes,
    )


def _require_interaction_kind(interaction_kind_name: str) -> SelectorInteractionKind:
    """Converts one raw interaction kind into the typed enum value."""

    try:
        return SelectorInteractionKind(interaction_kind_name)
    except ValueError as error:
        raise SelectorResolutionError(
            "Unknown selector interaction kind in selector catalog.",
            interaction_kind=interaction_kind_name,
    ) from error


def _require_surface_type(surface_type: str) -> SpatialSurfaceType:
    """Converts one raw spatial-surface type into the typed enum value."""

    try:
        return SpatialSurfaceType(surface_type)
    except ValueError as error:
        raise SelectorResolutionError("Unknown spatial surface type in selector catalog.", surface_type=surface_type) from error


def _require_spatial_object_kind(object_kind: str) -> SpatialObjectKind:
    """Converts one raw spatial object kind into the typed enum value."""

    try:
        return SpatialObjectKind(object_kind)
    except ValueError as error:
        raise SelectorResolutionError(
            "Unknown spatial object kind in selector catalog.",
            object_kind=object_kind,
        ) from error


def _require_spatial_viewport_addressing_kind(addressing_kind: str) -> SpatialViewportAddressingKind:
    """Converts one raw spatial viewport addressing kind into the typed enum value."""

    try:
        return SpatialViewportAddressingKind(addressing_kind)
    except ValueError as error:
        raise SelectorResolutionError(
            "Unknown spatial viewport addressing kind in selector catalog.",
            addressing_kind=addressing_kind,
        ) from error


def _create_surface_viewport(viewport: object) -> SurfaceViewportDefinition:
    """Builds one typed spatial viewport definition from the raw catalog metadata."""

    return SurfaceViewportDefinition(
        addressing_kind=_require_spatial_viewport_addressing_kind(getattr(viewport, "addressing_kind")),
        coordinate_selector=None
        if getattr(viewport, "coordinate_selector", None) is None
        else _require_selector_id(getattr(viewport, "coordinate_selector")),
        home_selector=None
        if getattr(viewport, "home_selector", None) is None
        else _require_selector_id(getattr(viewport, "home_selector")),
        optional_zoom_indicator_selector=None
        if getattr(viewport, "optional_zoom_indicator_selector", None) is None
        else _require_selector_id(getattr(viewport, "optional_zoom_indicator_selector")),
    )


def _create_surface_relationship_rules(
    relationship_rules: object | None,
) -> SurfaceRelationshipRulesDefinition | None:
    """Builds optional relationship heuristics for one spatial surface."""

    if relationship_rules is None:
        return None
    return SurfaceRelationshipRulesDefinition(
        self_castle_label=getattr(relationship_rules, "self_castle_label", None),
        ally_name_color_family=getattr(relationship_rules, "ally_name_color_family", None),
        other_alliance_color_family=getattr(relationship_rules, "other_alliance_color_family", None),
        self_color_family=getattr(relationship_rules, "self_color_family", None),
    )


def _require_ratio(value: float, *, field_name: str, inclusive_zero: bool) -> None:
    """Rejects runtime selector ratios outside the supported normalized range."""

    if inclusive_zero:
        if not 0 <= value <= 1:
            raise SelectorResolutionError("Selector relative_bounds ratios must stay within [0, 1].", field_name=field_name)
        return
    if not 0 < value <= 1:
        raise SelectorResolutionError("Selector relative_bounds sizes must stay within (0, 1].", field_name=field_name)


def _clamp_coordinate(value: int, *, maximum: int) -> int:
    """Clamps one pixel coordinate to the current screenshot bounds."""

    return min(max(0, value), maximum)


def _materialize_axis(*, start_ratio: float, size_ratio: float, total: int) -> tuple[int, int]:
    """Converts one normalized axis into a bounded pixel start and size."""

    start = _clamp_coordinate(int(round(total * start_ratio)), maximum=max(0, total - 1))
    end = _clamp_edge(int(round(total * (start_ratio + size_ratio))), minimum=start + 1, maximum=total)
    return start, max(1, end - start)


def _clamp_edge(value: int, *, minimum: int, maximum: int) -> int:
    """Clamps one rectangle edge to the current screenshot size."""

    return min(max(minimum, value), maximum)


def _require_positive_image_size(image_size: tuple[int, int]) -> tuple[int, int]:
    """Rejects non-positive screenshot sizes before geometry materialization."""

    width, height = image_size
    if width <= 0 or height <= 0:
        raise SelectorResolutionError("Selector geometry requires positive screenshot dimensions.", image_size=image_size)
    return width, height
