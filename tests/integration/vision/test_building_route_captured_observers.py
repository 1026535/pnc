"""Captured building endpoints through both production observation paths."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition" / "building_routes"
CATALOG_PATH = (
    Path(__file__).parents[3]
    / "pnc_automation"
    / "app"
    / "pnc"
    / "vision"
    / "data"
    / "screen_anchors.json"
)


CASES = (
    (
        "../wall_overview_20260918.png",
        ScreenType.PNC_WALL,
        "building_wall",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "blacksmith_reference_20260914.png",
        ScreenType.PNC_BLACKSMITH,
        "building_blacksmith",
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_BLACKSMITH_UPGRADE_BUTTON,
        },
    ),
    (
        "arena_reference_20260914.png",
        ScreenType.PNC_VERSUS_CENTER,
        "building_arena",
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_VERSUS_CENTER_TAB_ARENA,
            UiElementId.PNC_VERSUS_CENTER_TAB_EXCHANGE_SHOP,
        },
    ),
    (
        "hall_of_war_reference_20260914.png",
        ScreenType.PNC_HALL_OF_WAR,
        "building_hall_of_war",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_HALL_OF_WAR_UPGRADE_BUTTON},
    ),
    (
        "arena_validation_20260914.png",
        ScreenType.PNC_VERSUS_CENTER,
        "building_arena",
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_VERSUS_CENTER_TAB_ARENA,
            UiElementId.PNC_VERSUS_CENTER_TAB_EXCHANGE_SHOP,
        },
    ),
    (
        "sacred_tree_reference_20260914.png",
        ScreenType.PNC_SACRED_TREE,
        "building_sacred_tree",
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_SACRED_TREE_BLESSING_RECORD_BUTTON,
            UiElementId.PNC_SACRED_TREE_HARVEST_BUTTON,
        },
    ),
    (
        "sacred_tree_validation_20260914.png",
        ScreenType.PNC_SACRED_TREE,
        "building_sacred_tree",
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_SACRED_TREE_BLESSING_RECORD_BUTTON,
            UiElementId.PNC_SACRED_TREE_HARVEST_BUTTON,
        },
    ),
    (
        "hall_of_war_validation_20260914.png",
        ScreenType.PNC_HALL_OF_WAR,
        "building_hall_of_war",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_HALL_OF_WAR_UPGRADE_BUTTON},
    ),
    (
        "ranged_barracks_reference_20260922.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "ranged_barracks_native_20260929.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "ranged_barracks_native_correlated_20260929.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "ranged_barracks_native_prior_20260929.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "infantry_barracks_20260917.png",
        ScreenType.PNC_INFANTRY_BARRACKS,
        "building_infantry_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "infantry_barracks_native_20260929.png",
        ScreenType.PNC_INFANTRY_BARRACKS,
        "building_infantry_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "infantry_barracks_native_holdout_20260929.png",
        ScreenType.PNC_INFANTRY_BARRACKS,
        "building_infantry_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "cavalry_barracks_native_20260930.png",
        ScreenType.PNC_CAVALRY_BARRACKS,
        "building_cavalry_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "cavalry_barracks_native_correlated_20260930.png",
        ScreenType.PNC_CAVALRY_BARRACKS,
        "building_cavalry_barracks",
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
)


# Erasure boxes remain in each preserved native frame's coordinate space.
BARRACKS_REFERENCES = (
    (
        "ranged_barracks_reference_20260922.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        ("RGBA", (540, 960)),
        ((95, 15, 350, 90), (275, 140, 540, 185)),
        (0, 0, 100, 55),
    ),
    (
        "ranged_barracks_native_20260929.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        ("RGBA", (900, 1600)),
        ((158, 25, 583, 150), (458, 233, 900, 308)),
        (0, 0, 167, 92),
    ),
    (
        "ranged_barracks_native_prior_20260929.png",
        ScreenType.PNC_RANGED_BARRACKS,
        "building_ranged_barracks",
        ("RGBA", (900, 1600)),
        ((158, 25, 583, 150), (458, 233, 900, 308)),
        (0, 0, 167, 92),
    ),
    (
        "infantry_barracks_20260917.png",
        ScreenType.PNC_INFANTRY_BARRACKS,
        "building_infantry_barracks",
        ("RGB", (900, 1600)),
        ((175, 13, 675, 80), (466, 233, 900, 309)),
        (0, 0, 167, 92),
    ),
    (
        "infantry_barracks_native_20260929.png",
        ScreenType.PNC_INFANTRY_BARRACKS,
        "building_infantry_barracks",
        ("RGBA", (900, 1600)),
        ((175, 13, 675, 80), (466, 233, 900, 309)),
        (0, 0, 167, 92),
    ),
    (
        "cavalry_barracks_native_20260930.png",
        ScreenType.PNC_CAVALRY_BARRACKS,
        "building_cavalry_barracks",
        ("RGBA", (900, 1600)),
        ((55, 145, 280, 285), (466, 233, 900, 309)),
        (0, 0, 167, 92),
    ),
)


BARRACKS_MUTATION_SELECTORS = frozenset(
    {
        UiElementId.PNC_BARRACKS_GLORY_LEVEL_BUTTON,
        UiElementId.PNC_BARRACKS_UPGRADE_BUTTON,
        UiElementId.PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON,
        UiElementId.PNC_BARRACKS_UNIT_TIER_SLOT,
        UiElementId.PNC_BARRACKS_QUANTITY_LOCK_BUTTON,
        UiElementId.PNC_BARRACKS_QUANTITY_SLIDER,
        UiElementId.PNC_BARRACKS_TRAIN_BUTTON,
        UiElementId.PNC_BARRACKS_TRAIN_NOW_BUTTON,
        UiElementId.PNC_BARRACKS_SPEEDUP_BUTTON,
        UiElementId.PNC_BARRACKS_COLLECT_BUTTON,
        UiElementId.PNC_BARRACKS_EFFECT_TABLE_ROW,
    }
)


class BuildingRouteCapturedObserversTests(unittest.TestCase):
    """Protect reviewed building identity and controls on current captures."""

    def test_building_identity_and_controls_reach_both_observers(self) -> None:
        """Each static building capture publishes one typed, controllable endpoint."""

        for fixture_name, screen, layout_id, expected_controls in CASES:
            with self.subTest(fixture=fixture_name):
                fixture = FIXTURE_ROOT / fixture_name
                with Image.open(fixture) as source:
                    image = source.copy()
                for native_fixture, _, _, native_format, _, _ in BARRACKS_REFERENCES:
                    if fixture_name == native_fixture:
                        self.assertEqual(native_format, (image.mode, image.size))
                observations = self._both_observations(image, screen, layout_id)
                for observer_name, observation in observations:
                    with self.subTest(observer=observer_name):
                        self.assertEqual(observation.screen_type, screen)
                        self.assertEqual(observation.decision.layout_id, layout_id)
                        self.assertTrue(expected_controls.issubset(observation.visible_elements))

    def _both_observations(self, image, screen, layout_id):
        """Build the production ObservationBuilder and NavigationPerception outputs."""
        capture = CapturedScreenshot(
            artifact=None,
            image=image,
            image_format="PNG",
            # Synthetic erased images must not retain the original PNG payload.
            payload=None,
            ephemeral_captured_at=datetime.now(tz=UTC),
        )
        registry = build_default_selector_registry()
        matcher = OpenCvTemplateMatcher()
        recognizer = load_visual_screen_recognizer(CATALOG_PATH, matcher=matcher)
        enricher = PncObservationEnricher(selector_registry=registry, template_matcher=matcher)
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(matcher),
            screen_classifier=ScreenClassifier(),
            enricher=enricher,
            visual_recognizer=recognizer,
            ocr_service=_require_rapid_ocr_service(self),
            ocr_backend_revision=f"a02:{layout_id}",
        )
        navigation = NavigationPerception(
            recognizer,
            enricher,
            ScreenClassifier(),
            builder.create_ocr_context,
        )
        return (
            (
                "observation_builder",
                builder.build(
                    capture,
                    request=ObservationRequest.source_screen_retry(screen),
                ),
            ),
            ("navigation_perception", navigation.build(capture, include_content=True)),
        )

    def test_barracks_publish_no_mutation_controls(self) -> None:
        """Qualified family identity and Back do not enable training controls."""
        for fixture_name, screen, layout_id, _, _, _ in BARRACKS_REFERENCES:
            with Image.open(FIXTURE_ROOT / fixture_name) as source:
                image = source.copy()
            for observer_name, observation in self._both_observations(image, screen, layout_id):
                with self.subTest(fixture=fixture_name, observer=observer_name):
                    self.assertEqual(screen, observation.screen_type)
                    self.assertIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, observation.visible_elements)
                    self.assertTrue(
                        BARRACKS_MUTATION_SELECTORS.isdisjoint(observation.visible_elements)
                    )

    def test_barracks_identity_does_not_follow_the_requested_family(self) -> None:
        """The native frame determines identity even when another family is requested."""
        for fixture_name, screen, layout_id, _, _, _ in BARRACKS_REFERENCES:
            other_screen = next(item[1] for item in BARRACKS_REFERENCES if item[1] != screen)
            with Image.open(FIXTURE_ROOT / fixture_name) as source:
                image = source.copy()
            for observer_name, observation in self._both_observations(image, other_screen, layout_id):
                with self.subTest(fixture=fixture_name, observer=observer_name):
                    self.assertEqual(screen, observation.screen_type)
                    self.assertNotEqual(other_screen, observation.screen_type)
                    self.assertEqual(layout_id, observation.decision.layout_id)

    def test_erased_identity_anchor_blocks_barracks_identity(self) -> None:
        """Neither family title nor description alone may qualify the shared panel."""
        for fixture_name, screen, layout_id, _, identity_boxes, _ in BARRACKS_REFERENCES:
            with Image.open(FIXTURE_ROOT / fixture_name) as source:
                image = source.copy()
            for label, box in zip(("title", "description"), identity_boxes, strict=True):
                erased = image.copy()
                ImageDraw.Draw(erased).rectangle(box, fill=(10, 20, 40))
                for observer_name, observation in self._both_observations(erased, screen, layout_id):
                    with self.subTest(fixture=fixture_name, erased=label, observer=observer_name):
                        self.assertEqual(ScreenType.UNKNOWN, observation.screen_type)
                        self.assertFalse(observation.visible_elements)

    def test_erased_back_anchor_preserves_identity_but_withholds_control(self) -> None:
        """A missing measured Back cannot be recovered from geometry or content."""
        for fixture_name, screen, layout_id, _, _, back_box in BARRACKS_REFERENCES:
            with Image.open(FIXTURE_ROOT / fixture_name) as source:
                erased = source.copy()
            ImageDraw.Draw(erased).rectangle(back_box, fill=(10, 20, 40))
            for observer_name, observation in self._both_observations(erased, screen, layout_id):
                with self.subTest(fixture=fixture_name, observer=observer_name):
                    self.assertEqual(screen, observation.screen_type)
                    self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, observation.visible_elements)


if __name__ == "__main__":
    unittest.main()
