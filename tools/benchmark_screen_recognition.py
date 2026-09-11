"""Benchmark reviewed screen anchors against the canonical observation pipeline."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import statistics
import subprocess
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_catalog import load_selector_catalog_document
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorRegistry,
    build_default_selector_registry,
)
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualScreenRecognizer, load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot


_MANIFEST_VERSION = 1
_REQUIRED_SPLITS = frozenset({"reference", "validation", "holdout"})
_REQUIRED_SAMPLE_FIELDS = frozenset({"image", "screen", "split", "group", "sha256"})
_HEX_DIGITS = frozenset("0123456789abcdef")
_STATIC_REFERENCE_SUFFIXES = frozenset({".py", ".yaml", ".yml"})
_STATIC_REFERENCE_ROOTS = ("pnc_automation", "scripts", "config", "tools", "tests")
_STATIC_REFERENCE_IGNORES = frozenset({"__pycache__", ".git", ".mypy_cache", ".pytest_cache"})
_REACHABLE_REFERENCE_SCOPES = frozenset({"runtime", "authored", "tool"})
_RESOLVER_OWNERS = {
    DetectionKind.TEMPLATE.value: "ImageSelectorEngine.template_matcher",
    DetectionKind.COLLECTION.value: "ImageSelectorEngine.template_matcher",
    DetectionKind.OCR_REGION.value: "ImageSelectorEngine.ocr_region",
    DetectionKind.ANCHORED_REGION.value: "SelectorRegistry.materialize_for_screen",
    DetectionKind.PLANNED.value: None,
}


@dataclass(frozen=True, slots=True)
class StaticSelectorReference:
    """One source-level selector reference found without executing application code."""

    path: str
    line: int
    kind: str
    scope: str

    def to_document(self) -> dict[str, object]:
        """Return a stable, secret-free representation of this reference."""

        return {
            "path": self.path,
            "line": self.line,
            "kind": self.kind,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    """One validated, decoded screenshot sample from the reviewed manifest."""

    image_name: str
    path: Path
    expected_screen: ScreenType
    split: str
    group: str
    sha256: str
    decoded_sha256: str
    image: Image.Image


@dataclass(frozen=True, slots=True)
class FrameMetrics:
    """Safe, text-free per-frame benchmark output."""

    image: str
    expected_screen: str
    split: str
    group: str
    baseline_screen: str | None
    raw_visual_evidence_screen_ids: tuple[str, ...]
    final_guarded_screen: str | None
    blocking_popup: bool | None
    wrong_actionable_classification: bool | None
    abstention: bool | None
    baseline_latency_ms: float | None
    raw_visual_latency_ms: float
    guarded_latency_ms: float | None

    def to_document(self) -> dict[str, object]:
        """Return the stable JSON representation for one frame."""

        return {
            "image": self.image,
            "expected_screen": self.expected_screen,
            "split": self.split,
            "group": self.group,
            "baseline_screen": self.baseline_screen,
            "raw_visual_evidence_screen_ids": list(self.raw_visual_evidence_screen_ids),
            "final_guarded_screen": self.final_guarded_screen,
            "blocking_popup": self.blocking_popup,
            "wrong_actionable_classification": self.wrong_actionable_classification,
            "abstention": self.abstention,
            "latency_ms": {
                "baseline": self.baseline_latency_ms,
                "raw_visual": self.raw_visual_latency_ms,
                "guarded": self.guarded_latency_ms,
            },
        }


def load_manifest(path: Path) -> tuple[BenchmarkSample, ...]:
    """Load and validate the reviewed screenshot manifest and its image files."""

    if not path.is_file():
        raise FileNotFoundError(f"screen-recognition manifest does not exist: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"screen-recognition manifest could not be decoded: {path}") from error
    if not isinstance(document, dict) or set(document) != {"version", "annotation", "samples"}:
        raise ValueError("manifest must contain exactly version, annotation, and samples")
    if type(document["version"]) is not int or document["version"] != _MANIFEST_VERSION:
        raise ValueError(f"manifest version must be {_MANIFEST_VERSION}")
    if not isinstance(document["annotation"], str) or not document["annotation"].strip():
        raise ValueError("manifest annotation must be a non-empty string")
    raw_samples = document["samples"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ValueError("manifest samples must be a non-empty list")

    root = path.parent.resolve()
    samples: list[BenchmarkSample] = []
    image_names: set[str] = set()
    for index, raw_sample in enumerate(raw_samples):
        samples.append(_load_sample(raw_sample, index=index, root=root))
        if samples[-1].image_name in image_names:
            raise ValueError(f"manifest repeats image: {samples[-1].image_name}")
        image_names.add(samples[-1].image_name)

    split_names = {sample.split for sample in samples}
    missing_splits = _REQUIRED_SPLITS - split_names
    if missing_splits:
        raise ValueError(f"manifest is missing required split(s): {sorted(missing_splits)}")
    _validate_reference_holdout_isolation(samples)
    return tuple(samples)


def _load_sample(raw_sample: object, *, index: int, root: Path) -> BenchmarkSample:
    if not isinstance(raw_sample, dict) or set(raw_sample) != _REQUIRED_SAMPLE_FIELDS:
        raise ValueError(
            f"manifest sample {index} must contain exactly image, screen, split, group, and sha256"
        )
    image_name = raw_sample["image"]
    screen_name = raw_sample["screen"]
    split = raw_sample["split"]
    group = raw_sample["group"]
    expected_sha256 = raw_sample["sha256"]
    if not isinstance(image_name, str) or not image_name or Path(image_name).is_absolute():
        raise ValueError(f"manifest sample {index} image must be a relative path")
    if not isinstance(screen_name, str):
        raise ValueError(f"manifest sample {index} screen must be a string")
    try:
        expected_screen = ScreenType[screen_name]
    except KeyError:
        try:
            expected_screen = ScreenType(screen_name)
        except ValueError as error:
            raise ValueError(f"manifest sample {index} has unknown screen: {screen_name}") from error
    except TypeError as error:
        raise ValueError(f"manifest sample {index} has unknown screen: {screen_name}") from error
    if not isinstance(split, str) or split not in _REQUIRED_SPLITS:
        raise ValueError(f"manifest sample {index} split must be reference, validation, or holdout")
    if not isinstance(group, str) or not group:
        raise ValueError(f"manifest sample {index} group must be a non-empty string")
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or expected_sha256 != expected_sha256.lower()
        or any(character not in _HEX_DIGITS for character in expected_sha256)
    ):
        raise ValueError(f"manifest sample {index} sha256 must be a lowercase 64-character hex digest")

    sample_path = (root / image_name).resolve()
    if not sample_path.is_relative_to(root) or not sample_path.is_file():
        raise ValueError(f"manifest sample {index} image is missing or escapes its directory: {image_name}")
    try:
        with Image.open(sample_path) as opened:
            opened.load()
            image = opened.convert("RGB").copy()
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError(f"manifest sample {index} image is not a valid image: {image_name}") from error
    decoded_sha256 = _decoded_image_sha256(image)
    return BenchmarkSample(
        image_name=image_name,
        path=sample_path,
        expected_screen=expected_screen,
        split=split,
        group=group,
        sha256=expected_sha256,
        decoded_sha256=decoded_sha256,
        image=image,
    )


def _decoded_image_sha256(image: Image.Image) -> str:
    """Hash decoded RGB pixels and dimensions so PNG encoding cannot hide duplicates."""

    digest = hashlib.sha256()
    digest.update(image.width.to_bytes(8, "big"))
    digest.update(image.height.to_bytes(8, "big"))
    digest.update(image.convert("RGB").tobytes())
    return digest.hexdigest()


def _validate_reference_holdout_isolation(samples: Sequence[BenchmarkSample]) -> None:
    references = [sample for sample in samples if sample.split == "reference"]
    holdouts = [sample for sample in samples if sample.split == "holdout"]
    shared_groups = {sample.group for sample in references} & {sample.group for sample in holdouts}
    if shared_groups:
        raise ValueError(
            f"reference and holdout share reviewed group(s): {sorted(shared_groups)}"
        )
    reference_hashes = {sample.decoded_sha256 for sample in references}
    duplicate_hashes = reference_hashes & {sample.decoded_sha256 for sample in holdouts}
    if duplicate_hashes:
        raise ValueError("reference and holdout contain duplicate decoded image content")


def benchmark_manifest(
    manifest_path: Path,
    *,
    visual_only: bool = False,
    builder_factory: Callable[[SelectorRegistry], ObservationBuilder] | None = None,
    raw_recognizer: VisualScreenRecognizer | None = None,
) -> dict[str, object]:
    """Evaluate all manifest samples and return a JSON-ready benchmark document."""

    samples = load_manifest(manifest_path)
    visual = raw_recognizer or load_visual_screen_recognizer()
    baseline_builder: ObservationBuilder | None = None
    guarded_builder: ObservationBuilder | None = None
    if not visual_only:
        registry = build_default_selector_registry()
        factory = builder_factory or _canonical_builder_factory
        guarded_builder = factory(registry)
        baseline_builder = replace(factory(registry), visual_recognizer=None)
        if guarded_builder.visual_recognizer is None:
            raise RuntimeError("canonical observation builder did not provide a visual recognizer")

    records = tuple(
        _evaluate_sample(
            sample,
            visual_recognizer=visual,
            baseline_builder=baseline_builder,
            guarded_builder=guarded_builder,
        )
        for sample in samples
    )
    wrong_actionable = sum(record.wrong_actionable_classification is True for record in records)
    return {
        "version": 1,
        "manifest": str(manifest_path),
        "visual_only": visual_only,
        "frame_count": len(records),
        "wrong_actionable_classification_count": wrong_actionable,
        "splits": aggregate_metrics(records),
        "frames": [record.to_document() for record in records],
    }


def _canonical_builder_factory(selector_registry: SelectorRegistry) -> ObservationBuilder:
    """Build one canonical runtime observation pipeline without account configuration."""

    from pnc_automation.app.entrypoints.app import build_observation_builder

    return build_observation_builder(selector_registry)


def _evaluate_sample(
    sample: BenchmarkSample,
    *,
    visual_recognizer: VisualScreenRecognizer,
    baseline_builder: ObservationBuilder | None,
    guarded_builder: ObservationBuilder | None,
) -> FrameMetrics:
    raw_visual, raw_visual_latency_ms = _timed(
        lambda: visual_recognizer.recognize(sample.image)
    )
    raw_screen_ids = tuple(item.screen_type.value for item in raw_visual.evidence)
    if baseline_builder is None or guarded_builder is None:
        return FrameMetrics(
            image=sample.image_name,
            expected_screen=sample.expected_screen.value,
            split=sample.split,
            group=sample.group,
            baseline_screen=None,
            raw_visual_evidence_screen_ids=raw_screen_ids,
            final_guarded_screen=None,
            blocking_popup=None,
            wrong_actionable_classification=None,
            abstention=None,
            baseline_latency_ms=None,
            raw_visual_latency_ms=raw_visual_latency_ms,
            guarded_latency_ms=None,
        )

    baseline_capture = _captured_screenshot(sample.image)
    baseline_observation, baseline_latency_ms = _timed(
        lambda: baseline_builder.build(baseline_capture)
    )
    guarded_capture = _captured_screenshot(sample.image)
    guarded_observation, guarded_latency_ms = _timed(
        lambda: guarded_builder.build(guarded_capture)
    )
    final_screen = guarded_observation.screen_type.value
    wrong_actionable = (
        final_screen != sample.expected_screen.value
        and final_screen != ScreenType.UNKNOWN.value
    )
    return FrameMetrics(
        image=sample.image_name,
        expected_screen=sample.expected_screen.value,
        split=sample.split,
        group=sample.group,
        baseline_screen=baseline_observation.screen_type.value,
        raw_visual_evidence_screen_ids=raw_screen_ids,
        final_guarded_screen=final_screen,
        blocking_popup=guarded_observation.blocking_popup,
        wrong_actionable_classification=wrong_actionable,
        abstention=final_screen == ScreenType.UNKNOWN.value,
        baseline_latency_ms=baseline_latency_ms,
        raw_visual_latency_ms=raw_visual_latency_ms,
        guarded_latency_ms=guarded_latency_ms,
    )


def _captured_screenshot(image: Image.Image) -> CapturedScreenshot:
    return CapturedScreenshot(
        artifact=None,
        image=image.copy(),
        image_format="PNG",
        ephemeral_captured_at=datetime.now(tz=UTC),
    )


def aggregate_metrics(records: Iterable[FrameMetrics]) -> dict[str, dict[str, object]]:
    """Aggregate counts and timing summaries independently for each manifest split."""

    grouped: defaultdict[str, list[FrameMetrics]] = defaultdict(list)
    for record in records:
        grouped[record.split].append(record)
    return {split: _aggregate_split(grouped[split]) for split in sorted(grouped)}


def _aggregate_split(records: Sequence[FrameMetrics]) -> dict[str, object]:
    def count(predicate: Callable[[FrameMetrics], bool]) -> int:
        return sum(predicate(record) for record in records)

    return {
        "frame_count": len(records),
        "wrong_actionable_classifications": count(
            lambda record: record.wrong_actionable_classification is True
        ),
        "abstentions": count(lambda record: record.abstention is True),
        "blocking_popups": count(lambda record: record.blocking_popup is True),
        "latency_ms": {
            "baseline": _timing_summary(record.baseline_latency_ms for record in records),
            "raw_visual": _timing_summary(record.raw_visual_latency_ms for record in records),
            "guarded": _timing_summary(record.guarded_latency_ms for record in records),
        },
    }


def _timing_summary(values: Iterable[float | None]) -> dict[str, float] | None:
    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None
    return {
        "min": min(numeric_values),
        "median": statistics.median(numeric_values),
        "mean": statistics.mean(numeric_values),
        "max": max(numeric_values),
    }


def _timed(function: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    value = function()
    return value, (time.perf_counter() - started) * 1000.0


def build_recognition_coverage_audit(
    *,
    root: Path = ROOT,
    catalog_path: Path | None = None,
    template_root: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    """Build a deterministic inventory of effective selector recognition coverage.

    The audit reads the canonical catalog and registry, then scans source-level
    Python/YAML references. It deliberately reports missing asset paths and
    unannotated fixture dimensions as unknown dispositions; it does not infer a
    migration strategy from a selector name or from its current geometry.
    """

    audit_root = root.resolve()
    resolved_catalog_path = (catalog_path or _default_catalog_path()).resolve()
    resolved_template_root = (template_root or _default_template_root()).resolve()
    catalog = load_selector_catalog_document(resolved_catalog_path)
    registry = build_default_selector_registry(
        template_root=resolved_template_root,
        catalog_path=resolved_catalog_path,
    )
    selector_ids = frozenset(selector.id for selector in catalog.selectors)
    references = _scan_static_selector_references(audit_root, selector_ids)

    selector_rows: list[dict[str, object]] = []
    status_counts: defaultdict[str, int] = defaultdict(int)
    declared_kind_counts: defaultdict[str, int] = defaultdict(int)
    effective_kind_counts: defaultdict[str, int] = defaultdict(int)
    for catalog_entry in catalog.selectors:
        selector = registry.require(UiElementId[catalog_entry.id])
        declared_kind = catalog_entry.detection_kind
        effective_kind = selector.detection_kind.value
        status = selector.status.value
        selector_references = references.get(catalog_entry.id, ())
        asset_path = selector.template_path
        asset_required = asset_path is not None
        asset_exists = None if asset_path is None else asset_path.is_file()
        if asset_path is None:
            asset_path_text = None
            missing_asset_disposition = "not_required"
        else:
            asset_path_text = _relative_or_absolute_path(asset_path, audit_root)
            missing_asset_disposition = "resolved" if asset_exists else "unknown_intended_disposition"
        geometry = catalog_entry.relative_bounds
        status_counts[status] += 1
        declared_kind_counts[declared_kind] += 1
        effective_kind_counts[effective_kind] += 1
        selector_rows.append(
            {
                "id": catalog_entry.id,
                "screens": list(catalog_entry.screens),
                "interaction_kind": selector.interaction_kind.value,
                "declared_detection_kind": declared_kind,
                "effective_detection_kind": effective_kind,
                "resolver_owner": _RESOLVER_OWNERS.get(effective_kind),
                "resolver_supported": effective_kind in _RESOLVER_OWNERS and effective_kind != DetectionKind.PLANNED.value,
                "status": status,
                "maturity": status,
                "enabled": effective_kind != DetectionKind.PLANNED.value,
                "geometry": {
                    "has_relative_bounds": geometry is not None,
                    "materialize_relative_bounds": catalog_entry.materialize_relative_bounds,
                    "materialized_by_registry": (
                        geometry is not None
                        and catalog_entry.materialize_relative_bounds
                        and effective_kind != DetectionKind.OCR_REGION.value
                    ),
                    "action_point_declared": (
                        geometry is not None
                        and geometry.action_x_ratio is not None
                        and geometry.action_y_ratio is not None
                    ),
                },
                "asset": {
                    "required": asset_required,
                    "path": asset_path_text,
                    "exists": asset_exists,
                    "missing_path_disposition": missing_asset_disposition,
                },
                "catalog": {
                    "defined": True,
                    "click_outcome_count": 0 if catalog_entry.click is None else len(catalog_entry.click.outcomes),
                },
                "static_consumers": _references_document(selector_references),
            }
        )

    enum_ids = {member.name for member in UiElementId}
    catalog_ids = {selector.id for selector in catalog.selectors}
    orphan_rows = [
        {
            "id": selector_id,
            "catalog_defined": False,
            "static_consumers": _references_document(references.get(selector_id, ())),
            "intended_disposition": "unknown_intended_disposition",
        }
        for selector_id in sorted(enum_ids - catalog_ids)
    ]
    fixture_coverage = _build_fixture_coverage(
        manifest_path
        if manifest_path is not None
        else audit_root / "tests" / "data" / "screen_recognition" / "manifest.json",
        root=audit_root,
    )
    summary = {
        "selector_count": len(selector_rows),
        "enum_id_count": len(enum_ids),
        "catalog_defined_enum_count": len(catalog_ids & enum_ids),
        "orphan_enum_id_count": len(orphan_rows),
        "reachable_selector_count": sum(
            any(reference.scope in _REACHABLE_REFERENCE_SCOPES for reference in references.get(row["id"], ()))
            for row in selector_rows
        ),
        "selectors_with_static_references": sum(bool(references.get(row["id"])) for row in selector_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "declared_detection_kind_counts": dict(sorted(declared_kind_counts.items())),
        "effective_detection_kind_counts": dict(sorted(effective_kind_counts.items())),
        "enabled_count": sum(row["enabled"] for row in selector_rows),
        "geometry_defined_count": sum(row["geometry"]["has_relative_bounds"] for row in selector_rows),
        "geometry_materialized_count": sum(row["geometry"]["materialized_by_registry"] for row in selector_rows),
        "action_point_defined_count": sum(row["geometry"]["action_point_declared"] for row in selector_rows),
        "asset_required_count": sum(row["asset"]["required"] for row in selector_rows),
        "asset_present_count": sum(row["asset"]["exists"] is True for row in selector_rows),
        "asset_missing_count": sum(row["asset"]["exists"] is False for row in selector_rows),
        "unknown_missing_asset_disposition_count": sum(
            row["asset"]["missing_path_disposition"] == "unknown_intended_disposition"
            for row in selector_rows
        ),
    }
    return {
        "version": 1,
        "report_type": "non_yolo_recognition_coverage",
        "generated_at_utc": datetime.now(tz=UTC).isoformat(),
        "inputs": {
            "repository_root": _relative_or_absolute_path(audit_root, audit_root),
            "selector_catalog": _relative_or_absolute_path(resolved_catalog_path, audit_root),
            "template_root": _relative_or_absolute_path(resolved_template_root, audit_root),
            "fixture_manifest": _relative_or_absolute_path(
                Path(manifest_path).resolve() if manifest_path is not None else audit_root / "tests" / "data" / "screen_recognition" / "manifest.json",
                audit_root,
            ),
        },
        "criteria": {
            "enabled": "effective detection kind is not planned; this reflects the current registry only",
            "asset_required": "the effective registry has a template_path (template or collection resolver)",
            "missing_path_disposition": "unknown_intended_disposition is retained until a reviewed migration decision exists",
            "consumer_scan": "static Python AST references and non-comment YAML identifier references under runtime, authored, tool, and test source roots",
            "fixture_unknowns": "overlay, control state, layout, target identity, action point containment, and row identity are unknown when absent from the manifest schema",
        },
        "summary": summary,
        "selectors": selector_rows,
        "orphan_enum_ids": orphan_rows,
        "fixture_coverage": fixture_coverage,
        "working_tree_baseline": _capture_worktree_metadata(audit_root),
    }


def _default_catalog_path() -> Path:
    """Return the canonical catalog without importing a second catalog owner."""

    from pnc_automation.app.pnc.vision.selector_catalog import default_selector_catalog_path

    return default_selector_catalog_path()


def _default_template_root() -> Path:
    """Return the canonical template root used by the registry builder."""

    from pnc_automation.app.pnc.vision.selectors import default_selector_template_root

    return default_selector_template_root()


def _relative_or_absolute_path(path: Path, root: Path) -> str:
    """Represent a path relative to the audit root when it is inside it."""

    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved_path)


def _scan_static_selector_references(
    root: Path,
    selector_ids: frozenset[str],
) -> dict[str, tuple[StaticSelectorReference, ...]]:
    """Collect static references while excluding enum and catalog declarations."""

    found: defaultdict[str, list[StaticSelectorReference]] = defaultdict(list)
    for path in _iter_static_reference_files(root):
        relative_path = path.relative_to(root).as_posix()
        if path.name == "ui_element_id.py" or path.name == "selector_registry.yaml":
            continue
        scope = _reference_scope(relative_path)
        if path.suffix == ".py":
            references = _scan_python_references(path, selector_ids, relative_path, scope)
        else:
            references = _scan_yaml_references(path, selector_ids, relative_path, scope)
        for selector_id, reference in references:
            found[selector_id].append(reference)
    return {
        selector_id: tuple(sorted(values, key=lambda value: (value.path, value.line, value.kind)))
        for selector_id, values in found.items()
    }


def _iter_static_reference_files(root: Path) -> Iterable[Path]:
    """Yield supported source/config files in stable order."""

    candidates: list[Path] = []
    for source_root in _STATIC_REFERENCE_ROOTS:
        directory = root / source_root
        if not directory.is_dir():
            continue
        candidates.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and path.suffix.lower() in _STATIC_REFERENCE_SUFFIXES
            and not any(part in _STATIC_REFERENCE_IGNORES for part in path.parts)
        )
    return iter(sorted(set(candidates), key=lambda path: path.relative_to(root).as_posix()))


def _reference_scope(relative_path: str) -> str:
    """Classify a reference by its repository owner."""

    first_segment = Path(relative_path).parts[0]
    return {
        "pnc_automation": "runtime",
        "scripts": "authored",
        "config": "authored",
        "tools": "tool",
        "tests": "test",
    }.get(first_segment, "other")


def _scan_python_references(
    path: Path,
    selector_ids: frozenset[str],
    relative_path: str,
    scope: str,
) -> tuple[tuple[str, StaticSelectorReference], ...]:
    """Extract enum-attribute and literal references from Python source."""

    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return _scan_python_references_fallback(source, selector_ids, relative_path, scope)
    visitor = _SelectorReferenceVisitor(selector_ids, relative_path, scope)
    visitor.visit(tree)
    return tuple(visitor.references)


class _SelectorReferenceVisitor(ast.NodeVisitor):
    """AST visitor used by the coverage audit's static consumer inventory."""

    def __init__(self, selector_ids: frozenset[str], relative_path: str, scope: str) -> None:
        self.selector_ids = selector_ids
        self.relative_path = relative_path
        self.scope = scope
        self.references: list[tuple[str, StaticSelectorReference]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "UiElementId"
            and node.attr in self.selector_ids
        ):
            self.references.append(
                (
                    node.attr,
                    StaticSelectorReference(self.relative_path, node.lineno, "enum_attribute", self.scope),
                )
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and node.value in self.selector_ids:
            self.references.append(
                (
                    node.value,
                    StaticSelectorReference(self.relative_path, node.lineno, "string_literal", self.scope),
                )
            )


def _scan_python_references_fallback(
    source: str,
    selector_ids: frozenset[str],
    relative_path: str,
    scope: str,
) -> tuple[tuple[str, StaticSelectorReference], ...]:
    """Use a conservative line scanner when a source file cannot be parsed."""

    references: list[tuple[str, StaticSelectorReference]] = []
    pattern = re.compile(r"UiElementId\.(?P<enum>[A-Z][A-Z0-9_]+)|[\"'](?P<literal>PNC_[A-Z0-9_]+)[\"']")
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in pattern.finditer(line):
            selector_id = match.group("enum") or match.group("literal")
            if selector_id in selector_ids:
                kind = "enum_attribute" if match.group("enum") else "string_literal"
                references.append((selector_id, StaticSelectorReference(relative_path, line_number, kind, scope)))
    return tuple(references)


def _scan_yaml_references(
    path: Path,
    selector_ids: frozenset[str],
    relative_path: str,
    scope: str,
) -> tuple[tuple[str, StaticSelectorReference], ...]:
    """Extract identifier values from YAML without trusting arbitrary loaded objects."""

    pattern = re.compile(r"(?<![A-Z0-9_])(?P<selector>PNC_[A-Z0-9_]+)(?![A-Z0-9_])")
    references: list[tuple[str, StaticSelectorReference]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for match in pattern.finditer(line):
            selector_id = match.group("selector")
            if selector_id in selector_ids:
                references.append(
                    (
                        selector_id,
                        StaticSelectorReference(relative_path, line_number, "yaml_reference", scope),
                    )
                )
    return tuple(references)


def _references_document(references: Sequence[StaticSelectorReference]) -> dict[str, object]:
    """Serialize references while keeping source content out of reports."""

    counts: defaultdict[str, int] = defaultdict(int)
    for reference in references:
        counts[reference.scope] += 1
    return {
        "count": len(references),
        "by_scope": dict(sorted(counts.items())),
        "reachable_count": sum(reference.scope in _REACHABLE_REFERENCE_SCOPES for reference in references),
        "references": [reference.to_document() for reference in references],
    }


def _build_fixture_coverage(path: Path, *, root: Path) -> dict[str, object]:
    """Summarize manifest evidence and name dimensions it does not annotate."""

    if not path.is_file():
        return {
            "status": "not_available",
            "path": _relative_or_absolute_path(path, root),
            "reason": "manifest_not_found",
            "unknown_disposition": "not_annotated",
        }
    samples = load_manifest(path)
    by_screen: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    split_counts: defaultdict[str, int] = defaultdict(int)
    groups: set[str] = set()
    for sample in samples:
        split_counts[sample.split] += 1
        groups.add(sample.group)
        by_screen[sample.expected_screen.value].append(
            {"image": sample.image_name, "split": sample.split, "group": sample.group}
        )
    return {
        "status": "available",
        "path": _relative_or_absolute_path(path, root),
        "sample_count": len(samples),
        "split_counts": dict(sorted(split_counts.items())),
        "independent_source_groups": sorted(groups),
        "expected_screens": {
            screen: sorted(values, key=lambda value: (value["split"], value["image"]))
            for screen, values in sorted(by_screen.items())
        },
        "supported_target_layout_cells": {
            "status": "unknown",
            "unknown_disposition": "not_annotated_in_manifest",
        },
        "unannotated_dimensions": [
            "overlay",
            "control_state",
            "layout",
            "target_identity",
            "action_point_containment",
            "row_identity",
        ],
        "unknown_disposition": "not_annotated_in_manifest",
    }


def _capture_worktree_metadata(root: Path) -> dict[str, object]:
    """Capture hashes and diff metadata without copying source contents into the report."""

    def git_output(*arguments: str) -> bytes | None:
        try:
            return subprocess.run(
                ("git", *arguments),
                cwd=root,
                check=True,
                capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            return None

    status_bytes = git_output("status", "--porcelain=v1", "--untracked-files=all")
    diff_bytes = git_output("diff", "--binary")
    staged_diff_bytes = git_output("diff", "--cached", "--binary")
    head_bytes = git_output("rev-parse", "HEAD")
    branch_bytes = git_output("branch", "--show-current")
    if status_bytes is None:
        return {"status": "unavailable", "reason": "git_metadata_unavailable"}
    status_lines = status_bytes.decode("utf-8", errors="replace").splitlines()
    paths: dict[str, str | None] = {}
    for line in status_lines:
        if len(line) < 4:
            continue
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.rsplit(" -> ", 1)[-1]
        relative_path = raw_path.replace("\\", "/")
        candidate = (root / relative_path).resolve()
        paths[relative_path] = (
            hashlib.sha256(candidate.read_bytes()).hexdigest()
            if candidate.is_file()
            else None
        )
    return {
        "status": "captured",
        "captured_at_utc": datetime.now(tz=UTC).isoformat(),
        "head_commit": None if head_bytes is None else head_bytes.decode().strip(),
        "branch": None if branch_bytes is None else branch_bytes.decode().strip(),
        "status_sha256": hashlib.sha256(status_bytes).hexdigest(),
        "unstaged_diff_sha256": None if diff_bytes is None else hashlib.sha256(diff_bytes).hexdigest(),
        "staged_diff_sha256": None if staged_diff_bytes is None else hashlib.sha256(staged_diff_bytes).hexdigest(),
        "changed_file_count": len(paths),
        "changed_file_sha256": dict(sorted(paths.items())),
        "note": "Snapshot captured at audit generation so later slices can compare all changes present before subsequent slices.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark CLI and return its process exit code."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--coverage-audit",
        action="store_true",
        help="Write the deterministic selector/consumer/assets coverage inventory instead of a frame benchmark.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root scanned for static selector consumers.",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="Optional selector catalog path for --coverage-audit.",
    )
    parser.add_argument(
        "--template-root",
        type=Path,
        default=None,
        help="Optional selector template root for --coverage-audit.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "tests" / "data" / "screen_recognition" / "manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--visual-only",
        action="store_true",
        help="Run only raw visual evidence matching without OCR-backed observation builders.",
    )
    arguments = parser.parse_args(argv)
    if arguments.coverage_audit:
        document = build_recognition_coverage_audit(
            root=arguments.root,
            catalog_path=arguments.catalog,
            template_root=arguments.template_root,
            manifest_path=arguments.manifest,
        )
        output_path = arguments.output or arguments.root / "artifacts" / "non_yolo_recognition" / "coverage_audit.json"
    else:
        document = benchmark_manifest(arguments.manifest, visual_only=arguments.visual_only)
        output_path = arguments.output or ROOT / "artifacts" / "screen_recognition" / "benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 1 if document.get("wrong_actionable_classification_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
