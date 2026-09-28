"""Regression coverage for the decoded slot eligibility and occupancy models."""

import json
import unittest

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityMapCoordinate,
    HomeCityObjectId,
)
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotEligibility,
    HomeCitySlotKind,
    HomeCitySlotOccupancy,
    HomeCitySlotOccupancyState,
    _SCENE_GEOMETRY_PATH,
    _SCENE_PIVOT_EVIDENCE,
    home_city_client_building_type,
    home_city_scene_calibration,
    home_city_slot,
    home_city_slot_eligibility,
    home_city_slots_for_object,
    home_city_system_markers,
    home_city_system_nodes,
)
from pnc_automation.core.errors import SelectorResolutionError


def _scene_geometry_records() -> dict[str, object]:
    """Returns the packaged scene-geometry artifact the domain consumes."""

    return json.loads(_SCENE_GEOMETRY_PATH.read_text(encoding="utf-8"))


class HomeCitySlotEligibilityTests(unittest.TestCase):
    """The decoded BuildingPosition table must keep its reviewed shape."""

    def test_table_shape_matches_the_decoded_client_rows(self) -> None:
        slots = home_city_slot_eligibility()

        self.assertEqual(54, len(slots))
        self.assertEqual(
            16,
            sum(slot.kind == HomeCitySlotKind.SINGLE_TYPE for slot in slots),
        )
        self.assertEqual(
            38,
            sum(slot.kind == HomeCitySlotKind.MULTI_TYPE for slot in slots),
        )
        self.assertEqual(tuple(range(1, 55)), tuple(slot.slot_index for slot in slots))

    def test_small_slots_apply_the_default_seven_type_eligibility(self) -> None:
        slot = home_city_slot(17)

        self.assertEqual(HomeCitySlotKind.MULTI_TYPE, slot.kind)
        self.assertEqual(
            frozenset({1016, 1017, 1027, 1003, 1004, 1019, 1015}),
            slot.client_type_ids,
        )
        self.assertEqual(
            frozenset(
                {
                    HomeCityObjectId.FARM,
                    HomeCityObjectId.LUMBER_CAMP,
                    HomeCityObjectId.MOON_WELL,
                    HomeCityObjectId.RECRUITING_CENTER,
                    HomeCityObjectId.INFIRMARY,
                    HomeCityObjectId.IRON_MINE,
                    HomeCityObjectId.GOLD_MINE,
                }
            ),
            slot.eligible_object_ids,
        )

    def test_embassy_row_slots_stay_multi_type_without_occupant_hint(self) -> None:
        """Slots 11..13 allow 1010/1008/1009; the pivot binds no occupant."""
        for slot_index in (11, 12, 13):
            slot = home_city_slot(slot_index)

            self.assertEqual(HomeCitySlotKind.MULTI_TYPE, slot.kind)
            self.assertEqual(frozenset({1010, 1008, 1009}), slot.client_type_ids)
            self.assertEqual(
                frozenset(
                    {
                        HomeCityObjectId.ALLIANCE_HALL,
                        HomeCityObjectId.BLACKSMITH,
                        HomeCityObjectId.MARKET,
                    }
                ),
                slot.eligible_object_ids,
            )
            self.assertTrue(slot.calibrated)
            self.assertIsNotNone(slot.atlas_coordinate)
            self.assertIsNone(slot.inferred_atlas_coordinate)

    def test_single_type_slots_keep_catalog_coordinates_as_hints_only(self) -> None:
        """Catalog map anchors stay nominal hints beside the calibrated pivot."""
        slots = home_city_slot_eligibility()
        hinted = {
            slot.slot_index: slot
            for slot in slots
            if slot.inferred_atlas_coordinate is not None
        }

        self.assertEqual(
            {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15},
            set(hinted),
        )
        self.assertEqual(
            "catalog_map_coordinate:institute",
            hinted[9].inferred_coordinate_source,
        )
        self.assertTrue(all(slot.calibrated for slot in slots))
        for slot in hinted.values():
            self.assertNotEqual(slot.atlas_coordinate, slot.inferred_atlas_coordinate)

    def test_unbound_single_type_slots_keep_geometry_without_semantics(self) -> None:
        """VALKYRIE/HERO_RUNE/SEASON_TECH/WARGOD_MECHA pivots stay unbound."""
        for slot_index in (16, 52, 53, 54):
            slot = home_city_slot(slot_index)

            self.assertEqual(HomeCitySlotKind.SINGLE_TYPE, slot.kind)
            self.assertTrue(slot.calibrated)
            self.assertIsNotNone(slot.atlas_coordinate)
            self.assertEqual(frozenset(), slot.eligible_object_ids)
            self.assertIsNone(slot.inferred_atlas_coordinate)

    def test_nominal_catalog_coordinate_alone_cannot_qualify_a_slot(self) -> None:
        """A calibrated coordinate needs named qualification, never an inference."""
        base = dict(
            slot_index=9,
            area_id=1,
            kind=HomeCitySlotKind.SINGLE_TYPE,
            init_position=False,
            client_type_ids=frozenset({1007}),
            eligible_object_ids=frozenset({HomeCityObjectId.INSTITUTE}),
            unlock_cost_item_id=None,
            unlock_cost_count=None,
            inferred_atlas_coordinate=None,
            inferred_coordinate_source=None,
        )
        coordinate = home_city_slot(9).inferred_atlas_coordinate
        self.assertIsNotNone(coordinate)

        with self.assertRaises(SelectorResolutionError):
            HomeCitySlotEligibility(
                **base,
                atlas_coordinate=coordinate,
                coordinate_evidence=None,
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCitySlotEligibility(
                **base,
                atlas_coordinate=coordinate,
                coordinate_evidence="catalog_map_coordinate:institute",
            )

    def test_locked_area_eight_slots_carry_their_unlock_cost(self) -> None:
        slot = home_city_slot(48)

        self.assertEqual(12031001, slot.unlock_cost_item_id)
        self.assertEqual(500, slot.unlock_cost_count)
        self.assertFalse(slot.init_position)

    def test_init_position_matches_the_decoded_flags(self) -> None:
        self.assertEqual(
            {1, 2, 3, 4, 5, 6, 7, 8, 16, 52},
            {slot.slot_index for slot in home_city_slot_eligibility() if slot.init_position},
        )

    def test_unknown_slot_index_is_rejected(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            home_city_slot(55)

    def test_slots_for_object_returns_only_eligible_slots(self) -> None:
        self.assertEqual(
            (11, 12, 13),
            tuple(
                slot.slot_index
                for slot in home_city_slots_for_object(HomeCityObjectId.BLACKSMITH)
            ),
        )
        self.assertEqual(
            (9,),
            tuple(
                slot.slot_index
                for slot in home_city_slots_for_object(HomeCityObjectId.INSTITUTE)
            ),
        )


class HomeCityClientBuildingTypeTests(unittest.TestCase):
    """Client BuildIdType bindings stay evidence-scoped, never guessed."""

    def test_bound_types_publish_their_semantic_object(self) -> None:
        self.assertEqual(
            HomeCityObjectId.INSTITUTE,
            home_city_client_building_type(1007).object_id,
        )
        self.assertEqual(
            HomeCityObjectId.BLACKSMITH,
            home_city_client_building_type(1008).object_id,
        )
        self.assertEqual(
            HomeCityObjectId.HERO_HALL,
            home_city_client_building_type(5008).object_id,
        )

    def test_unbound_types_stay_unbound(self) -> None:
        for type_id in (1026, 1028, 1029, 1030, 5002, 5005, 5013):
            entry = home_city_client_building_type(type_id)

            self.assertIsNotNone(entry)
            self.assertFalse(entry.bound)
            self.assertIsNone(entry.object_id)

    def test_unknown_client_type_returns_none(self) -> None:
        self.assertIsNone(home_city_client_building_type(9999))
        self.assertIsNone(home_city_client_building_type(1040))


class HomeCitySystemNodeTests(unittest.TestCase):
    """The 15 decoded BuildingSystem rows keep their node paths and levels."""

    def test_system_nodes_match_the_decoded_table(self) -> None:
        nodes = home_city_system_nodes()

        self.assertEqual(15, len(nodes))
        self.assertEqual(
            (5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010, 5011,
             5012, 5014, 5015, 5016),
            tuple(node.client_type_id for node in nodes),
        )
        bank = nodes[0]
        self.assertEqual("sys_1/5001", bank.node_path)
        self.assertEqual(HomeCityObjectId.BANK, bank.object_id)
        self.assertEqual(1, bank.required_castle_level)
        self.assertTrue(all(node.atlas_coordinate is not None for node in nodes))
        self.assertTrue(all(node.coordinate_evidence == _SCENE_PIVOT_EVIDENCE for node in nodes))

    def test_tower_defend_stays_absent_from_the_system_table(self) -> None:
        self.assertNotIn(
            5013, {node.client_type_id for node in home_city_system_nodes()}
        )

    def test_beast_manor_binds_to_illusory_beast_manor_with_geometry(self) -> None:
        """5016 binds through the archived sys_16 marker plus PW destination evidence."""

        entry = home_city_client_building_type(5016)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.bound)
        self.assertIs(HomeCityObjectId.ILLUSORY_BEAST_MANOR, entry.object_id)

        node = next(n for n in home_city_system_nodes() if n.client_type_id == 5016)
        self.assertIs(HomeCityObjectId.ILLUSORY_BEAST_MANOR, node.object_id)
        self.assertIsNotNone(node.atlas_coordinate)


class HomeCitySystemMarkerTests(unittest.TestCase):
    """All 16 extracted sys_* markers publish geometry, declared or not."""

    def test_all_sixteen_markers_publish_calibrated_geometry(self) -> None:
        markers = home_city_system_markers()

        self.assertEqual(16, len(markers))
        self.assertEqual(
            tuple(f"sys_{index}" for index in range(1, 17)),
            tuple(marker.marker for marker in markers),
        )
        for marker in markers:
            self.assertIsNotNone(marker.atlas_coordinate)
            self.assertEqual(_SCENE_PIVOT_EVIDENCE, marker.coordinate_evidence)
            self.assertEqual(
                f"SceneContent/BuildingPosition/{marker.marker}", marker.node_path
            )
            self.assertEqual(5000 + int(marker.marker[4:]), marker.implied_client_type_id)

    def test_sys_13_marker_has_geometry_but_no_declared_node(self) -> None:
        markers = {marker.marker: marker for marker in home_city_system_markers()}
        sys_13 = markers["sys_13"]

        self.assertFalse(sys_13.declared_in_system_table)
        self.assertEqual(5013, sys_13.implied_client_type_id)
        self.assertNotIn(
            5013, {node.client_type_id for node in home_city_system_nodes()}
        )

    def test_declared_nodes_derive_their_pivot_from_the_same_marker(self) -> None:
        marker_by_type = {
            marker.implied_client_type_id: marker
            for marker in home_city_system_markers()
        }
        for node in home_city_system_nodes():
            self.assertEqual(
                marker_by_type[node.client_type_id].atlas_coordinate,
                node.atlas_coordinate,
            )


class HomeCitySceneGeometryTests(unittest.TestCase):
    """Published pivots must reproduce the extracted world positions."""

    def test_every_slot_pivot_derives_from_the_extracted_position(self) -> None:
        records = _scene_geometry_records()
        transform = records["transform"]
        k, tx, ty = transform["k"], transform["tx"], transform["ty"]

        artifact = {row["slot_index"]: row for row in records["ordinary_slots"]}
        for slot in home_city_slot_eligibility():
            row = artifact[slot.slot_index]
            wx, wy, _wz = row["world_position"]
            self.assertEqual(
                HomeCityMapCoordinate(x=round(k * wx + tx), y=round(-k * wy + ty)),
                slot.atlas_coordinate,
            )
            self.assertEqual(_SCENE_PIVOT_EVIDENCE, slot.coordinate_evidence)

    def test_marker_pivots_derive_from_the_extracted_positions(self) -> None:
        records = _scene_geometry_records()
        transform = records["transform"]
        k, tx, ty = transform["k"], transform["tx"], transform["ty"]

        artifact = {row["marker"]: row for row in records["system_markers"]}
        for marker in home_city_system_markers():
            row = artifact[marker.marker]
            wx, wy, _wz = row["world_position"]
            self.assertEqual(
                HomeCityMapCoordinate(x=round(k * wx + tx), y=round(-k * wy + ty)),
                marker.atlas_coordinate,
            )

    def test_negative_and_bottom_pivots_are_not_clipped(self) -> None:
        slots = {slot.slot_index: slot for slot in home_city_slot_eligibility()}

        self.assertTrue(
            all(slots[index].atlas_coordinate.x < 0 for index in (14, 27, 28, 54))
        )
        self.assertEqual(HomeCityMapCoordinate(x=1587, y=3725), slots[50].atlas_coordinate)

    def test_pivot_is_search_geometry_not_a_nameplate_point(self) -> None:
        """Slot pivots are placement pivots, not label or tap points."""

        castle = home_city_slot(1)
        self.assertNotEqual(
            castle.inferred_atlas_coordinate, castle.atlas_coordinate
        )
        # The catalog hint (991,625) is the measured nameplate; the pivot sits
        # ~2.3 world units above it on the slot placement marker.
        self.assertEqual(HomeCityMapCoordinate(x=989, y=371), castle.atlas_coordinate)

    def test_calibration_metadata_carries_extent_and_uncertainty(self) -> None:
        calibration = home_city_scene_calibration()

        self.assertAlmostEqual(108.24698772671348, calibration.scale)
        self.assertEqual(6.0, calibration.uncertainty_reference_px)
        self.assertLessEqual(
            calibration.leave_one_out_max_reference_px,
            calibration.uncertainty_reference_px,
        )
        self.assertEqual("5.0.203/233", calibration.archived_build)
        self.assertAlmostEqual(-332.2803, calibration.extent.min_x, places=3)
        self.assertAlmostEqual(2357.2244, calibration.extent.max_x, places=3)
        self.assertAlmostEqual(370.6231, calibration.extent.min_y, places=3)
        self.assertAlmostEqual(3724.9806, calibration.extent.max_y, places=3)

    def test_fit_reproduces_its_recorded_anchors_within_uncertainty(self) -> None:
        """The published transform reprojects every measured anchor in range."""

        records = _scene_geometry_records()
        transform = records["transform"]
        k, tx, ty = transform["k"], transform["tx"], transform["ty"]
        uncertainty = records["calibration"]["uncertainty_reference_px"]

        for anchor in records["calibration"]["fit_anchors"]:
            wx, wy, _wz = anchor["label_world_position"]
            measured_x, measured_y = anchor["measured_mean_atlas"]
            residual = (
                (k * wx + tx - measured_x) ** 2 + (-k * wy + ty - measured_y) ** 2
            ) ** 0.5
            self.assertLessEqual(residual, uncertainty, anchor["object_id"])
            self.assertLessEqual(anchor["leave_one_out_error_px"], uncertainty)


class HomeCityMapCoordinateTests(unittest.TestCase):
    """Signed calibrated coordinates are valid; malformed values are not."""

    def test_signed_coordinates_are_accepted(self) -> None:
        coordinate = HomeCityMapCoordinate(x=-332, y=972)

        self.assertEqual(-332, coordinate.x)
        self.assertEqual(972, coordinate.y)

    def test_non_integer_coordinates_are_rejected(self) -> None:
        for bad in ("10", 1.5, True, None):
            with self.assertRaises(ValueError):
                HomeCityMapCoordinate(x=bad, y=0)  # type: ignore[arg-type]
            with self.assertRaises(ValueError):
                HomeCityMapCoordinate(x=0, y=bad)  # type: ignore[arg-type]


class HomeCitySlotOccupancyTests(unittest.TestCase):
    """Occupancy is runtime evidence and cannot be fabricated statically."""

    def test_occupied_slot_requires_an_observed_occupant_and_evidence(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            HomeCitySlotOccupancy(
                slot_index=11,
                state=HomeCitySlotOccupancyState.OCCUPIED,
                observed_object_id=None,
                evidence="frame",
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCitySlotOccupancy(
                slot_index=11,
                state=HomeCitySlotOccupancyState.OCCUPIED,
                observed_object_id=HomeCityObjectId.BLACKSMITH,
                evidence="",
            )

    def test_non_occupied_slot_cannot_publish_an_occupant(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            HomeCitySlotOccupancy(
                slot_index=11,
                state=HomeCitySlotOccupancyState.EMPTY,
                observed_object_id=HomeCityObjectId.BLACKSMITH,
                evidence="frame",
            )

    def test_observed_occupancy_stays_scoped_to_its_evidence(self) -> None:
        occupancy = HomeCitySlotOccupancy(
            slot_index=11,
            state=HomeCitySlotOccupancyState.OCCUPIED,
            observed_object_id=HomeCityObjectId.BLACKSMITH,
            evidence="camera_match:blacksmith_structure",
        )

        self.assertEqual(HomeCityObjectId.BLACKSMITH, occupancy.observed_object_id)


if __name__ == "__main__":
    unittest.main()
