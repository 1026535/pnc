"""Unit tests for Campaign geometry and row de-duplication."""

from __future__ import annotations
import unittest
import numpy as np
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.vision.campaign import geometry
from pnc_automation.core.vision.image.models import Bounds

def _row(bounds: Bounds) -> DetectedListEntry:
    return DetectedListEntry(
        kind=ListEntryKind.CAMPAIGN_STAGE,
        bounds=bounds,
        row_status=RowRecognitionStatus.UNREADABLE,
    )

class CampaignFeatureArithmeticTests(unittest.TestCase):
    """White and high-red pixels must never classify as navy interiors."""

    def test_node_features_do_not_wrap_bright_pixels_into_navy(self) -> None:
        disc = Bounds(20, 20, 60, 60)
        for name, color in (
            ("white", (255, 255, 255)),
            ("bright_red", (240, 30, 30)),
        ):
            with self.subTest(fill=name):
                pixels = np.zeros((100, 100, 3), dtype=np.uint8)
                pixels[:, :] = color
                features = geometry._node_features(pixels, disc)
                self.assertEqual(0.0, features["blue"])
                self.assertEqual(0.0, features["navy_band"])

        pixels = np.zeros((100, 100, 3), dtype=np.uint8)
        pixels[:, :] = (20, 20, 120)
        features = geometry._node_features(pixels, disc)
        self.assertGreater(features["blue"], 0.9)

    def test_nameplate_navy_check_does_not_count_white_or_red_trim(self) -> None:
        plate = Bounds(0, 0, 60, 20)
        for name, color, expected in (
            ("white", (255, 255, 255), False),
            ("bright_red", (240, 30, 30), False),
        ):
            with self.subTest(fill=name):
                pixels = np.zeros((40, 80, 3), dtype=np.uint8)
                pixels[:, :] = color
                self.assertIs(
                    geometry._nameplate_supported(pixels, plate, gold=False), expected
                )

        pixels = np.zeros((40, 80, 3), dtype=np.uint8)
        pixels[:, :] = (15, 15, 25)
        pixels[:, :20] = (30, 30, 140)
        self.assertTrue(geometry._nameplate_supported(pixels, plate, gold=False))

class CampaignDedupTests(unittest.TestCase):
    """Duplicate ownership is decided by marker geometry, not row envelopes."""

    def test_distinct_nearby_markers_survive_overlapping_row_envelopes(self) -> None:
        rows = [
            (Bounds(10, 10, 30, 30), _row(Bounds(10, 10, 160, 60))),
            (Bounds(120, 20, 30, 30), _row(Bounds(50, 15, 160, 60))),
        ]
        kept = geometry._deduplicate_marked(rows)
        self.assertEqual(2, len(kept))

    def test_overlapping_markers_collapse_to_the_first_row(self) -> None:
        rows = [
            (Bounds(10, 10, 30, 30), _row(Bounds(10, 10, 160, 60))),
            (Bounds(20, 15, 30, 30), _row(Bounds(30, 12, 160, 60))),
        ]
        kept = geometry._deduplicate_marked(rows)
        self.assertEqual(1, len(kept))
        self.assertIs(kept[0], rows[0][1])

if __name__ == "__main__":
    unittest.main()
