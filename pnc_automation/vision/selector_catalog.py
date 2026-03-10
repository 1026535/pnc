"""Loads and writes the canonical selector catalog edited by offline refinement tooling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from pnc_automation.errors import SelectorResolutionError


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
class SelectorCatalogEntry:
    """Represents one raw selector entry as stored in the static catalog document."""

    id: str
    screens: tuple[str, ...]
    status: str
    detection_kind: str
    click: SelectorCatalogClickDefinition | None = None
    notes: tuple[str, ...] = ()

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one selector entry."""

        document: dict[str, object] = {
            "id": self.id,
            "screens": list(self.screens),
            "status": self.status,
            "detection_kind": self.detection_kind,
        }
        if self.click is not None:
            document["click"] = self.click.to_document()
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
    """Writes one selector catalog document back to disk."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(document.to_document(), handle, sort_keys=False)


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
        click = load_selector_schema_click_definition(
            mapping.get("click"),
            selector_id=selector_id,
            document_label="selector catalog",
            selector_label="selector",
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
                click=click,
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
