
"""Campaign frame and fixture provenance contracts."""

from __future__ import annotations
import json
from pathlib import Path
import unittest
from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import DetectionKind, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.support.pnc.campaign import CAMPAIGN_CHALLENGE_BOX, FIXTURES, _builder, _capture, _image, _navigation_perception


class CampaignFrameAndProvenanceTests(unittest.TestCase):
    def test_navigation_perception_publishes_campaign_rows_with_provenance(self) -> None:
        cases = (
            (
                "campaign_map.png",
                (
                    OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
                    OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
                ),
                ListEntryKind.CAMPAIGN_CHAPTER,
                ScreenType.PNC_CAMPAIGN_MAP,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (
                    OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
                    OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
                ),
                ListEntryKind.CAMPAIGN_STAGE,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                "campaign_chapter_10",
            ),
        )
        for name, lines, kind, screen, layout_id in cases:
            with self.subTest(name=name):
                capture = _capture(_image(name))
                observation = _navigation_perception(lines).build(capture, include_content=True)
                entries = observation.entries(kind)
                self.assertEqual(observation.screen_type, screen)
                self.assertTrue(entries)
                for entry in entries:
                    self.assertIsNotNone(entry.campaign_node)
                    self.assertEqual(entry.source_screen, screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                    self.assertNotIn("mode", entry.metadata)
                if screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIsNotNone(observation.campaign_chapter)
                    self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
                    control = observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.source_screen, screen)
                    self.assertEqual(control.source_layout_id, layout_id)
                    self.assertEqual(control.frame_ref, capture.frame_ref)

    def test_campaign_registry_and_reviewed_edges_are_canonical(self) -> None:
        registry = build_default_selector_registry()
        stage_node = registry.require(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE)
        self.assertEqual(stage_node.status.value, "planned")
        self.assertEqual(stage_node.detection_kind, DetectionKind.SEMANTIC)
        self.assertEqual(stage_node.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertFalse(stage_node.materialize_relative_bounds)

        battle = registry.require(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON)
        self.assertEqual(battle.status.value, "planned")
        self.assertEqual(battle.detection_kind, DetectionKind.SEMANTIC)
        self.assertEqual(battle.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertFalse(battle.materialize_relative_bounds)
        stage_profile = next(
            profile for profile in load_visual_screen_recognizer().profiles if profile.id == "campaign_stage_10_3"
        )
        challenge_anchor = next(
            control.anchor
            for control in stage_profile.controls
            if control.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(challenge_anchor.search_region, CAMPAIGN_CHALLENGE_BOX)
        entry = registry.require(UiElementId.PNC_CAMPAIGN_ENTRY_BUTTON)
        self.assertEqual(entry.detection_kind, DetectionKind.UNSUPPORTED)
        selector = registry.require(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
        self.assertEqual(selector.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(selector.click_outcomes[0].target_screen, ScreenType.PNC_HOME_CITY)
        self.assertTrue(selector.click_outcomes[0].safe_to_click)
        self.assertFalse(selector.click_outcomes[0].monetized)
        self.assertIn(
            (
                ScreenType.PNC_CAMPAIGN_MAP,
                UiElementId.PNC_CAMPAIGN_HOME_PORTAL,
                frozenset({ScreenType.PNC_HOME_CITY}),
            ),
            tuple((edge.source, edge.selector, edge.destinations) for edge in reviewed_navigation_edges()),
        )

        expected_returns = (
            (
                UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ScreenType.PNC_CAMPAIGN_MAP,
            ),
            (
                UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                ScreenType.PNC_CAMPAIGN_STAGE,
                ScreenType.PNC_CAMPAIGN_CHAPTER,
            ),
        )
        edges = tuple((edge.source, edge.selector, edge.destinations) for edge in reviewed_navigation_edges())
        registry = build_default_selector_registry()
        for selector_id, source, destination in expected_returns:
            with self.subTest(selector=selector_id):
                definition = registry.require(selector_id)
                self.assertEqual(definition.interaction_kind, SelectorInteractionKind.NAVIGATION)
                self.assertEqual(definition.click_outcomes[0].target_screen, destination)
                self.assertTrue(definition.click_outcomes[0].safe_to_click)
                self.assertFalse(definition.click_outcomes[0].monetized)
                self.assertIn((source, selector_id, frozenset({destination})), edges)

    def test_campaign_fixture_and_challenge_provenance_are_explicit(self) -> None:
        manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
        samples = {sample["image"]: sample for sample in manifest["samples"]}
        provenance = json.loads((FIXTURES / "replacement_core_provenance.json").read_text(encoding="utf-8"))
        by_asset = {item["asset"]: item for item in provenance}
        recognizer = load_visual_screen_recognizer()
        stage = next(profile for profile in recognizer.profiles if profile.id == "campaign_stage_10_3")
        sample = samples[Path(stage.source.fixture).name]
        self.assertEqual(sample["sha256"], stage.source.decoded_sha256)
        self.assertEqual(sample["group"], stage.source.capture_group)
        self.assertEqual(sample["split"], "reference")
        challenge = by_asset["screen_anchors/campaign_challenge_button.png"]
        self.assertEqual(challenge["reference_size"], [540, 960])
        self.assertEqual(challenge["crop"], [178, 643, 362, 697])
        self.assertEqual(challenge["capture_group"], stage.source.capture_group)
        self.assertEqual(challenge["source_sha256"], by_asset["tests/data/screen_recognition/campaign_stage_10_3.png"]["source_sha256"])
        stage_three = by_asset["screen_anchors/campaign_stage_three.png"]
        self.assertEqual(stage_three["reference_size"], [540, 960])
        self.assertEqual(stage_three["crop"], [301, 591, 351, 644])
        self.assertEqual(stage_three["capture_group"], "2026-09-12/serious_stuff/campaign_navigation")
        self.assertEqual(
            stage_three["source_sha256"],
            by_asset["tests/data/screen_recognition/campaign_chapter_10.png"]["source_sha256"],
        )
        chapter_six = next(
            profile for profile in recognizer.profiles if profile.id == "campaign_chapter_6"
        )
        chapter_six_sample = samples[Path(chapter_six.source.fixture).name]
        self.assertEqual(chapter_six_sample["sha256"], chapter_six.source.decoded_sha256)
        self.assertEqual(chapter_six_sample["group"], chapter_six.source.capture_group)
        self.assertEqual(chapter_six_sample["split"], "reference")
        for asset in (
            "screen_anchors/campaign_chapter_6_path_title.png",
            "screen_anchors/campaign_chapter_6_path_terrain.png",
        ):
            with self.subTest(asset=asset):
                anchor = by_asset[asset]
                self.assertEqual(anchor["reference_size"], [540, 960])
                self.assertEqual(anchor["capture_group"], chapter_six.source.capture_group)
                self.assertEqual(
                    anchor["source_sha256"],
                    by_asset["tests/data/screen_recognition/campaign_chapter_6_path.png"][
                        "source_sha256"
                    ],
                )
        for asset in (
            "screen_anchors/campaign_map_padlock.png",
            "screen_anchors/campaign_map_padlock_alt.png",
        ):
            with self.subTest(asset=asset):
                anchor = by_asset[asset]
                self.assertEqual(anchor["reference_size"], [540, 960])
                self.assertEqual(
                    anchor["capture_group"], "2026-09-15/vision_live_tour_20260915"
                )
                self.assertEqual(
                    anchor["source_sha256"],
                    by_asset["tests/data/screen_recognition/campaign_map_chapter_6.png"][
                        "source_sha256"
                    ],
                )

    def test_native_grandia_animation_frames_keep_map_and_owned_home_control(self) -> None:
        """The captured node animation cannot make a clear map lose its return route."""
        for name in (
            "campaign_map_grandia_pulse_20260922.png",
            "campaign_map_grandia_return_20260922.png",
        ):
            capture = _capture(_image(name))
            for publisher in ("builder", "navigation"):
                with self.subTest(frame=name, publisher=publisher):
                    observation = (
                        _builder().build(capture)
                        if publisher == "builder"
                        else _navigation_perception().build(capture)
                    )
                    self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, observation.screen_type)
                    self.assertEqual("clear", observation.decision.guard.value)
                    control = observation.get(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
                    self.assertIsNotNone(control)
                    self.assertEqual(capture.frame_ref, control.frame_ref)


if __name__ == "__main__":
    unittest.main()
