"""Evidence indexing must preserve uncertainty and avoid copying captured text."""

import json
from pathlib import Path
import tempfile
import unittest

from tools.audit_navigation_evidence import build_audit


class NavigationEvidenceAuditTests(unittest.TestCase):
    def test_indexes_predictions_without_inventing_transitions_or_copying_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            anchors = root / "pnc_automation/app/pnc/vision/data/screen_anchors.json"
            anchors.parent.mkdir(parents=True)
            anchors.write_text('{"profiles": []}')
            artifacts = root / "artifacts"
            artifacts.mkdir()
            for index, screen in enumerate(("pnc_home_city", "PNC_WORLD_MAP")):
                (artifacts / f"{index}_unidentified_ocr.json").write_text(json.dumps({
                    "screen_type": screen, "recognized_text_hints": ["private text"],
                }))
            (artifacts / "broken_ocr.json").write_text('{"screen_type": "unsupported"}')
            output = artifacts / "audit"
            result = build_audit(root, output)
            self.assertEqual(result["file_count"], 3)
            self.assertEqual(len(result["screens"]["PNC_HOME_CITY"]["recorded_frames"]), 1)
            self.assertEqual(len(result["parse_errors"]), 1)
            self.assertEqual(result["validation_results"], [])
            self.assertNotIn("private text", (output / "coverage.json").read_text())
            # Reruns exclude their own generated output, preserving the denominator.
            self.assertEqual(build_audit(root, output)["file_count"], 3)
