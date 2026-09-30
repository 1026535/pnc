
"""Campaign map and chapter identity contracts."""

from __future__ import annotations
import unittest
from PIL import Image, ImageDraw
from pnc_automation.app.pnc.domain.observation import ListEntryKind, RowRecognitionStatus, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.campaign_ocr_regions import CAMPAIGN_CHAPTER_TITLE_REGION
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.campaign import FIXTURES, _CampaignCropOcrService, _builder, _builder_with_backend, _capture, _image, _navigation_perception, _navigation_perception_with_backend


class CampaignIdentityTests(unittest.TestCase):
    def test_native_locked_chapter10_keeps_identity_back_and_available_stage(self) -> None:
        """A gold stage-1 halo must not hide its numbered, actionable inner disc."""

        backend = _require_rapid_ocr_service(self)
        capture = _capture(_image("campaign_chapter_10_locked_20260930.png"))
        for publisher in ("builder", "navigation"):
            with self.subTest(publisher=publisher):
                observation = (
                    _builder_with_backend(backend).build(
                        capture, request=ObservationRequest.campaign_map_follow_up(),
                    )
                    if publisher == "builder"
                    else _navigation_perception_with_backend(backend).build(
                        capture, include_content=True,
                    )
                )
                self.assertEqual(ScreenType.PNC_CAMPAIGN_CHAPTER, observation.screen_type)
                self.assertEqual("campaign_chapter_10", observation.decision.layout_id)
                self.assertFalse(observation.blocking_popup)
                self.assertEqual(10, observation.campaign_chapter.chapter_number)
                self.assertEqual(capture.frame_ref, observation.campaign_chapter.frame_ref)
                back = observation.get(UiElementId.PNC_CAMPAIGN_BACK_BUTTON)
                self.assertIsNotNone(back)
                self.assertEqual(VisibleElementSourceKind.TEMPLATE, back.source_kind)
                self.assertEqual(capture.frame_ref, back.frame_ref)
                rows = observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                available = [row for row in rows if row.row_status is RowRecognitionStatus.COMPLETE]
                self.assertEqual([1], [row.campaign_node.stage_number for row in available])
                self.assertIs(available[0].campaign_node.locked, False)
                self.assertTrue(available[0].action_bounds.contains_point(available[0].action_point))
                self.assertEqual(capture.frame_ref, available[0].frame_ref)
                self.assertEqual("campaign_chapter_10", available[0].source_layout_id)
                locked = [row for row in rows if row.row_status is RowRecognitionStatus.NO_ACTION]
                self.assertEqual(8, len(locked))
                self.assertTrue(all(row.action_point is None for row in locked))

        recognizer = load_visual_screen_recognizer()
        for other in ("campaign_map.png", "campaign_chapter_6_path.png"):
            with self.subTest(other=other):
                self.assertNotIn(
                    "campaign_chapter_10", recognizer.recognize(_image(other)).profile_ids,
                )

    def test_persisted_southern_map_view_has_owned_home_return_on_both_paths(self) -> None:
        """The live reopened map needs its measured portal and only honest rows."""
        image = _image("campaign_map_southern_view_20260916.png")
        expected_counts = {(540, 960): (1, 2), (900, 1600): (2, 2)}
        for size in ((540, 960), (900, 1600)):
            capture = _capture(image.resize(size, Image.Resampling.LANCZOS))
            for path in ("builder", "navigation"):
                with self.subTest(size=size, path=path):
                    observation = (
                        _builder().build(capture)
                        if path == "builder"
                        else _navigation_perception().build(capture, include_content=True)
                    )
                    self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, observation.screen_type)
                    control = observation.get(UiElementId.PNC_CAMPAIGN_HOME_PORTAL)
                    self.assertIsNotNone(control)
                    self.assertEqual(VisibleElementSourceKind.TEMPLATE, control.source_kind)
                    self.assertEqual(capture.frame_ref, control.frame_ref)
                    rows = observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)
                    clipped = [
                        row for row in rows if row.row_status is RowRecognitionStatus.CLIPPED
                    ]
                    unreadable = [
                        row for row in rows if row.row_status is RowRecognitionStatus.UNREADABLE
                    ]
                    expected_clipped, expected_unreadable = expected_counts[size]
                    self.assertEqual(expected_clipped, len(clipped))
                    self.assertEqual(expected_unreadable, len(unreadable))
                    for row in rows:
                        self.assertIsNone(row.action_point)
                        self.assertIsNone(row.action_bounds)
                        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, row.source_screen)
                        self.assertEqual("campaign_map", row.source_layout_id)
                        self.assertEqual(capture.frame_ref, row.frame_ref)
                    for row in unreadable:
                        self.assertIs(row.campaign_node.locked, False)
                        self.assertIsNone(row.campaign_node.chapter_number)
        # One isolated chapter label cannot qualify this appearance.
        erased = image.copy()
        ImageDraw.Draw(erased).rectangle((85, 350, 260, 413), fill=(0, 0, 0))
        recognition = load_visual_screen_recognizer().recognize(erased)
        self.assertNotIn("campaign_map_southern_view", recognition.profile_ids)

    def test_campaign_profiles_are_mutually_exclusive_at_reference_and_scaled_sizes(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (ScreenType.PNC_CAMPAIGN_MAP, {UiElementId.PNC_CAMPAIGN_HOME_PORTAL}),
            "campaign_map_chapter_6.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_map_chapter_6_pulse.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
            "campaign_chapter_10.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_chapter_10_unmasked.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {
                    UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
                    UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE,
                },
            ),
            "campaign_chapter_6_path.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_chapter_6_path_return.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_chapter_6_path_20260922.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_chapter_6_path_holdout_20260922.png": (
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                {UiElementId.PNC_CAMPAIGN_BACK_BUTTON},
            ),
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON, UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON},
            ),
        }
        for name, (screen, expected_selectors) in expected.items():
            with self.subTest(name=name):
                image = _image(name)
                alternate = image.resize((900, 1600) if image.size == (540, 960) else (540, 960))
                result = recognizer.recognize(alternate)
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, expected_selectors)

    def test_campaign_producer_publishes_typed_rows_with_provenance(self) -> None:
        """Map and chapter frames publish only evidence-backed typed node facts."""

        map_lines = (
            OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
            OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
        )
        map_observation = _builder(map_lines).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(map_observation.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertIsNone(map_observation.campaign_chapter)
        chapters = map_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(chapters), 2)
        unreadable = next(
            entry for entry in chapters if entry.row_status is RowRecognitionStatus.UNREADABLE
        )
        self.assertIsNotNone(unreadable.campaign_node)
        self.assertIsNone(unreadable.campaign_node.chapter_number)
        self.assertIs(unreadable.campaign_node.locked, False)
        self.assertIsNone(unreadable.action_point)
        self.assertEqual(unreadable.metadata, {})
        complete = next(
            entry for entry in chapters if entry.row_status is RowRecognitionStatus.COMPLETE
        )
        self.assertEqual(complete.campaign_node.chapter_number, 10)
        self.assertEqual(complete.campaign_node.name, "Grandia Ruins")
        self.assertIs(complete.campaign_node.locked, False)
        self.assertIsNone(complete.campaign_node.mode)
        self.assertEqual(complete.metadata, {"chapter_number": 10})
        self.assertIsNotNone(complete.action_point)
        self.assertTrue(complete.action_bounds.contains_point(complete.action_point))
        self.assertTrue(complete.bounds.contains_bounds(complete.action_bounds))
        for entry in chapters:
            self.assertEqual(entry.source_screen, ScreenType.PNC_CAMPAIGN_MAP)
            self.assertEqual(entry.source_layout_id, "campaign_map")
            self.assertEqual(entry.frame_ref, map_observation.frame_ref)

        chapter_lines = (
            OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
            OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
            OcrLine("3", Bounds(315, 610, 15, 20), 1.0),
        )
        chapter_observation = _builder(chapter_lines).build(
            _capture(_image("campaign_chapter_10.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(chapter_observation.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
        identity = chapter_observation.campaign_chapter
        self.assertIsNotNone(identity)
        self.assertEqual(identity.chapter_number, 10)
        self.assertEqual(identity.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(identity.source_layout_id, "campaign_chapter_10")
        self.assertEqual(identity.frame_ref, chapter_observation.frame_ref)
        stages = chapter_observation.entries(ListEntryKind.CAMPAIGN_STAGE)
        self.assertEqual(len(stages), 9)
        locked = [
            entry for entry in stages if entry.row_status is RowRecognitionStatus.NO_ACTION
        ]
        self.assertEqual(len(locked), 6)
        for entry in locked:
            self.assertIs(entry.campaign_node.locked, True)
            self.assertEqual(entry.campaign_node.chapter_number, 10)
            self.assertIsNone(entry.campaign_node.stage_number)
            self.assertIsNone(entry.action_point)
        unreadable_stages = [
            entry for entry in stages if entry.row_status is RowRecognitionStatus.UNREADABLE
        ]
        self.assertEqual(len(unreadable_stages), 2)
        for entry in unreadable_stages:
            self.assertIs(entry.campaign_node.locked, False)
            self.assertIsNone(entry.campaign_node.stage_number)
            self.assertIsNone(entry.action_point)
        stage_three = next(
            entry for entry in stages if entry.row_status is RowRecognitionStatus.COMPLETE
        )
        self.assertEqual(stage_three.campaign_node.chapter_number, 10)
        self.assertEqual(stage_three.campaign_node.stage_number, 3)
        self.assertIs(stage_three.campaign_node.locked, False)
        self.assertEqual(
            stage_three.metadata, {"chapter_number": 10, "stage_number": 3}
        )
        self.assertNotIn("mode", stage_three.metadata)
        self.assertIsNotNone(stage_three.action_point)
        self.assertTrue(stage_three.action_bounds.contains_point(stage_three.action_point))
        for entry in stages:
            self.assertEqual(entry.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
            self.assertEqual(entry.source_layout_id, "campaign_chapter_10")
            self.assertEqual(entry.frame_ref, chapter_observation.frame_ref)
        self.assertTrue(chapter_observation.has(UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE))
        chapter_control = chapter_observation.visible_elements[UiElementId.PNC_CAMPAIGN_MAP_REGION_NODE]
        self.assertEqual(chapter_control.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertEqual(chapter_control.source_screen, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertEqual(chapter_control.source_layout_id, "campaign_chapter_10")
        self.assertEqual(chapter_control.frame_ref, chapter_observation.frame_ref)

    def test_campaign_paths_use_bounded_ocr_and_retain_native_rows(self) -> None:
        """Both observation paths keep typed Campaign rows using only candidate-local reads."""

        cases = (
            (
                "campaign_map.png",
                (
                    OcrLine("10", Bounds(205, 468, 20, 16), 1.0),
                    OcrLine("Grandia Ruins", Bounds(235, 470, 107, 20), 1.0),
                ),
                ScreenType.PNC_CAMPAIGN_MAP,
                ListEntryKind.CAMPAIGN_CHAPTER,
                "campaign_map",
            ),
            (
                "campaign_chapter_10.png",
                (
                    OcrLine("Ch.10 C", Bounds(224, 50, 140, 39), 1.0),
                    OcrLine("Grandia Ruins", Bounds(368, 50, 160, 39), 1.0),
                ),
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                ListEntryKind.CAMPAIGN_STAGE,
                "campaign_chapter_10",
            ),
        )
        for name, lines, expected_screen, entry_kind, layout_id in cases:
            with self.subTest(path="builder", name=name):
                backend = _CampaignCropOcrService(lines)
                builder = _builder_with_backend(backend)
                capture = _capture(_image(name))
                context = ObservationOcrContext(
                    capture.image,
                    backend,
                    capture.frame_ref,
                    "campaign-visual-test",
                )
                observation = builder.build(
                    capture,
                    request=ObservationRequest.campaign_map_follow_up(),
                    ocr_context=context,
                )
                self.assertEqual(observation.screen_type, expected_screen)
                entries = observation.entries(entry_kind)
                self.assertTrue(entries)
                for entry in entries:
                    self.assertEqual(entry.source_screen, expected_screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                self.assertTrue(
                    all(
                        Bounds(0, 0, *capture.image.size).contains_bounds(region)
                        for region in backend.regions
                    )
                )
                if expected_screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIn(CAMPAIGN_CHAPTER_TITLE_REGION, backend.regions)
                    self.assertIsNotNone(observation.campaign_chapter)
                else:
                    badge_disc = Bounds(196, 458, 39, 39)
                    self.assertTrue(
                        any(
                            badge_disc.contains_bounds(region)
                            for region in backend.regions
                        ),
                        "map producer must read the badge numeral inside its disc",
                    )

            with self.subTest(path="navigation", name=name):
                backend = _CampaignCropOcrService(lines)
                capture = _capture(_image(name))
                observation = _navigation_perception_with_backend(backend).build(
                    capture,
                    include_content=True,
                )
                self.assertEqual(observation.screen_type, expected_screen)
                entries = observation.entries(entry_kind)
                self.assertTrue(entries)
                for entry in entries:
                    self.assertEqual(entry.source_screen, expected_screen)
                    self.assertEqual(entry.source_layout_id, layout_id)
                    self.assertEqual(entry.frame_ref, capture.frame_ref)
                self.assertTrue(backend.regions)
                self.assertTrue(all(region is not None for region in backend.regions))
                if expected_screen is ScreenType.PNC_CAMPAIGN_CHAPTER:
                    self.assertIn(CAMPAIGN_CHAPTER_TITLE_REGION, backend.regions)
                    self.assertIsNotNone(observation.campaign_chapter)

    def test_campaign_producer_abstains_on_missing_foreign_and_clipped_evidence(self) -> None:
        """Unprovable content stays unresolved; foreign features never publish a row."""

        empty_map = _builder().build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(empty_map.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        chapters = empty_map.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(chapters), 2)
        for entry in chapters:
            self.assertIs(entry.campaign_node.locked, False)
            self.assertIsNone(entry.campaign_node.chapter_number)
            self.assertIs(entry.row_status, RowRecognitionStatus.UNREADABLE)
            self.assertIsNone(entry.action_point)

        foreign_digits = _builder(
            (
                OcrLine("10", Bounds(10, 473, 22, 14), 1.0),
                OcrLine("Grandia Ruins", Bounds(41, 472, 106, 17), 1.0),
            )
        ).build(
            _capture(_image("campaign_map.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(foreign_digits.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        self.assertFalse(
            any(
                entry.row_status is RowRecognitionStatus.COMPLETE
                for entry in foreign_digits.entries(ListEntryKind.CAMPAIGN_CHAPTER)
            ),
            "text outside the measured badge disc must not prove a chapter number",
        )

        map6 = _builder().build(
            _capture(_image("campaign_map_chapter_6.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(map6.screen_type, ScreenType.PNC_CAMPAIGN_MAP)
        rows = map6.entries(ListEntryKind.CAMPAIGN_CHAPTER)
        self.assertEqual(len(rows), 6)
        locked_rows = [entry for entry in rows if entry.campaign_node.locked is True]
        self.assertEqual(len(locked_rows), 3)
        for entry in locked_rows:
            self.assertIs(entry.row_status, RowRecognitionStatus.NO_ACTION)
            self.assertIsNone(entry.action_point)
        unlocked_rows = [entry for entry in rows if entry.campaign_node.locked is False]
        self.assertEqual(len(unlocked_rows), 3)
        for entry in unlocked_rows:
            self.assertIs(entry.row_status, RowRecognitionStatus.UNREADABLE)
        neptune_padlock = Bounds(440, 640, 100, 120)
        self.assertFalse(
            any(
                not (
                    entry.bounds.x + entry.bounds.width <= neptune_padlock.x
                    or neptune_padlock.x + neptune_padlock.width <= entry.bounds.x
                    or entry.bounds.y + entry.bounds.height <= neptune_padlock.y
                    or neptune_padlock.y + neptune_padlock.height <= entry.bounds.y
                )
                for entry in rows
            ),
            "the foreign Neptune's Laby padlock must not publish a chapter row",
        )

        stage_observation = _builder(
            (OcrLine("10 Grandia Ruins", Bounds(237, 473, 105, 15), 1.0),)
        ).build(
            _capture(_image("campaign_stage_10_3.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertNotIn(
            stage_observation.screen_type,
            {ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER},
        )
        self.assertFalse(stage_observation.entries(ListEntryKind.CAMPAIGN_CHAPTER))
        self.assertFalse(stage_observation.entries(ListEntryKind.CAMPAIGN_STAGE))

        unnamed_title = _builder(
            (OcrLine("Marsh of Tear", Bounds(368, 50, 160, 39), 1.0),)
        ).build(
            _capture(_image("campaign_chapter_10.png")),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(unnamed_title.screen_type, ScreenType.PNC_CAMPAIGN_CHAPTER)
        self.assertIsNone(unnamed_title.campaign_chapter)
        self.assertTrue(unnamed_title.entries(ListEntryKind.CAMPAIGN_STAGE))

        missing_stage_badge = _image("campaign_chapter_10.png")
        missing_stage_badge.paste((0, 0, 0), (301, 591, 351, 644))
        missing_chapter_stage = _builder(
            (OcrLine("Ch.10 Grandia Ruins", Bounds(230, 55, 295, 30), 1.0),)
        ).build(
            _capture(missing_stage_badge),
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertIn(
            missing_chapter_stage.screen_type,
            {ScreenType.UNKNOWN, ScreenType.PNC_CAMPAIGN_CHAPTER},
        )
        stage_bounds = Bounds(302, 598, 49, 49)
        self.assertFalse(
            any(
                entry.bounds == stage_bounds or stage_bounds.contains_bounds(entry.bounds)
                for entry in missing_chapter_stage.entries(ListEntryKind.CAMPAIGN_STAGE)
            ),
            "a blacked-out badge must not publish a stage row",
        )

    def test_native_chapter6_frames_qualify_with_owned_return_on_both_publishers(self) -> None:
        """The current-build Chapter 6 appearance keeps its typed rows and owned Back.

        The unmodified 900x1600 RGBA frames from the parked M1 run previously
        returned UNKNOWN; the scoped 0.92 terrain bound restores them without
        weakening the 0.95 title identity or 0.85 Back control requirements.
        """
        backend = _require_rapid_ocr_service(self)
        for name in (
            "campaign_chapter_6_path_20260922.png",
            "campaign_chapter_6_path_holdout_20260922.png",
        ):
            with Image.open(FIXTURES / name) as source:
                image = source.copy()
            self.assertEqual("RGBA", image.mode)
            capture = _capture(image)
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
                    self.assertEqual(
                        ScreenType.PNC_CAMPAIGN_CHAPTER, observation.screen_type
                    )
                    self.assertEqual("clear", observation.decision.guard.value)
                    self.assertFalse(observation.blocking_popup)
                    back = observation.get(UiElementId.PNC_CAMPAIGN_BACK_BUTTON)
                    self.assertIsNotNone(back)
                    self.assertEqual(
                        VisibleElementSourceKind.TEMPLATE, back.source_kind
                    )
                    self.assertEqual(capture.frame_ref, back.frame_ref)
                    self.assertIsNotNone(observation.campaign_chapter)
                    self.assertEqual(6, observation.campaign_chapter.chapter_number)
                    self.assertEqual(
                        capture.frame_ref, observation.campaign_chapter.frame_ref
                    )
                    self.assertEqual(
                        "campaign_chapter_6",
                        observation.campaign_chapter.source_layout_id,
                    )
                    rows = observation.entries(ListEntryKind.CAMPAIGN_STAGE)
                    complete = {
                        row.campaign_node.stage_number
                        for row in rows
                        if row.row_status is RowRecognitionStatus.COMPLETE
                    }
                    self.assertEqual({1, 2, 3, 4}, complete)
                    locked = [
                        row
                        for row in rows
                        if row.row_status is RowRecognitionStatus.NO_ACTION
                    ]
                    self.assertEqual(4, len(locked))
                    for row in rows:
                        self.assertEqual(
                            ScreenType.PNC_CAMPAIGN_CHAPTER, row.source_screen
                        )
                        self.assertEqual("campaign_chapter_6", row.source_layout_id)
                        self.assertEqual(capture.frame_ref, row.frame_ref)
                        if row.row_status is RowRecognitionStatus.COMPLETE:
                            self.assertIs(row.campaign_node.locked, False)
                            self.assertIsNotNone(row.action_point)
                        else:
                            self.assertIs(row.campaign_node.locked, True)
                            self.assertIsNone(row.campaign_node.stage_number)
                            self.assertIsNone(row.action_point)

    def test_scaled_chapter6_20260922_frame_keeps_chapter_identity(self) -> None:
        """The retained frame resized to reference geometry still resolves chapter 6."""
        backend = _require_rapid_ocr_service(self)
        scaled = _capture(
            _image("campaign_chapter_6_path_20260922.png").resize(
                (540, 960), Image.Resampling.LANCZOS
            )
        )
        for publisher in ("builder", "navigation"):
            with self.subTest(publisher=publisher):
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

    def test_native_stage_identity_requires_both_independent_anchors(self) -> None:
        """Neither a title alone nor a generic lineup modal qualifies a stage."""
        recognizer = load_visual_screen_recognizer()
        for date in ("20260922", "20260927"):
            image = _image(f"campaign_stage_6_5_{date}.png").resize(
                (540, 960), Image.Resampling.LANCZOS
            )
            for region in ((210, 190, 440, 250), (198, 235, 361, 300)):
                with self.subTest(date=date, region=region):
                    erased = image.copy()
                    ImageDraw.Draw(erased).rectangle(region, fill=(0, 0, 0))
                    result = recognizer.recognize(erased)
                    self.assertNotIn("campaign_stage_chapter_6", result.profile_ids)

    def test_chapter6_terrain_calibration_does_not_admit_other_screens(self) -> None:
        """The scoped 0.92 terrain bound must not leak Chapter 6 onto other surfaces."""
        recognizer = load_visual_screen_recognizer()
        for name in (
            "campaign_chapter_5_path_20260916.png",
            "campaign_chapter_5_loading_20260916.png",
            "campaign_chapter_10.png",
            "campaign_chapter_10_unmasked.png",
            "campaign_map.png",
            "campaign_map_chapter_6.png",
            "campaign_map_chapter_6_pulse.png",
            "campaign_map_southern_view_20260916.png",
            "campaign_map_recentered_20260916.png",
            "campaign_stage_10_3.png",
            "world_map_core.png",
            "home_city_core.png",
            "vip_daily_reset.png",
            "update_over_bag.png",
        ):
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertNotIn("campaign_chapter_6", result.profile_ids)

    def test_campaign_anchor_gate_fails_closed_when_identity_is_partial(self) -> None:
        recognizer = load_visual_screen_recognizer()
        mutations = (
            ("campaign_map.png", (180, 220, 350, 350)),
            ("campaign_map_chapter_6.png", (178, 435, 363, 520)),
            ("campaign_chapter_10.png", (205, 38, 530, 98)),
            ("campaign_chapter_6_path.png", (95, 35, 540, 200)),
            ("campaign_stage_10_3.png", (120, 201, 420, 250)),
        )
        for name, box in mutations:
            with self.subTest(name=name):
                image = _image(name)
                image.paste((0, 0, 0), box)
                self.assertEqual(recognizer.recognize(image).evidence, ())


if __name__ == "__main__":
    unittest.main()
