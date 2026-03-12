"""Loads and writes the canonical selector catalog edited by offline refinement tooling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import SelectorResolutionKind
from pnc_automation.vision.pnc_parser_candidates import SUPPORTED_PARSER_CANDIDATE_IDS
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind

_CATALOG_HEADER_LINES = (
    "# `resolution` is the canonical ordered runtime selector policy:",
    "# - `template`: explicit template match using `template_path` and optional `threshold`",
    "# - `parser_candidate`: trusted screen-interpreter candidate keyed by the canonical selector id",
    "# - `relative_bounds`: normalized fallback geometry using `x_ratio` / `y_ratio` plus size and optional action point",
    "# `interaction_kind` is optional during migration:",
    "# - `navigation`: clicking is expected to navigate and must have reviewed click outcomes",
    "# - `action`: clicking performs an in-screen or stateful action, not a reviewed navigation contract",
    "# - `label`: non-interactive screen evidence; it must not declare click metadata or geometry fallback",
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
class SelectorCatalogRegion:
    """Stores one OCR extraction region in absolute screenshot coordinates."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        """Rejects non-positive OCR regions."""

        if self.width <= 0 or self.height <= 0:
            raise SelectorResolutionError("OCR regions must have positive width and height.", width=self.width, height=self.height)

    def to_document(self) -> dict[str, int]:
        """Returns the YAML-ready representation of one OCR region."""

        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True, slots=True)
class SelectorCatalogResolutionStep:
    """Represents one authored resolution step stored in the static catalog."""

    kind: str
    template_path: str | None = None
    threshold: float = 0.98
    relative_bounds: SelectorCatalogRelativeBounds | None = None
    ocr_region: SelectorCatalogRegion | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        """Rejects inconsistent authored resolution-step content."""

        resolution_kind = _require_resolution_kind(self.kind)
        if resolution_kind == SelectorResolutionKind.TEMPLATE:
            if self.template_path is None or self.template_path == "":
                raise SelectorResolutionError("Template resolution steps must declare template_path.")
            if not 0 < self.threshold <= 1:
                raise SelectorResolutionError("Template resolution thresholds must stay within (0, 1].", threshold=self.threshold)
            return
        if resolution_kind == SelectorResolutionKind.PARSER_CANDIDATE:
            if any(value is not None for value in (self.template_path, self.relative_bounds, self.ocr_region)):
                raise SelectorResolutionError("Parser-candidate steps must not declare extra geometry or assets.")
            return
        if resolution_kind == SelectorResolutionKind.RELATIVE_BOUNDS:
            if self.relative_bounds is None:
                raise SelectorResolutionError("Relative-bounds steps must declare normalized geometry.")
            return
        if resolution_kind == SelectorResolutionKind.OCR_REGION:
            return

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one resolution step."""

        document: dict[str, object] = {"kind": self.kind}
        if self.label is not None:
            document["label"] = self.label
        resolution_kind = _require_resolution_kind(self.kind)
        if resolution_kind == SelectorResolutionKind.TEMPLATE:
            document["template_path"] = self.template_path
            if self.threshold != 0.98:
                document["threshold"] = self.threshold
            return document
        if resolution_kind == SelectorResolutionKind.RELATIVE_BOUNDS:
            if self.relative_bounds is None:
                raise SelectorResolutionError("Relative-bounds steps must serialize authored geometry.")
            document.update(self.relative_bounds.to_document())
            return document
        if resolution_kind == SelectorResolutionKind.OCR_REGION:
            if self.ocr_region is not None:
                document["ocr_region"] = self.ocr_region.to_document()
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogEntry:
    """Represents one raw selector entry as stored in the static catalog document."""

    id: str
    screens: tuple[str, ...]
    status: str
    interaction_kind: str | None = None
    click: SelectorCatalogClickDefinition | None = None
    resolution: tuple[SelectorCatalogResolutionStep, ...] = ()
    notes: tuple[str, ...] = ()

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one selector entry."""

        document: dict[str, object] = {
            "id": self.id,
            "screens": list(self.screens),
            "status": self.status,
        }
        if self.interaction_kind is not None:
            document["interaction_kind"] = self.interaction_kind
        if self.click is not None:
            document["click"] = self.click.to_document()
        if self.resolution:
            document["resolution"] = [step.to_document() for step in self.resolution]
        if self.notes:
            document["notes"] = list(self.notes)
        return document


@dataclass(frozen=True, slots=True)
class SelectorCatalogDocument:
    """Represents the canonical static selector catalog file."""

    selectors: tuple[SelectorCatalogEntry, ...]

    def __post_init__(self) -> None:
        """Ensures the static catalog remains canonical and unambiguous."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed in the selector catalog.", duplicates=sorted(duplicates))
        validate_selector_catalog_references(self)
        validate_selector_catalog_interactions(self)

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of the full selector catalog."""

        return {"selectors": [selector.to_document() for selector in self.selectors]}


def default_selector_catalog_path() -> Path:
    """Returns the canonical static selector catalog path."""

    return Path(__file__).resolve().parent / "data" / "selector_registry.yaml"


def load_selector_catalog_document(path: Path | None = None) -> SelectorCatalogDocument:
    """Loads the static selector catalog document from disk."""

    catalog_path = path or default_selector_catalog_path()
    with catalog_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    document = require_selector_schema_mapping(loaded, context="selector catalog root", document_label="selector catalog")
    return SelectorCatalogDocument(selectors=tuple(_load_selector_entries(document.get("selectors"))))


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
        interaction_kind = (
            require_selector_schema_string(
                mapping.get("interaction_kind"),
                context=f"selector '{selector_id}' interaction_kind",
                document_label="selector catalog",
            )
            if "interaction_kind" in mapping
            else None
        )
        click = load_selector_schema_click_definition(
            mapping.get("click"),
            selector_id=selector_id,
            document_label="selector catalog",
            selector_label="selector",
        )
        resolution = (
            load_selector_schema_resolution_steps(
                mapping.get("resolution"),
                selector_id=selector_id,
                document_label="selector catalog",
                selector_label="selector",
            )
            if "resolution" in mapping
            else ()
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
                interaction_kind=interaction_kind,
                click=click,
                resolution=resolution,
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


def validate_selector_catalog_interactions(document: SelectorCatalogDocument) -> None:
    """Rejects selector interaction metadata that contradicts the declared click contract."""

    supported_parser_candidate_ids = {selector_id.name for selector_id in SUPPORTED_PARSER_CANDIDATE_IDS}
    for selector in document.selectors:
        _validate_selector_resolution_steps(selector, supported_parser_candidate_ids=supported_parser_candidate_ids)
        interaction_kind_name = selector.interaction_kind
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
            if any(
                _require_resolution_kind(step.kind) == SelectorResolutionKind.RELATIVE_BOUNDS
                for step in selector.resolution
            ) and not any(
                outcome.target_screen is not None and (outcome.verification_selectors or outcome.verification_texts)
                for outcome in click.outcomes
            ):
                raise SelectorResolutionError(
                    "Navigation selectors with geometry fallback must declare reviewed destination verification evidence.",
                    selector_id=selector.id,
                    interaction_kind=interaction_kind.value,
                )
            continue
        if interaction_kind == SelectorInteractionKind.LABEL:
            if selector.click is not None:
                raise SelectorResolutionError(
                    "Label selectors must not declare click metadata.",
                    selector_id=selector.id,
                    interaction_kind=interaction_kind.value,
                )
            if any(
                _require_resolution_kind(step.kind) == SelectorResolutionKind.RELATIVE_BOUNDS
                for step in selector.resolution
            ):
                raise SelectorResolutionError(
                    "Label selectors must not declare geometry fallback.",
                    selector_id=selector.id,
                    interaction_kind=interaction_kind.value,
                )


def _validate_selector_resolution_steps(
    selector: SelectorCatalogEntry,
    *,
    supported_parser_candidate_ids: set[str],
) -> None:
    """Rejects invalid selector-resolution policies in the static catalog."""

    if selector.status != "planned" and not selector.resolution:
        raise SelectorResolutionError(
            "Selectors above planned must declare at least one resolution step.",
            selector_id=selector.id,
            status=selector.status,
        )
    seen_kinds: set[SelectorResolutionKind] = set()
    for index, step in enumerate(selector.resolution):
        resolution_kind = _require_resolution_kind(step.kind)
        if resolution_kind in seen_kinds:
            raise SelectorResolutionError(
                "Selectors must not declare duplicate resolution steps.",
                selector_id=selector.id,
                resolution_kind=resolution_kind.value,
            )
        seen_kinds.add(resolution_kind)
        if resolution_kind == SelectorResolutionKind.RELATIVE_BOUNDS and index != len(selector.resolution) - 1:
            raise SelectorResolutionError(
                "Relative-bounds fallback must be the final selector resolution step.",
                selector_id=selector.id,
            )
        if resolution_kind == SelectorResolutionKind.PARSER_CANDIDATE and selector.id not in supported_parser_candidate_ids:
            raise SelectorResolutionError(
                "Parser-candidate resolution requires trusted screen-interpreter support for the selector id.",
                selector_id=selector.id,
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


def load_selector_schema_resolution_steps(
    value: object,
    *,
    selector_id: str,
    document_label: str,
    selector_label: str,
) -> tuple[SelectorCatalogResolutionStep, ...]:
    """Loads the ordered authored resolution steps for one selector."""

    steps = require_selector_schema_sequence(
        value,
        context=f"{selector_label} '{selector_id}' resolution",
        document_label=document_label,
    )
    loaded_steps: list[SelectorCatalogResolutionStep] = []
    for step in steps:
        mapping = require_selector_schema_mapping(
            step,
            context=f"{selector_label} '{selector_id}' resolution step",
            document_label=document_label,
        )
        kind = require_selector_schema_string(
            mapping.get("kind"),
            context=f"{selector_label} '{selector_id}' resolution step kind",
            document_label=document_label,
        )
        loaded_steps.append(
            SelectorCatalogResolutionStep(
                kind=kind,
                template_path=(
                    require_selector_schema_string(
                        mapping.get("template_path"),
                        context=f"{selector_label} '{selector_id}' template_path",
                        document_label=document_label,
                    )
                    if "template_path" in mapping
                    else None
                ),
                threshold=(
                    require_selector_schema_number(
                        mapping.get("threshold", 0.98),
                        context=f"{selector_label} '{selector_id}' threshold",
                        document_label=document_label,
                    )
                    if kind == SelectorResolutionKind.TEMPLATE.value or "threshold" in mapping
                    else 0.98
                ),
                relative_bounds=(
                    load_selector_schema_relative_bounds(
                        mapping,
                        selector_id=selector_id,
                        document_label=document_label,
                        selector_label=f"{selector_label} resolution step",
                    )
                    if kind == SelectorResolutionKind.RELATIVE_BOUNDS.value
                    else None
                ),
                ocr_region=(
                    load_selector_schema_region(
                        mapping.get("ocr_region"),
                        selector_id=selector_id,
                        document_label=document_label,
                        selector_label=f"{selector_label} resolution step",
                    )
                    if kind == SelectorResolutionKind.OCR_REGION.value or "ocr_region" in mapping
                    else None
                ),
                label=(
                    require_selector_schema_string(
                        mapping.get("label"),
                        context=f"{selector_label} '{selector_id}' resolution label",
                        document_label=document_label,
                    )
                    if "label" in mapping
                    else None
                ),
            )
        )
    return tuple(loaded_steps)


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


def load_selector_schema_region(
    value: object,
    *,
    selector_id: str,
    document_label: str,
    selector_label: str,
) -> SelectorCatalogRegion | None:
    """Loads one authored OCR region from a YAML mapping."""

    if value is None:
        return None
    mapping = require_selector_schema_mapping(
        value,
        context=f"{selector_label} '{selector_id}' ocr_region",
        document_label=document_label,
    )
    return SelectorCatalogRegion(
        x=int(
            require_selector_schema_number(
                mapping.get("x"),
                context=f"{selector_label} '{selector_id}' ocr_region x",
                document_label=document_label,
            )
        ),
        y=int(
            require_selector_schema_number(
                mapping.get("y"),
                context=f"{selector_label} '{selector_id}' ocr_region y",
                document_label=document_label,
            )
        ),
        width=int(
            require_selector_schema_number(
                mapping.get("width"),
                context=f"{selector_label} '{selector_id}' ocr_region width",
                document_label=document_label,
            )
        ),
        height=int(
            require_selector_schema_number(
                mapping.get("height"),
                context=f"{selector_label} '{selector_id}' ocr_region height",
                document_label=document_label,
            )
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


def _require_resolution_kind(kind_name: str) -> SelectorResolutionKind:
    """Converts one raw resolution kind into the typed enum value."""

    try:
        return SelectorResolutionKind(kind_name)
    except ValueError as error:
        raise SelectorResolutionError("Unsupported selector resolution kind in the selector catalog.", resolution_kind=kind_name) from error
