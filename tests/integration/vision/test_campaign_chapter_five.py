"""Qualify the live Costa Dorad path and its measured return control."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.integration.vision.test_campaign_visual_profiles import (
    _builder,
    _builder_with_backend,
    _capture,
    _image,
    _navigation_perception,
    _navigation_perception_with_backend,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)


class CampaignChapterFiveTests(unittest.TestCase):
    """The actual entrance animation and settled path share truthful identity."""

    def test_recentered_map_keeps_the_owned_home_portal(self) -> None:
        for size in ((540, 960), (900, 1600)):
            capture = _capture(_image("campaign_map_recentered_20260916.png").resize(size, Image.Resampling.LANCZOS))
            for publisher in ("builder", "navigation"):
                with self.subTest(size=size, publisher=publisher):
                    observation = (
                        _builder().build(capture)
                        if publisher == "builder"
                        else _navigation_perception().build(capture, include_content=True)
                    )
                    self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, observation.screen_type)
                    portal = observation.get(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
                    self.assertIsNotNone(portal)
                    self.assertEqual(capture.frame_ref, portal.frame_ref)
                    self.assertFalse(observation.has(UiElementId.PNC_CAMPAIGN_BACK_BUTTON))

    def test_live_path_and_entrance_animation_keep_the_owned_return(self) -> None:
        for name in (
            "campaign_chapter_5_path_20260916.png",
            "campaign_chapter_5_loading_20260916.png",
        ):
            for size in ((540, 960), (900, 1600)):
                capture = _capture(_image(name).resize(size, Image.Resampling.LANCZOS))
                for publisher in ("builder", "navigation"):
                    with self.subTest(frame=name, size=size, publisher=publisher):
                        observation = (
                            _builder().build(capture)
                            if publisher == "builder"
                            else _navigation_perception().build(capture, include_content=True)
                        )
                        self.assertEqual(ScreenType.PNC_CAMPAIGN_CHAPTER, observation.screen_type)
                        self.assertEqual("campaign_chapter_5", observation.decision.layout_id)
                        back = observation.get(UiElementId.PNC_CAMPAIGN_BACK_BUTTON)
                        self.assertIsNotNone(back)
                        self.assertEqual(capture.frame_ref, back.frame_ref)

    def test_real_ocr_binds_current_chapter_and_visible_stage_numbers(self) -> None:
        backend = _require_rapid_ocr_service(self)
        capture = _capture(_image("campaign_chapter_5_path_20260916.png"))
        for publisher in ("builder", "navigation"):
            with self.subTest(publisher=publisher):
                observation = (
                    _builder_with_backend(backend).build(capture)
                    if publisher == "builder"
                    else _navigation_perception_with_backend(backend).build(capture, include_content=True)
                )
                self.assertEqual(5, observation.campaign_chapter.chapter_number)
                self.assertEqual(capture.frame_ref, observation.campaign_chapter.frame_ref)
                stages = observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                self.assertEqual(9, len(stages))
                complete = [
                    row
                    for row in stages
                    if row.row_status is RowRecognitionStatus.COMPLETE
                ]
                self.assertEqual(
                    {1, 2, 3, 5, 6, 8, 9},
                    {row.campaign_node.stage_number for row in complete},
                )
                unreadable = [
                    row
                    for row in stages
                    if row.row_status is RowRecognitionStatus.UNREADABLE
                ]
                self.assertEqual(2, len(unreadable))
                self.assertEqual(
                    {Bounds(615, 728, 75, 75), Bounds(537, 357, 72, 72)},
                    {marker.bounds for marker in unreadable},
                )
                for marker in unreadable:
                    self.assertIsNone(marker.campaign_node.stage_number)
                    self.assertIs(marker.campaign_node.locked, False)
                    self.assertIsNone(marker.action_point)
                    self.assertIsNone(marker.action_bounds)
                for row in stages:
                    self.assertEqual(5, row.campaign_node.chapter_number)
                    self.assertEqual(capture.frame_ref, row.frame_ref)
                    self.assertIsNone(row.campaign_node.mode)
                    self.assertIsNone(row.campaign_node.completed)

    def test_missing_title_does_not_publish_a_return_control(self) -> None:
        image = _image("campaign_chapter_5_path_20260916.png")
        ImageDraw.Draw(image).rectangle((450, 87, 882, 149), fill=(0, 0, 0))
        observation = _builder().build(_capture(image))
        self.assertNotEqual(ScreenType.PNC_CAMPAIGN_CHAPTER, observation.screen_type)
        self.assertFalse(observation.has(UiElementId.PNC_CAMPAIGN_BACK_BUTTON))


if __name__ == "__main__":
    unittest.main()
