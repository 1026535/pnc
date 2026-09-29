"""Campaign Challenge formation preparation recognition and control contracts."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from tests.support.pnc.campaign import _builder, _capture, _image, _navigation_perception


class CampaignFormationPreparationTests(unittest.TestCase):
    def test_native_formation_preparation_publishes_only_the_owned_back(self) -> None:
        """Both publishers type the recorded Challenge preparation via the dedicated profile."""

        for name in (
            "hero_formation_challenge_preparation_20260929.png",
            "hero_formation_challenge_preparation_reconcile_20260929.png",
        ):
            image = _image(name)
            recognition = load_visual_screen_recognizer().recognize(image)
            self.assertEqual(
                ("hero_formation_challenge_preparation",),
                recognition.profile_ids,
            )
            self.assertEqual(
                {UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON},
                {item.selector_id for item in recognition.controls},
            )
            self.assertEqual(
                {UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON},
                {item.selector_id for item in recognition.dismiss_controls},
            )
            capture = _capture(image)
            for publisher in ("builder", "navigation"):
                with self.subTest(frame=name, publisher=publisher):
                    observation = (
                        _builder().build(capture)
                        if publisher == "builder"
                        else _navigation_perception().build(capture)
                    )
                    self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_FORMATION)
                    self.assertEqual(
                        observation.decision.layout_id, "hero_formation_challenge_preparation"
                    )
                    control = observation.get(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON)
                    self.assertIsNotNone(control)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(
                        control.source_layout_id, "hero_formation_challenge_preparation"
                    )
                    self.assertEqual(control.frame_ref, capture.frame_ref)
                    # Formation Challenge/Save/edit/continuation controls stay
                    # unpublished, and no Campaign stage/AP facts are projected.
                    self.assertFalse(observation.has(UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON))
                    self.assertFalse(observation.has(UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON))
                    self.assertFalse(observation.has(UiElementId.PNC_HERO_FORMATION_HEADER))
                    self.assertIsNone(observation.campaign_stage)

    def test_formation_preparation_identity_requires_its_headings_and_challenge_caption(self) -> None:
        recognizer = load_visual_screen_recognizer()
        image = _image("hero_formation_challenge_preparation_20260929.png").resize((540, 960))

        for region in ((108, 10, 312, 38), (124, 58, 270, 82), (214, 897, 327, 922)):
            with self.subTest(erased=region):
                negative = image.copy()
                negative.paste((0, 0, 0), region)
                result = recognizer.recognize(negative)
                self.assertNotIn("hero_formation_challenge_preparation", result.profile_ids)
                self.assertNotIn(
                    UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
                    {item.selector_id for item in result.controls},
                )

    def test_save_form_caption_cannot_publish_the_campaign_preparation_back(self) -> None:
        """Shared formation headings do not identify the preparation action variant."""
        image = _image("hero_formation_challenge_preparation_20260929.png").resize(
            (540, 960), Image.Resampling.LANCZOS
        )
        image.paste((185, 135, 55), (214, 897, 327, 922))
        ImageDraw.Draw(image).text((223, 903), "Save Form", fill="white")
        recognition = load_visual_screen_recognizer().recognize(image)
        self.assertNotIn("hero_formation_challenge_preparation", recognition.profile_ids)
        save_form = (OcrLine("Save Form", Bounds(223, 903, 90, 18), 0.99),)
        capture = _capture(image)
        for publisher in (_builder(save_form), _navigation_perception(save_form)):
            observation = publisher.build(capture)
            self.assertFalse(observation.has(UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON))

    def test_formation_preparation_missing_back_keeps_identity_without_control(self) -> None:
        recognizer = load_visual_screen_recognizer()
        image = _image("hero_formation_challenge_preparation_20260929.png").resize((540, 960))
        image.paste((0, 0, 0), (14, 4, 62, 46))

        result = recognizer.recognize(image)

        self.assertEqual(("hero_formation_challenge_preparation",), result.profile_ids)
        self.assertNotIn(
            UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
            {item.selector_id for item in result.controls},
        )

    def test_current_stage_fixture_does_not_match_formation_preparation(self) -> None:
        """A saved Campaign stage frame must not degrade into the formation variant."""

        recognizer = load_visual_screen_recognizer()
        for name in ("campaign_stage_6_5_20260927.png", "campaign_stage_10_3.png"):
            with self.subTest(name=name):
                result = recognizer.recognize(_image(name))
                self.assertNotIn("hero_formation_challenge_preparation", result.profile_ids)
                self.assertNotIn(
                    UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
                    {item.selector_id for item in result.controls},
                )


if __name__ == "__main__":
    unittest.main()
