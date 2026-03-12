"""Applies explicit offline selector-registry updates to the static catalog and enum source."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogResolutionStep,
    load_selector_catalog_document,
    load_selector_schema_click_definition,
    load_selector_schema_resolution_steps,
    load_selector_schema_string_sequence,
    require_selector_schema_mapping,
    require_selector_schema_sequence,
    require_selector_schema_string,
    write_selector_catalog_document,
)
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import SelectorStatus

_UI_ELEMENT_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ENUM_MEMBER_PATTERN = re.compile(r"^\s+([A-Z][A-Z0-9_]*)\s*=")
_STATUS_RANK = {status.value: index for index, status in enumerate(SelectorStatus)}


@dataclass(frozen=True, slots=True)
class SelectorRegistryUpdate:
    """Represents one explicit registry update requested by the offline refinement flow."""

    id: str
    screens: tuple[str, ...]
    status: str
    click: SelectorCatalogClickDefinition | None = None
    update_click: bool = False
    interaction_kind: str | None = None
    update_interaction_kind: bool = False
    resolution: tuple[SelectorCatalogResolutionStep, ...] | None = None
    update_resolution: bool = False
    notes: tuple[str, ...] = ()
    update_notes: bool = False


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
    document = require_selector_schema_mapping(loaded, context="selector update spec", document_label="selector update spec")
    updates = tuple(
        _load_update(update)
        for update in require_selector_schema_sequence(
            document.get("selectors"),
            context="selector update spec selectors",
            document_label="selector update spec",
        )
    )
    _ensure_unique_update_ids(updates)
    return updates


def apply_selector_updates(
    document: SelectorCatalogDocument,
    updates: Sequence[SelectorRegistryUpdate],
) -> tuple[SelectorCatalogDocument, SelectorRegistryUpdateResult]:
    """Applies explicit selector updates to one raw catalog document."""

    _ensure_unique_update_ids(updates)
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
                interaction_kind=update.interaction_kind,
                click=update.click,
                resolution=() if not update.update_resolution or update.resolution is None else update.resolution,
                notes=update.notes,
            )
            selector_order.append(update.id)
            added_selector_ids.append(update.id)
            continue

        promoted_status = _promote_status(entry.status, update.status, selector_id=update.id)
        merged_screens = tuple(dict.fromkeys((*entry.screens, *update.screens)))
        merged_click = update.click if update.update_click else entry.click
        merged_interaction_kind = update.interaction_kind if update.update_interaction_kind else entry.interaction_kind
        merged_resolution = update.resolution if update.update_resolution and update.resolution is not None else entry.resolution
        merged_notes = update.notes if update.update_notes else entry.notes
        if (
            promoted_status != entry.status
            or merged_screens != entry.screens
            or merged_click != entry.click
            or merged_interaction_kind != entry.interaction_kind
            or merged_resolution != entry.resolution
            or merged_notes != entry.notes
        ):
            updated_selector_ids.append(update.id)
        selectors_by_id[update.id] = SelectorCatalogEntry(
            id=entry.id,
            screens=merged_screens,
            status=promoted_status,
            interaction_kind=merged_interaction_kind,
            click=merged_click,
            resolution=merged_resolution,
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

    mapping = require_selector_schema_mapping(value, context="selector update entry", document_label="selector update spec")
    selector_id = require_selector_schema_string(
        mapping.get("id"),
        context="selector update id",
        document_label="selector update spec",
    )
    screens = tuple(
        load_selector_schema_string_sequence(
            mapping.get("screens"),
            context=f"selector update '{selector_id}' screens",
            document_label="selector update spec",
        )
    )
    if not screens:
        raise SelectorResolutionError("Selector updates must declare at least one screen.", selector_id=selector_id)
    status = require_selector_schema_string(
        mapping.get("status"),
        context=f"selector update '{selector_id}' status",
        document_label="selector update spec",
    )
    if status not in _STATUS_RANK:
        raise SelectorResolutionError("Selector updates must use a known selector status.", selector_id=selector_id, status=status)
    raw_click = mapping.get("click")
    if "click" in mapping and raw_click is None:
        raise SelectorResolutionError(
            "Selector updates cannot clear reviewed click metadata without a dedicated destructive flag.",
            selector_id=selector_id,
        )
    click = (
        load_selector_schema_click_definition(
            raw_click,
            selector_id=selector_id,
            document_label="selector update spec",
            selector_label="selector update",
            validate_target_screen=lambda screen_name: _validate_update_screens(
                (screen_name,),
                selector_id=selector_id,
                context="click outcome target_screen",
            ),
            validate_verification_selector=_validate_selector_id,
        )
        if "click" in mapping
        else None
    )
    raw_interaction_kind = mapping.get("interaction_kind")
    if "interaction_kind" in mapping and raw_interaction_kind is None:
        raise SelectorResolutionError(
            "Selector updates cannot clear interaction_kind without a dedicated destructive flag.",
            selector_id=selector_id,
        )
    interaction_kind = (
        require_selector_schema_string(
            raw_interaction_kind,
            context=f"selector update '{selector_id}' interaction_kind",
            document_label="selector update spec",
        )
        if "interaction_kind" in mapping
        else None
    )
    if interaction_kind is not None:
        _validate_interaction_kind(interaction_kind, selector_id=selector_id)
    raw_resolution = mapping.get("resolution")
    if "resolution" in mapping and raw_resolution is None:
        raise SelectorResolutionError(
            "Selector updates cannot clear resolution without a dedicated destructive flag.",
            selector_id=selector_id,
        )
    resolution = (
        load_selector_schema_resolution_steps(
            raw_resolution,
            selector_id=selector_id,
            document_label="selector update spec",
            selector_label="selector update",
        )
        if "resolution" in mapping
        else None
    )
    notes = tuple(
        load_selector_schema_string_sequence(
            mapping.get("notes", ()),
            context=f"selector update '{selector_id}' notes",
            document_label="selector update spec",
        )
    )
    return SelectorRegistryUpdate(
        id=selector_id,
        screens=screens,
        status=status,
        click=click,
        update_click="click" in mapping,
        interaction_kind=interaction_kind,
        update_interaction_kind="interaction_kind" in mapping,
        resolution=resolution,
        update_resolution="resolution" in mapping,
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


def _ensure_unique_update_ids(updates: Sequence[SelectorRegistryUpdate]) -> None:
    """Rejects one update batch that tries to mutate the same selector twice."""

    selector_ids = [update.id for update in updates]
    duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
    if duplicates:
        raise SelectorResolutionError(
            "Selector update specs cannot repeat the same selector id in one run.",
            duplicates=sorted(duplicates),
        )


def _validate_selector_id(selector_id: str) -> None:
    """Ensures selector identifiers written by the updater remain enum-safe."""

    if _UI_ELEMENT_ID_PATTERN.fullmatch(selector_id) is None:
        raise SelectorResolutionError("Selector ids must be uppercase enum-safe identifiers.", selector_id=selector_id)


def _validate_interaction_kind(interaction_kind_name: str, *, selector_id: str) -> None:
    """Rejects selector-update interaction kinds outside the supported enum."""

    try:
        SelectorInteractionKind(interaction_kind_name)
    except ValueError as error:
        raise SelectorResolutionError(
            "Selector updates must use a supported interaction kind.",
            selector_id=selector_id,
            interaction_kind=interaction_kind_name,
        ) from error


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
