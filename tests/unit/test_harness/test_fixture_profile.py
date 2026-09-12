"""Portable fixture selection must never consult machine-local configuration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.local_fixture_artifacts import require_local_fixture_artifact


class PortableFixtureProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        module_path = self.root / "tests" / "local_fixture_artifacts.py"
        module_patch = patch("tests.local_fixture_artifacts.__file__", str(module_path))
        module_patch.start()
        self.addCleanup(module_patch.stop)
        profile_patch = patch.dict(os.environ, {"PNC_TEST_FIXTURE_PROFILE": "portable"})
        profile_patch.start()
        self.addCleanup(profile_patch.stop)
        loader_patch = patch(
            "tests.local_fixture_artifacts._load_fixture_document",
            side_effect=AssertionError("portable tests read machine-local config"),
        )
        self.local_loader = loader_patch.start()
        self.addCleanup(loader_patch.stop)

    def test_missing_default_skips_without_reading_local_config(self) -> None:
        with self.assertRaisesRegex(unittest.SkipTest, "Portable offline profile"):
            require_local_fixture_artifact(
                "screenshot", default_repo_relative_path="tests/data/missing.png"
            )
        self.local_loader.assert_not_called()

    def test_no_default_skips_without_reading_local_config(self) -> None:
        with self.assertRaisesRegex(unittest.SkipTest, "Portable offline profile"):
            require_local_fixture_artifact("screenshot")
        self.local_loader.assert_not_called()

    def test_existing_default_returns_without_reading_local_config(self) -> None:
        default = self.root / "tests" / "data" / "portable.png"
        default.parent.mkdir(parents=True)
        default.touch()
        actual = require_local_fixture_artifact(
            "screenshot", default_repo_relative_path="tests/data/portable.png"
        )
        self.assertEqual(actual, default)
        self.assertTrue(actual.is_file())
        self.local_loader.assert_not_called()

    def test_default_directory_is_not_a_fixture_and_does_not_enable_local_config(self) -> None:
        directory = self.root / "tests" / "data"
        directory.mkdir(parents=True)
        with self.assertRaisesRegex(unittest.SkipTest, "Portable offline profile"):
            require_local_fixture_artifact(
                "screenshot", default_repo_relative_path="tests/data"
            )
        self.local_loader.assert_not_called()
