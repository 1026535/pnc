
"""Bounded real OCR and runtime-scope Campaign contracts."""

from __future__ import annotations
import unittest
from PIL import Image
from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.campaign import _builder_with_backend, _capture, _image, _navigation_perception_with_backend


class CampaignRealOcrTests(unittest.TestCase):
    def test_real_ocr_binds_current_typed_rows_on_both_publishers(self) -> None:
        """RapidOCR 3.4.5 proves the measured chapter/stage ordinals end to end."""
        backend = _require_rapid_ocr_service(self)
        cases = (
            (
                "campaign_map.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
                {9, 10},
                (),
                None,
            ),
            (
                "campaign_map_chapter_6.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map_chapter_6",
                {4, 5, 6},
                {7, 8, 9},
                None,
            ),
            (
                "campaign_map_chapter_6_pulse.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map_chapter_6",
                {4, 5, 6},
                None,
                None,
            ),
            (
                "campaign_map_southern_view_20260916.png",
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
                {2, 5},
                (),
                None,
            ),
            (
                "campaign_chapter_10_unmasked.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_10",
                {1, 2, 3},
                (),
                10,
            ),
            (
                "campaign_chapter_6_path.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_6",
                {1, 2, 3, 4, 5},
                (),
                6,
            ),
            (
                "campaign_chapter_6_path_return.png",
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_6",
                {1, 2, 3, 4, 5},
                (),
                6,
            ),
        )
        for name, screen, kind, layout_id, complete_numbers, locked_numbers, chapter in cases:
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
                    self.assertEqual(screen, observation.screen_type)
                    rows = observation.entries(kind)
                    complete = [
                        row for row in rows if row.row_status is RowRecognitionStatus.COMPLETE
                    ]
                    number_of = (
                        (lambda row: row.campaign_node.chapter_number)
                        if kind is ListEntryKind.CAMPAIGN_CHAPTER
                        else (lambda row: row.campaign_node.stage_number)
                    )
                    self.assertEqual(
                        complete_numbers, {number_of(row) for row in complete}
                    )
                    for row in complete:
                        self.assertIs(row.campaign_node.locked, False)
                        self.assertIsNone(row.campaign_node.mode)
                        self.assertIsNone(row.campaign_node.completed)
                        self.assertIsNotNone(row.action_point)
                        self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
                        self.assertTrue(row.action_bounds.contains_point(row.action_point))
                    locked = [
                        row for row in rows if row.row_status is RowRecognitionStatus.NO_ACTION
                    ]
                    if locked_numbers:
                        self.assertEqual(
                            locked_numbers, {number_of(row) for row in locked}
                        )
                    for row in locked:
                        self.assertIs(row.campaign_node.locked, True)
                        self.assertIsNone(row.action_point)
                        if kind is ListEntryKind.CAMPAIGN_STAGE:
                            self.assertIsNone(row.campaign_node.stage_number)
                    for row in rows:
                        self.assertEqual(screen, row.source_screen)
                        self.assertEqual(layout_id, row.source_layout_id)
                        self.assertEqual(capture.frame_ref, row.frame_ref)
                    if chapter is not None:
                        self.assertIsNotNone(observation.campaign_chapter)
                        self.assertEqual(chapter, observation.campaign_chapter.chapter_number)
                        self.assertEqual(
                            capture.frame_ref, observation.campaign_chapter.frame_ref
                        )

    def test_real_ocr_binds_scaled_return_path_stage_numbers(self) -> None:
        """The reference-size return frame still resolves every visible stage."""
        backend = _require_rapid_ocr_service(self)
        capture = _capture(
            _image("campaign_chapter_6_path_return.png").resize(
                (540, 960), Image.Resampling.LANCZOS
            )
        )
        for publisher in ("builder", "navigation"):
            with self.subTest(publisher=publisher):
                observation = (
                    _builder_with_backend(backend).build(
                        capture, request=ObservationRequest.campaign_map_follow_up()
                    )
                    if publisher == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        capture, include_content=True
                    )
                )
                self.assertEqual(
                    {1, 2, 3, 4, 5},
                    {
                        row.campaign_node.stage_number
                        for row in observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                        if row.row_status is RowRecognitionStatus.COMPLETE
                    },
                )

    def test_campaign_chapter_is_in_the_narrow_and_full_runtime_ocr_scopes(self) -> None:
        follow_up = ObservationRequest.campaign_map_follow_up()
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, follow_up.candidate_screen_types)
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, follow_up.ocr_screen_types)
        self.assertIn(ScreenType.PNC_CAMPAIGN_CHAPTER, ObservationRequest.full_runtime_default().ocr_screen_types)


if __name__ == "__main__":
    unittest.main()
