
"""Campaign frame and fixture provenance contracts."""

from __future__ import annotations
import json
from pathlib import Path
import unittest
from PIL import Image
from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import DetectionKind, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.campaign import CAMPAIGN_CHALLENGE_BOX, FIXTURES, _CampaignCropOcrService, _builder, _builder_with_backend, _capture, _image, _navigation_perception, _navigation_perception_with_backend


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

    def test_native_chapter6_frames_qualify_with_owned_return_on_both_publishers(self) -> None:
        """Retained 2026-09-22 captures resolve to chapter 6 and keep its owned Back."""
        backend = _require_rapid_ocr_service(self)
        for name in (
            "campaign_chapter_6_path_20260922.png",
            "campaign_chapter_6_path_holdout_20260922.png",
        ):
            capture = _capture(_image(name))
            for publisher in ("builder", "navigation"):
                with self.subTest(frame=name, publisher=publisher):
                    observation = (
                        _builder_with_backend(backend).build(
                            capture, request=ObservationRequest.campaign_map_follow_up()
                        )
                        if publisher == "builder"
                        else _navigation_perception_with_backend(backend).build(
                            capture, include_content=True
                        )
                    )
                    self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
                    self.assertIsNotNone(observation.campaign_chapter)
                    self.assertEqual(observation.campaign_chapter.chapter_number, 6)
                    self.assertEqual(
                        observation.campaign_chapter.source_layout_id, "campaign_chapter_6"
                    )
                    back = observation.visible_elements.get(UiElementId.PNC_CAMPAIGN_BACK_BUTTON)
                    self.assertIsNotNone(back)
                    assert back is not None
                    self.assertEqual(back.source_layout_id, "campaign_chapter_6")
                    self.assertEqual(back.frame_ref, capture.frame_ref)
                    rows = observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                    self.assertTrue(
                        any(
                            row.row_status is RowRecognitionStatus.COMPLETE
                            and row.campaign_node.stage_number == 4
                            for row in rows
                        ),
                        "the 4th stage must publish on the retained path",
                    )

        scaled = _capture(
            _image("campaign_chapter_6_path_20260922.png").resize(
                (540, 960), Image.Resampling.LANCZOS
            )
        )
        for publisher in ("builder", "navigation"):
            with self.subTest(frame="scaled-20260922", publisher=publisher):
                observation = (
                    _builder_with_backend(backend).build(
                        scaled, request=ObservationRequest.campaign_map_follow_up()
                    )
                    if publisher == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        scaled, include_content=True
                    )
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
                self.assertIsNotNone(observation.campaign_chapter)

    def test_stage_detail_facts_publish_through_both_publishers_with_provenance(self) -> None:
        """Both observation paths bind the reviewed stage facts to the stage frame."""
        stage_lines = (
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 0.99),
            OcrLine("150/120", Bounds(368, 590, 84, 24), 0.95),
            OcrLine("12", Bounds(244, 646, 30, 18), 0.95),
        )
        capture = _capture(_image("campaign_stage_10_3.png"))
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                backend = _CampaignCropOcrService(stage_lines)
                observation = (
                    _builder_with_backend(backend).build(
                        capture, request=ObservationRequest.campaign_map_follow_up()
                    )
                    if path == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        capture, include_content=True
                    )
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
                detail = observation.campaign_stage
                self.assertIsNotNone(detail)
                assert detail is not None
                self.assertEqual(detail.chapter_number, 10)
                self.assertEqual(detail.stage_number, 3)
                self.assertEqual(detail.name, "Grandia Ruins")
                self.assertEqual(detail.action_points, 150)
                self.assertEqual(detail.max_action_points, 120)
                self.assertEqual(detail.challenge_cost, 12)
                self.assertIsNone(detail.mode)
                self.assertEqual(detail.source_screen, ScreenType.PNC_CAMPAIGN_STAGE)
                self.assertEqual(detail.source_layout_id, "campaign_stage_10_3")
                self.assertEqual(detail.frame_ref, capture.frame_ref)

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
