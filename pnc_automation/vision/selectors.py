"""Canonical selector registry and selector metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.selector_catalog import load_selector_catalog_document


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
class SelectorDefinition:
    """Defines one selector in the canonical registry."""

    id: UiElementId
    screens: tuple[ScreenType, ...]
    detection_kind: DetectionKind
    status: SelectorStatus
    template_path: Path | None = None
    threshold: float = 0.98
    click: ClickDefinition | None = field(default_factory=ClickDefinition)
    ocr_region: Region | None = None
    click_outcomes: tuple[ClickOutcome, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorRegistry:
    """Owns canonical selector lookup and validation."""

    selectors: tuple[SelectorDefinition, ...]

    def __post_init__(self) -> None:
        """Ensures selector identifiers remain unique."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed.", duplicates=sorted(duplicates))

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
        selectors=tuple(
            _create_selector(
                selector_id=_require_selector_id(selector.id),
                screens=tuple(_require_screen_type(screen) for screen in selector.screens),
                root=root,
                detection_kind=_require_detection_kind(selector.detection_kind),
                status=_require_selector_status(selector.status),
                click=_create_click_definition(selector.detection_kind, selector.click),
                click_outcomes=tuple(_create_click_outcome(outcome) for outcome in selector.click.outcomes) if selector.click is not None else (),
                notes=selector.notes,
            )
            for selector in catalog.selectors
        )
    )


def _create_selector(
    *,
    selector_id: UiElementId,
    screens: tuple[ScreenType, ...],
    root: Path,
    detection_kind: DetectionKind,
    status: SelectorStatus,
    click: ClickDefinition | None,
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
            template_path=None,
            click=click,
            click_outcomes=click_outcomes,
            notes=notes,
        )

    if detection_kind == DetectionKind.OCR_REGION:
        return SelectorDefinition(
            id=selector_id,
            screens=screens,
            detection_kind=DetectionKind.OCR_REGION,
            status=status,
            template_path=None,
            click=click,
            click_outcomes=click_outcomes,
            notes=notes,
        )

    return SelectorDefinition(
        id=selector_id,
        screens=screens,
        detection_kind=detection_kind,
        status=status,
        template_path=(root / f"{selector_id.value.lower()}.png") if detection_kind in {DetectionKind.TEMPLATE, DetectionKind.COLLECTION} else None,
        click=click,
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
    detection_kind_name: str,
    click: object,
) -> ClickDefinition | None:
    """Builds optional click metadata while preserving canonical defaults."""

    if click is not None:
        anchor = getattr(click, "anchor", None)
        if not isinstance(anchor, str) or anchor == "":
            raise SelectorResolutionError("Selector click anchors must be non-empty strings.", anchor=anchor)
        return ClickDefinition(anchor=anchor)
    detection_kind = _require_detection_kind(detection_kind_name)
    if detection_kind in {DetectionKind.OCR_REGION, DetectionKind.PLANNED}:
        return None
    return ClickDefinition()


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
