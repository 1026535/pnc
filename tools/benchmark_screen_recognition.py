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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, UnidentifiedImageError

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ROOT = ensure_repo_root_on_path()

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_catalog import load_selector_catalog_document
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorRegistry,
    build_default_selector_registry,
)
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition

if TYPE_CHECKING:
    from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualScreenRecognizer


_MANIFEST_VERSION = 2
_HASH_FORMAT = "sha256(width.to_bytes(8, 'big') + height.to_bytes(8, 'big') + decoded RGB bytes)"
_REQUIRED_SPLITS = frozenset({"reference", "validation", "holdout"})
_REQUIRED_SAMPLE_FIELDS = frozenset({"image", "screen", "split", "group", "sha256"})
_OPTIONAL_SAMPLE_FIELDS = frozenset({"expected_visual_screens"})
_HEX_DIGITS = frozenset("0123456789abcdef")
_STATIC_REFERENCE_SUFFIXES = frozenset({".py", ".yaml", ".yml"})
_STATIC_REFERENCE_ROOTS = ("pnc_automation", "scripts", "config", "tools", "tests")
_STATIC_REFERENCE_IGNORES = frozenset({"__pycache__", ".git", ".mypy_cache", ".pytest_cache"})
_REACHABLE_REFERENCE_SCOPES = frozenset({"runtime", "authored", "tool"})
_RESOLVER_OWNERS = {
    DetectionKind.TEMPLATE.value: "ImageSelectorEngine.template_matcher",
    DetectionKind.GUARDED_GEOMETRY.value: "SelectorRegistry.materialize_for_screen",
    DetectionKind.OCR_REGION.value: "ImageSelectorEngine.ocr_region",
    DetectionKind.SEMANTIC.value: "ObservationBuilder.semantic_enricher",
    DetectionKind.UNSUPPORTED.value: None,
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
    expected_visual_screens: tuple[ScreenType, ...] = ()


@dataclass(frozen=True, slots=True)
class WarmReplayMetrics:
    """Measured stages for one optional warm canonical-pipeline replay."""

    total_latency_ms: float
    visual_latency_ms: float | None
    content_latency_ms: float | None
    guard_latency_ms: float | None
    ocr_metrics: Mapping[str, int | float] | None = None
    ocr_diagnostics: tuple[Mapping[str, object], ...] = ()
    fallback_reasons: tuple[str, ...] | None = None

    def to_document(self) -> dict[str, object]:
        """Return only measurements observed by the benchmark adapters."""

        return {
            "latency_ms": {
                "total": self.total_latency_ms,
                "visual": self.visual_latency_ms,
                "content": self.content_latency_ms,
                "guard": self.guard_latency_ms,
            },
            "ocr": None if self.ocr_metrics is None else dict(self.ocr_metrics),
            "ocr_diagnostics": [dict(item) for item in self.ocr_diagnostics],
            "fallback_reasons": (
                None if self.fallback_reasons is None else list(self.fallback_reasons)
            ),
        }


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
    baseline_targets: tuple[dict[str, object], ...] = ()
    baseline_facts: Mapping[str, object] = field(default_factory=dict)
    guarded_targets: tuple[dict[str, object], ...] = ()
    guarded_facts: Mapping[str, object] = field(default_factory=dict)
    warm_replays: tuple[WarmReplayMetrics, ...] = ()
    manual_annotation: Mapping[str, object] | None = None

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
            "guarded_decision": {
                "screen": self.final_guarded_screen,
                "blocking_popup": self.blocking_popup,
                "wrong_actionable_classification": self.wrong_actionable_classification,
                "abstention": self.abstention,
            },
            "returned_targets": list(self.guarded_targets),
            "returned_facts": dict(self.guarded_facts),
            "baseline_label": "same revision without visual recognizer",
            "baseline_returned_targets": list(self.baseline_targets),
            "baseline_returned_facts": dict(self.baseline_facts),
            "warm_replays": [replay.to_document() for replay in self.warm_replays],
            "manual_annotation": (
                None if self.manual_annotation is None else dict(self.manual_annotation)
            ),
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
    if not isinstance(raw_sample, dict) or not _REQUIRED_SAMPLE_FIELDS.issubset(raw_sample) or (
        set(raw_sample) - _REQUIRED_SAMPLE_FIELDS
    ) - _OPTIONAL_SAMPLE_FIELDS:
        raise ValueError(
            f"manifest sample {index} must contain exactly image, screen, split, group, and sha256 "
            "plus optional expected_visual_screens"
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

    raw_visual_screens = raw_sample.get("expected_visual_screens")
    if raw_visual_screens is None:
        raw_visual_screens = []
    if not isinstance(raw_visual_screens, list) or any(
        not isinstance(screen, str) for screen in raw_visual_screens
    ):
        raise ValueError(f"manifest sample {index} expected_visual_screens must be a list of screen names")
    expected_visual_screens: list[ScreenType] = []
    for visual_screen in raw_visual_screens:
        try:
            expected_visual_screens.append(ScreenType[visual_screen])
        except KeyError:
            try:
                expected_visual_screens.append(ScreenType(visual_screen))
            except ValueError as error:
                raise ValueError(
                    f"manifest sample {index} has unknown expected visual screen: {visual_screen}"
                ) from error

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
    if decoded_sha256 != expected_sha256:
        raise ValueError(
            f"manifest sample {index} decoded sha256 does not match image: {image_name}"
        )
    return BenchmarkSample(
        image_name=image_name,
        path=sample_path,
        expected_screen=expected_screen,
        split=split,
        group=group,
        sha256=expected_sha256,
        decoded_sha256=decoded_sha256,
        image=image,
        expected_visual_screens=tuple(expected_visual_screens),
    )


def _decoded_image_sha256(image: Image.Image) -> str:
    """Hash ``width || height || RGB`` after decoding the image.

    Width and height are each encoded as unsigned eight-byte big-endian values,
    followed by the decoded RGB bytes. This makes the manifest independent of
    PNG compression while keeping differently sized images distinct.
    """

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
    warm_replays: int = 0,
    measurement_profile: str = "pre_d",
) -> dict[str, object]:
    """Evaluate reviewed samples and optionally replay each through the builder.

    ``warm_replays`` is zero by default so correctness and coverage runs remain
    quick. When enabled it must be at least five, matching the plan's warm
    measurement gate; replay timings are emitted only for canonical builder
    runs, never synthesized from a single total duration.
    """

    if not isinstance(warm_replays, int) or isinstance(warm_replays, bool) or warm_replays < 0:
        raise ValueError("warm_replays must be zero or a positive integer")
    if warm_replays not in {0} and warm_replays < 5:
        raise ValueError("warm_replays must be zero or at least five")
    if measurement_profile not in {"pre_d", "post_d"}:
        raise ValueError("measurement_profile must be pre_d or post_d")

    samples = load_manifest(manifest_path)
    visual = raw_recognizer or _load_visual_screen_recognizer()
    manual_annotations = _load_manual_annotations(manifest_path)
    baseline_builder: ObservationBuilder | None = None
    guarded_builder: ObservationBuilder | None = None
    if not visual_only:
        registry = build_default_selector_registry()
        factory = builder_factory or _canonical_builder_factory
        guarded_builder = factory(registry)
        baseline_builder = _without_visual_recognizer(factory(registry))
        if getattr(guarded_builder, "visual_recognizer", None) is None:
            raise RuntimeError("canonical observation builder did not provide a visual recognizer")
        guarded_builder, guarded_probe = _instrument_builder(guarded_builder)
    else:
        guarded_probe = None

    records = tuple(
        _evaluate_sample(
            sample,
            visual_recognizer=visual,
            baseline_builder=baseline_builder,
            guarded_builder=guarded_builder,
            warm_replays=warm_replays,
            manual_annotation=manual_annotations.get(sample.image_name),
            guarded_probe=guarded_probe,
        )
        for sample in samples
    )
    wrong_actionable = sum(record.wrong_actionable_classification is True for record in records)
    manual_comparison_failures = sum(
        len(
            tuple(
                (record.manual_annotation or {}).get("comparison_failures", ())
            )
        )
        for record in records
    )
    baseline_recovery_regressions = sum(
        int(
            ((record.manual_annotation or {}).get("baseline_recovery") or {}).get(
                "lost_previously_correct_count",
                0,
            )
        )
        for record in records
    )
    return {
        "version": 2,
        "manifest": str(manifest_path),
        "manifest_version": _MANIFEST_VERSION,
        "manifest_hash_format": _HASH_FORMAT,
        "visual_only": visual_only,
        "measurement_profile": measurement_profile,
        "baseline_label": "same revision without visual recognizer",
        "warm_replays": warm_replays,
        "frame_count": len(records),
        "wrong_actionable_classification_count": wrong_actionable,
        "manual_comparison_failure_count": manual_comparison_failures,
        "baseline_recovery_regression_count": baseline_recovery_regressions,
        "splits": aggregate_metrics(records),
        "frames": [record.to_document() for record in records],
    }


def _canonical_builder_factory(selector_registry: SelectorRegistry) -> ObservationBuilder:
    """Build one canonical runtime observation pipeline without account configuration."""

    from pnc_automation.app.entrypoints.app import build_observation_builder

    return build_observation_builder(selector_registry)


def _without_visual_recognizer(builder: ObservationBuilder) -> ObservationBuilder:
    """Keep the legacy OCR-only comparison when the builder exposes that seam."""

    if not hasattr(builder, "visual_recognizer"):
        return builder
    return replace(builder, visual_recognizer=None)


def _load_visual_screen_recognizer() -> Any:
    """Load the optional global visual recognizer only when a frame benchmark runs."""

    from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer

    return load_visual_screen_recognizer()


def _evaluate_sample(
    sample: BenchmarkSample,
    *,
    visual_recognizer: VisualScreenRecognizer,
    baseline_builder: ObservationBuilder | None,
    guarded_builder: ObservationBuilder | None,
    warm_replays: int = 0,
    manual_annotation: Mapping[str, object] | None = None,
    guarded_probe: "_StageProbe | None" = None,
) -> FrameMetrics:
    first_run = _run_pipeline(
        sample.image,
        visual_recognizer=visual_recognizer,
        baseline_builder=baseline_builder,
        guarded_builder=guarded_builder,
    )
    raw_visual = first_run.raw_visual
    raw_visual_latency_ms = first_run.metrics.visual_latency_ms
    raw_screen_ids = tuple(item.screen_type.value for item in raw_visual.evidence)
    if baseline_builder is None or guarded_builder is None:
        manual_summary = _manual_annotation_summary(manual_annotation)
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
            manual_annotation=manual_summary,
        )

    baseline_observation = first_run.baseline_observation
    guarded_observation = first_run.guarded_observation
    assert baseline_observation is not None
    assert guarded_observation is not None
    baseline_latency_ms = first_run.metrics.content_latency_ms
    guarded_latency_ms = first_run.metrics.guard_latency_ms
    final_screen = guarded_observation.screen_type.value
    wrong_actionable = (
        final_screen != sample.expected_screen.value
        and final_screen != ScreenType.UNKNOWN.value
    )
    baseline_targets = _observation_targets(baseline_observation)
    guarded_targets = _observation_targets(guarded_observation)
    baseline_facts = _observation_facts(baseline_observation)
    guarded_facts = _observation_facts(guarded_observation)
    manual_summary = _manual_annotation_summary(manual_annotation)
    if manual_summary is not None:
        manual_summary = dict(manual_summary)
        guarded_comparisons = _manual_comparisons(
            manual_summary,
            guarded_observation,
            guarded_targets,
        )
        manual_summary["guarded_comparisons"] = guarded_comparisons
        baseline_comparisons = _manual_comparisons(
            manual_summary,
            baseline_observation,
            baseline_targets,
        )
        manual_summary["baseline_comparisons"] = baseline_comparisons
        manual_summary["baseline_recovery"] = _compare_baseline_recovery(
            baseline_comparisons,
            guarded_comparisons,
        )
        manual_summary["baseline_comparison_label"] = "same revision without visual recognizer"
        manual_summary["promotion_disposition"] = manual_summary["baseline_recovery"][
            "promotion_disposition"
        ]
        manual_summary["comparison_failures"] = _manual_comparison_failures(guarded_comparisons)
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
        baseline_targets=baseline_targets,
        baseline_facts=baseline_facts,
        guarded_targets=guarded_targets,
        guarded_facts=guarded_facts,
        warm_replays=tuple(
            _run_warm_replay(
                sample.image,
                guarded_builder=guarded_builder,
                probe=guarded_probe,
            ).metrics
            for _ in range(warm_replays)
        ),
        manual_annotation=manual_summary,
    )


@dataclass(frozen=True, slots=True)
class _PipelineRun:
    """One measured visual, content, and guard pass used by the benchmark only."""

    raw_visual: VisualRecognition | None
    baseline_observation: Observation | None
    guarded_observation: Observation | None
    metrics: WarmReplayMetrics


@dataclass(slots=True)
class _StageProbe:
    """Small benchmark-only stage accumulator for the existing builder seams."""

    visual_seconds: float = 0.0
    guard_seconds: float = 0.0
    content_seconds: float = 0.0
    visual_calls: int = 0
    guard_calls: int = 0
    content_calls: int = 0

    def reset(self) -> None:
        self.visual_seconds = 0.0
        self.guard_seconds = 0.0
        self.content_seconds = 0.0
        self.visual_calls = 0
        self.guard_calls = 0
        self.content_calls = 0


class _TimedVisualRecognizer:
    """Delegate visual recognition while measuring the canonical call."""

    def __init__(self, inner: Any, probe: _StageProbe) -> None:
        self._inner = inner
        self._probe = probe

    def recognize(self, image: Image.Image) -> Any:
        value, elapsed = _timed(lambda: self._inner.recognize(image))
        self._probe.visual_seconds += elapsed / 1000.0
        self._probe.visual_calls += 1
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _TimedEnricher:
    """Delegate guard/content enrichment while measuring existing methods."""

    def __init__(self, inner: Any, probe: _StageProbe) -> None:
        self._inner = inner
        self._probe = probe

    def recognize_guards(
        self,
        image: Image.Image,
        request: Any,
        *,
        ocr_context: ObservationOcrContext,
    ) -> Any:
        value, elapsed = _timed(
            lambda: self._inner.recognize_guards(
                image,
                request,
                ocr_context=ocr_context,
            )
        )
        self._probe.guard_seconds += elapsed / 1000.0
        self._probe.guard_calls += 1
        return value

    def enrich(
        self,
        image: Image.Image,
        screen_type: Any,
        visible_elements: Any,
        request: Any,
        *,
        ocr_context: ObservationOcrContext,
        ocr_regions: Mapping[Any, Any],
    ) -> Any:
        value, elapsed = _timed(
            lambda: self._inner.enrich(
                image,
                screen_type,
                visible_elements,
                request,
                ocr_context=ocr_context,
                ocr_regions=ocr_regions,
            )
        )
        self._probe.content_seconds += elapsed / 1000.0
        self._probe.content_calls += 1
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _instrument_builder(builder: ObservationBuilder) -> tuple[ObservationBuilder, _StageProbe | None]:
    """Clone a builder with narrow timing delegates when its canonical seams exist."""

    probe = _StageProbe()
    changes: dict[str, object] = {}
    visual = getattr(builder, "visual_recognizer", None)
    if visual is not None:
        changes["visual_recognizer"] = _TimedVisualRecognizer(visual, probe)
    enricher = getattr(builder, "enricher", None)
    if enricher is not None and hasattr(enricher, "enrich"):
        changes["enricher"] = _TimedEnricher(enricher, probe)
    if not changes or not is_dataclass(builder):
        return builder, None
    try:
        return replace(builder, **changes), probe
    except (TypeError, ValueError):
        # Fakes and older builders without these constructor fields still get
        # honest total timing; unavailable stage durations remain null.
        return builder, None


def _run_warm_replay(
    image: Image.Image,
    *,
    guarded_builder: ObservationBuilder,
    probe: _StageProbe | None,
) -> _PipelineRun:
    """Run one warm replay through the guarded canonical builder only."""

    if probe is not None:
        probe.reset()
    capture = _captured_screenshot(image.copy())
    ocr_context = guarded_builder.create_ocr_context(capture)
    before = _ocr_context_snapshot(ocr_context)
    observation, total_latency_ms = _timed(
        lambda: guarded_builder.build(capture, ocr_context=ocr_context)
    )
    after = _ocr_context_snapshot(ocr_context)
    if probe is None:
        visual_latency_ms = None
        content_latency_ms = None
        guard_latency_ms = None
    else:
        visual_latency_ms = probe.visual_seconds * 1000.0 if probe.visual_calls else None
        content_latency_ms = probe.content_seconds * 1000.0 if probe.content_calls else None
        guard_latency_ms = probe.guard_seconds * 1000.0 if probe.guard_calls else None
    metrics = WarmReplayMetrics(
        total_latency_ms=total_latency_ms,
        visual_latency_ms=visual_latency_ms,
        content_latency_ms=content_latency_ms,
        guard_latency_ms=guard_latency_ms,
        ocr_metrics=_delta_ocr_metrics(before, after),
        ocr_diagnostics=_serialize_ocr_diagnostics(ocr_context),
        fallback_reasons=_ocr_fallback_reasons(ocr_context),
    )
    return _PipelineRun(
        raw_visual=None,
        baseline_observation=None,
        guarded_observation=observation,
        metrics=metrics,
    )


def _delta_ocr_metrics(
    before: Mapping[str, int | float] | None,
    after: Mapping[str, int | float] | None,
) -> dict[str, int | float] | None:
    """Return deltas from the explicit raw OCR/cache probe for one replay."""

    if before is None or after is None:
        return None
    delta: dict[str, int | float] = {}
    for key in set(before) & set(after):
        value = after[key] - before[key]
        if value >= 0:
            delta[key] = value
    return delta if any(value != 0 for value in delta.values()) else None


def _ocr_context_snapshot(context: ObservationOcrContext) -> dict[str, int | float]:
    """Read benchmark counters from the explicit context bound to one capture."""

    metrics = context.metrics
    return {
        "requests": metrics.requests,
        "engine_calls": metrics.engine_calls,
        "processed_pixel_area": metrics.processed_pixel_area,
        "cache_hits": metrics.cache_hits,
        "fullframe_reuses": metrics.fullframe_reuses,
        "engine_seconds": metrics.engine_seconds,
    }


def _serialize_ocr_diagnostics(
    context: ObservationOcrContext,
) -> tuple[Mapping[str, object], ...]:
    """Return explicit per-read owners and outcomes for one measured capture."""

    diagnostics: list[Mapping[str, object]] = []
    for item in context.read_diagnostics:
        region = None
        if item.region is not None:
            region = [item.region.x, item.region.y, item.region.width, item.region.height]
        diagnostics.append(
            {
                "purpose": item.purpose.value,
                "status": item.status.value,
                "region": region,
                "detail": item.detail,
            }
        )
    return tuple(diagnostics)


def _ocr_fallback_reasons(context: ObservationOcrContext) -> tuple[str, ...] | None:
    """Return only fallback labels emitted by actual configured OCR-region reads."""

    reasons = {
        item.detail.split(";fallback=", 1)[1]
        for item in context.read_diagnostics
        if item.detail is not None and ";fallback=" in item.detail
    }
    return tuple(sorted(reasons)) or None


def _observation_targets(observation: Observation) -> tuple[dict[str, object], ...]:
    """Serialize returned selector targets without using manual boxes as labels."""

    targets: list[dict[str, object]] = []
    for selector_id, element in sorted(
        observation.visible_elements.items(),
        key=lambda item: item[0].value,
    ):
        bounds = element.bounds
        bounds_document = None
        if bounds is not None:
            bounds_document = [bounds.x, bounds.y, bounds.width, bounds.height]
        # TapAction uses the declared point or the center of the visible bounds.
        # A missing override is not an abstention when dispatch has this target.
        action_point = element.action_point if element.action_point is not None else bounds.center()
        targets.append(
            {
                "id": selector_id.value,
                "bounds": bounds_document,
                "action_point": None if action_point is None else list(action_point),
                "source": element.source_kind.value,
            }
        )
    return tuple(targets)


def _observation_facts(observation: Observation) -> dict[str, object]:
    """Serialize returned typed facts with text and secrets omitted."""

    entries = observation.list_entries
    kind_counts: defaultdict[str, int] = defaultdict(int)
    for entry in entries:
        kind_counts[entry.kind.value] += 1
    spatial = observation.spatial_surface
    return {
        "list_entry_count": len(entries),
        "list_entry_kinds": dict(sorted(kind_counts.items())),
        "spatial_surface": (
            None
            if spatial is None
            else spatial.surface_type.value
        ),
        "current_castle_present": observation.current_castle is not None,
        "current_account_present": observation.current_pnc_account_id is not None,
        "available_march_slots": observation.available_march_slots,
        "mailbox_empty": observation.mailbox_empty,
        "text_field_count": len(observation.text_field_states),
    }


def _load_manual_annotations(manifest_path: Path) -> dict[str, Mapping[str, object]]:
    """Load sidecar labels for independent reporting; never feed them to recognition."""

    path = manifest_path.with_name("manual_annotations.json")
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"manual annotation sidecar could not be decoded: {path}") from error
    raw_samples = document.get("samples") if isinstance(document, dict) else None
    if not isinstance(raw_samples, list):
        raise ValueError("manual annotation sidecar samples must be a list")
    annotations: dict[str, Mapping[str, object]] = {}
    for index, raw_sample in enumerate(raw_samples):
        if not isinstance(raw_sample, dict) or not isinstance(raw_sample.get("image"), str):
            raise ValueError(f"manual annotation sample {index} must identify an image")
        image_name = raw_sample["image"]
        if image_name in annotations:
            raise ValueError(f"manual annotation repeats image: {image_name}")
        annotations[image_name] = raw_sample
    return annotations


def _manual_annotation_summary(annotation: Mapping[str, object] | None) -> Mapping[str, object] | None:
    """Retain independent control/row labels beside, never inside, runtime output."""

    if annotation is None:
        return None
    boxes = annotation.get("boxes")
    rows = annotation.get("rows")
    return {
        "screen": annotation.get("screen"),
        "state": annotation.get("state"),
        "group": annotation.get("group"),
        "source_artifact": annotation.get("source_artifact"),
        "historical_only": annotation.get("historical_only"),
        "controls": boxes if isinstance(boxes, dict) else {},
        "control_selector_ids": (
            annotation.get("control_selector_ids")
            if isinstance(annotation.get("control_selector_ids"), dict)
            else {}
        ),
        "forbidden_background": (
            annotation.get("forbidden_background")
            if isinstance(annotation.get("forbidden_background"), list)
            else []
        ),
        "rows": rows if isinstance(rows, list) else [],
        "expected_daily_rows": annotation.get("expected_daily_rows"),
        "comparison_policy": "manual controls and rows remain independent labels; runtime targets are reported separately",
    }


def _manual_comparisons(
    manual_summary: Mapping[str, object],
    observation: Observation,
    targets: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Evaluate one observation against the independent manual labels."""

    return {
        "action_point_containment": _compare_action_points(manual_summary, targets),
        "row_comparisons": _compare_manual_rows(manual_summary, observation),
        "state_comparison": _compare_manual_state(manual_summary, observation),
        "forbidden_background_comparison": _compare_forbidden_background(
            manual_summary,
            observation,
        ),
        "expected_daily_rows_comparison": _compare_expected_daily_rows(
            manual_summary,
            observation,
        ),
    }


def _comparison_items(comparisons: Mapping[str, object]) -> tuple[dict[str, str], ...]:
    """Flatten independently reviewed controls, rows, and state into comparable facts."""

    items: list[dict[str, str]] = []
    action_points = comparisons.get("action_point_containment")
    if isinstance(action_points, list):
        for item in action_points:
            if isinstance(item, Mapping):
                label = str(item.get("annotation_control", item.get("selector_id", "control")))
                items.append({"key": f"control:{label}", "status": str(item.get("status", "error"))})
    rows = comparisons.get("row_comparisons")
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, Mapping):
                identity = str(item.get("identity", item.get("index", "row")))
                items.append({"key": f"row:{identity}", "status": str(item.get("status", "error"))})
                action_status = item.get("action_control_status")
                if action_status is not None:
                    items.append({"key": f"row:{identity}:action", "status": str(action_status)})
    state = comparisons.get("state_comparison")
    if isinstance(state, Mapping) and state.get("status") != "not_annotated":
        items.append({"key": "state", "status": str(state.get("status", "error"))})
    daily_rows = comparisons.get("expected_daily_rows_comparison")
    if (
        isinstance(daily_rows, Mapping)
        and daily_rows.get("status") != "not_annotated"
        and isinstance(daily_rows.get("expected_complete"), int)
        and not isinstance(daily_rows.get("expected_complete"), bool)
        and daily_rows["expected_complete"] > 0
    ):
        items.append({"key": "daily_rows", "status": str(daily_rows.get("status", "error"))})
    forbidden = comparisons.get("forbidden_background_comparison")
    if isinstance(forbidden, Mapping) and forbidden.get("status") != "not_annotated":
        items.append({"key": "forbidden_background", "status": str(forbidden.get("status", "error"))})
    return tuple(items)


def _compare_baseline_recovery(
    baseline_comparisons: Mapping[str, object],
    guarded_comparisons: Mapping[str, object],
) -> dict[str, object]:
    """Classify guarded facts relative to the same-revision OCR-only baseline.

    A recovery is credited only when the baseline was explicitly missing or
    abstaining. Guard and forbidden-background checks are excluded from the
    positive-content qualification count. A baseline wrong fact is reported
    separately, so a newly found guarded fact cannot be presented as recovery
    from an already-wrong result.
    """

    baseline = {
        item["key"]: item["status"]
        for item in _comparison_items(baseline_comparisons)
        if not item["key"].startswith(("state", "forbidden_background"))
    }
    guarded = {
        item["key"]: item["status"]
        for item in _comparison_items(guarded_comparisons)
        if not item["key"].startswith(("state", "forbidden_background"))
    }
    missing_or_abstain = {"missing", "ambiguous", "abstain", "missing_action_point"}
    unsafe = {"wrong_facts", "wrong_state", "wrong_count", "outside", "click_through"}
    rows: list[dict[str, str]] = []
    for key in sorted(set(baseline) | set(guarded)):
        baseline_status = baseline.get(key, "not_evaluated")
        guarded_status = guarded.get(key, "not_evaluated")
        if baseline_status in missing_or_abstain and guarded_status == "found":
            disposition = "recovered"
        elif baseline_status == "found" and guarded_status != "found":
            disposition = "lost_previously_correct"
        elif guarded_status in unsafe:
            disposition = "error"
        elif baseline_status not in {"found", *missing_or_abstain}:
            disposition = "baseline_wrong"
        elif guarded_status in missing_or_abstain:
            disposition = "missing_or_abstain"
        else:
            disposition = "unchanged"
        rows.append(
            {
                "key": key,
                "baseline_status": baseline_status,
                "guarded_status": guarded_status,
                "disposition": disposition,
            }
        )
    recovery_count = sum(item["disposition"] == "recovered" for item in rows)
    lost_count = sum(item["disposition"] == "lost_previously_correct" for item in rows)
    error_count = sum(item["guarded_status"] in unsafe for item in rows)
    missing_count = sum(item["disposition"] == "missing_or_abstain" for item in rows)
    if not rows or (
        recovery_count == 0
        and all(item["guarded_status"] in missing_or_abstain for item in rows)
    ):
        promotion_disposition = "not qualified"
    elif lost_count or error_count:
        promotion_disposition = "unsafe"
    else:
        promotion_disposition = "review"
    return {
        "facts": rows,
        "expected_count": len(rows),
        "baseline_correct_count": sum(item["baseline_status"] == "found" for item in rows),
        "guarded_correct_count": sum(item["guarded_status"] == "found" for item in rows),
        "recovery_count": recovery_count,
        "newly_recovered_count": recovery_count,
        "missing_or_abstain_count": missing_count,
        "error_count": error_count,
        "lost_previously_correct_count": lost_count,
        "promotion_disposition": promotion_disposition,
    }


def _compare_action_points(
    manual_summary: Mapping[str, object],
    targets: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Compare emitted action points with independently reviewed control boxes."""

    controls = manual_summary.get("controls")
    if not isinstance(controls, Mapping):
        return []
    selector_ids = manual_summary.get("control_selector_ids")
    if not isinstance(selector_ids, Mapping):
        selector_ids = {}
    comparisons: list[dict[str, object]] = []
    targets_by_id = {str(target.get("id", "")): target for target in targets}
    for label, bounds in controls.items():
        label_text = str(label)
        selector_id = selector_ids.get(label_text)
        base = {
            "annotation_control": label_text,
            "selector_id": selector_id,
        }
        if not isinstance(selector_id, str) or not selector_id:
            comparisons.append({**base, "status": "unmapped_selector_id"})
            continue
        if not isinstance(bounds, list) or len(bounds) != 4 or not all(isinstance(value, int) for value in bounds):
            comparisons.append({**base, "status": "invalid_annotation_bounds"})
            continue
        target = targets_by_id.get(selector_id)
        if target is None:
            comparisons.append({**base, "status": "missing"})
            continue
        action_point = target.get("action_point")
        if not isinstance(action_point, list) or len(action_point) != 2:
            comparisons.append({**base, "status": "missing_action_point"})
            continue
        x, y = action_point
        left, top, width, height = bounds
        comparisons.append(
            {
                **base,
                "action_point": list(action_point),
                "status": "found" if left <= x < left + width and top <= y < top + height else "outside",
                "contained": left <= x < left + width and top <= y < top + height,
            }
        )
    return comparisons


def _compare_manual_rows(
    manual_summary: Mapping[str, object],
    observation: Observation,
) -> list[dict[str, object]]:
    """Compare independently authored row facts to typed runtime entries."""

    expected_rows = manual_summary.get("rows")
    if not isinstance(expected_rows, list):
        return []
    actual_rows = tuple(observation.list_entries)
    comparisons: list[dict[str, object]] = []
    for index, expected in enumerate(expected_rows):
        if not isinstance(expected, Mapping):
            comparisons.append({"index": index, "status": "invalid_annotation"})
            continue
        expected_kind = expected.get("expected_kind")
        expected_metadata = expected.get("expected_metadata")
        expected_metadata = expected_metadata if isinstance(expected_metadata, Mapping) else {}
        identity = expected_metadata.get("item_id") or expected_metadata.get("quest_id")
        identity_key = "item_id" if "item_id" in expected_metadata else "quest_id"
        candidates = tuple(
            entry
            for entry in actual_rows
            if (
                identity is not None
                and entry.metadata.get(identity_key) == identity
            )
        )
        if len(candidates) != 1:
            comparisons.append(
                {
                    "index": index,
                    "identity": identity,
                    "status": "missing" if not candidates else "ambiguous",
                }
            )
            continue
        entry = candidates[0]
        actual_kind = entry.kind.value
        actual_metadata = entry.metadata
        metadata_mismatches = {
            str(key): {"expected": value, "actual": actual_metadata.get(key)}
            for key, value in expected_metadata.items()
            if actual_metadata.get(key) != value
        }
        action_point = entry.action_point
        comparison: dict[str, object] = {
            "index": index,
            "identity": identity,
            "status": "found" if actual_kind == expected_kind and not metadata_mismatches else "wrong_facts",
            "expected_kind": expected_kind,
            "actual_kind": actual_kind,
            "metadata_mismatches": metadata_mismatches,
            "action_point": None if action_point is None else list(action_point),
        }
        for control_key in ("Use", "Go", "Claim", "action"):
            box = expected.get(control_key)
            if not isinstance(box, list) or len(box) != 4 or not all(isinstance(value, int) for value in box):
                continue
            if not isinstance(action_point, tuple) or len(action_point) != 2:
                comparison["action_control_status"] = "missing_action_point"
                break
            x, y = action_point
            left, top, width, height = box
            comparison["action_control_status"] = (
                "found" if left <= x < left + width and top <= y < top + height else "outside"
            )
            break
        comparisons.append(comparison)
    return comparisons


def _compare_manual_state(
    manual_summary: Mapping[str, object],
    observation: Observation,
) -> dict[str, object]:
    """Compare the independently reviewed clear/blocked state to the guard decision."""

    expected = manual_summary.get("state")
    if expected not in {"clear", "blocked"}:
        return {"status": "not_annotated"}
    actual_guard = observation.decision.guard.value
    expected_guard = "blocked" if expected == "blocked" else "clear"
    if actual_guard == expected_guard:
        status = "found"
    elif actual_guard in {"not_evaluated", "unresolved"}:
        status = "abstain"
    else:
        status = "wrong_state"
    return {"expected": expected, "actual_guard": actual_guard, "status": status}


def _compare_forbidden_background(
    manual_summary: Mapping[str, object],
    observation: Observation,
) -> dict[str, object]:
    """Report whether a blocked fixture leaked forbidden background controls."""

    forbidden = manual_summary.get("forbidden_background")
    if not isinstance(forbidden, list) or not forbidden:
        return {"status": "not_annotated", "present": []}
    actual_ids = {selector_id.value for selector_id in observation.visible_elements}
    present = sorted(str(selector_id) for selector_id in forbidden if str(selector_id) in actual_ids)
    return {"status": "click_through" if present else "clear", "present": present}


def _compare_expected_daily_rows(
    manual_summary: Mapping[str, object],
    observation: Observation,
) -> dict[str, object]:
    """Compare complete daily-row count while reporting clipped rows separately."""

    expected = manual_summary.get("expected_daily_rows")
    if not isinstance(expected, int) or isinstance(expected, bool):
        return {"status": "not_annotated"}
    daily_rows = tuple(entry for entry in observation.list_entries if entry.kind.value == "daily_quest")
    complete_rows = tuple(entry for entry in daily_rows if entry.row_status.value == "complete")
    clipped_rows = tuple(entry for entry in daily_rows if entry.row_status.value == "clipped")
    if len(complete_rows) == expected:
        status = "found"
    elif len(complete_rows) < expected:
        status = "missing"
    else:
        status = "wrong_count"
    return {
        "expected_complete": expected,
        "actual_complete": len(complete_rows),
        "actual_clipped": len(clipped_rows),
        "status": status,
    }


def _manual_comparison_failures(comparisons: Mapping[str, object]) -> list[str]:
    """Return only concrete unsafe or incorrect manual-comparison outcomes."""

    failures: list[str] = []
    action_points = comparisons.get("action_point_containment")
    if isinstance(action_points, list):
        failures.extend(
            f"control:{item.get('annotation_control', item.get('selector_id'))}:{item.get('status')}"
            for item in action_points
            if isinstance(item, Mapping) and item.get("status") == "outside"
        )
    rows = comparisons.get("row_comparisons")
    if isinstance(rows, list):
        failures.extend(
            f"row:{item.get('identity', item.get('index'))}:{item.get('status')}"
            for item in rows
            if isinstance(item, Mapping) and item.get("status") == "wrong_facts"
        )
        failures.extend(
            f"row:{item.get('identity', item.get('index'))}:action:{item.get('action_control_status')}"
            for item in rows
            if isinstance(item, Mapping) and item.get("action_control_status") == "outside"
        )
    state = comparisons.get("state_comparison")
    if isinstance(state, Mapping) and state.get("status") == "wrong_state":
        failures.append("state:wrong_state")
    forbidden = comparisons.get("forbidden_background_comparison")
    if isinstance(forbidden, Mapping) and forbidden.get("status") == "click_through":
        failures.append("forbidden_background:click_through")
    daily_rows = comparisons.get("expected_daily_rows_comparison")
    if isinstance(daily_rows, Mapping) and daily_rows.get("status") == "wrong_count":
        failures.append("daily_rows:wrong_count")
    return failures


def _run_pipeline(
    image: Image.Image,
    *,
    visual_recognizer: Any,
    baseline_builder: ObservationBuilder | None,
    guarded_builder: ObservationBuilder | None,
) -> _PipelineRun:
    started = time.perf_counter()
    raw_visual, visual_latency_ms = _timed(lambda: visual_recognizer.recognize(image))
    if baseline_builder is None or guarded_builder is None:
        total_latency_ms = (time.perf_counter() - started) * 1000.0
        return _PipelineRun(
            raw_visual=raw_visual,
            baseline_observation=None,
            guarded_observation=None,
            metrics=WarmReplayMetrics(
                total_latency_ms=total_latency_ms,
                visual_latency_ms=visual_latency_ms,
                content_latency_ms=0.0,
                guard_latency_ms=0.0,
            ),
        )

    baseline_capture = _captured_screenshot(image.copy())
    baseline_context = baseline_builder.create_ocr_context(baseline_capture)
    baseline_observation, content_latency_ms = _timed(
        lambda: baseline_builder.build(baseline_capture, ocr_context=baseline_context)
    )
    guarded_capture = _captured_screenshot(image.copy())
    guarded_context = guarded_builder.create_ocr_context(guarded_capture)
    guarded_observation, guard_latency_ms = _timed(
        lambda: guarded_builder.build(guarded_capture, ocr_context=guarded_context)
    )
    total_latency_ms = (time.perf_counter() - started) * 1000.0
    return _PipelineRun(
        raw_visual=raw_visual,
        baseline_observation=baseline_observation,
        guarded_observation=guarded_observation,
        metrics=WarmReplayMetrics(
            total_latency_ms=total_latency_ms,
            visual_latency_ms=visual_latency_ms,
            content_latency_ms=content_latency_ms,
            guard_latency_ms=guard_latency_ms,
            ocr_metrics=None,
            fallback_reasons=None,
        ),
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

    recovery_counts = {
        "expected": 0,
        "baseline_correct": 0,
        "guarded_correct": 0,
        "recovered": 0,
        "newly_recovered": 0,
        "missing_or_abstain": 0,
        "errors": 0,
        "lost_previously_correct": 0,
    }
    promotion_dispositions: defaultdict[str, int] = defaultdict(int)
    for record in records:
        recovery = (record.manual_annotation or {}).get("baseline_recovery")
        if not isinstance(recovery, Mapping):
            continue
        recovery_counts["expected"] += int(recovery.get("expected_count", 0))
        recovery_counts["baseline_correct"] += int(recovery.get("baseline_correct_count", 0))
        recovery_counts["guarded_correct"] += int(recovery.get("guarded_correct_count", 0))
        recovery_counts["recovered"] += int(recovery.get("recovery_count", 0))
        recovery_counts["newly_recovered"] += int(recovery.get("newly_recovered_count", 0))
        recovery_counts["missing_or_abstain"] += int(recovery.get("missing_or_abstain_count", 0))
        recovery_counts["errors"] += int(recovery.get("error_count", 0))
        recovery_counts["lost_previously_correct"] += int(
            recovery.get("lost_previously_correct_count", 0)
        )
        disposition = recovery.get("promotion_disposition")
        if isinstance(disposition, str):
            promotion_dispositions[disposition] += 1
    return {
        "frame_count": len(records),
        "baseline_label": "same revision without visual recognizer",
        "wrong_actionable_classifications": count(
            lambda record: record.wrong_actionable_classification is True
        ),
        "abstentions": count(lambda record: record.abstention is True),
        "blocking_popups": count(lambda record: record.blocking_popup is True),
        "baseline_recovery": {
            **recovery_counts,
            "promotion_dispositions": dict(sorted(promotion_dispositions.items())),
        },
        "latency_ms": {
            "baseline": _timing_summary(record.baseline_latency_ms for record in records),
            "raw_visual": _timing_summary(record.raw_visual_latency_ms for record in records),
            "guarded": _timing_summary(record.guarded_latency_ms for record in records),
        },
        "warm_replays": _aggregate_warm_replays(records),
    }


def _aggregate_warm_replays(records: Sequence[FrameMetrics]) -> dict[str, object] | None:
    replays = [replay for record in records for replay in record.warm_replays]
    if not replays:
        return None
    ocr_totals: dict[str, int | float] = {}
    fallback_reasons: set[str] = set()
    for replay in replays:
        if replay.ocr_metrics is not None:
            for key, value in replay.ocr_metrics.items():
                ocr_totals[key] = ocr_totals.get(key, 0) + value
        if replay.fallback_reasons is not None:
            fallback_reasons.update(replay.fallback_reasons)
    return {
        "replay_count": len(replays),
        "latency_ms": {
            "total": _timing_summary(replay.total_latency_ms for replay in replays),
            "visual": _timing_summary(replay.visual_latency_ms for replay in replays),
            "content": _timing_summary(replay.content_latency_ms for replay in replays),
            "guard": _timing_summary(replay.guard_latency_ms for replay in replays),
        },
        "ocr": ocr_totals or None,
        "fallback_reasons": sorted(fallback_reasons) if fallback_reasons else None,
    }


def _timing_summary(values: Iterable[float | None]) -> dict[str, float] | None:
    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None
    return {
        "min": min(numeric_values),
        "p50": statistics.median(numeric_values),
        "p95": (
            numeric_values[0]
            if len(numeric_values) == 1
            else statistics.quantiles(numeric_values, n=100, method="inclusive")[94]
        ),
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
    asset_root: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    """Build a deterministic inventory of effective selector recognition coverage.

    The audit reads the canonical catalog and registry, then scans source-level
    Python/YAML references. It reports explicit TEMPLATE asset requirements and
    UNSUPPORTED dispositions separately; it does not infer a migration strategy
    from a selector name or from its current geometry.
    """

    audit_root = root.resolve()
    resolved_catalog_path = (catalog_path or _default_catalog_path()).resolve()
    resolved_asset_root = (asset_root or _default_asset_root()).resolve()
    catalog = load_selector_catalog_document(
        resolved_catalog_path,
        asset_root=resolved_asset_root,
        validate_assets=False,
    )
    registry = build_default_selector_registry(
        asset_root=resolved_asset_root,
        catalog_path=resolved_catalog_path,
        validate_assets=False,
    )
    selector_ids = frozenset(selector.id for selector in catalog.selectors)
    enum_ids = frozenset(member.name for member in UiElementId)
    # Scan the enum as well as the catalog so orphaned IDs retain their
    # actual static consumers in the inventory.  Catalog membership is a
    # separate fact from whether a runtime/authored/tool reference exists.
    references = _scan_static_selector_references(audit_root, selector_ids | enum_ids)

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
        asset_required = effective_kind == DetectionKind.TEMPLATE.value
        asset_exists = None if asset_path is None else asset_path.is_file()
        if asset_path is None:
            asset_path_text = None
            missing_asset_disposition = "missing_template_asset" if asset_required else "not_required"
        else:
            asset_path_text = _relative_or_absolute_path(asset_path, audit_root)
            missing_asset_disposition = "resolved" if asset_exists else "missing_template_asset"
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
                "resolver_supported": effective_kind in {
                    DetectionKind.TEMPLATE.value,
                    DetectionKind.GUARDED_GEOMETRY.value,
                    DetectionKind.OCR_REGION.value,
                    DetectionKind.SEMANTIC.value,
                },
                "status": status,
                "maturity": status,
                "enabled": effective_kind != DetectionKind.UNSUPPORTED.value,
                "geometry": {
                    "has_relative_bounds": geometry is not None,
                    "materialize_relative_bounds": catalog_entry.materialize_relative_bounds,
                    "materialized_by_registry": (
                        geometry is not None
                        and catalog_entry.materialize_relative_bounds
                        and effective_kind == DetectionKind.GUARDED_GEOMETRY.value
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

    catalog_ids = {selector.id for selector in catalog.selectors}
    orphan_rows = [
        {
            "id": selector_id,
            "catalog_defined": False,
            "static_consumers": _references_document(references.get(selector_id, ())),
            "intended_disposition": "unregistered_enum_id",
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
        "static_referenced_selector_count": sum(
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
        "missing_template_asset_count": sum(
            row["asset"]["missing_path_disposition"] == "missing_template_asset"
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
            "asset_root": _relative_or_absolute_path(resolved_asset_root, audit_root),
            "fixture_manifest": _relative_or_absolute_path(
                Path(manifest_path).resolve() if manifest_path is not None else audit_root / "tests" / "data" / "screen_recognition" / "manifest.json",
                audit_root,
            ),
        },
        "criteria": {
            "enabled": "effective detection kind is not UNSUPPORTED; this does not prove parser/geometry support or safe action authorization",
            "asset_required": "every TEMPLATE selector requires explicit template_asset metadata; other detection kinds do not imply an asset",
            "missing_path_disposition": "missing_template_asset means a TEMPLATE selector declares an asset that is absent; UNSUPPORTED selectors are reported separately",
            "consumer_scan": "static Python AST references and non-comment YAML identifier references under runtime, authored, tool, and test source roots; source presence is not proof of execution reachability",
            "static_referenced_selector_count": "selectors with at least one runtime, authored, or tool static reference; this is not proved execution reachability",
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


def _default_asset_root() -> Path:
    """Return the canonical packaged asset root used by the registry builder."""

    from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root

    return default_selector_asset_root()


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
        "--asset-root",
        type=Path,
        default=None,
        help="Optional selector asset root for --coverage-audit.",
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
    parser.add_argument(
        "--warm-replays",
        type=int,
        default=0,
        help="Run this many warm guarded ObservationBuilder replays per frame (0 or at least 5).",
    )
    parser.add_argument(
        "--measurement-profile",
        choices=("pre_d", "post_d"),
        default="pre_d",
        help="Label the measured canonical pipeline revision in the report.",
    )
    arguments = parser.parse_args(argv)
    if arguments.coverage_audit:
        document = build_recognition_coverage_audit(
            root=arguments.root,
            catalog_path=arguments.catalog,
            asset_root=arguments.asset_root,
            manifest_path=arguments.manifest,
        )
        output_path = arguments.output or arguments.root / "artifacts" / "non_yolo_recognition" / "coverage_audit.json"
    else:
        document = benchmark_manifest(
            arguments.manifest,
            visual_only=arguments.visual_only,
            warm_replays=arguments.warm_replays,
            measurement_profile=arguments.measurement_profile,
        )
        output_path = arguments.output or ROOT / "artifacts" / "screen_recognition" / "benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output_path)
    return 1 if (
        document.get("wrong_actionable_classification_count", 0)
        or document.get("manual_comparison_failure_count", 0)
        or document.get("baseline_recovery_regression_count", 0)
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
