"""Provenance and strict schema checks for the guarded visual screen catalog."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from tools.benchmark_screen_recognition import _decoded_image_sha256
from tests.support.paths import REPOSITORY_ROOT, TEST_DATA_ROOT


DATA_ROOT = TEST_DATA_ROOT / "screen_recognition"
CATALOG_PATH = REPOSITORY_ROOT / "pnc_automation" / "app" / "pnc" / "vision" / "data" / "screen_anchors.json"
MANIFEST_PATH = DATA_ROOT / "manifest.json"


class VisualScreenMetadataTests(unittest.TestCase):
    """Keep source provenance strict without making artifacts runtime dependencies."""

    def test_all_profiles_match_the_frozen_reference_manifest(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        references = {
            sample["image"]: sample
            for sample in manifest["samples"]
            if sample["split"] == "reference"
        }
        self.assertEqual(31, len(catalog["profiles"]))
        for profile in catalog["profiles"]:
            with self.subTest(profile=profile["id"]):
                source = profile["source"]
                fixture = (
                    REPOSITORY_ROOT / source["fixture"]
                    if source["fixture"].startswith("tests/")
                    else DATA_ROOT / source["fixture"]
                )
                self.assertTrue(fixture.is_file())
                with Image.open(fixture) as image:
                    decoded_sha256 = _decoded_image_sha256(image)
                self.assertEqual(decoded_sha256, source["decoded_sha256"])
                if source["fixture"] in references:
                    sample = references[source["fixture"]]
                    self.assertEqual(sample["sha256"], source["decoded_sha256"])
                    self.assertEqual(sample["group"], source["capture_group"])
                    self.assertEqual("tests/data/screen_recognition/manifest.json", profile["review"]["reference_manifest"])
                elif profile["review"]["reference_manifest"] == "tests/data/screen_recognition/manifest.json":
                    self.assertEqual("tests/data/screen_recognition/manifest.json", profile["review"]["reference_manifest"])
                else:
                    self.assertEqual("tests/data/game_first_navigation/provenance.json", profile["review"]["reference_manifest"])
                self.assertEqual("guarded_reference_only", profile["review"]["qualification"])
                self.assertIsNone(profile["review"]["build"])
                self.assertIsNone(profile["review"]["locale"])
                expected_revision = 2 if profile["id"] == "institute" else 1
                self.assertEqual(expected_revision, profile["revision"])

        recognizer = load_visual_screen_recognizer()
        self.assertEqual(31, len(recognizer.profiles))
        self.assertTrue(all(profile.review.qualification == "guarded_reference_only" for profile in recognizer.profiles))

        class _MatchAll:
            def prepare_frame(self, image, *, reference_size):
                del reference_size
                return image

            def find_best_match(self, image, template_path, *, threshold, search_region):
                del image, template_path, threshold, search_region
                return object()

        recognition = load_visual_screen_recognizer(matcher=_MatchAll()).recognize(Image.new("RGB", (540, 960)))
        self.assertEqual(26, len({item.screen_type for item in recognition.evidence}))
        self.assertTrue(
            all(
                item.layout_revision == (2 if item.screen_type == ScreenType.PNC_INSTITUTE else 1)
                for item in recognition.evidence
            )
        )

    def test_malformed_provenance_is_rejected_eagerly(self) -> None:
        original = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        mutations = (
            lambda profile: profile.pop("revision"),
            lambda profile: profile.update(revision=0),
            lambda profile: profile["source"].update(decoded_sha256="bad"),
            lambda profile: profile["source"].update(fixture="../secret.png"),
            lambda profile: profile["review"].pop("qualification"),
            lambda profile: profile["review"].update(qualification="promotion_ready"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                document = copy.deepcopy(original)
                mutate(document["profiles"][0])
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    shutil.copytree(CATALOG_PATH.parent / "screen_anchors", root / "screen_anchors")
                    path = root / "screen_anchors.json"
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_visual_screen_recognizer(path)

        layout_mutations = (
            lambda document: document["profiles"][0].pop("layout_id"),
            lambda document: document["profiles"][0].update(layout_id=""),
            lambda document: document["profiles"][1].update(
                layout_id=document["profiles"][0]["layout_id"],
            ),
        )
        for mutate in layout_mutations:
            with self.subTest(layout_mutation=mutate):
                document = copy.deepcopy(original)
                mutate(document)
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    shutil.copytree(CATALOG_PATH.parent / "screen_anchors", root / "screen_anchors")
                    path = root / "screen_anchors.json"
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_visual_screen_recognizer(path)


if __name__ == "__main__":
    unittest.main()
