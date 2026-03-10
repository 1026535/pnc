"""Applies explicit offline selector-registry updates to the static catalog and enum source."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    SelectorCatalogClickOutcome,
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    load_selector_catalog_document,
    write_selector_catalog_document,
)
from pnc_automation.vision.selectors import DetectionKind, SelectorStatus

_UI_ELEMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ENUM_MEMBER_PATTERN = re.compile(r"^\s+([A-Z][A-Z0-9_]*)\s*=")
_STATUS_RANK = {status.value: index for index, status in enumerate(SelectorStatus)}


@dataclass(frozen=True, slots=True)
class SelectorRegistryUpdate:
    """Represents one explicit registry update requested by the offline refinement flow."""

    id: str
    screens: tuple[str, ...]
    status: str
    detection_kind: str
    click: SelectorCatalogClickDefinition | None
    update_click: bool
    notes: tuple[str, ...]
    update_notes: bool


@dataclass(frozen=True, slots=True)
class SelectorRegistryUpdateResult:
    """Summarizes the changes applied by one offline selector-registry update run."""

    added_selector_ids: tuple[str, ...]
    updated_selector_ids: tuple[str, ...]
    added_ui_element_ids: tuple[str, ...]


def load_selector_update_spec(path: Path) -> tuple[SelectorRegistryUpdate, ...]:
    """Loads one explicit selector update spec from disk."""

    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    document = _require_mapping(loaded, context="selector update spec")
    updates = _require_sequence(document.get("selectors"), context="selector update spec selectors")
    return tuple(_load_update(update) for update in updates)


def apply_selector_updates(
    document: SelectorCatalogDocument,
    updates: Sequence[SelectorRegistryUpdate],
) -> tuple[SelectorCatalogDocument, SelectorRegistryUpdateResult]:
    """Applies explicit selector updates to one raw catalog document."""

    selectors_by_id = {selector.id: selector for selector in document.selectors}
    selector_order = [selector.id for selector in document.selectors]
    added_selector_ids: list[str] = []
    updated_selector_ids: list[str] = []

    for update in updates:
        _validate_selector_id(update.id)
        _validate_update_screens(update.screens, selector_id=update.id, context="screens")
        entry = selectors_by_id.get(update.id)
        if entry is None:
            selectors_by_id[update.id] = SelectorCatalogEntry(
                id=update.id,
                screens=update.screens,
                status=update.status,
                detection_kind=update.detection_kind,
                click=update.click,
                notes=update.notes,
            )
            selector_order.append(update.id)
            added_selector_ids.append(update.id)
        else:
            promoted_status = _promote_status(entry.status, update.status, selector_id=update.id)
            merged_screens = tuple(dict.fromkeys((*entry.screens, *update.screens)))
            merged_click = update.click if update.update_click else entry.click
            merged_notes = update.notes if update.update_notes else entry.notes
            if (
                promoted_status != entry.status
                or merged_screens != entry.screens
                or update.detection_kind != entry.detection_kind
                or merged_click != entry.click
                or merged_notes != entry.notes
            ):
                updated_selector_ids.append(update.id)
            selectors_by_id[update.id] = SelectorCatalogEntry(
                id=entry.id,
                screens=merged_screens,
                status=promoted_status,
                detection_kind=update.detection_kind,
                click=merged_click,
                notes=merged_notes,
            )

    updated_document = SelectorCatalogDocument(selectors=tuple(selectors_by_id[selector_id] for selector_id in selector_order))
    return updated_document, SelectorRegistryUpdateResult(
        added_selector_ids=tuple(added_selector_ids),
        updated_selector_ids=tuple(updated_selector_ids),
        added_ui_element_ids=(),
    )


def ensure_ui_element_ids(source_text: str, selector_ids: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    """Adds missing selector enum members to the `UiElementId` source when required."""

    lines = source_text.splitlines()
    class_index = next((index for index, line in enumerate(lines) if line.startswith("class UiElementId(")), None)
    if class_index is None:
        raise SelectorResolutionError("Could not find the UiElementId enum class while updating selector ids.")

    end_index = len(lines)
    for index in range(class_index + 1, len(lines)):
        line = lines[index]
        if line != "" and not line.startswith("    "):
            end_index = index
            break

    existing_ids = {
        match.group(1)
        for line in lines[class_index + 1 : end_index]
        if (match := _ENUM_MEMBER_PATTERN.match(line)) is not None
    }
    missing_ids: list[str] = []
    for selector_id in selector_ids:
        _validate_selector_id(selector_id)
        if selector_id in existing_ids or selector_id in missing_ids:
            continue
        missing_ids.append(selector_id)
    if not missing_ids:
        return source_text, ()

    insert_lines = [f"    {selector_id} = \"{selector_id}\"" for selector_id in missing_ids]
    updated_lines = [*lines[:end_index], *insert_lines, *lines[end_index:]]
    updated_text = "\n".join(updated_lines)
    if source_text.endswith("\n"):
        updated_text += "\n"
    return updated_text, tuple(missing_ids)


def update_selector_registry_files(
    *,
    spec_path: Path,
    catalog_path: Path,
    ui_element_id_path: Path,
    dry_run: bool = False,
) -> SelectorRegistryUpdateResult:
    """Applies one explicit selector update spec to the static catalog and enum source."""

    updates = load_selector_update_spec(spec_path)
    updated_document, result = apply_selector_updates(load_selector_catalog_document(catalog_path), updates)
    updated_ui_source, added_ui_element_ids = ensure_ui_element_ids(
        ui_element_id_path.read_text(encoding="utf-8"),
        [update.id for update in updates],
    )
    final_result = SelectorRegistryUpdateResult(
        added_selector_ids=result.added_selector_ids,
        updated_selector_ids=result.updated_selector_ids,
        added_ui_element_ids=added_ui_element_ids,
    )
    if dry_run:
        return final_result

    write_selector_catalog_document(catalog_path, updated_document)
    ui_element_id_path.write_text(updated_ui_source, encoding="utf-8", newline="\n")
    return final_result


def _load_update(value: object) -> SelectorRegistryUpdate:
    """Builds one typed selector update from the raw YAML spec entry."""

    mapping = _require_mapping(value, context="selector update entry")
    selector_id = _require_string(mapping.get("id"), context="selector update id")
    screens = tuple(_load_string_sequence(mapping.get("screens"), context=f"selector update '{selector_id}' screens"))
    if not screens:
        raise SelectorResolutionError("Selector updates must declare at least one screen.", selector_id=selector_id)
    status = _require_string(mapping.get("status"), context=f"selector update '{selector_id}' status")
    detection_kind = _require_string(
        mapping.get("detection_kind", DetectionKind.TEMPLATE.value),
        context=f"selector update '{selector_id}' detection_kind",
    )
    if detection_kind not in {kind.value for kind in DetectionKind}:
        raise SelectorResolutionError(
            "Selector updates must use a supported detection kind.",
            selector_id=selector_id,
            detection_kind=detection_kind,
        )
    if status not in _STATUS_RANK:
        raise SelectorResolutionError("Selector updates must use a known selector status.", selector_id=selector_id, status=status)
    raw_click = mapping.get("click")
    click = _load_click_definition(raw_click, selector_id=selector_id) if "click" in mapping else None
    notes = tuple(_load_string_sequence(mapping.get("notes", ()), context=f"selector update '{selector_id}' notes"))
    return SelectorRegistryUpdate(
        id=selector_id,
        screens=screens,
        status=status,
        detection_kind=detection_kind,
        click=click,
        update_click="click" in mapping,
        notes=notes,
        update_notes="notes" in mapping,
    )


def _promote_status(existing_status: str, requested_status: str, *, selector_id: str) -> str:
    """Promotes one selector status forward while rejecting regressions."""

    existing_rank = _STATUS_RANK.get(existing_status)
    requested_rank = _STATUS_RANK.get(requested_status)
    if existing_rank is None or requested_rank is None:
        raise SelectorResolutionError("Selector updates must use known selector statuses.", selector_id=selector_id)
    if requested_rank < existing_rank:
        raise SelectorResolutionError(
            "Selector updates cannot move status backward.",
            selector_id=selector_id,
            existing_status=existing_status,
            requested_status=requested_status,
        )
    return requested_status


def _validate_selector_id(selector_id: str) -> None:
    """Ensures selector identifiers written by the updater remain enum-safe."""

    if _UI_ELEMENT_ID_PATTERN.fullmatch(selector_id) is None:
        raise SelectorResolutionError("Selector ids must be uppercase enum-safe identifiers.", selector_id=selector_id)


def _load_string_sequence(value: object, *, context: str) -> tuple[str, ...]:
    """Loads one YAML string sequence while failing fast on invalid content."""

    return tuple(_require_string(item, context=context) for item in _require_sequence(value, context=context))


def _require_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    """Returns one YAML mapping or raises when the loaded content is invalid."""

    if not isinstance(value, Mapping):
        raise SelectorResolutionError("Expected a mapping in the selector update spec.", context=context)
    return value


def _require_sequence(value: object, *, context: str) -> Sequence[object]:
    """Returns one YAML sequence or raises when the loaded content is invalid."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise SelectorResolutionError("Expected a sequence in the selector update spec.", context=context)
    return value


def _require_string(value: object, *, context: str) -> str:
    """Returns one YAML string or raises when the loaded content is invalid."""

    if not isinstance(value, str) or value == "":
        raise SelectorResolutionError("Expected a non-empty string in the selector update spec.", context=context)
    return value


def _load_click_definition(value: object, *, selector_id: str) -> SelectorCatalogClickDefinition | None:
    """Loads optional click metadata from the explicit update spec."""

    if value is None:
        return None
    mapping = _require_mapping(value, context=f"selector update '{selector_id}' click")
    anchor = _require_string(mapping.get("anchor", "center"), context=f"selector update '{selector_id}' click anchor")
    outcomes = tuple(_load_click_outcomes(mapping.get("outcomes", ()), selector_id=selector_id))
    return SelectorCatalogClickDefinition(anchor=anchor, outcomes=outcomes)


def _load_click_outcomes(value: object, *, selector_id: str) -> tuple[SelectorCatalogClickOutcome, ...]:
    """Loads reviewed click outcomes from the explicit update spec."""

    outcomes = _require_sequence(value, context=f"selector update '{selector_id}' click outcomes")
    loaded_outcomes: list[SelectorCatalogClickOutcome] = []
    for outcome in outcomes:
        mapping = _require_mapping(outcome, context=f"selector update '{selector_id}' click outcome")
        target_screen = mapping.get("target_screen")
        if target_screen is not None:
            target_screen = _require_string(target_screen, context=f"selector update '{selector_id}' click outcome target_screen")
            _validate_update_screens((target_screen,), selector_id=selector_id, context="click outcome target_screen")
        verification_selectors = tuple(
            _load_string_sequence(
                mapping.get("verification_selectors", ()),
                context=f"selector update '{selector_id}' click outcome verification_selectors",
            )
        )
        for verification_selector in verification_selectors:
            _validate_selector_id(verification_selector)
        verification_texts = tuple(
            _load_string_sequence(
                mapping.get("verification_texts", ()),
                context=f"selector update '{selector_id}' click outcome verification_texts",
            )
        )
        notes = tuple(
            _load_string_sequence(
                mapping.get("notes", ()),
                context=f"selector update '{selector_id}' click outcome notes",
            )
        )
        loaded_outcomes.append(
            SelectorCatalogClickOutcome(
                target_screen=target_screen,
                verification_selectors=verification_selectors,
                verification_texts=verification_texts,
                safe_to_click=_require_bool(
                    mapping.get("safe_to_click", True),
                    context=f"selector update '{selector_id}' click outcome safe_to_click",
                ),
                monetized=_require_bool(
                    mapping.get("monetized", False),
                    context=f"selector update '{selector_id}' click outcome monetized",
                ),
                notes=notes,
            )
        )
    return tuple(loaded_outcomes)


def _validate_update_screens(screen_names: Sequence[str], *, selector_id: str, context: str) -> None:
    """Rejects selector-update screens that do not map to known screen identifiers."""

    valid_screen_names = ScreenType.__members__
    for screen_name in screen_names:
        if screen_name not in valid_screen_names:
            raise SelectorResolutionError(
                "Selector updates must use known screen names.",
                selector_id=selector_id,
                context=context,
                screen_type=screen_name,
            )


def _require_bool(value: object, *, context: str) -> bool:
    """Returns one YAML boolean or raises when the loaded content is invalid."""

    if not isinstance(value, bool):
        raise SelectorResolutionError("Expected a boolean in the selector update spec.", context=context)
    return value
