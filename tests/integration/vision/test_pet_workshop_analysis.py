"""PW05 saved-screenshot analysis: production recognizer -> planner -> report.

Replays the tracked native captures through ``tools/pet_workshop_analyze``
(the real production observation pipeline plus the accepted ``plan_next``)
and compares machine-readable reports against the reviewed label manifest
``tests/data/pet_workshop/analysis_labels.json``. Covered acceptance:

- the ready three-coconut order is read as three pieces and rejected
- the Wood 10 + beast-lasso detail recipe is eligible but never executable
- the same lasso recipe on the board strip reads completely, stays
  eligible, and reports not-ready with no Complete control
- the saved produce-and-merge sequence stays distinguishable through
  recognized deltas while the foliage-occluded Tree 4 brackets abstain
- black, unknown and unreadable frames yield no gameplay proposal
- invalid inputs fail with actionable errors; native RGBA stays native
- duplicate output stems are rejected before any report is written
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from pnc_automation.app.pnc.pet_workshop_catalog import load_pet_workshop_catalog

from tools.pet_workshop_analyze import (
    LABELS_SCHEMA,
    AnalysisError,
    analyze_image,
    build_perception,
    compare_labels,
    load_labels,
    main,
    _load_image,
)

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service

FIXTURES = TEST_DATA_ROOT / "screen_recognition"
LABELS_PATH = TEST_DATA_ROOT / "pet_workshop" / "analysis_labels.json"

_BOARD_LASSO = "pet_workshop_board_lasso_native_rgba.png"
_DETAIL_LASSO = "pet_workshop_order_detail_lasso_native_rgba.png"
_TREE4 = "pet_workshop_selected_tree4_native_rgba.png"
_PRODUCED = "pet_workshop_produced_native_rgba.png"
_MERGED = "pet_workshop_merged_native_rgba.png"


def _order(report: dict, order_ref: int) -> dict:
    return {order["order_ref"]: order for order in report["orders"]}[order_ref]


def _cell(report: dict, cell_id: int) -> dict:
    return {cell["cell_id"]: cell for cell in report["workshop"]["cells"]}[cell_id]


class PetWorkshopSavedFrameAnalysisTests(unittest.TestCase):
    """Reviewed-label acceptance over the production analysis entry point."""

    _perception = None
    _catalog = None
    _reports: dict[str, dict] = {}

    def _ensure_pipeline(self) -> None:
        if self._perception is None:
            type(self)._perception = build_perception(
                ocr_service=_require_rapid_ocr_service(self)
            ).perception
            type(self)._catalog = load_pet_workshop_catalog()

    def _report(self, image_name: str) -> dict:
        """Analyze one labeled fixture once, reusing the production pipeline."""

        self._ensure_pipeline()
        if image_name not in self._reports:
            with Image.open(FIXTURES / image_name) as source:
                image = source.copy()
            type(self)._reports[image_name] = analyze_image(
                self._perception,
                image,
                input_path=str(FIXTURES / image_name),
                source_kind="real_screenshot",
                catalog=self._catalog,
            )
        return self._reports[image_name]

    def test_reviewed_labels_match_production_reports(self) -> None:
        """Every labeled fixture's report matches its reviewed expectations."""

        labels = load_labels(LABELS_PATH)
        self.assertEqual(
            {_BOARD_LASSO, _DETAIL_LASSO, _TREE4, _PRODUCED, _MERGED}, set(labels)
        )
        for name in sorted(labels):
            with self.subTest(image=name):
                report = self._report(name)
                check = compare_labels(report, labels[name]["expected"])
                self.assertEqual("match", check["status"], msg=json.dumps(check))

    def test_ready_three_coconut_order_is_rejected(self) -> None:
        """The ready card reads three pieces; policy rejects the count."""

        report = self._report(_TREE4)
        order = _order(report, 1)
        self.assertEqual({"20105": 3}, order["requirements"])
        self.assertEqual("complete", order["completeness"])
        self.assertIs(True, order["ready"])
        assessment = order["assessment"]
        self.assertFalse(assessment["eligible"])
        self.assertEqual("piece total 3 != 2", assessment["ineligible_reason"])
        # No gameplay intent may be proposed while the survey stays partial.
        decision = report["decision"]
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual("inspect", decision["intent"]["kind"])
        self.assertFalse(decision["intent"]["gameplay"])

    def test_lasso_detail_recipe_is_eligible_but_incomplete(self) -> None:
        """The detail modal proves the recipe yet offers no execution path."""

        report = self._report(_DETAIL_LASSO)
        self.assertEqual("order_detail", report["workshop"]["surface"])
        order = _order(report, 1)
        self.assertEqual({"20210": 1, "20105": 1}, order["requirements"])
        self.assertEqual(
            ["feed", "beast_lasso"],
            [reward["category"] for reward in order["rewards"]],
        )
        self.assertEqual("complete", order["completeness"])
        self.assertIsNone(order["ready"])
        self.assertTrue(order["assessment"]["eligible"])
        self.assertEqual("beast_lasso", order["assessment"]["category"])
        # The modal is an excluded surface for planning: a stop, no gesture.
        decision = report["decision"]
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual("stop", decision["intent"]["kind"])
        self.assertEqual("excluded_surface", decision["intent"]["stop_reason"])
        self.assertFalse(decision["intent"]["gameplay"])

    def test_lasso_board_order_is_eligible_but_not_ready(self) -> None:
        """The scrolled-left lasso card reads fully and stays unsubmittable."""

        report = self._report(_BOARD_LASSO)
        self.assertEqual("board", report["workshop"]["surface"])
        # The left-clipped sliver keeps the survey partial -> no gesture.
        self.assertEqual("partial", report["workshop"]["order_survey"]["coverage"])
        self.assertEqual("clipped", _order(report, 1)["completeness"])

        order = _order(report, 3)
        # The full-width card ending inside the frame is complete, not clipped.
        self.assertEqual("complete", order["completeness"])
        self.assertEqual({"20210": 1, "20105": 1}, order["requirements"])
        self.assertEqual(
            [("beast_lasso", 2), ("feed", 4380)],
            [(reward["category"], reward["quantity"]) for reward in order["rewards"]],
        )
        # No Complete control is measured on this card.
        self.assertIs(False, order["ready"])
        assessment = order["assessment"]
        self.assertTrue(assessment["eligible"])
        self.assertEqual("beast_lasso", assessment["category"])
        self.assertFalse(assessment["unresolved"])
        # The partial survey still yields a non-gameplay inspection only.
        decision = report["decision"]
        self.assertIsNotNone(decision)
        assert decision is not None
        self.assertEqual("inspect", decision["intent"]["kind"])
        self.assertFalse(decision["intent"]["gameplay"])

    def test_saved_produce_and_merge_sequence_is_distinguishable(self) -> None:
        """Recognized deltas separate the select/produce/merge frames."""

        selected = self._report(_TREE4)
        produced = self._report(_PRODUCED)
        merged = self._report(_MERGED)

        # The visually selected but foliage-occluded Tree 4 stays unknown:
        # no per-instance corner template was authored for cell 7.
        for report in (selected, produced):
            self.assertEqual("unknown", report["workshop"]["selection"]["kind"])
            self.assertIsNone(report["workshop"]["selection"]["cell_id"])
        # Clean brackets on the merged result read the real selection.
        self.assertEqual("selected", merged["workshop"]["selection"]["kind"])
        self.assertEqual(17, merged["workshop"]["selection"]["cell_id"])

        # Produce spends one energy and drops Fruit 2 on the empty cell 14.
        self.assertEqual(166, selected["workshop"]["energy"]["current"])
        self.assertEqual(165, produced["workshop"]["energy"]["current"])
        self.assertEqual("empty", _cell(selected, 14)["occupancy"])
        self.assertEqual(
            ("occupied", 20102),
            (_cell(produced, 14)["occupancy"], _cell(produced, 14)["item_id"]),
        )
        # The merge consumes 14's Fruit 2 into cell 17's pair -> Fruit 3.
        self.assertEqual("empty", _cell(merged, 14)["occupancy"])
        self.assertEqual(
            ("occupied", 20102),
            (_cell(produced, 17)["occupancy"], _cell(produced, 17)["item_id"]),
        )
        self.assertEqual(
            ("occupied", 20103),
            (_cell(merged, 17)["occupancy"], _cell(merged, 17)["item_id"]),
        )
        # Merge is free: energy holds at 165.
        self.assertEqual(165, merged["workshop"]["energy"]["current"])
        # All three frames share the rejected three-coconut order read.
        for report in (selected, produced, merged):
            self.assertEqual(
                "piece total 3 != 2",
                _order(report, 1)["assessment"]["ineligible_reason"],
            )

    def test_synthesized_frames_never_propose_gameplay(self) -> None:
        """Black, blank and undersized frames publish no workshop action."""

        self._ensure_pipeline()
        for tag, image in (
            ("black", Image.new("RGBA", (900, 1600), (0, 0, 0, 255))),
            ("blank", Image.new("RGBA", (900, 1600), (255, 255, 255, 255))),
            ("tiny", Image.new("RGBA", (32, 32), (0, 0, 0, 255))),
        ):
            with self.subTest(frame=tag):
                report = analyze_image(
                    self._perception,
                    image,
                    input_path=f"<synthesized:{tag}>",
                    source_kind="synthesized",
                    catalog=self._catalog,
                )
                self.assertIsNone(report["workshop"])
                self.assertEqual([], report["orders"])
                self.assertIsNone(report["decision"])
                self.assertEqual("synthesized", report["input"]["source_kind"])

    def test_invalid_input_fails_with_actionable_errors(self) -> None:
        """Missing files, non-images and bad label manifests fail clearly."""

        with self.assertRaisesRegex(AnalysisError, "input image not found"):
            _load_image(FIXTURES / "does_not_exist.png")
        with tempfile.TemporaryDirectory() as tmp:
            not_an_image = Path(tmp) / "notes.png"
            not_an_image.write_text("not an image", encoding="utf-8")
            with self.assertRaisesRegex(AnalysisError, "not a readable image"):
                _load_image(not_an_image)
            bad_labels = Path(tmp) / "labels.json"
            bad_labels.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AnalysisError, LABELS_SCHEMA):
                load_labels(bad_labels)

    def test_native_rgba_input_stays_native(self) -> None:
        """Native captures report their real mode, never a conversion."""

        for name in (_BOARD_LASSO, _DETAIL_LASSO, _TREE4, _PRODUCED, _MERGED):
            with self.subTest(image=name):
                report = self._report(name)
                self.assertEqual("RGBA", report["input"]["mode"])
                self.assertEqual([900, 1600], report["input"]["size"])
                self.assertEqual("real_screenshot", report["input"]["source_kind"])

    def test_main_writes_reports_annotations_and_index(self) -> None:
        """The CLI writes the JSON report, annotated image and run index."""

        _require_rapid_ocr_service(self)  # main() builds its own real backend
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "analysis"
            exit_code = main(
                [
                    _DETAIL_LASSO,
                    "--labels",
                    str(LABELS_PATH),
                    "--out-dir",
                    str(out_dir),
                    "--fail-on-mismatch",
                ]
            )
            self.assertEqual(0, exit_code)
            stem = Path(_DETAIL_LASSO).stem
            report_path = out_dir / f"{stem}.report.json"
            annotated_path = out_dir / f"{stem}.annotated.png"
            self.assertTrue(report_path.is_file())
            self.assertTrue(annotated_path.is_file())
            with Image.open(annotated_path) as annotated:
                self.assertEqual((900, 1600), annotated.size)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual("pet_workshop_analysis/v1", report["schema"])
            self.assertEqual("match", report["label_check"]["status"])
            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(index["reports"]))
            self.assertEqual("ok", index["reports"][0]["status"])

    def test_duplicate_output_stems_are_rejected(self) -> None:
        """Two valid inputs sharing a basename fail before any report write."""

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for dirname in ("dir_a", "dir_b"):
                directory = Path(tmp) / dirname
                directory.mkdir()
                image_path = directory / "screen.png"
                Image.new("RGB", (32, 32)).save(image_path)
                paths.append(image_path)
            out_dir = Path(tmp) / "out"
            # Only costly perception is stubbed: the naming boundary is real.
            with mock.patch(
                "tools.pet_workshop_analyze.build_perception"
            ) as build:
                with self.assertRaisesRegex(AnalysisError, "output name collision"):
                    main([*[str(path) for path in paths], "--out-dir", str(out_dir)])
            build.assert_not_called()
            self.assertFalse(out_dir.exists())
            self.assertEqual([], list(Path(tmp).rglob("*.report.json")))
            self.assertEqual([], list(Path(tmp).rglob("*.annotated.png")))
            self.assertEqual([], list(Path(tmp).rglob("index.json")))


if __name__ == "__main__":
    unittest.main()
