
"""Campaign controls and blocking-overlay contracts."""

from __future__ import annotations
import unittest
from PIL import ImageDraw
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.support.pnc.capture_vision.modal_overlay import update_modal_lines, with_update_modal
from tests.support.pnc.campaign import CAMPAIGN_CHALLENGE_BOX, _CampaignCropOcrService, _builder, _builder_with_backend, _capture, _image, _navigation_perception, _navigation_perception_with_backend


class CampaignControlsAndOverlaysTests(unittest.TestCase):
    def test_stage_content_request_preserves_controls_without_unused_body_ocr(self) -> None:
        """A recognized stage skips popup guard OCR while retaining measured controls."""
        capture = _capture(_image("campaign_stage_10_3.png"))
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                backend = _CampaignCropOcrService(())
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
                for selector in (
                    UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                    UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                ):
                    self.assertTrue(observation.has(selector))
                    self.assertEqual(observation.visible_elements[selector].frame_ref, capture.frame_ref)
                self.assertFalse(observation.list_entries)
                self.assertEqual(backend.regions, [])

    def test_benchmark_wrapper_preserves_owned_detail_close(self) -> None:
        """Timing instrumentation forwards the base-first visual contract."""
        from tools.benchmark_screen_recognition import _instrument_builder

        builder, probe = _instrument_builder(_builder((
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),
            OcrLine("Challenge", Bounds(216, 666, 109, 25), 1.0),
        )))
        observation = builder.build(_capture(_image("campaign_stage_10_3.png")))
        self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertIsNotNone(probe)
        self.assertEqual(probe.guard_calls, 0)

    def test_campaign_profiles_expose_their_measured_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        expected = {
            "campaign_map.png": (
                ScreenType.PNC_CAMPAIGN_MAP,
                {UiElementId.PNC_CAMPAIGN_HOME_PORTAL},
            ),
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
            "campaign_stage_10_3.png": (
                ScreenType.PNC_CAMPAIGN_STAGE,
                {
                    UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
                    UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                },
            ),
        }
        for name, (screen, selectors) in expected.items():
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertEqual({item.screen_type for item in result.evidence}, {screen})
                self.assertEqual({item.selector_id for item in result.controls}, selectors)
                self.assertTrue(
                    all(item.source_kind is VisibleElementSourceKind.TEMPLATE for item in result.controls)
                )
                if screen is ScreenType.PNC_CAMPAIGN_STAGE:
                    self.assertEqual(
                        {item.selector_id for item in result.dismiss_controls},
                        {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
                    )
                else:
                    self.assertEqual(result.dismiss_controls, ())

    def test_campaign_detail_close_and_challenge_are_owned_controls(self) -> None:
        recognizer = load_visual_screen_recognizer()
        result = recognizer.recognize(_image("campaign_stage_10_3.png"))
        self.assertEqual(
            {item.selector_id for item in result.dismiss_controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )
        self.assertIn(
            UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
            {item.selector_id for item in result.controls},
        )
        stage_profile = next(profile for profile in recognizer.profiles if profile.id == "campaign_stage_10_3")
        close_control = next(
            control
            for control in stage_profile.controls
            if control.selector_id is UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON
        )
        self.assertTrue(close_control.dismisses_surface)

    def test_campaign_challenge_removal_preserves_stage_identity_without_control(self) -> None:
        recognizer = load_visual_screen_recognizer()
        image = _image("campaign_stage_10_3.png")
        image.paste((0, 0, 0), (178, 643, 362, 697))

        result = recognizer.recognize(image)

        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CAMPAIGN_STAGE})
        self.assertEqual(
            {item.selector_id for item in result.controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )
        self.assertEqual(
            {item.selector_id for item in result.dismiss_controls},
            {UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON},
        )

    def test_campaign_challenge_uses_measured_geometry_at_both_viewports(self) -> None:
        recognizer = load_visual_screen_recognizer()
        control = next(
            item
            for item in recognizer.recognize(_image("campaign_stage_10_3.png")).controls
            if item.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(control.bounds, CAMPAIGN_CHALLENGE_BOX)
        self.assertTrue(CAMPAIGN_CHALLENGE_BOX.contains_point(control.action_point or control.bounds.center()))

        scaled = recognizer.recognize(_image("campaign_stage_10_3.png").resize((900, 1600)))
        scaled_control = next(
            item
            for item in scaled.controls
            if item.selector_id is UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON
        )
        self.assertEqual(scaled_control.bounds, Bounds(297, 1072, 306, 90))
        self.assertTrue(
            scaled_control.bounds.contains_point(scaled_control.action_point or scaled_control.bounds.center())
        )

    def test_campaign_blocking_overlay_suppresses_background_controls_and_rows(self) -> None:
        image = with_update_modal(_image("campaign_stage_10_3.png"))
        popup_lines = update_modal_lines(image.size)
        stage_capture = _capture(image)
        blocked_builder = _builder(popup_lines).build(
            stage_capture,
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(blocked_builder.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(blocked_builder.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(blocked_builder.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertFalse(blocked_builder.list_entries)

        blocked_navigation = _navigation_perception(popup_lines).build(
            stage_capture,
            include_content=True,
        )
        self.assertEqual(blocked_navigation.screen_type, ScreenType.PNC_POPUP)
        self.assertFalse(blocked_navigation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(blocked_navigation.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertFalse(blocked_navigation.list_entries)

    def test_navigation_perception_keeps_stage_detail_outside_generic_popup_guard(self) -> None:
        """The owned stage Close is passed to popup detection without making it a popup."""

        capture = _capture(_image("campaign_stage_10_3.png"))
        stage_lines = (
            OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),
            OcrLine("Enemylineup", Bounds(209, 271, 117, 20), 1.0),
            OcrLine("150/120", Bounds(379, 593, 78, 20), 1.0),
            OcrLine("Challenge", Bounds(216, 666, 109, 25), 1.0),
        )
        perception = _navigation_perception(stage_lines)

        result = perception.build(capture)

        self.assertEqual(result.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertFalse(result.blocking_popup)
        self.assertTrue(result.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertTrue(result.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
        self.assertEqual(result.decision.guard.value, "clear")

        builder_result = _builder(stage_lines).build(
            capture,
            request=ObservationRequest.campaign_map_follow_up(),
        )
        self.assertEqual(builder_result.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
        self.assertFalse(builder_result.blocking_popup)
        self.assertTrue(builder_result.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
        self.assertTrue(builder_result.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
        self.assertFalse(builder_result.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))
        self.assertEqual(builder_result.decision.guard.value, "clear")

    def test_recognized_stage_owns_generic_like_x_without_popup_promotion(self) -> None:
        """A recognized stage keeps its own controls when another X is present."""

        image = _image("campaign_stage_10_3.png")
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((465, 300, 510, 345), fill=(15, 28, 68))
        drawing.line((474, 309, 501, 336), fill=(255, 247, 218), width=5)
        drawing.line((501, 309, 474, 336), fill=(255, 247, 218), width=5)
        self.assertTrue(load_visual_screen_recognizer().recognize(image).dismiss_controls)
        lines = (OcrLine("[10-3] Grandia Ruins", Bounds(142, 211, 256, 27), 1.0),)
        capture = _capture(image)

        for index, observation in enumerate((
            _builder(lines).build(capture),
            _navigation_perception(lines).build(capture),
        )):
            with self.subTest(path=index):
                self.assertEqual(observation.screen_type, ScreenType.PNC_CAMPAIGN_STAGE)
                self.assertEqual(observation.decision.guard.value, "clear")
                self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON))
                self.assertTrue(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
                self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))


if __name__ == "__main__":
    unittest.main()
