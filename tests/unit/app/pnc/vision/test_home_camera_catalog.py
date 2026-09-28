"""Home camera catalog tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_definition_for_label,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.vision.home_city_camera import load_home_city_camera_catalog


class HomeCityCameraCatalogTests(unittest.TestCase):
    """The packaged landmark catalog must stay self-consistent and small."""

    def test_catalog_loads_reviewed_landmarks_targets_and_anchor_basis(self) -> None:
        catalog = load_home_city_camera_catalog()

        self.assertEqual((900, 1600), catalog.reference_size)
        self.assertEqual((-532, 222), catalog.atlas_to_reference_offset)
        self.assertEqual(
            (HomeCityObjectId.CASTLE, HomeCityObjectId.INFANTRY_BARRACKS),
            catalog.anchor_object_ids,
        )
        self.assertEqual(30, len(catalog.landmarks))
        self.assertEqual(7, len(catalog.targets))
        groups = {landmark.group_id for landmark in catalog.landmarks}
        self.assertEqual(
            {
                "institute_structure",
                "garden_terrace",
                "plaza_low",
                "barracks_roofs",
                "tower_structure",
                "blacksmith_structure",
                "southern_courtyard",
                "castle_structure",
                "courtyard_garden",
                "east_fortification",
                "east_cliff",
                "alliance_hall_structure",
                "sanctum_structure",
                "campaign_portal",
                "illusory_beast_manor_structure",
                "sauroi_lair_structure",
            },
            groups,
        )
        # Institute-correlated crops share one group so they cannot outvote
        # independent contradictory evidence.
        institute_votes = [
            landmark.id
            for landmark in catalog.landmarks
            if landmark.group_id == "institute_structure"
        ]
        self.assertEqual(
            {"p2_institute_facade", "p3_institute_base_left", "p6_path_right"},
            set(institute_votes),
        )
        # Correlated eastern wall/cliff crops are grouped honestly for the same reason.
        by_group = {}
        for landmark in catalog.landmarks:
            by_group.setdefault(landmark.group_id, set()).add(landmark.id)
        self.assertEqual(
            {
                "east_aqueduct",
                "east_parapet",
                "ridge_wall",
                "northeast_moat_cap",
                "northeast_moat_shaft",
            },
            by_group["east_fortification"],
        )
        # The Sauroi Lair pier is a new independent fixed structure; the two
        # moat parts above join east_fortification and never vote apart.
        self.assertEqual({"northeast_sauroi_pier"}, by_group["sauroi_lair_structure"])
        # The portal body and its left pedestal are two measured regions of
        # the same fixed Campaign structure; they share one group and can
        # never vote as independent scene proof.
        self.assertEqual(
            {"campaign_portal_body", "campaign_left_pedestal"},
            by_group["campaign_portal"],
        )
        self.assertEqual({"east_cliff_rock", "east_rock_trees"}, by_group["east_cliff"])
        self.assertEqual({"tower_of_trial_body", "west_trial_wall"}, by_group["tower_structure"])
        # Castle keep crops share one structure group; the statue monument and
        # courtyard gardens are genuinely independent scene regions.
        self.assertEqual(
            {
                "castle_fountain",
                "castle_tower",
            },
            by_group["castle_structure"],
        )
        self.assertEqual(
            {"statue_wings", "plaza_ring", "p5_plaza_low", "t6_plaza_south"},
            by_group["plaza_low"],
        )
        self.assertEqual({"garden_west"}, by_group["courtyard_garden"])
        # Two distinct parts of one Manor share one group so the structure can
        # supply only one group's identity correspondences, not an extra vote.
        self.assertEqual(
            {"illusory_beast_manor_owl_head", "illusory_beast_manor_right_tower"},
            by_group["illusory_beast_manor_structure"],
        )
        for item in (*catalog.landmarks, *catalog.targets):
            self.assertTrue(catalog.template_path(item.file_name).is_file())
        self.assertIs(
            catalog.target_for(HomeCityObjectId.INSTITUTE),
            catalog.targets[0],
        )
        campaign = catalog.target_for(HomeCityObjectId.CAMPAIGN)
        self.assertIsNotNone(campaign)
        self.assertEqual((2083, 1121), campaign.atlas_action_point())
        blacksmith = catalog.target_for(HomeCityObjectId.BLACKSMITH)
        self.assertIsNotNone(blacksmith)
        self.assertEqual(
            HomeCitySlotSelector(12),
            blacksmith.reference_slot,
        )
        manor = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        self.assertIsNotNone(manor)
        # The Manor is a fixed camera target: it publishes no slot candidate.
        self.assertIsNone(manor.reference_slot)
        self.assertEqual((1032, 2068), manor.atlas_action_point())
        self.assertIsNone(catalog.target_for(HomeCityObjectId.CASTLE))
        # An unrelated nearby "Manor" label is not the Illusory Beast Manor and
        # must never resolve to it.
        self.assertIsNone(home_city_object_definition_for_label("Manor"))
