from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, replace
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrResult
from tests.test_support import make_observation

from tools.benchmark_screen_recognition import (
    FrameMetrics,
    BenchmarkSample,
    _decoded_image_sha256,
    _compare_baseline_recovery,
    _evaluate_sample,
    _manual_comparison_failures,
    _instrument_builder,
    _observation_targets,
    aggregate_metrics,
    build_recognition_coverage_audit,
    load_manifest,
    main,
)


class ScreenRecognitionBenchmarkTests(unittest.TestCase):
    def test_selector_targets_include_the_executors_implicit_center(self) -> None:
        selector = UiElementId.PNC_BACK_BUTTON_TOP_LEFT
        observation = make_observation(ScreenType.PNC_SETTINGS, visible_ids=(selector,))
        original = observation.visible_elements[selector]
        for override, expected in ((None, [30, 45]), ((24, 38), [24, 38])):
            with self.subTest(override=override):
                element = replace(original, bounds=Bounds(10, 20, 40, 50), action_point=override)
                current = replace(observation, visible_elements={selector: element})
                self.assertEqual(_observation_targets(current)[0]["action_point"], expected)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_manifest_rejects_missing_fields(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        manifest = {
            "version": 2,
            "annotation": "reviewed",
            "samples": [
                {
                    "image": image.name,
                    "screen": "pnc_bag",
                    "split": "reference",
                    "group": "reference-group",
                }
            ],
        }
        path = self._write_manifest(manifest)

        with self.assertRaisesRegex(ValueError, "exactly image, screen, split, group, and sha256"):
            load_manifest(path)

    def test_manifest_rejects_legacy_hash_version(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        document = self._manifest(
            (
                (image, "pnc_bag", "reference", "reference-group"),
                (self._write_image("validation.png", (40, 50, 60)), "pnc_bag", "validation", "validation-group"),
                (self._write_image("holdout.png", (70, 80, 90)), "pnc_bag", "holdout", "holdout-group"),
            )
        )
        document["version"] = 1

        with self.assertRaisesRegex(ValueError, "manifest version must be 2"):
            load_manifest(self._write_manifest(document))

    def test_manifest_rejects_shared_reference_holdout_group(self) -> None:
        first = self._write_image("reference.png", (12, 20, 30))
        second = self._write_image("holdout.png", (50, 60, 70))
        manifest = self._manifest(
            (
                (first, "pnc_bag", "reference", "same-group"),
                (second, "pnc_bag", "holdout", "same-group"),
                (self._write_image("validation.png", (80, 90, 100)), "unknown", "validation", "validation-group"),
            )
        )

        with self.assertRaisesRegex(ValueError, "share reviewed group"):
            load_manifest(self._write_manifest(manifest))

    def test_manifest_rejects_duplicate_decoded_reference_holdout_image(self) -> None:
        first = self._write_image("reference.png", (12, 20, 30))
        second = self._write_image("holdout.png", (12, 20, 30))
        validation = self._write_image("validation.png", (80, 90, 100))
        manifest = self._manifest(
            (
                (first, "pnc_bag", "reference", "reference-group"),
                (second, "pnc_bag", "holdout", "holdout-group"),
                (validation, "unknown", "validation", "validation-group"),
            )
        )

        with self.assertRaisesRegex(ValueError, "duplicate decoded image"):
            load_manifest(self._write_manifest(manifest))

    def test_aggregate_metrics_counts_actionable_errors_and_abstentions(self) -> None:
        records = (
            FrameMetrics(
                image="reference.png",
                expected_screen="pnc_bag",
                split="reference",
                group="reference-group",
                baseline_screen="unknown",
                raw_visual_evidence_screen_ids=("pnc_bag",),
                final_guarded_screen="pnc_bag",
                blocking_popup=False,
                wrong_actionable_classification=False,
                abstention=False,
                baseline_latency_ms=10.0,
                raw_visual_latency_ms=2.0,
                guarded_latency_ms=12.0,
            ),
            FrameMetrics(
                image="validation.png",
                expected_screen="pnc_home_city",
                split="validation",
                group="validation-group",
                baseline_screen="pnc_home_city",
                raw_visual_evidence_screen_ids=(),
                final_guarded_screen="unknown",
                blocking_popup=False,
                wrong_actionable_classification=False,
                abstention=True,
                baseline_latency_ms=20.0,
                raw_visual_latency_ms=3.0,
                guarded_latency_ms=25.0,
            ),
            FrameMetrics(
                image="holdout.png",
                expected_screen="pnc_popup",
                split="holdout",
                group="holdout-group",
                baseline_screen="pnc_popup",
                raw_visual_evidence_screen_ids=("pnc_bag",),
                final_guarded_screen="pnc_bag",
                blocking_popup=False,
                wrong_actionable_classification=True,
                abstention=False,
                baseline_latency_ms=30.0,
                raw_visual_latency_ms=4.0,
                guarded_latency_ms=35.0,
            ),
        )

        result = aggregate_metrics(records)

        self.assertEqual(result["reference"]["wrong_actionable_classifications"], 0)
        self.assertEqual(result["validation"]["abstentions"], 1)
        self.assertEqual(result["holdout"]["wrong_actionable_classifications"], 1)
        self.assertEqual(result["holdout"]["latency_ms"]["guarded"]["median"], 35.0)
        self.assertEqual(result["holdout"]["latency_ms"]["guarded"]["p50"], 35.0)
        self.assertEqual(result["holdout"]["latency_ms"]["guarded"]["p95"], 35.0)

    def test_baseline_recovery_separates_abstain_wrong_and_lost_facts(self) -> None:
        recovered = _compare_baseline_recovery(
            {"row_comparisons": [{"identity": "food", "status": "missing"}]},
            {
                "row_comparisons": [{"identity": "food", "status": "found"}],
            }
        )
        self.assertEqual(recovered["recovery_count"], 1)
        self.assertEqual(recovered["facts"][0]["disposition"], "recovered")

        all_abstain = _compare_baseline_recovery(
            {
                "row_comparisons": [{"identity": "food", "status": "abstain"}],
            },
            {
                "row_comparisons": [{"identity": "food", "status": "abstain"}],
            }
        )
        self.assertEqual(all_abstain["recovery_count"], 0)
        self.assertEqual(all_abstain["promotion_disposition"], "not qualified")

        zero_row_safety_only = _compare_baseline_recovery(
            {
                "expected_daily_rows_comparison": {
                    "expected_complete": 0,
                    "actual_complete": 0,
                    "status": "found",
                }
            },
            {
                "expected_daily_rows_comparison": {
                    "expected_complete": 0,
                    "actual_complete": 0,
                    "status": "found",
                }
            },
        )
        self.assertEqual(zero_row_safety_only["expected_count"], 0)
        self.assertEqual(zero_row_safety_only["promotion_disposition"], "not qualified")

        baseline_wrong = _compare_baseline_recovery(
            {
                "row_comparisons": [{"identity": "food", "status": "wrong_facts"}],
            },
            {
                "row_comparisons": [{"identity": "food", "status": "found"}],
            }
        )
        self.assertEqual(baseline_wrong["recovery_count"], 0)
        self.assertEqual(baseline_wrong["facts"][0]["disposition"], "baseline_wrong")

        lost = _compare_baseline_recovery(
            {
                "row_comparisons": [{"identity": "food", "status": "found"}],
            },
            {
                "row_comparisons": [{"identity": "food", "status": "missing"}],
            }
        )
        self.assertEqual(lost["lost_previously_correct_count"], 1)

    def test_aggregate_reports_recovery_without_treating_missing_as_failure(self) -> None:
        record = FrameMetrics(
            image="reference.png",
            expected_screen="pnc_bag",
            split="reference",
            group="reference-group",
            baseline_screen="pnc_bag",
            raw_visual_evidence_screen_ids=(),
            final_guarded_screen="pnc_bag",
            blocking_popup=False,
            wrong_actionable_classification=False,
            abstention=False,
            baseline_latency_ms=1.0,
            raw_visual_latency_ms=1.0,
            guarded_latency_ms=1.0,
            manual_annotation={
                "baseline_recovery": {
                    "recovery_count": 1,
                    "missing_or_abstain_count": 2,
                    "error_count": 0,
                    "lost_previously_correct_count": 0,
                    "promotion_disposition": "review",
                }
            },
        )
        result = aggregate_metrics((record,))
        self.assertEqual(result["reference"]["baseline_recovery"]["recovered"], 1)
        self.assertEqual(result["reference"]["baseline_recovery"]["missing_or_abstain"], 2)
        self.assertEqual(result["reference"]["baseline_recovery"]["promotion_dispositions"], {"review": 1})

    def test_unsafe_manual_facts_and_baseline_regressions_fail_cli(self) -> None:
        failures = _manual_comparison_failures(
            {
                "row_comparisons": [
                    {"identity": "food", "status": "wrong_facts", "action_control_status": "outside"}
                ],
                "forbidden_background_comparison": {
                    "status": "click_through",
                    "present": ["PNC_BAG_MAIN_TAB_BAG"],
                },
            }
        )
        self.assertEqual(
            failures,
            [
                "row:food:wrong_facts",
                "row:food:action:outside",
                "forbidden_background:click_through",
            ],
        )
        output = self.root / "benchmark.json"
        with patch(
            "tools.benchmark_screen_recognition.benchmark_manifest",
            return_value={
                "wrong_actionable_classification_count": 0,
                "manual_comparison_failure_count": 0,
                "baseline_recovery_regression_count": 1,
            },
        ):
            self.assertEqual(
                main(["--manifest", str(self.root / "manifest.json"), "--output", str(output)]),
                1,
            )

    def test_manifest_rejects_corrupted_image_when_decoded_hash_changes(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        manifest_path = self._write_manifest(
            self._manifest(
                (
                    (image, "pnc_bag", "reference", "reference-group"),
                    (self._write_image("validation.png", (40, 50, 60)), "pnc_bag", "validation", "validation-group"),
                    (self._write_image("holdout.png", (70, 80, 90)), "pnc_bag", "holdout", "holdout-group"),
                )
            )
        )
        self._write_image("reference.png", (99, 88, 77))

        with self.assertRaisesRegex(ValueError, "decoded sha256 does not match image"):
            load_manifest(manifest_path)

    def test_warm_replays_measure_guarded_builder_and_preserve_independent_labels(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        sample = BenchmarkSample(
            image_name=image.name,
            path=image,
            expected_screen=ScreenType.PNC_BAG,
            split="reference",
            group="reference-group",
            sha256=_decoded_image_sha256(Image.open(image).convert("RGB")),
            decoded_sha256=_decoded_image_sha256(Image.open(image).convert("RGB")),
            image=Image.open(image).convert("RGB").copy(),
        )

        class FakeVisual:
            def recognize(self, image):
                del image
                return VisualRecognition()

        class _EmptyOcrBackend:
            def read_result(self, image, region=None):
                del image, region
                return OcrResult(lines=(), words=())

        class FakeBuilder:
            def __init__(self, visual_recognizer=None):
                self.visual_recognizer = visual_recognizer
                self.calls = 0
                self.images = []

            def create_ocr_context(self, screenshot):
                return ObservationOcrContext(
                    screenshot.image,
                    _EmptyOcrBackend(),
                    screenshot.frame_ref,
                    "benchmark-test",
                )

            def build(self, screenshot, *, ocr_context=None):
                self.calls += 1
                self.images.append(screenshot.image)
                del ocr_context
                observation = make_observation(
                    sample.expected_screen,
                    visible_ids=(UiElementId.PNC_BAG_MAIN_TAB_BAG,),
                    decision=ScreenDecision(
                        base_screen=sample.expected_screen,
                        effective_screen=sample.expected_screen,
                        guard=GuardVerdict.CLEAR,
                    ),
                )
                element = replace(
                    observation.visible_elements[UiElementId.PNC_BAG_MAIN_TAB_BAG],
                    bounds=Bounds(x=1, y=2, width=3, height=4),
                    action_point=(2, 4),
                )
                return replace(
                    observation,
                    visible_elements={UiElementId.PNC_BAG_MAIN_TAB_BAG: element},
                )

        guarded = FakeBuilder(visual_recognizer=FakeVisual())
        baseline = FakeBuilder()
        record = _evaluate_sample(
            sample,
            visual_recognizer=FakeVisual(),
            baseline_builder=baseline,
            guarded_builder=guarded,
            warm_replays=5,
            manual_annotation={
                "screen": "PNC_BAG",
                "state": "clear",
                "group": "reference-group",
                "boxes": {"Bag": [1, 2, 3, 4]},
                "control_selector_ids": {"Bag": "PNC_BAG_MAIN_TAB_BAG"},
                "rows": [{"title": "1K Food", "owned": 2}],
            },
        )

        self.assertEqual(len(record.warm_replays), 5)
        self.assertEqual(guarded.calls, 6)
        self.assertEqual(len({id(image) for image in guarded.images}), 6)
        self.assertEqual(record.guarded_targets[0]["id"], "PNC_BAG_MAIN_TAB_BAG")
        self.assertEqual(record.baseline_targets[0]["id"], "PNC_BAG_MAIN_TAB_BAG")
        self.assertEqual(record.baseline_facts["list_entry_count"], 0)
        self.assertEqual(record.manual_annotation["controls"]["Bag"], [1, 2, 3, 4])
        self.assertEqual(
            record.manual_annotation["guarded_comparisons"]["action_point_containment"][0]["status"],
            "found",
        )
        self.assertEqual(
            record.manual_annotation["baseline_comparisons"]["action_point_containment"][0]["status"],
            "found",
        )
        self.assertEqual(
            record.manual_annotation["guarded_comparisons"]["forbidden_background_comparison"]["status"],
            "not_annotated",
        )
        self.assertIsNone(record.warm_replays[0].ocr_metrics)

    def test_all_abstain_content_is_not_qualified_even_when_guard_is_clear(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        decoded_hash = _decoded_image_sha256(Image.open(image).convert("RGB"))
        sample = BenchmarkSample(
            image_name=image.name,
            path=image,
            expected_screen=ScreenType.PNC_BAG,
            split="reference",
            group="reference-group",
            sha256=decoded_hash,
            decoded_sha256=decoded_hash,
            image=Image.open(image).convert("RGB").copy(),
        )

        class FakeVisual:
            def recognize(self, image):
                del image
                return VisualRecognition()

        class _EmptyOcrBackend:
            def read_result(self, image, region=None):
                del image, region
                return OcrResult(lines=(), words=())

        class FakeBuilder:
            visual_recognizer = FakeVisual()

            def create_ocr_context(self, screenshot):
                return ObservationOcrContext(
                    screenshot.image,
                    _EmptyOcrBackend(),
                    screenshot.frame_ref,
                    "benchmark-test",
                )

            def build(self, screenshot, *, ocr_context=None):
                del screenshot, ocr_context
                return make_observation(ScreenType.PNC_BAG)

        record = _evaluate_sample(
            sample,
            visual_recognizer=FakeVisual(),
            baseline_builder=FakeBuilder(),
            guarded_builder=FakeBuilder(),
            manual_annotation={
                "screen": "PNC_BAG",
                "state": "clear",
                "boxes": {"Bag": [1, 2, 3, 4]},
                "control_selector_ids": {"Bag": "PNC_BAG_MAIN_TAB_BAG"},
                "forbidden_background": ["PNC_BAG_MAIN_TAB_HOME"],
                "rows": [
                    {
                        "expected_kind": "resource_item",
                        "expected_metadata": {"item_id": "food:1000:normal"},
                    }
                ],
            },
        )

        recovery = record.manual_annotation["baseline_recovery"]
        self.assertEqual(recovery["expected_count"], 2)
        self.assertEqual(recovery["guarded_correct_count"], 0)
        self.assertEqual(recovery["newly_recovered_count"], 0)
        self.assertEqual(recovery["promotion_disposition"], "not qualified")
        self.assertEqual(
            record.manual_annotation["guarded_comparisons"]["forbidden_background_comparison"]["status"],
            "clear",
        )

    def test_builder_probe_counts_only_raw_backend_and_exact_cache_reuse(self) -> None:
        class RawBackend:
            def __init__(self):
                self.calls = 0

            def read_result(self, image, region=None):
                self.calls += 1
                return OcrResult(lines=(), words=())

        @dataclass(slots=True)
        class SelectorEngine:
            ocr_service: object

        @dataclass(slots=True)
        class Enricher:
            ocr_service: object

            def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions):
                del image, screen_type, visible_elements, request, ocr_context, ocr_regions
                return None

        @dataclass(slots=True)
        class Builder:
            selector_engine: object
            enricher: object
            visual_recognizer: object
            debug_artifact_collector: object | None = None

        raw = RawBackend()
        original = Builder(
            selector_engine=SelectorEngine(raw),
            enricher=Enricher(raw),
            visual_recognizer=SimpleNamespace(recognize=lambda image: None),
        )
        image = Image.new("RGB", (12, 8), (1, 2, 3))
        context = ObservationOcrContext(image, raw, None, "benchmark-test")
        instrumented, stage_probe = _instrument_builder(original)
        self.assertIsNotNone(stage_probe)
        instrumented.visual_recognizer.recognize(image)
        self.assertEqual(stage_probe.visual_calls, 1)
        context.read_result(image)
        context.read_result(image)

        self.assertEqual(raw.calls, 1)
        self.assertEqual(context.metrics.engine_calls, 1)
        self.assertEqual(context.metrics.processed_pixel_area, 96)
        self.assertEqual(context.metrics.cache_hits, 1)

    def test_context_uses_one_backend_dispatch_for_repeated_reads(self) -> None:
        calls = []

        class Delegate:
            def read_result(self, image, region=None):
                calls.append("result")
                return OcrResult(lines=(), words=())

        delegate = Delegate()
        image = Image.new("RGB", (12, 8), (1, 2, 3))
        context = ObservationOcrContext(image, delegate, None, "benchmark-test")

        context.read_lines(image)
        context.read_text(image, Bounds(0, 0, 4, 4))

        self.assertEqual(calls, ["result"])
        self.assertEqual(context.metrics.requests, 2)

    def test_coverage_audit_reports_reachable_consumers_and_missing_asset_disposition(self) -> None:
        catalog_path = self.root / "selector_registry.yaml"
        catalog_path.write_text(
            """
selectors:
- id: PNC_HOME_BUILD_BUTTON
  screens: [PNC_HOME_CITY]
  status: screenshot_seeded
  detection_kind: template
  template_asset:
    path: missing/home_build.png
    reference_size: [540, 960]
    mask: embedded_alpha
    threshold: 0.9
- id: PNC_HOME_RESEARCH_BUTTON
  screens: [PNC_HOME_CITY]
  status: screenshot_seeded
  detection_kind: unsupported
  notes: ["fixture intentionally has no implemented resolver"]
""".lstrip(),
            encoding="utf-8",
        )
        runtime_path = self.root / "pnc_automation" / "consumer.py"
        runtime_path.parent.mkdir(parents=True)
        runtime_path.write_text(
            "from pnc_automation.app.pnc.enums.ui_element_id import UiElementId\n"
            "SELECTOR = UiElementId.PNC_HOME_BUILD_BUTTON\n",
            encoding="utf-8",
        )
        authored_path = self.root / "scripts" / "workflow.yaml"
        authored_path.parent.mkdir(parents=True)
        authored_path.write_text("selector: PNC_HOME_BUILD_BUTTON\n", encoding="utf-8")

        report = build_recognition_coverage_audit(
            root=self.root,
            catalog_path=catalog_path,
            asset_root=self.root / "templates",
            manifest_path=self.root / "missing-manifest.json",
        )

        self.assertEqual(report["summary"]["selector_count"], 2)
        self.assertEqual(report["summary"]["enabled_count"], 1)
        self.assertEqual(report["summary"]["asset_required_count"], 1)
        self.assertEqual(report["summary"]["asset_missing_count"], 1)
        self.assertEqual(report["summary"]["missing_template_asset_count"], 1)
        rows = {row["id"]: row for row in report["selectors"]}
        build_row = rows["PNC_HOME_BUILD_BUTTON"]
        self.assertEqual(build_row["asset"]["missing_path_disposition"], "missing_template_asset")
        self.assertEqual(build_row["static_consumers"]["reachable_count"], 2)
        self.assertEqual(
            {reference["path"] for reference in build_row["static_consumers"]["references"]},
            {"pnc_automation/consumer.py", "scripts/workflow.yaml"},
        )
        self.assertEqual(rows["PNC_HOME_RESEARCH_BUTTON"]["effective_detection_kind"], "unsupported")
        self.assertFalse(rows["PNC_HOME_RESEARCH_BUTTON"]["enabled"])

    def test_coverage_audit_reports_static_consumers_for_orphan_enum_ids(self) -> None:
        catalog_path = self.root / "selector_registry.yaml"
        catalog_path.write_text(
            """
selectors:
- id: PNC_HOME_BUILD_BUTTON
  screens: [PNC_HOME_CITY]
  status: screenshot_seeded
  detection_kind: unsupported
  notes: ["fixture intentionally has no implemented resolver"]
""".lstrip(),
            encoding="utf-8",
        )
        runtime_path = self.root / "pnc_automation" / "orphan_consumer.py"
        runtime_path.parent.mkdir(parents=True)
        runtime_path.write_text(
            "from pnc_automation.app.pnc.enums.ui_element_id import UiElementId\n"
            "SELECTOR = UiElementId.PNC_POPUP_CLOSE_BUTTON\n",
            encoding="utf-8",
        )

        report = build_recognition_coverage_audit(
            root=self.root,
            catalog_path=catalog_path,
            asset_root=self.root / "templates",
            manifest_path=self.root / "missing-manifest.json",
        )

        orphan = next(
            row for row in report["orphan_enum_ids"]
            if row["id"] == "PNC_POPUP_CLOSE_BUTTON"
        )
        self.assertEqual(orphan["static_consumers"]["reachable_count"], 1)
        self.assertEqual(
            orphan["static_consumers"]["references"][0]["path"],
            "pnc_automation/orphan_consumer.py",
        )

    def test_coverage_audit_keeps_fixture_dimensions_unknown_when_unannotated(self) -> None:
        catalog_path = self.root / "selector_registry.yaml"
        catalog_path.write_text(
            """
selectors:
- id: PNC_HOME_BUILD_BUTTON
  screens: [PNC_HOME_CITY]
  status: screenshot_seeded
  detection_kind: unsupported
  notes: ["fixture intentionally has no implemented resolver"]
""".lstrip(),
            encoding="utf-8",
        )
        first = self._write_image("reference.png", (12, 20, 30))
        second = self._write_image("validation.png", (50, 60, 70))
        third = self._write_image("holdout.png", (80, 90, 100))
        manifest_path = self._write_manifest(
            self._manifest(
                (
                    (first, "pnc_home_city", "reference", "source-a"),
                    (second, "pnc_home_city", "validation", "source-b"),
                    (third, "pnc_home_city", "holdout", "source-c"),
                )
            )
        )

        report = build_recognition_coverage_audit(
            root=self.root,
            catalog_path=catalog_path,
            asset_root=self.root / "templates",
            manifest_path=manifest_path,
        )

        fixture = report["fixture_coverage"]
        self.assertEqual(fixture["status"], "available")
        self.assertEqual(fixture["sample_count"], 3)
        self.assertEqual(fixture["supported_target_layout_cells"]["status"], "unknown")
        self.assertEqual(fixture["unknown_disposition"], "not_annotated_in_manifest")
        self.assertIn("control_state", fixture["unannotated_dimensions"])

    def _write_image(self, name: str, color: tuple[int, int, int]) -> Path:
        path = self.root / name
        Image.new("RGB", (12, 8), color).save(path, format="PNG")
        return path

    def _manifest(
        self,
        samples: tuple[tuple[Path, str, str, str], ...],
    ) -> dict[str, object]:
        return {
            "version": 2,
            "annotation": "reviewed; decoded RGB sha256",
            "samples": [
                {
                    "image": image.name,
                    "screen": screen,
                    "split": split,
                    "group": group,
                    "sha256": _decoded_image_sha256(Image.open(image).convert("RGB")),
                }
                for image, screen, split, group in samples
            ],
        }

    def _write_manifest(self, document: dict[str, object]) -> Path:
        path = self.root / "manifest.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
