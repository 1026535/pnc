"""Home camera consensus tests."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraStatus

from tests.support.pnc.capture_vision.home_camera_doubles import _scripted_localizer


class HomeCityCameraConsensusTests(unittest.TestCase):
    """Consensus fitting must qualify independent groups and reject conflicts."""

    def test_no_correspondences_is_insufficient(self) -> None:
        localizer = _scripted_localizer({})

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("no_landmark_correspondences", proof.reason)

    def test_single_group_cannot_localize_even_with_three_votes(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertIsNone(proof.translation)

    def test_two_groups_with_too_few_votes_is_insufficient(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "t5_barracks_roofs": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_landmark_correspondences", proof.reason)

    def test_agreeing_groups_fit_the_consensus_translation(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (11, -20),
                "t5_barracks_roofs": (9, -21),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Consensus image translation (10,-20) plus the (-532,+222) atlas offset.
        self.assertEqual((-522, 202), proof.translation)
        self.assertEqual(5, len(proof.evidence))
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_outlier_votes_do_not_pollute_the_consensus_cluster(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (10, -19),
                "t5_barracks_roofs": (400, 500),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-522, 202), proof.translation)
        self.assertNotIn("t5_barracks_roofs", {item.landmark_id for item in proof.evidence})

    def test_two_qualifying_contradictory_clusters_are_ambiguous(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p4_garden_terrace": (10, -20),
                "t5_barracks_roofs": (10, -20),
                "p3_institute_base_left": (300, 400),
                "p6_path_right": (300, 400),
                "p5_plaza_low": (300, 400),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.AMBIGUOUS, proof.status)
        self.assertIsNone(proof.translation)
