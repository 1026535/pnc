"""Loads and writes the canonical selector catalog edited by offline refinement tooling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind

_CATALOG_HEADER_LINES = (
    "# `relative_bounds` is always normalized to the current screenshot size and is the canonical region schema",
    "# for both click geometry and `detection_kind: ocr_region` OCR crops:",
    "# - `x_ratio` / `y_ratio`: top-left corner of the clickable region, not the center",
    "# - `width_ratio` / `height_ratio`: size of the clickable region",
    "# - `action_x_ratio` / `action_y_ratio`: optional explicit click point for tap-capable selectors",
    "#   If omitted, the runtime clicks the center of the defined region.",
    "# - `materialize_relative_bounds: false`: keep the relative click region without auto-marking the selector visible",
    "# `interaction_kind` is optional during migration:",
    "# - `navigation`: clicking is expected to navigate and must have reviewed click outcomes",
    "# - `action`: clicking performs an in-screen or stateful action, not a reviewed navigation contract",
    "# - `label`: non-interactive screen evidence; it must not declare click metadata",
    "# `surfaces` extend the same canonical file with scrollable-scene definitions used for world-map",
    "# and home-city spatial parsing; fixed overlay UI remains in `selectors`.",
)


@dataclass(frozen=True, slots=True)
class SelectorCatalogClickOutcome:
    """Represents one reviewed click outcome stored for a selector."""

    target_screen: str | None
    verification_selectors: tuple[str, ...]
    verification_texts: tuple[str, ...]
    safe_to_click: bool
    monetized: bool
    notes: tuple[str, ...]

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one click outcome."""

        document: dict[str, object] = {
            "safe_to_click": self.safe_to_click,
            "monetized": self.monetized,
        }
        if self.target_screen is not None:
            document["target_screen"] = self.target_screen
        if self.verification_selectors:
            document["verification_selectors"] = list(self.verification_selectors)
        if self.verification_texts:
            document["verification_texts"] = list(self.verification_texts)
        if self.notes:
            document["notes"] = list(self.notes)
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogClickDefinition:
    """Represents click metadata stored for one selector entry."""

    anchor: str
    outcomes: tuple[SelectorCatalogClickOutcome, ...]

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of the click metadata."""

        document: dict[str, object] = {"anchor": self.anchor}
        if self.outcomes:
            document["outcomes"] = [outcome.to_document() for outcome in self.outcomes]
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogRelativeBounds:
    """Stores one screen-relative selector region as top-left plus size and optional tap point."""

    x_ratio: float
    y_ratio: float
    width_ratio: float
    height_ratio: float
    action_x_ratio: float | None = None
    action_y_ratio: float | None = None

    def __post_init__(self) -> None:
        """Rejects invalid ratio content before it reaches the runtime registry."""

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

    def to_document(self) -> dict[str, float]:
        """Returns the YAML-ready representation of one relative selector region."""

        document: dict[str, float] = {
            "x_ratio": self.x_ratio,
            "y_ratio": self.y_ratio,
            "width_ratio": self.width_ratio,
            "height_ratio": self.height_ratio,
        }
        if self.action_x_ratio is not None and self.action_y_ratio is not None:
            document["action_x_ratio"] = self.action_x_ratio
            document["action_y_ratio"] = self.action_y_ratio
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogEntry:
    """Represents one raw selector entry as stored in the static catalog document."""

    id: str
    screens: tuple[str, ...]
    status: str
    detection_kind: str
    interaction_kind: str | None = None
    click: SelectorCatalogClickDefinition | None = None
    relative_bounds: SelectorCatalogRelativeBounds | None = None
    materialize_relative_bounds: bool = True
    notes: tuple[str, ...] = ()

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one selector entry."""

        document: dict[str, object] = {
            "id": self.id,
            "screens": list(self.screens),
            "status": self.status,
            "detection_kind": self.detection_kind,
        }
        if self.interaction_kind is not None:
            document["interaction_kind"] = self.interaction_kind
        if self.click is not None:
            document["click"] = self.click.to_document()
        if self.relative_bounds is not None:
            document["relative_bounds"] = self.relative_bounds.to_document()
        if not self.materialize_relative_bounds:
            document["materialize_relative_bounds"] = False
        if self.notes:
            document["notes"] = list(self.notes)
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogSurfaceViewport:
    """Stores the catalog-backed viewport addressing metadata for one spatial surface."""

    addressing_kind: str
    coordinate_selector: str | None = None
    home_selector: str | None = None
    optional_zoom_indicator_selector: str | None = None

    def __post_init__(self) -> None:
        """Rejects unsupported viewport-addressing combinations in the static catalog."""

        if self.addressing_kind not in {"coordinate_bar", "camera_relative"}:
            raise SelectorResolutionError(
                "Spatial-surface viewport addressing_kind must use a supported value.",
                addressing_kind=self.addressing_kind,
            )
        if self.addressing_kind == "coordinate_bar" and self.coordinate_selector is None:
            raise SelectorResolutionError(
                "Coordinate-addressable spatial surfaces must declare coordinate_selector.",
                addressing_kind=self.addressing_kind,
            )
        if self.addressing_kind == "camera_relative" and self.coordinate_selector is not None:
            raise SelectorResolutionError(
                "Camera-relative spatial surfaces must not declare coordinate_selector.",
                addressing_kind=self.addressing_kind,
                coordinate_selector=self.coordinate_selector,
            )

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one spatial viewport definition."""

        document: dict[str, object] = {"addressing_kind": self.addressing_kind}
        if self.coordinate_selector is not None:
            document["coordinate_selector"] = self.coordinate_selector
        if self.home_selector is not None:
            document["home_selector"] = self.home_selector
        if self.optional_zoom_indicator_selector is not None:
            document["optional_zoom_indicator_selector"] = self.optional_zoom_indicator_selector
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogSurfaceRelationshipRules:
    """Stores the catalog-backed relationship heuristics for one spatial surface."""

    self_castle_label: str | None = None
    ally_name_color_family: str | None = None
    other_alliance_color_family: str | None = None
    self_color_family: str | None = None

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of the spatial relationship rules."""

        document: dict[str, object] = {}
        if self.self_castle_label is not None:
            document["self_castle_label"] = self.self_castle_label
        if self.ally_name_color_family is not None:
            document["ally_name_color_family"] = self.ally_name_color_family
        if self.other_alliance_color_family is not None:
            document["other_alliance_color_family"] = self.other_alliance_color_family
        if self.self_color_family is not None:
            document["self_color_family"] = self.self_color_family
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogSurfaceEntry:
    """Represents one raw spatial-surface entry stored in the static catalog document."""

    id: str
    surface_type: str
    screen: str
    viewport: SelectorCatalogSurfaceViewport
    object_kinds: tuple[str, ...]
    relationship_rules: SelectorCatalogSurfaceRelationshipRules | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Rejects empty spatial-object catalogs before runtime loading."""

        if not self.object_kinds:
            raise SelectorResolutionError(
                "Spatial-surface catalog entries must declare at least one object kind.",
                surface_id=self.id,
            )

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one spatial-surface catalog entry."""

        document: dict[str, object] = {
            "id": self.id,
            "surface_type": self.surface_type,
            "screen": self.screen,
            "viewport": self.viewport.to_document(),
            "object_kinds": list(self.object_kinds),
        }
        if self.relationship_rules is not None:
            document["relationship_rules"] = self.relationship_rules.to_document()
        if self.notes:
            document["notes"] = list(self.notes)
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogDocument:
    """Represents the canonical static selector catalog file."""

    selectors: tuple[SelectorCatalogEntry, ...]
    surfaces: tuple[SelectorCatalogSurfaceEntry, ...] = ()

    def __post_init__(self) -> None:
        """Ensures the static catalog remains canonical and unambiguous."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed in the selector catalog.", duplicates=sorted(duplicates))
        surface_ids = [surface.id for surface in self.surfaces]
        surface_duplicates = {surface_id for surface_id in surface_ids if surface_ids.count(surface_id) > 1}
        if surface_duplicates:
            raise SelectorResolutionError(
                "Duplicate spatial-surface ids are not allowed in the selector catalog.",
                duplicates=sorted(surface_duplicates),
            )
        surface_types = [surface.surface_type for surface in self.surfaces]
        surface_type_duplicates = {
            surface_type for surface_type in surface_types if surface_types.count(surface_type) > 1
        }
        if surface_type_duplicates:
            raise SelectorResolutionError(
                "Duplicate spatial-surface types are not allowed in the selector catalog.",
                duplicates=sorted(surface_type_duplicates),
            )
        validate_selector_catalog_references(self)
        validate_selector_catalog_interactions(self)

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of the full selector catalog."""

        document: dict[str, object] = {"selectors": [selector.to_document() for selector in self.selectors]}
        if self.surfaces:
            document["surfaces"] = [surface.to_document() for surface in self.surfaces]
        return document


def default_selector_catalog_path() -> Path:
    """Returns the canonical static selector catalog path."""

    return Path(__file__).resolve().parent / "data" / "selector_registry.yaml"


def load_selector_catalog_document(path: Path | None = None) -> SelectorCatalogDocument:
    """Loads the static selector catalog document from disk."""

    catalog_path = path or default_selector_catalog_path()
    with catalog_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    document = require_selector_schema_mapping(loaded, context="selector catalog root", document_label="selector catalog")
    return SelectorCatalogDocument(
        selectors=tuple(_load_selector_entries(document.get("selectors"))),
        surfaces=tuple(_load_surface_entries(document.get("surfaces", ()))),
    )


def write_selector_catalog_document(path: Path, document: SelectorCatalogDocument) -> None:
    """Writes one selector catalog document back to disk with the canonical schema header."""

    serialized_document = yaml.safe_dump(document.to_document(), sort_keys=False)
    header = "\n".join(_CATALOG_HEADER_LINES)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{header}\n{serialized_document}")


def _load_selector_entries(value: object) -> tuple[SelectorCatalogEntry, ...]:
    """Builds the raw selector entries from one loaded YAML sequence."""

    entries = require_selector_schema_sequence(value, context="selectors", document_label="selector catalog")
    loaded_entries: list[SelectorCatalogEntry] = []
    for entry in entries:
        mapping = require_selector_schema_mapping(entry, context="selector entry", document_label="selector catalog")
        selector_id = require_selector_schema_string(mapping.get("id"), context="selector entry id", document_label="selector catalog")
        screens = tuple(
            load_selector_schema_string_sequence(
                mapping.get("screens"),
                context=f"selector '{selector_id}' screens",
                document_label="selector catalog",
            )
        )
        if not screens:
            raise SelectorResolutionError("Selector catalog entries must declare at least one screen.", selector_id=selector_id)
        status = require_selector_schema_string(
            mapping.get("status"),
            context=f"selector '{selector_id}' status",
            document_label="selector catalog",
        )
        detection_kind = require_selector_schema_string(
            mapping.get("detection_kind"),
            context=f"selector '{selector_id}' detection_kind",
            document_label="selector catalog",
        )
        interaction_kind = (
            require_selector_schema_string(
                mapping.get("interaction_kind"),
                context=f"selector '{selector_id}' interaction_kind",
                document_label="selector catalog",
            )
            if "interaction_kind" in mapping
            else None
        )
        if "ocr_region" in mapping:
            raise SelectorResolutionError(
                "Selector catalog entries must use normalized relative_bounds instead of legacy ocr_region rectangles.",
                selector_id=selector_id,
            )
        click = load_selector_schema_click_definition(
            mapping.get("click"),
            selector_id=selector_id,
            document_label="selector catalog",
            selector_label="selector",
        )
        relative_bounds = load_selector_schema_relative_bounds(
            mapping.get("relative_bounds"),
            selector_id=selector_id,
            document_label="selector catalog",
            selector_label="selector",
        )
        materialize_relative_bounds = (
            require_selector_schema_bool(
                mapping.get("materialize_relative_bounds"),
                context=f"selector '{selector_id}' materialize_relative_bounds",
                document_label="selector catalog",
            )
            if "materialize_relative_bounds" in mapping
            else True
        )
        notes = tuple(
            load_selector_schema_string_sequence(
                mapping.get("notes", ()),
                context=f"selector '{selector_id}' notes",
                document_label="selector catalog",
            )
        )
        loaded_entries.append(
            SelectorCatalogEntry(
                id=selector_id,
                screens=screens,
                status=status,
                detection_kind=detection_kind,
                interaction_kind=interaction_kind,
                click=click,
                relative_bounds=relative_bounds,
                materialize_relative_bounds=materialize_relative_bounds,
                notes=notes,
            )
        )
    return tuple(loaded_entries)


def _load_surface_entries(value: object) -> tuple[SelectorCatalogSurfaceEntry, ...]:
    """Builds the raw spatial-surface entries from one loaded YAML sequence."""

    entries = require_selector_schema_sequence(value, context="surfaces", document_label="selector catalog")
    loaded_entries: list[SelectorCatalogSurfaceEntry] = []
    for entry in entries:
        mapping = require_selector_schema_mapping(entry, context="surface entry", document_label="selector catalog")
        surface_id = require_selector_schema_string(mapping.get("id"), context="surface entry id", document_label="selector catalog")
        surface_type = require_selector_schema_string(
            mapping.get("surface_type"),
            context=f"surface '{surface_id}' surface_type",
            document_label="selector catalog",
        )
        screen = require_selector_schema_string(
            mapping.get("screen"),
            context=f"surface '{surface_id}' screen",
            document_label="selector catalog",
        )
        viewport = load_selector_schema_surface_viewport(
            mapping.get("viewport"),
            surface_id=surface_id,
            document_label="selector catalog",
        )
        object_kinds = tuple(
            load_selector_schema_string_sequence(
                mapping.get("object_kinds"),
                context=f"surface '{surface_id}' object_kinds",
                document_label="selector catalog",
            )
        )
        relationship_rules = load_selector_schema_surface_relationship_rules(
            mapping.get("relationship_rules"),
            surface_id=surface_id,
            document_label="selector catalog",
        )
        notes = tuple(
            load_selector_schema_string_sequence(
                mapping.get("notes", ()),
                context=f"surface '{surface_id}' notes",
                document_label="selector catalog",
            )
        )
        loaded_entries.append(
            SelectorCatalogSurfaceEntry(
                id=surface_id,
                surface_type=surface_type,
                screen=screen,
                viewport=viewport,
                object_kinds=object_kinds,
                relationship_rules=relationship_rules,
                notes=notes,
            )
        )
    return tuple(loaded_entries)


def validate_selector_catalog_references(document: SelectorCatalogDocument) -> None:
    """Rejects click metadata that references selectors missing from the same catalog document."""

    selector_ids = {selector.id for selector in document.selectors}
    for selector in document.selectors:
        click = selector.click
        if click is None:
            continue
        for outcome in click.outcomes:
            for verification_selector in outcome.verification_selectors:
                if verification_selector not in selector_ids:
                    raise SelectorResolutionError(
                        "Selector click outcomes must reference selectors declared in the same catalog document.",
                        selector_id=selector.id,
                        verification_selector=verification_selector,
                    )
    for surface in document.surfaces:
        viewport_selector_ids = (
            surface.viewport.coordinate_selector,
            surface.viewport.home_selector,
            surface.viewport.optional_zoom_indicator_selector,
        )
        for selector_id in viewport_selector_ids:
            if selector_id is None:
                continue
            if selector_id not in selector_ids:
                raise SelectorResolutionError(
                    "Spatial-surface viewport selectors must reference selectors declared in the same catalog document.",
                    surface_id=surface.id,
                    selector_id=selector_id,
                )


def validate_selector_catalog_interactions(document: SelectorCatalogDocument) -> None:
    """Rejects selector interaction metadata that contradicts the declared click contract."""

    for selector in document.selectors:
        if selector.relative_bounds is None and not selector.materialize_relative_bounds:
            raise SelectorResolutionError(
                "Selector materialize_relative_bounds requires relative_bounds.",
                selector_id=selector.id,
            )
        if selector.detection_kind == "ocr_region" and selector.status != "planned" and selector.relative_bounds is None:
            raise SelectorResolutionError(
                "Non-planned ocr_region selectors must declare normalized relative_bounds.",
                selector_id=selector.id,
                detection_kind=selector.detection_kind,
                status=selector.status,
            )
        interaction_kind_name = selector.interaction_kind
        if selector.click is not None:
            for outcome in selector.click.outcomes:
                if outcome.verification_texts:
                    raise SelectorResolutionError(
                        "Reviewed click outcomes do not support verification_texts at runtime.",
                        selector_id=selector.id,
                        verification_texts=outcome.verification_texts,
                    )
        if interaction_kind_name is None:
            continue
        try:
            interaction_kind = SelectorInteractionKind(interaction_kind_name)
        except ValueError as error:
            raise SelectorResolutionError(
                "Selector interaction kinds must use a supported value.",
                selector_id=selector.id,
                interaction_kind=interaction_kind_name,
            ) from error
        if interaction_kind == SelectorInteractionKind.UNKNOWN:
            continue
        if interaction_kind == SelectorInteractionKind.NAVIGATION:
            click = selector.click
            if click is None or not click.outcomes:
                raise SelectorResolutionError(
                    "Navigation selectors must declare reviewed click outcomes.",
                    selector_id=selector.id,
                    interaction_kind=interaction_kind.value,
                )
            if not any(outcome.target_screen is not None for outcome in click.outcomes):
                raise SelectorResolutionError(
                    "Navigation selectors must declare at least one target_screen outcome.",
                    selector_id=selector.id,
                    interaction_kind=interaction_kind.value,
                )
            continue
        if interaction_kind == SelectorInteractionKind.LABEL and selector.click is not None:
            raise SelectorResolutionError(
                "Label selectors must not declare click metadata.",
                selector_id=selector.id,
                interaction_kind=interaction_kind.value,
            )


def load_selector_schema_click_definition(
    value: object,
    *,
    selector_id: str,
    document_label: str,
    selector_label: str,
    validate_target_screen: Callable[[str], None] | None = None,
    validate_verification_selector: Callable[[str], None] | None = None,
) -> SelectorCatalogClickDefinition | None:
    """Loads optional click metadata shared by the catalog and updater schema paths."""

    if value is None:
        return None
    mapping = require_selector_schema_mapping(
        value,
        context=f"{selector_label} '{selector_id}' click",
        document_label=document_label,
    )
    anchor = require_selector_schema_string(
        mapping.get("anchor", "center"),
        context=f"{selector_label} '{selector_id}' click anchor",
        document_label=document_label,
    )
    outcomes = tuple(
        load_selector_schema_click_outcomes(
            mapping.get("outcomes", ()),
            selector_id=selector_id,
            document_label=document_label,
            selector_label=selector_label,
            validate_target_screen=validate_target_screen,
            validate_verification_selector=validate_verification_selector,
        )
    )
    return SelectorCatalogClickDefinition(anchor=anchor, outcomes=outcomes)


def load_selector_schema_click_outcomes(
    value: object,
    *,
    selector_id: str,
    document_label: str,
    selector_label: str,
    validate_target_screen: Callable[[str], None] | None = None,
    validate_verification_selector: Callable[[str], None] | None = None,
) -> tuple[SelectorCatalogClickOutcome, ...]:
    """Loads reviewed click outcomes shared by the catalog and updater schema paths."""

    outcomes = require_selector_schema_sequence(
        value,
        context=f"{selector_label} '{selector_id}' click outcomes",
        document_label=document_label,
    )
    loaded_outcomes: list[SelectorCatalogClickOutcome] = []
    for outcome in outcomes:
        mapping = require_selector_schema_mapping(
            outcome,
            context=f"{selector_label} '{selector_id}' click outcome",
            document_label=document_label,
        )
        target_screen = mapping.get("target_screen")
        if target_screen is not None:
            target_screen = require_selector_schema_string(
                target_screen,
                context=f"{selector_label} '{selector_id}' click outcome target_screen",
                document_label=document_label,
            )
            if validate_target_screen is not None:
                validate_target_screen(target_screen)
        safe_to_click = require_selector_schema_bool(
            mapping.get("safe_to_click", True),
            context=f"{selector_label} '{selector_id}' click outcome safe_to_click",
            document_label=document_label,
        )
        monetized = require_selector_schema_bool(
            mapping.get("monetized", False),
            context=f"{selector_label} '{selector_id}' click outcome monetized",
            document_label=document_label,
        )
        verification_selectors = tuple(
            load_selector_schema_string_sequence(
                mapping.get("verification_selectors", ()),
                context=f"{selector_label} '{selector_id}' click outcome verification_selectors",
                document_label=document_label,
            )
        )
        if validate_verification_selector is not None:
            for verification_selector in verification_selectors:
                validate_verification_selector(verification_selector)
        verification_texts = tuple(
            load_selector_schema_string_sequence(
                mapping.get("verification_texts", ()),
                context=f"{selector_label} '{selector_id}' click outcome verification_texts",
                document_label=document_label,
            )
        )
        if verification_texts:
            raise SelectorResolutionError(
                "Reviewed click outcomes do not support verification_texts at runtime.",
                selector_id=selector_id,
                verification_texts=verification_texts,
            )
        notes = tuple(
            load_selector_schema_string_sequence(
                mapping.get("notes", ()),
                context=f"{selector_label} '{selector_id}' click outcome notes",
                document_label=document_label,
            )
        )
        loaded_outcomes.append(
            SelectorCatalogClickOutcome(
                target_screen=target_screen,
                verification_selectors=verification_selectors,
                verification_texts=verification_texts,
                safe_to_click=safe_to_click,
                monetized=monetized,
                notes=notes,
            )
        )
    return tuple(loaded_outcomes)


def load_selector_schema_relative_bounds(
    value: object,
    *,
    selector_id: str,
    document_label: str,
    selector_label: str,
) -> SelectorCatalogRelativeBounds | None:
    """Loads optional screen-relative selector geometry from one YAML mapping."""

    if value is None:
        return None
    mapping = require_selector_schema_mapping(
        value,
        context=f"{selector_label} '{selector_id}' relative_bounds",
        document_label=document_label,
    )
    return SelectorCatalogRelativeBounds(
        x_ratio=require_selector_schema_number(
            mapping.get("x_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds x_ratio",
            document_label=document_label,
        ),
        y_ratio=require_selector_schema_number(
            mapping.get("y_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds y_ratio",
            document_label=document_label,
        ),
        width_ratio=require_selector_schema_number(
            mapping.get("width_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds width_ratio",
            document_label=document_label,
        ),
        height_ratio=require_selector_schema_number(
            mapping.get("height_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds height_ratio",
            document_label=document_label,
        ),
        action_x_ratio=None
        if "action_x_ratio" not in mapping
        else require_selector_schema_number(
            mapping.get("action_x_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds action_x_ratio",
            document_label=document_label,
        ),
        action_y_ratio=None
        if "action_y_ratio" not in mapping
        else require_selector_schema_number(
            mapping.get("action_y_ratio"),
            context=f"{selector_label} '{selector_id}' relative_bounds action_y_ratio",
            document_label=document_label,
        ),
    )


def load_selector_schema_surface_viewport(
    value: object,
    *,
    surface_id: str,
    document_label: str,
) -> SelectorCatalogSurfaceViewport:
    """Loads one spatial-surface viewport definition from the catalog schema."""

    mapping = require_selector_schema_mapping(
        value,
        context=f"surface '{surface_id}' viewport",
        document_label=document_label,
    )
    return SelectorCatalogSurfaceViewport(
        addressing_kind=require_selector_schema_string(
            mapping.get("addressing_kind"),
            context=f"surface '{surface_id}' viewport addressing_kind",
            document_label=document_label,
        ),
        coordinate_selector=None
        if "coordinate_selector" not in mapping
        else require_selector_schema_string(
            mapping.get("coordinate_selector"),
            context=f"surface '{surface_id}' viewport coordinate_selector",
            document_label=document_label,
        ),
        home_selector=None
        if "home_selector" not in mapping
        else require_selector_schema_string(
            mapping.get("home_selector"),
            context=f"surface '{surface_id}' viewport home_selector",
            document_label=document_label,
        ),
        optional_zoom_indicator_selector=None
        if "optional_zoom_indicator_selector" not in mapping
        else require_selector_schema_string(
            mapping.get("optional_zoom_indicator_selector"),
            context=f"surface '{surface_id}' viewport optional_zoom_indicator_selector",
            document_label=document_label,
        ),
    )


def load_selector_schema_surface_relationship_rules(
    value: object,
    *,
    surface_id: str,
    document_label: str,
) -> SelectorCatalogSurfaceRelationshipRules | None:
    """Loads optional spatial-surface relationship rules from one YAML mapping."""

    if value is None:
        return None
    mapping = require_selector_schema_mapping(
        value,
        context=f"surface '{surface_id}' relationship_rules",
        document_label=document_label,
    )
    return SelectorCatalogSurfaceRelationshipRules(
        self_castle_label=None
        if "self_castle_label" not in mapping
        else require_selector_schema_string(
            mapping.get("self_castle_label"),
            context=f"surface '{surface_id}' relationship_rules self_castle_label",
            document_label=document_label,
        ),
        ally_name_color_family=None
        if "ally_name_color_family" not in mapping
        else require_selector_schema_string(
            mapping.get("ally_name_color_family"),
            context=f"surface '{surface_id}' relationship_rules ally_name_color_family",
            document_label=document_label,
        ),
        other_alliance_color_family=None
        if "other_alliance_color_family" not in mapping
        else require_selector_schema_string(
            mapping.get("other_alliance_color_family"),
            context=f"surface '{surface_id}' relationship_rules other_alliance_color_family",
            document_label=document_label,
        ),
        self_color_family=None
        if "self_color_family" not in mapping
        else require_selector_schema_string(
            mapping.get("self_color_family"),
            context=f"surface '{surface_id}' relationship_rules self_color_family",
            document_label=document_label,
        ),
    )


def load_selector_schema_string_sequence(
    value: object,
    *,
    context: str,
    document_label: str,
) -> tuple[str, ...]:
    """Loads one YAML string sequence while failing fast on invalid content."""

    return tuple(
        require_selector_schema_string(item, context=context, document_label=document_label)
        for item in require_selector_schema_sequence(value, context=context, document_label=document_label)
    )


def require_selector_schema_mapping(value: object, *, context: str, document_label: str) -> Mapping[str, Any]:
    """Returns one YAML mapping or raises when the loaded content is invalid."""

    if not isinstance(value, Mapping):
        raise SelectorResolutionError(f"Expected a mapping in the {document_label}.", context=context)
    return value


def require_selector_schema_sequence(value: object, *, context: str, document_label: str) -> Sequence[object]:
    """Returns one YAML sequence or raises when the loaded content is invalid."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SelectorResolutionError(f"Expected a sequence in the {document_label}.", context=context)
    return value


def require_selector_schema_string(value: object, *, context: str, document_label: str) -> str:
    """Returns one YAML string or raises when the loaded content is invalid."""

    if not isinstance(value, str) or value == "":
        raise SelectorResolutionError(f"Expected a non-empty string in the {document_label}.", context=context)
    return value


def require_selector_schema_bool(value: object, *, context: str, document_label: str) -> bool:
    """Returns one YAML boolean or raises when the loaded content is invalid."""

    if not isinstance(value, bool):
        raise SelectorResolutionError(f"Expected a boolean in the {document_label}.", context=context)
    return value


def require_selector_schema_number(value: object, *, context: str, document_label: str) -> float:
    """Returns one YAML numeric scalar or raises when the loaded content is invalid."""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SelectorResolutionError(f"Expected a number in the {document_label}.", context=context)
    return float(value)


def _require_ratio(value: float, *, field_name: str, inclusive_zero: bool) -> None:
    """Rejects ratios outside the supported normalized range."""

    if inclusive_zero:
        if not 0 <= value <= 1:
            raise SelectorResolutionError("Selector relative_bounds ratios must stay within [0, 1].", field_name=field_name)
        return
    if not 0 < value <= 1:
        raise SelectorResolutionError("Selector relative_bounds sizes must stay within (0, 1].", field_name=field_name)
