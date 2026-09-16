"""Focused tests for the packaged Pet Workshop catalog seed and its schema."""

from __future__ import annotations

import copy
import importlib.resources
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pnc_automation.app.pnc
from pnc_automation.app.pnc.pet_workshop_catalog import (
    PetWorkshopCatalog,
    PetWorkshopCatalogError,
    load_pet_workshop_catalog,
)


def _minimal_document() -> dict[str, Any]:
    """Returns the smallest schema-valid catalog document for mutation tests."""

    return {
        "provenance": {
            "packaged_build": "test",
            "generator": "test",
            "source_tables": {},
        },
        "board": {"columns": 2, "rows": 2},
        "activity": {
            "energy_item_id": 44009010,
            "energy_capacity": 200,
            "production_energy_cost": 1,
            "energy_regen_ms": 300000,
            "cooldown_ms": 20000,
            "cooldown_skip_cost": 50,
            "assist_cost": 2,
            "assist_level": 999,
            "buy_add_productivity": 1,
            "buy_count": 0,
            "buy_costs": [{"count": -10, "type": 1001}],
            "item_limit_raw": "8_5|7_5",
            "item_time_ms": 120000,
            "description": "",
        },
        "items": [
            {
                "id": 1, "name": "Gen", "tips": "", "icon": "a", "tier": 1,
                "type": 1, "sub_type": 1, "sort": 0, "get_type": 1, "exp": 0,
                "merge_successor_id": None, "unlock_cost": 0, "recoverable": False,
                "recycle_reward": None,
            },
            {
                "id": 2, "name": "Piece", "tips": "", "icon": "b", "tier": 1,
                "type": 2, "sub_type": 0, "sort": 0, "get_type": 11, "exp": 0,
                "merge_successor_id": None, "unlock_cost": 0, "recoverable": True,
                "recycle_reward": {"item_id": 44009010, "count": 8, "reward_type": 9},
            },
        ],
        "producers": [
            {
                "item_id": 1, "group_id": 7, "worker_type": 1, "num": 30, "max_num": 0,
                "cooldown_ms": 30000, "change_item_id": None, "feed_item_id": None, "assist": 0,
            },
        ],
        "drop_groups": {"7": [{"item_id": 2, "weight": 600}, {"item_id": 1, "weight": 400}]},
        "grid_cells": [
            {"cell_id": 1, "position": 1, "unlock_level": 0, "unlock_type": 2, "seed_item_ids": [2]},
        ],
        "workshop_levels": [
            {"level": 1, "exp": 0, "productivity": 30, "rewards": [{"item_id": 2, "count": 1}]},
        ],
    }


class PackagedSeedTests(unittest.TestCase):
    """Checks the tracked seed loads through package resources with real relationships."""

    @classmethod
    def setUpClass(cls) -> None:
        """Loads the real packaged seed shared by the catalog relationship checks."""

        cls.catalog = load_pet_workshop_catalog()

    def test_packaged_seed_loads_with_expected_coverage(self) -> None:
        """Verifies that packaged seed loads with expected coverage."""
        catalog = self.catalog
        self.assertEqual(len(catalog.items), 114)
        self.assertEqual(len(catalog.producers), 20)
        self.assertEqual(len(catalog.drop_groups), 20)
        self.assertEqual(len(catalog.cells), 63)
        self.assertEqual(len(catalog.levels), 21)
        self.assertEqual(catalog.provenance.packaged_build, "5.0.203")
        self.assertTrue(catalog.provenance.source_tables)
        for table in catalog.provenance.source_tables:
            self.assertTrue(table.decoded_sha256)
            self.assertTrue(table.source_sha256)
            self.assertGreater(table.rows, 0)
        self.assertEqual((catalog.board.columns, catalog.board.rows), (7, 9))

    def test_catalog_file_is_reachable_as_package_resource(self) -> None:
        """Verifies that catalog file is reachable as package resource."""
        resource = (
            importlib.resources.files("pnc_automation.app.pnc")
            .joinpath("data")
            .joinpath("pet_workshop")
            .joinpath("catalog.json")
        )
        self.assertTrue(resource.is_file())
        with importlib.resources.as_file(resource) as path:
            package_dir = Path(pnc_automation.app.pnc.__file__).resolve().parent
            self.assertTrue(path.resolve().is_relative_to(package_dir))
            catalog = load_pet_workshop_catalog(path)
        self.assertEqual(len(catalog.items), 114)

    def test_real_seed_relationships_and_inherited_defaults(self) -> None:
        """Verifies that real seed relationships and inherited defaults."""
        catalog = self.catalog
        fruit5 = catalog.require_item(20105)
        self.assertEqual(fruit5.name, "Fruit 5")
        self.assertEqual((fruit5.recycle_reward.item_id, fruit5.recycle_reward.count, fruit5.recycle_reward.reward_type), (44009010, 8, 9))
        statue5 = catalog.require_item(10205)
        self.assertEqual((statue5.recycle_reward.count, statue5.recycle_reward.item_id), (8, 44009010))
        # Merge chain facts and the inherited level/successor defaults.
        self.assertEqual(catalog.require_item(20001).merge_successor_id, 20002)
        self.assertIsNone(catalog.require_item(20004).merge_successor_id)
        self.assertIsNone(catalog.require_item(10004).merge_successor_id)
        self.assertEqual(catalog.require_item(10101).tier, 1)
        # Producer records: inherited 30s cooldown, feed ingredient, exhaustion transform.
        map1 = catalog.producer_for(10001)
        self.assertEqual((map1.cooldown_ms, map1.num, map1.group_id), (30000, 50, 1))
        self.assertEqual(catalog.producer_for(50004).feed_item_id, 31103)
        self.assertEqual(catalog.producer_for(40209).change_item_id, 40206)
        self.assertIsNone(catalog.producer_for(20105))
        # Grid/level facts: inherited unlock defaults and authored rewards.
        self.assertEqual((catalog.cell(1).unlock_type, catalog.cell(1).unlock_level), (2, 0))
        self.assertEqual(catalog.cell(1).seed_item_ids, (30101,))
        self.assertEqual(catalog.cell(54).unlock_level, 10)
        self.assertEqual({r.item_id for r in catalog.level(3).rewards}, {20001, 10002})
        self.assertEqual({r.item_id for r in catalog.level(10).rewards}, {40001, 30003, 60001})
        # Energy facts from the activity record.
        self.assertEqual((catalog.activity.energy_capacity, catalog.activity.production_energy_cost), (200, 1))
        self.assertEqual(catalog.activity.energy_item_id, 44009010)

    def test_drop_weights_normalize_by_actual_sums(self) -> None:
        """Verifies that drop weights normalize by actual sums."""
        group66 = self.catalog.drop_group(66)
        self.assertEqual(group66.total_weight, 500)
        self.assertAlmostEqual(group66.probability_of(60101), 0.37)
        self.assertAlmostEqual(group66.probability_of(60203), 0.03)
        self.assertEqual(group66.probability_of(20105), 0.0)
        group1 = self.catalog.drop_group(1)
        self.assertEqual(group1.total_weight, 1000)
        self.assertTrue(any(entry.weight == 0 for entry in group1.entries))
        self.assertEqual(group1.probability_of(10102), 0.0)

    def test_items_excluded_by_policy_remain_representable(self) -> None:
        """Verifies that items excluded by policy remain representable."""
        omni = self.catalog.require_item(100001)
        self.assertEqual(omni.name, "Omni Card")
        self.assertEqual(omni.item_type, 0)
        self.assertEqual(self.catalog.require_item(60101).name, "AP 1")
        self.assertIsNone(self.catalog.producer_for(100001))


class CatalogSchemaTests(unittest.TestCase):
    """Checks the loader fails fast on malformed authored documents."""

    def test_duplicate_json_keys_fail_before_values_are_discarded(self) -> None:
        """An authored duplicate section must not silently replace its earlier value."""

        document = json.dumps(_minimal_document()).replace(
            '"drop_groups": {', '"drop_groups": {}, "drop_groups": {', 1
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text(document, encoding="utf-8")
            with self.assertRaisesRegex(PetWorkshopCatalogError, "Duplicate JSON key 'drop_groups'"):
                load_pet_workshop_catalog(path)

    def test_minimal_document_loads(self) -> None:
        """Verifies that minimal document loads."""
        catalog = PetWorkshopCatalog(_minimal_document())
        self.assertEqual(len(catalog.items), 2)
        self.assertAlmostEqual(catalog.drop_group(7).probability_of(2), 0.6)

    def test_non_1000_group_sum_normalizes(self) -> None:
        """Verifies that non 1000 group sum normalizes."""
        document = _minimal_document()
        document["drop_groups"] = {"7": [{"item_id": 2, "weight": 3}, {"item_id": 1, "weight": 1}]}
        catalog = PetWorkshopCatalog(document)
        self.assertEqual(catalog.drop_group(7).total_weight, 4)
        self.assertAlmostEqual(catalog.drop_group(7).probability_of(2), 0.75)

    def test_duplicate_item_id_fails(self) -> None:
        """Verifies that duplicate item id fails."""
        document = _minimal_document()
        document["items"].append(copy.deepcopy(document["items"][0]))
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_dangling_merge_successor_fails(self) -> None:
        """Verifies that dangling merge successor fails."""
        document = _minimal_document()
        document["items"][1]["merge_successor_id"] = 999
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_dangling_producer_references_fail(self) -> None:
        """Verifies that dangling producer references fail."""
        for field, value in (("item_id", 999), ("group_id", 999), ("feed_item_id", 999), ("change_item_id", 999)):
            document = _minimal_document()
            document["producers"][0][field] = value
            with self.assertRaises(PetWorkshopCatalogError, msg=field):
                PetWorkshopCatalog(document)

    def test_dangling_drop_and_seed_and_reward_references_fail(self) -> None:
        """Verifies that dangling drop and seed and reward references fail."""
        document = _minimal_document()
        document["drop_groups"] = {"7": [{"item_id": 999, "weight": 1}]}
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["grid_cells"][0]["seed_item_ids"] = [999]
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["workshop_levels"][0]["rewards"] = [{"item_id": 999, "count": 1}]
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_nonpositive_required_quantities_fail(self) -> None:
        """Verifies that nonpositive required quantities fail."""
        document = _minimal_document()
        document["items"][1]["tier"] = 0
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["items"][1]["recycle_reward"]["count"] = 0
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["activity"]["energy_capacity"] = 0
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["workshop_levels"][0]["rewards"] = [{"item_id": 2, "count": 0}]
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_nonpositive_group_weight_fails_but_zero_entries_are_kept(self) -> None:
        """Verifies that nonpositive group weight fails but zero entries are kept."""
        document = _minimal_document()
        document["drop_groups"] = {"7": [{"item_id": 2, "weight": 0}]}
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["drop_groups"] = {"7": [{"item_id": 2, "weight": 0}, {"item_id": 1, "weight": 5}]}
        catalog = PetWorkshopCatalog(document)
        self.assertEqual(catalog.drop_group(7).entries[0].weight, 0)
        self.assertEqual(catalog.drop_group(7).probability_of(2), 0.0)
        document = _minimal_document()
        document["drop_groups"] = {"7": [{"item_id": 2, "weight": -1}]}
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_merge_cycle_fails(self) -> None:
        """Verifies that merge cycle fails."""
        document = _minimal_document()
        document["items"][0]["merge_successor_id"] = 2
        document["items"][1]["merge_successor_id"] = 1
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_invalid_grid_coordinates_fail(self) -> None:
        """Verifies that invalid grid coordinates fail."""
        document = _minimal_document()
        document["grid_cells"][0]["position"] = 5
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)
        document = _minimal_document()
        document["grid_cells"].append(
            {"cell_id": 2, "position": 1, "unlock_level": 0, "unlock_type": 0, "seed_item_ids": []}
        )
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)

    def test_missing_section_fails(self) -> None:
        """Verifies that missing section fails."""
        document = _minimal_document()
        del document["items"]
        with self.assertRaises(PetWorkshopCatalogError):
            PetWorkshopCatalog(document)


if __name__ == "__main__":
    unittest.main()
