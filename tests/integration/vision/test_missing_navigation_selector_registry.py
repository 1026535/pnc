"""Coverage for reviewed navigation controls missing from the selector catalog."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.automation.engine.navigation_core import reviewed_navigation_edges
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorStatus,
    build_default_selector_registry,
)
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition"


def _capture(fixture_name: str) -> CapturedScreenshot:
    """Load one committed visual fixture and attach a fresh frame proof."""

    with Image.open(FIXTURE_ROOT / fixture_name) as source:
        image = source.convert("RGB")
    frame = make_captured_frame(_encode_png(image), session_id="missing-selector-registry")
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _perception() -> NavigationPerception:
    """Wire visual recognition to the canonical navigation perception boundary."""

    ocr = _FakeOcrService(lines=())
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "missing-selector-registry-test",
        ),
    )


class MissingNavigationSelectorRegistryTests(unittest.TestCase):
    """Keep reviewed profile controls registered without inventing geometry."""

    def test_missing_controls_have_exact_profile_backed_source_scopes(self) -> None:
        """Requires semantic planned entries to name only their reviewed source screens."""

        expected = {
            UiElementId.PNC_MORE_RANK: (ScreenType.PNC_MORE_MENU,),
            UiElementId.PNC_SETTINGS_RANK: (ScreenType.PNC_SETTINGS,),
            UiElementId.PNC_SETTINGS_PREFERENCES: (ScreenType.PNC_SETTINGS,),
            UiElementId.PNC_SETTINGS_NOTIFICATIONS: (ScreenType.PNC_SETTINGS,),
            UiElementId.PNC_WORLD_HUD_TOGGLE: (
                ScreenType.PNC_WORLD_MAP,
                ScreenType.PNC_WORLD_MAP_EXPANDED,
            ),
        }
        registry = build_default_selector_registry()
        for selector_id, source_screens in expected.items():
            with self.subTest(selector=selector_id):
                definition = registry.require_supported(selector_id)
                self.assertEqual(definition.screens, source_screens)
                self.assertEqual(definition.status, SelectorStatus.PLANNED)
                self.assertEqual(definition.detection_kind, DetectionKind.SEMANTIC)
                self.assertFalse(definition.materialize_relative_bounds)
                self.assertIsNone(definition.relative_bounds)

    def test_reviewed_profiles_produce_all_missing_controls_on_saved_fixtures(self) -> None:
        """Binds each registration to the profile and fixture that actually emits it."""

        expected = (
            ("more_overlay.png", "more_overlay", ScreenType.PNC_MORE_MENU, {UiElementId.PNC_MORE_RANK}),
            (
                "settings.png",
                "settings",
                ScreenType.PNC_SETTINGS,
                {
                    UiElementId.PNC_SETTINGS_RANK,
                    UiElementId.PNC_SETTINGS_PREFERENCES,
                    UiElementId.PNC_SETTINGS_NOTIFICATIONS,
                },
            ),
            (
                "world_map_core.png",
                "world_map",
                ScreenType.PNC_WORLD_MAP,
                {UiElementId.PNC_WORLD_HUD_TOGGLE},
            ),
            (
                "world_expanded_core.png",
                "world_expanded",
                ScreenType.PNC_WORLD_MAP_EXPANDED,
                {UiElementId.PNC_WORLD_HUD_TOGGLE},
            ),
        )
        recognizer = load_visual_screen_recognizer()
        for fixture_name, profile_id, screen, selector_ids in expected:
            with self.subTest(fixture=fixture_name):
                with Image.open(FIXTURE_ROOT / fixture_name) as source:
                    recognition = recognizer.recognize(source.convert("RGB"))
                self.assertIn(profile_id, recognition.profile_ids)
                self.assertEqual({item.screen_type for item in recognition.evidence}, {screen})
                self.assertTrue(
                    selector_ids <= {item.selector_id for item in recognition.controls}
                )

    def test_action_executor_dispatches_profile_controls_with_frame_provenance(self) -> None:
        """Dispatches each visual target only from its current captured frame."""

        expected = (
            ("more_overlay.png", ScreenType.PNC_MORE_MENU, UiElementId.PNC_MORE_RANK),
            ("settings.png", ScreenType.PNC_SETTINGS, UiElementId.PNC_SETTINGS_RANK),
            ("settings.png", ScreenType.PNC_SETTINGS, UiElementId.PNC_SETTINGS_PREFERENCES),
            ("settings.png", ScreenType.PNC_SETTINGS, UiElementId.PNC_SETTINGS_NOTIFICATIONS),
            ("world_map_core.png", ScreenType.PNC_WORLD_MAP, UiElementId.PNC_WORLD_HUD_TOGGLE),
            (
                "world_expanded_core.png",
                ScreenType.PNC_WORLD_MAP_EXPANDED,
                UiElementId.PNC_WORLD_HUD_TOGGLE,
            ),
        )
        session = FakeSession()
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        expected_taps: list[tuple[int, int]] = []
        for fixture_name, screen, selector_id in expected:
            with self.subTest(fixture=fixture_name, selector=selector_id):
                observation = _perception().build(_capture(fixture_name))
                self.assertEqual(observation.screen_type, screen)
                target = observation.require(selector_id)
                self.assertEqual(target.source_kind, VisibleElementSourceKind.TEMPLATE)
                expected_taps.append(target.action_point or target.bounds.center())
                self.assertTrue(executor.execute_action(TapAction(selector_id=selector_id), observation))
        self.assertEqual(session.taps, expected_taps)

    def test_reviewed_navigation_edges_use_supported_registry_selectors(self) -> None:
        """Prevents a reviewed graph edge from bypassing the canonical registry."""

        registry = build_default_selector_registry()
        for edge in reviewed_navigation_edges():
            with self.subTest(source=edge.source, selector=edge.selector):
                self.assertEqual(registry.require_supported(edge.selector).id, edge.selector)


if __name__ == "__main__":
    unittest.main()
