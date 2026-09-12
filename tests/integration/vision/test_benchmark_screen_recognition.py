from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from tools.benchmark_screen_recognition import (
    FrameMetrics,
    aggregate_metrics,
    build_recognition_coverage_audit,
    load_manifest,
)


class ScreenRecognitionBenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def test_manifest_rejects_missing_fields(self) -> None:
        image = self._write_image("reference.png", (12, 20, 30))
        manifest = {
            "version": 1,
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

    def test_coverage_audit_reports_reachable_consumers_and_missing_asset_disposition(self) -> None:
        catalog_path = self.root / "selector_registry.yaml"
        catalog_path.write_text(
            """
selectors:
- id: PNC_HOME_BUILD_BUTTON
  screens: [PNC_HOME_CITY]
  status: screenshot_seeded
  detection_kind: template
- id: PNC_HOME_RESEARCH_BUTTON
  screens: [PNC_HOME_CITY]
  status: planned
  detection_kind: planned
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
            template_root=self.root / "templates",
            manifest_path=self.root / "missing-manifest.json",
        )

        self.assertEqual(report["summary"]["selector_count"], 2)
        self.assertEqual(report["summary"]["enabled_count"], 1)
        self.assertEqual(report["summary"]["asset_required_count"], 1)
        self.assertEqual(report["summary"]["asset_missing_count"], 1)
        self.assertEqual(report["summary"]["unknown_missing_asset_disposition_count"], 1)
        rows = {row["id"]: row for row in report["selectors"]}
        build_row = rows["PNC_HOME_BUILD_BUTTON"]
        self.assertEqual(build_row["asset"]["missing_path_disposition"], "unknown_intended_disposition")
        self.assertEqual(build_row["static_consumers"]["reachable_count"], 2)
        self.assertEqual(
            {reference["path"] for reference in build_row["static_consumers"]["references"]},
            {"pnc_automation/consumer.py", "scripts/workflow.yaml"},
        )
        self.assertEqual(rows["PNC_HOME_RESEARCH_BUTTON"]["effective_detection_kind"], "planned")
        self.assertFalse(rows["PNC_HOME_RESEARCH_BUTTON"]["enabled"])

    def test_coverage_audit_keeps_fixture_dimensions_unknown_when_unannotated(self) -> None:
        catalog_path = self.root / "selector_registry.yaml"
        catalog_path.write_text(
            """
selectors:
- id: PNC_HOME_BUILD_BUTTON
  screens: [PNC_HOME_CITY]
  status: planned
  detection_kind: planned
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
            template_root=self.root / "templates",
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
            "version": 1,
            "annotation": "reviewed",
            "samples": [
                {
                    "image": image.name,
                    "screen": screen,
                    "split": split,
                    "group": group,
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
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
