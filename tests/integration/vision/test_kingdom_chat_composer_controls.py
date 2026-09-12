"""Portable visual contracts for the measured Kingdom Chat composer controls."""

from __future__ import annotations

from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import DetectionKind, SelectorStatus, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer

from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
_COMPOSER_CONTROLS = frozenset(
    {
        UiElementId.PNC_CHAT_INPUT_FIELD,
        UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT,
        UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
    }
)


def _fixture(name: str) -> Image.Image:
    """Load one sanitized reference frame without retaining the file handle."""

    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB").copy()


def _recognition(name: str):
    """Recognize one sanitized Kingdom Chat frame with the packaged catalog."""

    return load_visual_screen_recognizer().recognize(_fixture(name))


class KingdomChatComposerControlTests(unittest.TestCase):
    """Require positive current-frame evidence for each composer state."""

    def test_normal_empty_composer_exposes_only_white_input_template(self) -> None:
        result = _recognition("chat_kingdom_normal_empty.png")

        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CHAT})
        controls = {item.selector_id for item in result.controls}
        self.assertIn(UiElementId.PNC_CHAT_INPUT_FIELD, controls)
        self.assertNotIn(UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT, controls)
        self.assertNotIn(UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON, controls)
        input_control = next(
            item for item in result.controls if item.selector_id == UiElementId.PNC_CHAT_INPUT_FIELD
        )
        self.assertEqual(input_control.source_kind, VisibleElementSourceKind.TEMPLATE)
        self.assertGreaterEqual(input_control.confidence, 0.95)
        center_x, center_y = input_control.bounds.center()
        self.assertTrue(60 <= center_x <= 220)
        self.assertTrue(918 <= center_y <= 943)

    def test_focused_empty_composer_exposes_pink_empty_and_gold_send(self) -> None:
        result = _recognition("chat_kingdom_focused_empty.png")

        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CHAT})
        controls = {item.selector_id for item in result.controls}
        self.assertNotIn(UiElementId.PNC_CHAT_INPUT_FIELD, controls)
        self.assertTrue(
            {
                UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT,
                UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
            }
            <= controls
        )
        self.assertTrue(
            all(
                item.source_kind == VisibleElementSourceKind.TEMPLATE
                for item in result.controls
                if item.selector_id
                in {
                    UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT,
                    UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
                }
            )
        )

    def test_typed_hello_keeps_gold_send_and_loses_empty_evidence(self) -> None:
        result = _recognition("chat_kingdom_focused_send.png")

        controls = {item.selector_id for item in result.controls}
        self.assertIn(UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON, controls)
        self.assertNotIn(UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT, controls)
        self.assertNotIn(UiElementId.PNC_CHAT_INPUT_FIELD, controls)

    def test_blank_composer_has_no_composer_controls(self) -> None:
        image = _fixture("chat_kingdom_normal_empty.png")
        image.paste((15, 28, 68), (0, 885, 540, 960))

        result = load_visual_screen_recognizer().recognize(image)

        self.assertEqual({item.screen_type for item in result.evidence}, {ScreenType.PNC_CHAT})
        self.assertFalse(_COMPOSER_CONTROLS & {item.selector_id for item in result.controls})

    def test_decoy_gold_control_outside_bounded_search_region_does_not_qualify(self) -> None:
        image = _fixture("chat_kingdom_focused_send.png")
        image.paste((15, 28, 68), (448, 906, 530, 943))
        with Image.open(
            Path(__file__).parents[3]
            / "pnc_automation"
            / "app"
            / "pnc"
            / "vision"
            / "data"
            / "screen_anchors"
            / "chat_focused_send_button.png"
        ) as template:
            image.paste(template.convert("RGB"), (350, 906))

        result = load_visual_screen_recognizer().recognize(image)

        self.assertNotIn(
            UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
            {item.selector_id for item in result.controls},
        )

    def test_composer_controls_survive_reference_scaling(self) -> None:
        expected = {
            "chat_kingdom_normal_empty.png": {UiElementId.PNC_CHAT_INPUT_FIELD},
            "chat_kingdom_focused_empty.png": {
                UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT,
                UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
            },
            "chat_kingdom_focused_send.png": {UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON},
        }
        recognizer = load_visual_screen_recognizer()
        for name, expected_controls in expected.items():
            with self.subTest(name=name):
                scaled_image = _fixture(name).resize((900, 1600))
                result = recognizer.recognize(scaled_image)
                controls = {item.selector_id for item in result.controls}
                self.assertTrue(expected_controls <= controls)

    def test_registry_declares_template_contracts_without_changing_blue_send(self) -> None:
        registry = build_default_selector_registry()
        normal = registry.require(UiElementId.PNC_CHAT_INPUT_FIELD)
        focused_empty = registry.require(UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT)
        focused_send = registry.require(UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON)
        blue_send = registry.require(UiElementId.PNC_CHAT_SEND_BUTTON)

        self.assertEqual(normal.detection_kind, DetectionKind.GUARDED_GEOMETRY)
        self.assertEqual(normal.status, SelectorStatus.PLANNED)
        self.assertEqual(normal.relative_bounds.y_ratio, 0.935)
        self.assertEqual(normal.relative_bounds.height_ratio, 0.05)
        self.assertEqual(focused_empty.detection_kind, DetectionKind.TEMPLATE)
        self.assertEqual(focused_empty.interaction_kind.value, "label")
        self.assertIsNone(focused_empty.click)
        self.assertEqual(focused_send.detection_kind, DetectionKind.TEMPLATE)
        self.assertEqual(focused_send.interaction_kind.value, "action")
        self.assertIsNotNone(focused_send.click)
        self.assertEqual(blue_send.detection_kind, DetectionKind.GUARDED_GEOMETRY)
        self.assertIsNone(blue_send.template_path)


if __name__ == "__main__":
    unittest.main()
