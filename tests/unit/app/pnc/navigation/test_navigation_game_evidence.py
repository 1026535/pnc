"""Navigation game evidence tests."""

from datetime import UTC, datetime
from pathlib import Path
import json, unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.visual_screen_recognizer import (
    load_visual_screen_recognizer,
)
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot

from tests.support.pnc.navigation.core_perception import Guard, _perception


class GameFirstNavigationEvidenceTests(unittest.TestCase):
    directory = Path('tests/data/game_first_navigation')

    def test_fresh_game_frames_have_distinct_identities_at_both_resolutions(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        manifest = json.loads((self.directory / 'provenance.json').read_text(encoding='utf-8'))
        for case in manifest['fixtures']:
            for size in ((540, 960), (900, 1600)):
                with self.subTest(frame=case['file'], size=size), Image.open(self.directory / case['file']) as image:
                    capture = CapturedScreenshot(None, image.resize(size), 'PNG', ephemeral_captured_at=datetime.now(UTC))
                    result = perception.build(capture)
                    self.assertEqual(result.screen_type, ScreenType[case['screen']])
                    self.assertTrue(result.visible_elements)
                    self.assertTrue(all(control.source_kind == VisibleElementSourceKind.TEMPLATE for control in result.visible_elements.values()))

    def test_preferences_title_alone_does_not_identify_settings_hub(self):
        with Image.open(self.directory / 'settings_preferences_after.png') as image:
            image = image.copy()
        image.paste((0, 0, 0), (190, 65, 350, 100))
        capture = CapturedScreenshot(None, image, 'PNG', ephemeral_captured_at=datetime.now(UTC))
        result = _perception(load_visual_screen_recognizer(), Guard()).build(capture)
        self.assertEqual(result.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(result.visible_elements)

    def test_preferences_and_roster_expose_only_back(self):
        perception = _perception(load_visual_screen_recognizer(), Guard())
        for name in ('settings_preferences_after.png', 'settings_notifications_after.png', 'settings_manage_after.png'):
            with self.subTest(frame=name), Image.open(self.directory / name) as image:
                capture = CapturedScreenshot(None, image.copy(), 'PNG', ephemeral_captured_at=datetime.now(UTC))
                self.assertEqual(set(perception.build(capture).visible_elements), {UiElementId.PNC_BACK_BUTTON_TOP_LEFT})
