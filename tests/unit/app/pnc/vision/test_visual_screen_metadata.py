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
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
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
        self.assertEqual(69, len(catalog["profiles"]))
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
                fixture_key = fixture.relative_to(DATA_ROOT).as_posix() if fixture.is_relative_to(DATA_ROOT) else None
                if profile["review"]["reference_manifest"] == "tests/data/screen_recognition/manifest.json":
                    self.assertIn(fixture_key, references)
                    sample = references[fixture_key]
                    self.assertEqual(sample["sha256"], source["decoded_sha256"])
                    self.assertEqual(sample["group"], source["capture_group"])
                    self.assertEqual("tests/data/screen_recognition/manifest.json", profile["review"]["reference_manifest"])
                else:
                    self.assertEqual("tests/data/game_first_navigation/provenance.json", profile["review"]["reference_manifest"])
                self.assertEqual("guarded_reference_only", profile["review"]["qualification"])
                if profile["id"] == "player_mail_mailbox_list":
                    self.assertEqual("5.2.76 / AppVersion 5.0.204.235", profile["review"]["build"])
                    self.assertEqual("English", profile["review"]["locale"])
                elif profile["id"] in {
                    "loading_configured_game_launch",
                    "alliance_invitation_portrait",
                    "alliance_join_landing",
                    "bag_arena_chest_preview",
                    "campaign_map_chapter_6",
                    "trial_challenge_live",
                }:
                    self.assertEqual(
                        "5.2.80" if profile["id"] in {
                            "bag_arena_chest_preview",
                            "campaign_map_chapter_6",
                            "trial_challenge_live",
                        } else "5.2.77 / AppVersion 5.0.201.227",
                        profile["review"]["build"],
                    )
                    self.assertEqual("English", profile["review"]["locale"])
                else:
                    self.assertIsNone(profile["review"]["build"])
                    self.assertIsNone(profile["review"]["locale"])
                expected_revision = (
                    3
                    if profile["id"] == "bag"
                    else 2
                    if profile["id"] in {
                        "institute",
                        "hero_hall",
                        "alliance_invitation",
                        "world_map",
                        "campaign_chapter_10",
                        "campaign_stage_10_3",
                    }
                    else 1
                )
                self.assertEqual(expected_revision, profile["revision"])

        recognizer = load_visual_screen_recognizer()
        self.assertEqual(69, len(recognizer.profiles))
        self.assertTrue(all(profile.review.qualification == "guarded_reference_only" for profile in recognizer.profiles))

        class _MatchAll:
            def prepare_frame(self, image, *, reference_size):
                del reference_size
                return image

            def find_best_match(self, image, template_path, *, threshold, search_region):
                del image, template_path, threshold, search_region
                return object()

        recognition = load_visual_screen_recognizer(matcher=_MatchAll()).recognize(Image.new("RGB", (540, 960)))
        self.assertEqual(50, len({item.screen_type for item in recognition.evidence}))
        # Alternate appearances can share a layout and retain separate source
        # revisions; each evidence item must preserve its matched profile's one.
        revisions = {f"visual_anchor:{profile['id']}": profile["revision"] for profile in catalog["profiles"]}
        self.assertTrue(all(item.layout_revision == revisions[item.reason] for item in recognition.evidence))

    def test_profile_controls_are_declared_for_their_screen(self) -> None:
        """Keep visual control publication aligned with selector ownership metadata."""

        registry = build_default_selector_registry()
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        for profile in catalog["profiles"]:
            screen = ScreenType[profile["screen"]]
            for control in profile.get("controls", ()):
                selector = registry.require(UiElementId(control["selector"]))
                with self.subTest(profile=profile["id"], selector=control["selector"]):
                    self.assertIn(screen, selector.screens)

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

        popup_control_mutations = (
            lambda document: next(
                profile for profile in document["profiles"] if profile["id"] == "alliance_invitation"
            )["controls"][0].pop("popup_control_kind"),
            lambda document: next(
                profile for profile in document["profiles"] if profile["id"] == "alliance_invitation"
            )["controls"][0].update(popup_control_kind="update_confirm"),
            lambda document: next(
                profile for profile in document["profiles"] if profile["id"] == "vip_daily_reset"
            )["controls"][0].update(popup_control_kind="cancel"),
            lambda document: next(
                profile for profile in document["profiles"] if profile["id"] == "alliance_invitation"
            )["controls"][0].update(dismisses_surface=False),
        )
        for mutate in popup_control_mutations:
            with self.subTest(popup_control_mutation=mutate):
                document = copy.deepcopy(original)
                mutate(document)
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
