"""Configured rules retain contract safety and narrow feature helpers."""

from pathlib import Path
import unittest

from tools.test_selection.models import inventory
from tools.test_selection.ownership import load_rules
from tools.test_selection.planner import affected_plan

ROOT = Path(__file__).resolve().parents[3]


class ScopedOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tests = inventory([
            "tests/unit/app/pnc/domain/test_sample.py",
            "tests/unit/app/pnc/vision/test_sample.py",
            "tests/unit/app/pnc/vision/home_city_camera/test_bodies.py",
            "tests/unit/app/pnc/navigation/test_sample.py",
            "tests/unit/tools/agent_runtime/test_devin_worker.py",
            "tests/integration/sample/test_capture.py",
            "tests/integration/vision/home_city_camera/test_publishers.py",
            "tests/contract/sample/test_api.py",
            "tests/architecture/test_imports.py",
        ])
        self.rules = load_rules(ROOT / "tests/selection_rules.yaml", self.tests)
        self.sources = {test.path: "pass\n" for test in self.tests}
        self.helper = "tests/support/pnc/capture_vision/feature.py"
        self.domain = "pnc_automation/app/pnc/domain/sample.py"
        self.sources.update({
            self.helper: "def make_frame():\n    return 1\n",
            self.domain: "def value():\n    return 1\n",
            "tests/unit/app/pnc/vision/test_sample.py": "from tests.support.pnc.capture_vision.feature import make_frame\n",
            "tests/unit/app/pnc/domain/test_sample.py": "from pnc_automation.app.pnc.domain.sample import value\n",
            "tests/contract/sample/test_api.py": "from pnc_automation.app.pnc.domain.sample import value\n",
        })

    def test_scoped_helper_selects_consumers_and_architecture(self) -> None:
        plan = affected_plan(self.tests, self.rules, [self.helper], self.sources, self.sources, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.app.pnc.vision.test_sample",
            "tests.architecture.test_imports",
        })

    def test_domain_body_edit_does_not_select_unrelated_vision(self) -> None:
        updated = {**self.sources, self.domain: "def value():\n    return 2\n"}
        plan = affected_plan(self.tests, self.rules, [self.domain], self.sources, updated, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertNotIn("tests.unit.app.pnc.vision.test_sample", plan.reasons)
        self.assertIn("tests.unit.app.pnc.domain.test_sample", plan.reasons)

    def test_home_slot_body_fixture_selects_its_two_camera_groups(self) -> None:
        owned = "tests/data/home_city_slot_bodies/home_city_watchtower_slot4_0050_20260930.png"
        for path in (owned, "tests/data/home_city_slot_bodies/manifest.json"):
            with self.subTest(path=path):
                plan = affected_plan(self.tests, self.rules, [path], self.sources, self.sources, "base", "head")
                self.assertFalse(plan.fallbacks)
                self.assertEqual(set(plan.reasons), {
                    "tests.unit.app.pnc.vision.home_city_camera.test_bodies",
                    "tests.integration.vision.home_city_camera.test_publishers",
                    "tests.architecture.test_imports",
                })

    def test_packaged_camera_crop_also_selects_its_navigation_readers(self) -> None:
        path = "pnc_automation/app/pnc/vision/data/home_city_camera/watchtower_body.png"
        plan = affected_plan(self.tests, self.rules, [path], self.sources, self.sources, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.app.pnc.vision.test_sample",
            "tests.unit.app.pnc.vision.home_city_camera.test_bodies",
            "tests.unit.app.pnc.navigation.test_sample",
            "tests.integration.sample.test_capture",
            "tests.integration.vision.home_city_camera.test_publishers",
            "tests.architecture.test_imports",
        })

    def test_sibling_vision_data_path_keeps_broad_groups_without_navigation(self) -> None:
        path = "pnc_automation/app/pnc/vision/data/screen_anchors/campaign_back_button.png"
        plan = affected_plan(self.tests, self.rules, [path], self.sources, self.sources, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertNotIn("tests.unit.app.pnc.navigation.test_sample", plan.reasons)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.app.pnc.vision.test_sample",
            "tests.unit.app.pnc.vision.home_city_camera.test_bodies",
            "tests.integration.sample.test_capture",
            "tests.integration.vision.home_city_camera.test_publishers",
            "tests.architecture.test_imports",
        })

    def test_unowned_fixture_path_keeps_unknown_resource_fallback(self) -> None:
        for path in ("tests/data/screen_recognition/home_city_new.png",
                     "tests/data/pet_workshop/analysis_labels.json"):
            with self.subTest(path=path):
                plan = affected_plan(self.tests, self.rules, [path], self.sources, self.sources, "base", "head")
                self.assertTrue(any("unknown non-Python dependency" in reason for reason in plan.fallbacks))
                self.assertEqual(set(plan.reasons), {test.module for test in self.tests})

    def test_shared_screen_manifests_stay_conservative(self) -> None:
        for path in ("tests/data/screen_recognition/manifest.json",
                     "tests/data/screen_recognition/replacement_core_provenance.json"):
            with self.subTest(path=path):
                plan = affected_plan(self.tests, self.rules, [path], self.sources, self.sources, "base", "head")
                self.assertTrue(any("shared contract/infrastructure" in reason for reason in plan.fallbacks))
                self.assertEqual(set(plan.reasons), {test.module for test in self.tests})

    def test_mixed_owned_and_unknown_fixture_falls_back(self) -> None:
        changed = ["tests/data/home_city_slot_bodies/home_city_new_slot_0099_20260930.png",
                   "tests/data/world_map/anchor.png"]
        plan = affected_plan(self.tests, self.rules, changed, self.sources, self.sources, "base", "head")
        self.assertTrue(any("unknown non-Python dependency" in reason for reason in plan.fallbacks))
        self.assertEqual(set(plan.reasons), {test.module for test in self.tests})

    def test_public_domain_signature_change_selects_its_contract_and_owner(self) -> None:
        updated = {**self.sources, self.domain: "def value(arg):\n    return arg\n"}
        plan = affected_plan(self.tests, self.rules, [self.domain], self.sources, updated, "base", "head")
        self.assertFalse(plan.fallbacks)
        self.assertEqual(set(plan.reasons), {
            "tests.unit.app.pnc.domain.test_sample", "tests.contract.sample.test_api",
            "tests.architecture.test_imports",
        })
