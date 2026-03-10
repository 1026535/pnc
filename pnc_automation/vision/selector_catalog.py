"""Loads and writes the canonical selector catalog edited by offline refinement tooling."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    document = _require_mapping(loaded, context="selector catalog root")
    return SelectorCatalogDocument(selectors=tuple(_load_selector_entries(document.get("selectors"))))


def write_selector_catalog_document(path: Path, document: SelectorCatalogDocument) -> None:
    """Writes one selector catalog document back to disk."""

    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(document.to_document(), handle, sort_keys=False)


def _load_selector_entries(value: object) -> tuple[SelectorCatalogEntry, ...]:
    """Builds the raw selector entries from one loaded YAML sequence."""

    entries = _require_sequence(value, context="selectors")
    loaded_entries: list[SelectorCatalogEntry] = []
    for entry in entries:
        mapping = _require_mapping(entry, context="selector entry")
        selector_id = _require_string(mapping.get("id"), context="selector entry id")
        screens = tuple(_load_string_sequence(mapping.get("screens"), context=f"selector '{selector_id}' screens"))
        if not screens:
            raise SelectorResolutionError("Selector catalog entries must declare at least one screen.", selector_id=selector_id)
        status = _require_string(mapping.get("status"), context=f"selector '{selector_id}' status")
        detection_kind = _require_string(mapping.get("detection_kind"), context=f"selector '{selector_id}' detection_kind")
        click = _load_click_definition(mapping.get("click"), selector_id=selector_id)
        notes = tuple(_load_string_sequence(mapping.get("notes", ()), context=f"selector '{selector_id}' notes"))
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


def _load_click_definition(value: object, *, selector_id: str) -> SelectorCatalogClickDefinition | None:
    """Loads optional click metadata for one selector entry."""

    if value is None:
        return None
    mapping = _require_mapping(value, context=f"selector '{selector_id}' click")
    anchor = _require_string(mapping.get("anchor", "center"), context=f"selector '{selector_id}' click anchor")
    outcomes = tuple(_load_click_outcomes(mapping.get("outcomes", ()), selector_id=selector_id))
    return SelectorCatalogClickDefinition(anchor=anchor, outcomes=outcomes)


def _load_click_outcomes(value: object, *, selector_id: str) -> tuple[SelectorCatalogClickOutcome, ...]:
    """Loads reviewed click outcomes for one selector entry."""

    outcomes = _require_sequence(value, context=f"selector '{selector_id}' click outcomes")
    loaded_outcomes: list[SelectorCatalogClickOutcome] = []
    for outcome in outcomes:
        mapping = _require_mapping(outcome, context=f"selector '{selector_id}' click outcome")
        target_screen = mapping.get("target_screen")
        if target_screen is not None:
            target_screen = _require_string(target_screen, context=f"selector '{selector_id}' click outcome target_screen")
        safe_to_click = _require_bool(mapping.get("safe_to_click", True), context=f"selector '{selector_id}' click outcome safe_to_click")
        monetized = _require_bool(mapping.get("monetized", False), context=f"selector '{selector_id}' click outcome monetized")
        verification_selectors = tuple(
            _load_string_sequence(
                mapping.get("verification_selectors", ()),
                context=f"selector '{selector_id}' click outcome verification_selectors",
            )
        )
        verification_texts = tuple(
            _load_string_sequence(
                mapping.get("verification_texts", ()),
                context=f"selector '{selector_id}' click outcome verification_texts",
            )
        )
        notes = tuple(_load_string_sequence(mapping.get("notes", ()), context=f"selector '{selector_id}' click outcome notes"))
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


def _load_string_sequence(value: object, *, context: str) -> tuple[str, ...]:
    """Loads one YAML string sequence while failing fast on invalid content."""

    return tuple(_require_string(item, context=context) for item in _require_sequence(value, context=context))


def _require_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    """Returns one YAML mapping or raises when the loaded content is invalid."""

    if not isinstance(value, Mapping):
        raise SelectorResolutionError("Expected a mapping in the selector catalog.", context=context)
    return value


def _require_sequence(value: object, *, context: str) -> Sequence[object]:
    """Returns one YAML sequence or raises when the loaded content is invalid."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SelectorResolutionError("Expected a sequence in the selector catalog.", context=context)
    return value


def _require_string(value: object, *, context: str) -> str:
    """Returns one YAML string or raises when the loaded content is invalid."""

    if not isinstance(value, str) or value == "":
        raise SelectorResolutionError("Expected a non-empty string in the selector catalog.", context=context)
    return value


def _require_bool(value: object, *, context: str) -> bool:
    """Returns one YAML boolean or raises when the loaded content is invalid."""

    if not isinstance(value, bool):
        raise SelectorResolutionError("Expected a boolean in the selector catalog.", context=context)
    return value
