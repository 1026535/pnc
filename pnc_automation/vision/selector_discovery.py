"""Draft selector-discovery tooling for reviewed registry refinement workflows."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import yaml
from PIL import Image

from pnc_automation.capture.artifact_store import ArtifactRecord
from pnc_automation.capture.screenshot_service import CapturedScreenshot
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import Observation, SelectorResolutionKind
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import CapturedObservation, ObservationBuilder
from pnc_automation.vision.ocr_service import OcrLine, OcrResult, OcrService
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    SelectorCatalogClickOutcome,
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    SelectorCatalogResolutionStep,
)
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import SelectorStatus
from pnc_automation.vision.text_anchors import DetectedTextAnchor, TextAnchorDetector, normalize_ocr_text

_STATUS_RANK = {status.value: index for index, status in enumerate(SelectorStatus)}
_MergedValue = TypeVar("_MergedValue")


@dataclass(frozen=True, slots=True)
class SelectorDiscoveryRule:
    """Maps one screen-local OCR label to a draft selector suggestion."""

    screen_type: ScreenType
    selector_id: str
    normalized_text: str
    resolution_kind: SelectorResolutionKind
    status: SelectorStatus
    min_x_ratio: float = 0.0
    max_x_ratio: float = 1.0
    min_y_ratio: float = 0.0
    max_y_ratio: float = 1.0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScreenSelectorDiscoveryRule:
    """Adds one draft selector whenever a whole screen contract is observed."""

    screen_type: ScreenType
    selector_id: str
    resolution_kind: SelectorResolutionKind
    status: SelectorStatus
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectorDiscoveryDraft:
    """Represents one reviewed-draft selector update ready for spec serialization."""

    id: str
    screens: tuple[str, ...]
    status: str
    resolution: tuple[SelectorCatalogResolutionStep, ...]
    interaction_kind: str | None = None
    notes: tuple[str, ...] = ()
    click: SelectorCatalogClickDefinition | None = None

    def to_update_spec_entry(self) -> dict[str, object]:
        """Returns the updater-spec representation of one draft selector entry."""

        document: dict[str, object] = {
            "id": self.id,
            "screens": list(self.screens),
            "status": self.status,
            "resolution": [step.to_document() for step in self.resolution],
        }
        if self.interaction_kind is not None:
            document["interaction_kind"] = self.interaction_kind
        if self.click is not None:
            document["click"] = self.click.to_document()
        if self.notes:
            document["notes"] = list(self.notes)
        return document

    def to_document(self) -> dict[str, object]:
        """Returns the report representation of one draft selector entry."""

        return self.to_update_spec_entry()


@dataclass(frozen=True, slots=True)
class SelectorDiscoverySnapshot:
    """Captures one analyzed screenshot artifact and its draft selector suggestions."""

    artifact_path: Path
    screen_type: ScreenType
    blocking_popup: bool
    visible_selector_ids: tuple[str, ...]
    text_anchors: tuple[DetectedTextAnchor, ...]
    ocr_lines: tuple[OcrLine, ...]
    draft_selectors: tuple[SelectorDiscoveryDraft, ...]

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one analyzed screenshot snapshot."""

        return {
            "artifact_path": str(self.artifact_path),
            "screen_type": self.screen_type.name,
            "blocking_popup": self.blocking_popup,
            "visible_selector_ids": list(self.visible_selector_ids),
            "text_anchors": [_anchor_to_document(anchor) for anchor in self.text_anchors],
            "ocr_lines": [_ocr_line_to_document(line) for line in self.ocr_lines],
            "draft_selector_ids": [draft.id for draft in self.draft_selectors],
        }


@dataclass(frozen=True, slots=True)
class SelectorDiscoveryProbe:
    """Captures one reviewed live probe from a source selector to a destination screen."""

    selector_id: str
    source_artifact_path: Path
    source_screen_type: ScreenType
    destination_artifact_path: Path
    destination_screen_type: ScreenType
    destination_visible_selector_ids: tuple[str, ...]
    destination_blocking_popup: bool
    draft_selector: SelectorDiscoveryDraft | None = None

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready representation of one live selector probe."""

        document: dict[str, object] = {
            "selector_id": self.selector_id,
            "source_artifact_path": str(self.source_artifact_path),
            "source_screen_type": self.source_screen_type.name,
            "destination_artifact_path": str(self.destination_artifact_path),
            "destination_screen_type": self.destination_screen_type.name,
            "destination_visible_selector_ids": list(self.destination_visible_selector_ids),
            "destination_blocking_popup": self.destination_blocking_popup,
        }
        if self.draft_selector is not None:
            document["draft_selector"] = self.draft_selector.to_document()
        return document


@dataclass(frozen=True, slots=True)
class SelectorDiscoveryReport:
    """Summarizes one discovery pass across saved screenshots or a live session."""

    snapshots: tuple[SelectorDiscoverySnapshot, ...]
    probes: tuple[SelectorDiscoveryProbe, ...]
    draft_selectors: tuple[SelectorDiscoveryDraft, ...]

    def to_document(self) -> dict[str, object]:
        """Returns the YAML-ready report representation."""

        return {
            "snapshots": [snapshot.to_document() for snapshot in self.snapshots],
            "probes": [probe.to_document() for probe in self.probes],
            "draft_selectors": [draft.to_document() for draft in self.draft_selectors],
        }

    def to_update_spec_document(self) -> dict[str, object]:
        """Returns an updater-spec document containing the merged draft selector updates."""

        return {"selectors": [draft.to_update_spec_entry() for draft in self.draft_selectors]}


@dataclass(slots=True)
class SelectorDiscoveryAnalyzer:
    """Builds discovery snapshots and draft update specs from screenshot evidence."""

    observation_builder: ObservationBuilder
    ocr_service: OcrService
    catalog: SelectorCatalogDocument
    text_anchor_detector: TextAnchorDetector = field(default_factory=TextAnchorDetector)

    def analyze_captured_observation(self, captured_observation: CapturedObservation) -> SelectorDiscoverySnapshot:
        """Analyzes one already-built captured observation without rebuilding it."""

        return self._build_snapshot(
            screenshot=captured_observation.screenshot,
            observation=captured_observation.observation,
        )

    def analyze_captured_screenshot(self, screenshot: CapturedScreenshot) -> SelectorDiscoverySnapshot:
        """Analyzes one captured screenshot and returns its typed discovery snapshot."""

        return self._build_snapshot(screenshot=screenshot, observation=self.observation_builder.build(screenshot))

    def analyze_artifact_path(self, artifact_path: Path) -> SelectorDiscoverySnapshot:
        """Loads one saved screenshot artifact from disk and analyzes it."""

        payload = artifact_path.read_bytes()
        with Image.open(artifact_path) as opened_image:
            image_format = opened_image.format or artifact_path.suffix.lstrip(".").upper() or "PNG"
            image = opened_image.copy()
        screenshot = CapturedScreenshot(
            artifact=ArtifactRecord(
                path=artifact_path,
                label=artifact_path.stem,
                captured_at=datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC),
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
            image=image,
            image_format=image_format,
        )
        return self.analyze_captured_screenshot(screenshot)

    def build_probe_draft(
        self,
        *,
        selector_id: UiElementId,
        source_observation: Observation,
        destination_observation: Observation,
        source_artifact_path: Path,
        destination_artifact_path: Path,
    ) -> SelectorDiscoveryProbe:
        """Builds one reviewed click-mapping probe and an optional draft selector update."""

        draft = self._build_click_mapping_draft(
            selector_id=selector_id,
            source_observation=source_observation,
            destination_observation=destination_observation,
            source_artifact_path=source_artifact_path,
            destination_artifact_path=destination_artifact_path,
        )
        return SelectorDiscoveryProbe(
            selector_id=selector_id.value,
            source_artifact_path=source_artifact_path,
            source_screen_type=source_observation.screen_type,
            destination_artifact_path=destination_artifact_path,
            destination_screen_type=destination_observation.screen_type,
            destination_visible_selector_ids=tuple(sorted(item.value for item in destination_observation.visible_elements)),
            destination_blocking_popup=destination_observation.blocking_popup,
            draft_selector=draft,
        )

    def build_report(
        self,
        *,
        snapshots: Sequence[SelectorDiscoverySnapshot],
        probes: Sequence[SelectorDiscoveryProbe] = (),
    ) -> SelectorDiscoveryReport:
        """Merges draft selectors across snapshots and probes into one review report."""

        merged = _merge_discovery_drafts(
            [
                *(draft for snapshot in snapshots for draft in snapshot.draft_selectors),
                *(probe.draft_selector for probe in probes if probe.draft_selector is not None),
            ]
        )
        return SelectorDiscoveryReport(
            snapshots=tuple(snapshots),
            probes=tuple(probes),
            draft_selectors=merged,
        )

    def _discover_snapshot_drafts(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_result: OcrResult,
    ) -> tuple[SelectorDiscoveryDraft, ...]:
        """Builds draft selectors suggested by one analyzed screenshot."""

        drafts: list[SelectorDiscoveryDraft] = []
        drafts.extend(self._build_line_rule_drafts(screenshot=screenshot, observation=observation, lines=ocr_result.lines))
        drafts.extend(self._build_screen_rule_drafts(screenshot=screenshot, observation=observation))
        return _merge_discovery_drafts(drafts)

    def _build_snapshot(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
    ) -> SelectorDiscoverySnapshot:
        """Builds one discovery snapshot from one screenshot and its already-built observation."""

        ocr_result = self.ocr_service.read_result(screenshot.image)
        drafts = self._discover_snapshot_drafts(
            screenshot=screenshot,
            observation=observation,
            ocr_result=ocr_result,
        )
        return SelectorDiscoverySnapshot(
            artifact_path=screenshot.artifact.path,
            screen_type=observation.screen_type,
            blocking_popup=observation.blocking_popup,
            visible_selector_ids=tuple(sorted(selector_id.value for selector_id in observation.visible_elements)),
            text_anchors=self.text_anchor_detector.detect(ocr_result),
            ocr_lines=ocr_result.lines,
            draft_selectors=drafts,
        )

    def _build_line_rule_drafts(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        lines: tuple[OcrLine, ...],
    ) -> tuple[SelectorDiscoveryDraft, ...]:
        """Builds draft selectors from screen-specific OCR line rules."""

        drafts: list[SelectorDiscoveryDraft] = []
        for rule in _LINE_DISCOVERY_RULES:
            if observation.screen_type != rule.screen_type:
                continue
            if not self._should_propose(rule.selector_id):
                continue
            line = _find_matching_line(screenshot.image.size, lines, rule=rule)
            if line is None:
                continue
            drafts.append(
                SelectorDiscoveryDraft(
                    id=rule.selector_id,
                    screens=(observation.screen_type.name,),
                    status=rule.status.value,
                    resolution=_default_resolution_for_rule(rule.selector_id, kind=rule.resolution_kind),
                    notes=(
                        *rule.notes,
                        f"Discovery artifact: {screenshot.artifact.path}",
                        f"OCR evidence: {line.text}",
                    ),
                )
            )
        return tuple(drafts)

    def _build_screen_rule_drafts(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
    ) -> tuple[SelectorDiscoveryDraft, ...]:
        """Builds draft selectors implied by the whole observed screen contract."""

        drafts: list[SelectorDiscoveryDraft] = []
        for rule in _SCREEN_DISCOVERY_RULES:
            if observation.screen_type != rule.screen_type:
                continue
            if not self._should_propose(rule.selector_id):
                continue
            drafts.append(
                SelectorDiscoveryDraft(
                    id=rule.selector_id,
                    screens=(observation.screen_type.name,),
                    status=rule.status.value,
                    resolution=_default_resolution_for_rule(rule.selector_id, kind=rule.resolution_kind),
                    notes=(
                        *rule.notes,
                        f"Discovery artifact: {screenshot.artifact.path}",
                    ),
                )
            )
        return tuple(drafts)

    def _build_click_mapping_draft(
        self,
        *,
        selector_id: UiElementId,
        source_observation: Observation,
        destination_observation: Observation,
        source_artifact_path: Path,
        destination_artifact_path: Path,
    ) -> SelectorDiscoveryDraft | None:
        """Builds one draft click-mapping update when the catalog still lacks reviewed outcomes."""

        catalog_entry = self._find_catalog_entry(selector_id.value)
        if catalog_entry is None:
            raise SelectorResolutionError(
                "Live selector discovery probes require a catalog-backed selector id.",
                selector_id=selector_id.value,
                source_screen=source_observation.screen_type.name,
            )
        existing_status_rank = _STATUS_RANK[catalog_entry.status]
        click_mapped_rank = _STATUS_RANK[SelectorStatus.CLICK_MAPPED.value]
        if existing_status_rank >= click_mapped_rank and catalog_entry.click is not None and catalog_entry.click.outcomes:
            return None
        click = _build_click_definition(
            destination_observation,
            anchor="center" if catalog_entry.click is None else catalog_entry.click.anchor,
        )
        if click is None:
            return None

        return SelectorDiscoveryDraft(
            id=selector_id.value,
            screens=tuple(dict.fromkeys((*catalog_entry.screens, source_observation.screen_type.name))),
            status=SelectorStatus.CLICK_MAPPED.value,
            resolution=_merge_resolution_with_relative_bounds(
                catalog_entry.resolution,
                _build_relative_bounds_from_observation(
                    observation=source_observation,
                    selector_id=selector_id,
                ),
            ),
            interaction_kind=SelectorInteractionKind.NAVIGATION.value,
            click=click,
            notes=(
                "Autogenerated live probe draft for review.",
                f"Source artifact: {source_artifact_path}",
                f"Destination artifact: {destination_artifact_path}",
            ),
        )

    def _should_propose(self, selector_id: str) -> bool:
        """Returns whether discovery should still emit a draft for the requested selector id."""

        catalog_entry = self._find_catalog_entry(selector_id)
        if catalog_entry is None:
            return True
        return catalog_entry.status == SelectorStatus.PLANNED.value or not catalog_entry.resolution

    def _find_catalog_entry(self, selector_id: str) -> SelectorCatalogEntry | None:
        """Returns one catalog entry when present."""

        for selector in self.catalog.selectors:
            if selector.id == selector_id:
                return selector
        return None


def load_artifact_paths(*, artifact_paths: Sequence[Path] = (), artifact_directory: Path | None = None) -> tuple[Path, ...]:
    """Loads the discovery input artifact paths from explicit files or one directory tree."""

    loaded_paths: list[Path] = []
    for artifact_path in artifact_paths:
        if not artifact_path.is_file():
            raise SelectorResolutionError("Discovery artifacts must point to existing files.", artifact_path=str(artifact_path))
        loaded_paths.append(artifact_path)
    if artifact_directory is not None:
        if not artifact_directory.is_dir():
            raise SelectorResolutionError(
                "Discovery artifact directories must point to an existing directory.",
                artifact_directory=str(artifact_directory),
            )
        loaded_paths.extend(sorted(path for path in artifact_directory.rglob("*") if _is_png_artifact(path)))
    unique_paths = tuple(dict.fromkeys(path.resolve() for path in loaded_paths))
    if not unique_paths:
        raise SelectorResolutionError("Selector discovery requires at least one artifact path or one artifact directory.")
    return unique_paths


def write_selector_discovery_report(path: Path, report: SelectorDiscoveryReport) -> None:
    """Writes one YAML discovery report to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(report.to_document(), sort_keys=False), encoding="utf-8", newline="\n")


def write_selector_discovery_spec(path: Path, report: SelectorDiscoveryReport) -> None:
    """Writes one YAML updater-spec draft to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(report.to_update_spec_document(), sort_keys=False), encoding="utf-8", newline="\n")


def _build_click_definition(
    destination_observation: Observation,
    *,
    anchor: str = "center",
) -> SelectorCatalogClickDefinition | None:
    """Builds one draft click definition when the probe destination is known and explicitly verifiable."""

    verification_selectors = tuple(sorted(selector_id.value for selector_id in destination_observation.visible_elements)[:5])
    if destination_observation.screen_type == ScreenType.UNKNOWN or not verification_selectors:
        return None
    safe_to_click = not destination_observation.blocking_popup
    return SelectorCatalogClickDefinition(
        anchor=anchor,
        outcomes=(
            SelectorCatalogClickOutcome(
                target_screen=destination_observation.screen_type.name,
                verification_selectors=verification_selectors,
                verification_texts=(),
                safe_to_click=safe_to_click,
                monetized=False,
                notes=(
                    "Autogenerated click outcome from a reviewed live probe.",
                ),
            ),
        ),
    )


def _find_matching_line(
    image_size: tuple[int, int],
    lines: tuple[OcrLine, ...],
    *,
    rule: SelectorDiscoveryRule,
) -> OcrLine | None:
    """Returns the first OCR line that satisfies one discovery rule."""

    width, height = image_size
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text != rule.normalized_text:
            continue
        if line.bounds.x < int(width * rule.min_x_ratio) or line.bounds.x > int(width * rule.max_x_ratio):
            continue
        if line.bounds.y < int(height * rule.min_y_ratio) or line.bounds.y > int(height * rule.max_y_ratio):
            continue
        return line
    return None


def _merge_discovery_drafts(drafts: Sequence[SelectorDiscoveryDraft]) -> tuple[SelectorDiscoveryDraft, ...]:
    """Merges duplicate draft selector updates while preserving deterministic order."""

    drafts_by_id: dict[str, SelectorDiscoveryDraft] = {}
    ordered_ids: list[str] = []
    for draft in drafts:
        existing = drafts_by_id.get(draft.id)
        if existing is None:
            drafts_by_id[draft.id] = draft
            ordered_ids.append(draft.id)
            continue
        drafts_by_id[draft.id] = _merge_draft(existing, draft)
    return tuple(drafts_by_id[draft_id] for draft_id in ordered_ids)


def _merge_draft(left: SelectorDiscoveryDraft, right: SelectorDiscoveryDraft) -> SelectorDiscoveryDraft:
    """Merges two drafts for the same selector id while rejecting incompatible content."""

    if left.id != right.id:
        raise SelectorResolutionError("Can only merge discovery drafts for the same selector id.", left=left.id, right=right.id)
    merged_status = left.status if _STATUS_RANK[left.status] >= _STATUS_RANK[right.status] else right.status
    merged_click = _merge_click_definitions(left.click, right.click, selector_id=left.id)
    merged_interaction_kind = _merge_optional_scalar(
        left.interaction_kind,
        right.interaction_kind,
        selector_id=left.id,
        field_name="interaction_kind",
    )
    return SelectorDiscoveryDraft(
        id=left.id,
        screens=tuple(dict.fromkeys((*left.screens, *right.screens))),
        status=merged_status,
        resolution=_merge_resolution_steps(left.resolution, right.resolution, selector_id=left.id),
        interaction_kind=merged_interaction_kind,
        notes=tuple(dict.fromkeys((*left.notes, *right.notes))),
        click=merged_click,
    )


def _merge_click_definitions(
    left: SelectorCatalogClickDefinition | None,
    right: SelectorCatalogClickDefinition | None,
    *,
    selector_id: str,
) -> SelectorCatalogClickDefinition | None:
    """Merges optional draft click definitions for the same selector id."""

    if left is None:
        return right
    if right is None:
        return left
    if left.anchor != right.anchor:
        raise SelectorResolutionError(
            "Discovery drafts produced conflicting click anchors for the same selector id.",
            selector_id=selector_id,
            left_anchor=left.anchor,
            right_anchor=right.anchor,
        )
    merged_outcomes = list(left.outcomes)
    for outcome in right.outcomes:
        if outcome in merged_outcomes:
            continue
        merged_outcomes.append(outcome)
    return SelectorCatalogClickDefinition(anchor=left.anchor, outcomes=tuple(merged_outcomes))


def _merge_optional_scalar(
    left: _MergedValue | None,
    right: _MergedValue | None,
    *,
    selector_id: str,
    field_name: str,
) -> _MergedValue | None:
    """Merges one optional scalar draft field while rejecting conflicting authored values."""

    if left is None:
        return right
    if right is None:
        return left
    if left != right:
        raise SelectorResolutionError(
            "Discovery drafts produced conflicting authored values for the same selector id.",
            selector_id=selector_id,
            field_name=field_name,
            left_value=left,
            right_value=right,
        )
    return left


def _merge_resolution_steps(
    left: tuple[SelectorCatalogResolutionStep, ...],
    right: tuple[SelectorCatalogResolutionStep, ...],
    *,
    selector_id: str,
) -> tuple[SelectorCatalogResolutionStep, ...]:
    """Merges authored resolution policies while rejecting conflicting step sets."""

    if left == right:
        return left
    if not left:
        return right
    if not right:
        return left
    raise SelectorResolutionError(
        "Discovery drafts produced conflicting resolution policies for the same selector id.",
        selector_id=selector_id,
    )


def _default_resolution_for_rule(
    selector_id: str,
    *,
    kind: SelectorResolutionKind,
) -> tuple[SelectorCatalogResolutionStep, ...]:
    """Builds the canonical authored resolution policy for one discovery rule."""

    if kind != SelectorResolutionKind.TEMPLATE:
        raise SelectorResolutionError(
            "Selector discovery only supports template-backed authored draft rules today.",
            selector_id=selector_id,
            resolution_kind=kind.value,
        )
    return (
        SelectorCatalogResolutionStep(
            kind=kind.value,
            template_path=f"{selector_id.lower()}.png",
        ),
    )


def _merge_resolution_with_relative_bounds(
    existing_resolution: tuple[SelectorCatalogResolutionStep, ...],
    relative_bounds: SelectorCatalogRelativeBounds | None,
) -> tuple[SelectorCatalogResolutionStep, ...]:
    """Appends one geometry fallback step when the observed source provides reviewed bounds."""

    if relative_bounds is None:
        return existing_resolution
    if any(step.kind == SelectorResolutionKind.RELATIVE_BOUNDS.value for step in existing_resolution):
        return existing_resolution
    return (
        *existing_resolution,
        SelectorCatalogResolutionStep(
            kind=SelectorResolutionKind.RELATIVE_BOUNDS.value,
            relative_bounds=relative_bounds,
        ),
    )


def _build_relative_bounds_from_observation(
    *,
    observation: Observation,
    selector_id: UiElementId,
) -> SelectorCatalogRelativeBounds | None:
    """Returns normalized geometry for one visible source selector when the observation carries image dimensions."""

    if observation.image_size is None:
        return None
    element = observation.get(selector_id)
    if element is None:
        return None
    image_width, image_height = observation.image_size
    if image_width <= 0 or image_height <= 0:
        raise SelectorResolutionError(
            "Discovery observations must carry positive image dimensions before geometry can be normalized.",
            selector_id=selector_id.value,
            image_size=observation.image_size,
        )
    action_x_ratio = None
    action_y_ratio = None
    if element.action_point is not None and element.action_point != element.bounds.center():
        action_x_ratio = _round_ratio(element.action_point[0], total=image_width)
        action_y_ratio = _round_ratio(element.action_point[1], total=image_height)
    return SelectorCatalogRelativeBounds(
        x_ratio=_round_ratio(element.bounds.x, total=image_width),
        y_ratio=_round_ratio(element.bounds.y, total=image_height),
        width_ratio=_round_ratio(element.bounds.width, total=image_width),
        height_ratio=_round_ratio(element.bounds.height, total=image_height),
        action_x_ratio=action_x_ratio,
        action_y_ratio=action_y_ratio,
    )


def _round_ratio(value: int, *, total: int) -> float:
    """Returns one deterministic normalized ratio rounded for stable YAML serialization."""

    if total <= 0:
        raise SelectorResolutionError("Normalized selector ratios require a positive dimension.", total=total)
    return round(value / total, 12)


def _is_png_artifact(path: Path) -> bool:
    """Returns whether the provided path points to a PNG artifact regardless of suffix casing."""

    return path.is_file() and path.suffix.lower() == ".png"


def _anchor_to_document(anchor: DetectedTextAnchor) -> dict[str, object]:
    """Returns the report representation of one detected text anchor."""

    document: dict[str, object] = {
        "id": anchor.id.value,
        "text": anchor.text,
        "normalized_text": anchor.normalized_text,
        "bounds": _region_to_document(anchor.bounds),
        "confidence": anchor.confidence,
    }
    if anchor.metadata:
        document["metadata"] = {key: value for key, value in anchor.metadata}
    return document


def _ocr_line_to_document(line: OcrLine) -> dict[str, object]:
    """Returns the report representation of one OCR line."""

    return {
        "text": line.text,
        "bounds": _region_to_document(line.bounds),
        "confidence": line.confidence,
    }


def _region_to_document(region: object) -> dict[str, int]:
    """Returns a YAML-ready representation of one rectangular region."""

    return {
        "x": int(region.x),
        "y": int(region.y),
        "width": int(region.width),
        "height": int(region.height),
    }


_LINE_DISCOVERY_RULES: tuple[SelectorDiscoveryRule, ...] = (
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ALLIANCE_JOIN,
        selector_id="PNC_ALLIANCE_JOIN_BUTTON",
        normalized_text="JOIN",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.65,
        notes=("Drafted from the alliance-join landing CTA.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ALLIANCE_JOIN,
        selector_id="PNC_ALLIANCE_CREATE_BUTTON",
        normalized_text="CREATEALLIANCE",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.65,
        notes=("Drafted from the alliance-join creation CTA.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_DEVELOPMENT",
        normalized_text="DEVELOPMENT",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_ECONOMY",
        normalized_text="ECONOMY",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_MILITARY",
        normalized_text="MILITARY",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_FORTIFICATION",
        normalized_text="FORTIFICATION",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_UNIT_TACTICS",
        normalized_text="UNITTACTICS",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
    SelectorDiscoveryRule(
        screen_type=ScreenType.PNC_ACADEMY,
        selector_id="PNC_ACADEMY_CATEGORY_FORMATIONS",
        normalized_text="FORMATIONS",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        min_y_ratio=0.2,
        max_y_ratio=0.8,
        notes=("Drafted from the academy overview category grid.",),
    ),
)

_SCREEN_DISCOVERY_RULES: tuple[ScreenSelectorDiscoveryRule, ...] = (
    ScreenSelectorDiscoveryRule(
        screen_type=ScreenType.PNC_RESEARCH_TREE,
        selector_id="PNC_RESEARCH_NODE_ENTRY",
        resolution_kind=SelectorResolutionKind.TEMPLATE,
        status=SelectorStatus.SCREENSHOT_SEEDED,
        notes=("Drafted as a dynamic research-node collection from the live research tree.",),
    ),
)
