"""Canonical selector registry and selector metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import Bounds, SelectorResolutionKind, VisibleElement
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.pnc_parser_candidates import SUPPORTED_PARSER_CANDIDATE_IDS
from pnc_automation.vision.selector_catalog import load_selector_catalog_document
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind


class SelectorStatus(StrEnum):
    """Tracks refinement maturity for selectors."""

    PLANNED = "planned"
    SCREENSHOT_SEEDED = "screenshot_seeded"
    CLICK_MAPPED = "click_mapped"
    INTERACTION_VALIDATED = "interaction_validated"
    TASK_VALIDATED = "task_validated"


@dataclass(frozen=True, slots=True)
class Region:
    """Defines one rectangular image region."""

    x: int
    y: int
    width: int
    height: int


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

    def materialize(self, *, selector_id: UiElementId, image_size: tuple[int, int]) -> VisibleElement:
        """Builds one visible selector using normalized geometry for the current screenshot dimensions."""

        image_width, image_height = image_size
        bounds = Bounds(
            x=_clamp_coordinate(int(image_width * self.x_ratio), maximum=max(0, image_width - 1)),
            y=_clamp_coordinate(int(image_height * self.y_ratio), maximum=max(0, image_height - 1)),
            width=max(1, int(image_width * self.width_ratio)),
            height=max(1, int(image_height * self.height_ratio)),
        )
        action_point = None
        if self.action_x_ratio is not None and self.action_y_ratio is not None:
            action_point = (
                _clamp_coordinate(int(image_width * self.action_x_ratio), maximum=max(0, image_width - 1)),
                _clamp_coordinate(int(image_height * self.action_y_ratio), maximum=max(0, image_height - 1)),
            )
        return VisibleElement(
            selector_id=selector_id,
            bounds=bounds,
            confidence=1.0,
            action_point=action_point,
        )


@dataclass(frozen=True, slots=True)
class SelectorResolutionStep:
    """Defines one ordered runtime resolution step for a selector."""

    kind: SelectorResolutionKind
    template_path: Path | None = None
    threshold: float = 0.98
    ocr_region: Region | None = None
    relative_bounds: RelativeBounds | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        """Rejects inconsistent step configuration before it reaches runtime use."""

        if self.kind == SelectorResolutionKind.TEMPLATE:
            if self.template_path is None:
                raise SelectorResolutionError("Template resolution steps must declare a template asset path.")
            if not 0 < self.threshold <= 1:
                raise SelectorResolutionError("Template resolution thresholds must stay within (0, 1].", threshold=self.threshold)
            return
        if self.kind == SelectorResolutionKind.OCR_REGION:
            return
        if self.kind == SelectorResolutionKind.PARSER_CANDIDATE:
            if any(value is not None for value in (self.template_path, self.ocr_region, self.relative_bounds)):
                raise SelectorResolutionError("Parser-candidate steps must not declare exact-detection geometry.")
            return
        if self.kind == SelectorResolutionKind.RELATIVE_BOUNDS:
            if self.relative_bounds is None:
                raise SelectorResolutionError("Relative-bounds resolution steps must declare normalized geometry.")
            return
        raise SelectorResolutionError("Unsupported selector resolution step kind.", kind=self.kind)

    @property
    def strategy_label(self) -> str:
        """Returns the stable diagnostic label for this step."""

        return self.label or self.kind.value

    @property
    def is_exact(self) -> bool:
        """Returns whether the step can be evaluated before parser-candidate fallback."""

        return self.kind in {SelectorResolutionKind.TEMPLATE, SelectorResolutionKind.OCR_REGION}

    def materialize(self, *, selector_id: UiElementId, image_size: tuple[int, int]) -> VisibleElement:
        """Materializes one relative-bounds step into a visible element."""

        if self.relative_bounds is None:
            raise SelectorResolutionError(
                "Only relative-bounds resolution steps can be materialized.",
                selector_id=selector_id.value,
                resolution_kind=self.kind.value,
            )
        return self.relative_bounds.materialize(selector_id=selector_id, image_size=image_size)


@dataclass(frozen=True, slots=True)
class SelectorResolutionPolicy:
    """Defines the ordered runtime resolution policy for one selector."""

    steps: tuple[SelectorResolutionStep, ...] = ()

    def __post_init__(self) -> None:
        """Rejects ambiguous or unsupported resolution ordering."""

        seen_kinds: set[SelectorResolutionKind] = set()
        for index, step in enumerate(self.steps):
            if step.kind in seen_kinds:
                raise SelectorResolutionError(
                    "Selectors must not declare duplicate resolution steps.",
                    resolution_kind=step.kind.value,
                )
            seen_kinds.add(step.kind)
            if step.kind == SelectorResolutionKind.RELATIVE_BOUNDS and index != len(self.steps) - 1:
                raise SelectorResolutionError(
                    "Relative-bounds fallback must be the final selector resolution step.",
                )

    def has_kind(self, kind: SelectorResolutionKind) -> bool:
        """Returns whether the policy contains the requested strategy kind."""

        return any(step.kind == kind for step in self.steps)

    def stronger_step_indexes(self, strategy_index: int) -> tuple[int, ...]:
        """Returns the indexes that are stronger than the provided successful strategy."""

        return tuple(index for index in range(strategy_index))


@dataclass(frozen=True, slots=True)
class SelectorDefinition:
    """Defines one selector in the canonical registry."""

    id: UiElementId
    screens: tuple[ScreenType, ...]
    status: SelectorStatus
    interaction_kind: SelectorInteractionKind = SelectorInteractionKind.UNKNOWN
    resolution: SelectorResolutionPolicy = field(default_factory=SelectorResolutionPolicy)
    click: ClickDefinition | None = field(default_factory=ClickDefinition)
    click_outcomes: tuple[ClickOutcome, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorRegistry:
    """Owns canonical selector lookup and validation."""

    selectors: tuple[SelectorDefinition, ...]

    def __post_init__(self) -> None:
        """Ensures selector identifiers remain unique and resolution contracts stay valid."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed.", duplicates=sorted(duplicates))
        for selector in self.selectors:
            _validate_selector_resolution_contract(selector)

    def all(self) -> tuple[SelectorDefinition, ...]:
        """Returns all selector definitions."""

        return self.selectors

    def require(self, selector_id: UiElementId) -> SelectorDefinition:
        """Returns one selector definition or fails fast."""

        for selector in self.selectors:
            if selector.id == selector_id:
                return selector
        raise SelectorResolutionError(f"Unknown selector '{selector_id}'.", selector_id=selector_id)

    def for_screen(self, screen_type: ScreenType) -> tuple[SelectorDefinition, ...]:
        """Returns selectors that can appear on the requested screen."""

        return tuple(selector for selector in self.selectors if screen_type in selector.screens)


def build_default_selector_registry(
    template_root: Path | None = None,
    *,
    catalog_path: Path | None = None,
) -> SelectorRegistry:
    """Builds the static selector registry described by the implementation plan."""

    root = template_root or (Path(__file__).resolve().parents[2] / "templates" / "pnc")
    catalog = load_selector_catalog_document(catalog_path)
    return SelectorRegistry(
        selectors=tuple(_create_selector_from_catalog_entry(selector=selector, root=root) for selector in catalog.selectors)
    )


def _create_selector_from_catalog_entry(*, selector: object, root: Path) -> SelectorDefinition:
    """Builds one runtime selector from one raw catalog entry."""

    interaction_kind = _create_interaction_kind(
        getattr(selector, "interaction_kind", None),
        click=getattr(selector, "click", None),
    )
    return SelectorDefinition(
        id=_require_selector_id(selector.id),
        screens=tuple(_require_screen_type(screen) for screen in selector.screens),
        status=_require_selector_status(selector.status),
        interaction_kind=interaction_kind,
        resolution=_create_resolution_policy(raw_steps=getattr(selector, "resolution"), root=root),
        click=_create_click_definition(
            interaction_kind=interaction_kind,
            click=selector.click,
        ),
        click_outcomes=tuple(_create_click_outcome(outcome) for outcome in selector.click.outcomes) if selector.click is not None else (),
        notes=selector.notes,
    )


def _create_resolution_policy(*, raw_steps: tuple[object, ...], root: Path) -> SelectorResolutionPolicy:
    """Builds one typed selector-resolution policy from the raw catalog metadata."""

    return SelectorResolutionPolicy(steps=tuple(_create_resolution_step(step, root=root) for step in raw_steps))


def _create_resolution_step(step: object, *, root: Path) -> SelectorResolutionStep:
    """Builds one typed runtime resolution step from the raw catalog metadata."""

    kind = _require_resolution_kind(getattr(step, "kind"))
    template_path = getattr(step, "template_path", None)
    if template_path is not None:
        template_path = Path(template_path)
        if not template_path.is_absolute():
            template_path = root / template_path
    return SelectorResolutionStep(
        kind=kind,
        template_path=template_path,
        threshold=float(getattr(step, "threshold", 0.98)),
        ocr_region=_create_region(getattr(step, "ocr_region", None)),
        relative_bounds=_create_relative_bounds(getattr(step, "relative_bounds", None)),
        label=getattr(step, "label", None),
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


def _require_resolution_kind(kind_name: str) -> SelectorResolutionKind:
    """Converts one raw resolution kind into the typed enum value."""

    try:
        return SelectorResolutionKind(kind_name)
    except ValueError as error:
        raise SelectorResolutionError("Unknown selector resolution kind in selector catalog.", resolution_kind=kind_name) from error


def _create_click_definition(
    *,
    interaction_kind: SelectorInteractionKind,
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


def _create_region(region: object | None) -> Region | None:
    """Builds one typed OCR region from the loaded catalog metadata."""

    if region is None:
        return None
    return Region(
        x=int(getattr(region, "x")),
        y=int(getattr(region, "y")),
        width=int(getattr(region, "width")),
        height=int(getattr(region, "height")),
    )


def _create_click_outcome(outcome: object) -> ClickOutcome:
    """Builds one typed click outcome from the raw catalog metadata."""

    target_screen = getattr(outcome, "target_screen")
    verification_selectors = tuple(
        _require_selector_id(selector_id) for selector_id in getattr(outcome, "verification_selectors")
    )
    verification_texts = tuple(getattr(outcome, "verification_texts"))
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


def _validate_selector_resolution_contract(selector: SelectorDefinition) -> None:
    """Rejects invalid runtime selector contracts after raw catalog loading."""

    if selector.status != SelectorStatus.PLANNED and not selector.resolution.steps:
        raise SelectorResolutionError(
            "Selectors above planned must declare at least one resolution step.",
            selector_id=selector.id.value,
            status=selector.status.value,
        )
    if selector.resolution.has_kind(SelectorResolutionKind.PARSER_CANDIDATE) and selector.id not in SUPPORTED_PARSER_CANDIDATE_IDS:
        raise SelectorResolutionError(
            "Parser-candidate resolution requires trusted screen-interpreter support for the selector id.",
            selector_id=selector.id.value,
        )
    if selector.interaction_kind == SelectorInteractionKind.LABEL and selector.resolution.has_kind(SelectorResolutionKind.RELATIVE_BOUNDS):
        raise SelectorResolutionError(
            "Label selectors must not declare relative-bounds fallback.",
            selector_id=selector.id.value,
            interaction_kind=selector.interaction_kind.value,
        )
    if selector.interaction_kind != SelectorInteractionKind.NAVIGATION:
        return
    if not selector.resolution.has_kind(SelectorResolutionKind.RELATIVE_BOUNDS):
        return
    if not selector.click_outcomes:
        raise SelectorResolutionError(
            "Navigation selectors with geometry fallback must declare reviewed click outcomes.",
            selector_id=selector.id.value,
        )
    if not any(
        outcome.target_screen is not None and (outcome.verification_selectors or outcome.verification_texts)
        for outcome in selector.click_outcomes
    ):
        raise SelectorResolutionError(
            "Navigation selectors with geometry fallback must declare reviewed destination verification evidence.",
            selector_id=selector.id.value,
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
