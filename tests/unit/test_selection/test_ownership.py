"""Strict ownership schema and segment-based group membership."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from tools.test_selection.models import inventory
from tools.test_selection.ownership import OwnershipRules, group_matches, load_rules


TESTS = inventory([
    "tests/unit/core/vision/test_match.py",
    "tests/unit/core/visionary/test_unrelated.py",
    "tests/unit/entrypoints/test_helper.py",
    "tests/contract/entrypoints/test_api.py",
    "tests/integration/entrypoints/test_runner.py",
    "tests/contract/public_exports/test_exports.py",
    "tests/architecture/test_imports.py",
])


class GroupTests(unittest.TestCase):
    def test_tiers_components_and_qualified_groups(self) -> None:
        expectations = {
            "unit": {"tests.unit.core.vision.test_match", "tests.unit.core.visionary.test_unrelated", "tests.unit.entrypoints.test_helper"},
            "core": {"tests.unit.core.vision.test_match", "tests.unit.core.visionary.test_unrelated"},
            "unit.core.vision": {"tests.unit.core.vision.test_match"},
            "core.vision": {"tests.unit.core.vision.test_match"},
            "architecture": {"tests.architecture.test_imports"},
            "missing": set(),
            "core.vis": set(),
            "uni": set(),
            "": set(),
        }
        for group, expected in expectations.items():
            with self.subTest(group=group):
                self.assertEqual({t.module for t in TESTS if group_matches(t, group)}, expected)

    def test_api_includes_contract_integration_and_exports(self) -> None:
        self.assertEqual(
            {t.module for t in TESTS if group_matches(t, "api")},
            {"tests.contract.entrypoints.test_api", "tests.integration.entrypoints.test_runner",
             "tests.contract.public_exports.test_exports"},
        )

    def test_vision_alias_requires_complete_segment(self) -> None:
        self.assertEqual(
            {t.module for t in TESTS if group_matches(t, "vision")},
            {"tests.unit.core.vision.test_match"},
        )


class RuleLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="selection-rules-")
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "rules.yaml"
        self.valid = {
            "version": 1, "full": ["pyproject.toml"], "documentation": ["*.md"],
            "resources": [{"pattern": "assets/*", "groups": ["vision"]}],
        }

    def load(self, document: object) -> OwnershipRules:
        self.path.write_text(json.dumps(document), encoding="utf-8")
        return load_rules(self.path, TESTS)

    def test_valid_rules_are_typed_and_match_nested_resources(self) -> None:
        rules = self.load(self.valid)
        self.assertEqual(rules.full, ("pyproject.toml",))
        self.assertEqual(rules.documentation, ("*.md",))
        self.assertEqual(rules.resource_groups("assets/nested/button.png"), ("vision",))
        self.assertEqual(rules.resource_groups("unowned.json"), ())

    def test_overlapping_resource_owners_are_additive(self) -> None:
        self.valid["resources"].append({"pattern": "assets/*.png", "groups": ["integration", "vision"]})
        self.assertEqual(self.load(self.valid).resource_groups("assets/button.png"), ("integration", "vision"))

    def test_empty_rules_are_valid(self) -> None:
        rules = self.load({"version": 1, "full": [], "documentation": [], "resources": []})
        self.assertEqual(rules.resources, ())

    def test_rejects_non_mapping_missing_extra_and_wrong_version(self) -> None:
        documents = [None, [], "rules", {}, {**self.valid, "extra": []}]
        documents.extend({**self.valid, "version": version} for version in [True, False, 0, 2, "1", 1.0, None])
        documents.extend({k: v for k, v in self.valid.items() if k != missing} for missing in self.valid)
        for document in documents:
            with self.subTest(document=document), self.assertRaises(ValueError):
                self.load(document)

    def test_rejects_invalid_string_lists(self) -> None:
        for field in ("full", "documentation"):
            for value in (None, "*.py", {}, [1], [""], ["  "], ["a", "a"], ["a", None]):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.load({**self.valid, field: value})

    def test_rejects_invalid_resource_shapes(self) -> None:
        values = [None, {}, "assets/*", [None], ["assets/*"], [{}],
                  [{"pattern": "a"}], [{"groups": ["unit"]}],
                  [{"pattern": "a", "groups": ["unit"], "exclude": True}]]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.load({**self.valid, "resources": value})

    def test_rejects_empty_unknown_or_duplicate_owners(self) -> None:
        for groups in ([], ["absent"], ["vision", "absent"], ["vision", "vision"], "vision", [None], [" "]):
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                self.load({**self.valid, "resources": [{"pattern": "assets/*", "groups": groups}]})

    def test_rejects_empty_nonstring_or_duplicate_patterns(self) -> None:
        for pattern in ("", None, 3, ["assets/*"]):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError):
                self.load({**self.valid, "resources": [{"pattern": pattern, "groups": ["vision"]}]})
        document = copy.deepcopy(self.valid)
        document["resources"].append({"pattern": "assets/*", "groups": ["api"]})
        with self.assertRaises(ValueError):
            self.load(document)

    def test_missing_rule_file_reports_io_error(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_rules(self.path, TESTS)

    def test_yaml_tags_cannot_construct_python_objects(self) -> None:
        self.path.write_text("!!python/object/apply:builtins.print ['must not execute']", encoding="utf-8")
        with self.assertRaises(yaml.YAMLError):
            load_rules(self.path, TESTS)

    def test_rejects_whitespace_only_resource_pattern(self) -> None:
        with self.assertRaises(ValueError):
            self.load({**self.valid, "resources": [{"pattern": "  ", "groups": ["vision"]}]})
