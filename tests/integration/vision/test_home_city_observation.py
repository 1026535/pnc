"""Home city semantic projection checks using offline OCR geometry."""

from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialSurfaceType,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_home_city_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query
from tests.support.pnc.mail.build_chat_fixture_image import _build_chat_fixture_image
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.encode_png import _encode_png
from tests.support.pnc.mail.fake_ocr_service import _FakeOcrService
from tests.support.pnc.mail.fake_screenshot_session import _FakeScreenshotSession


class HomeCityObservationTests(unittest.TestCase):
    """Proves the home-city parser after an explicit screen decision."""

    def test_observation_builder_classifies_home_city_from_bottom_nav_ocr(self) -> None:
        """Projects bottom navigation and home actions through the canonical parser."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=120, y=1180, width=90, height=30),
                _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                _ocr_line("More", x=740, y=1500, width=74, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_VIP_SHORTCUT))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_IMPROVE_MIGHT_SHORTCUT))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_live_like_home_city_when_build_anchor_is_left_aligned(self) -> None:
        """Keeps a left-rail Build anchor in the canonical home action projection."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=27, y=354, width=65, height=28),
                _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
        self.assertIsNotNone(observation.spatial_surface)
        self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_busy_builder_home_city_from_help_anchor(self) -> None:
        """Treats the occupied-builder Help label as the canonical build-slot signal."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Help", x=27, y=354, width=58, height=28),
                _ocr_line("(1/1)", x=20, y=389, width=76, height=26),
                _ocr_line("Research", x=121, y=1182, width=118, height=29),
                _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                _ocr_line("Mail", x=571, y=1568, width=57, height=24),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_exposes_home_city_active_build_timer_and_building_level(self) -> None:
        """Preserves timer, building level, and current OCR geometry in the spatial surface."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_HOME_CITY,
            semantic_parser=_build_home_city_semantic_additions,
            lines=(
                _ocr_line("Build", x=27, y=354, width=65, height=28),
                _ocr_line("Wall", x=455, y=918, width=81, height=28),
                _ocr_line("6", x=506, y=956, width=22, height=22),
                _ocr_line("00:48:33", x=404, y=872, width=140, height=24),
                _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                _ocr_line("More", x=795, y=1568, width=70, height=25),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.metadata["active_build_timer_text"], "00:48:33")
        wall = observation.require_spatial_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                kind=SpatialObjectKind.HOME_BUILDING,
                metadata_key="home_city_object_id",
                metadata_value="wall",
            )
        )
        self.assertEqual(wall.level, 6)

    def test_visually_proved_clear_home_city_keeps_measured_navigation_controls(self) -> None:
        """A visually-proved CLEAR home city keeps OCR-anchored nav the profile lacks.

        The ``home_city`` visual profile owns template controls for the bottom
        nav tabs that match (Quest/Bag/Mail/More), but Alliance and Hero have no
        stable icon template — they only exist as semantic selectors derived
        from footer OCR anchors. The CLEAR-screen rebuild once discarded them,
        which hid ``PNC_BOTTOM_NAV_ALLIANCE`` from the canonical navigation
        planner on exactly the visually-proved path it relies on. Measured
        navigation controls now ride alongside the visual controls while the
        profile keeps ownership of every control it claims.
        """

        class _HomeCityVisualRecognizer:
            """Publishes the home-city profile shape: template nav, no Alliance/Hero."""

            def recognize(self, image, **kwargs):
                del image, kwargs
                controls = tuple(
                    VisibleElement(
                        selector_id=selector_id,
                        bounds=bounds,
                        confidence=0.99,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                        action_point=(bounds.x + bounds.width // 2, bounds.y + bounds.height // 2),
                    )
                    for selector_id, bounds in (
                        (UiElementId.PNC_HOME_BUILD_BUTTON, Bounds(20, 1380, 100, 80)),
                        (UiElementId.PNC_HOME_RESEARCH_BUTTON, Bounds(140, 1380, 100, 80)),
                        (UiElementId.PNC_HOME_WORLD_SWITCH, Bounds(20, 1480, 90, 100)),
                        (UiElementId.PNC_BOTTOM_NAV_QUEST, Bounds(280, 1440, 130, 140)),
                        (UiElementId.PNC_BOTTOM_NAV_BAG, Bounds(390, 1440, 130, 140)),
                        (UiElementId.PNC_BOTTOM_NAV_MORE, Bounds(700, 1440, 130, 140)),
                        (UiElementId.PNC_BOTTOM_NAV_MAIL, Bounds(520, 1440, 130, 140)),
                    )
                )
                return VisualRecognition(
                    evidence=(
                        ScreenEvidence(
                            ScreenType.PNC_HOME_CITY,
                            "visual_anchor:home_city",
                            layout_id="home_city",
                        ),
                    ),
                    profile_ids=("home_city",),
                    controls=controls,
                    control_selector_ids=frozenset(
                        element.selector_id for element in controls
                    ),
                )

        image = _build_chat_fixture_image(image_size=(900, 1600))
        payload = _encode_png(image)
        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot_service = ScreenshotService(
                artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts"),
            )
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(payload),
                artifact_directory="home_city_test",
                label="visual_home_city",
            )
            registry = build_default_selector_registry()
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(selector_registry=registry),
                visual_recognizer=_HomeCityVisualRecognizer(),
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                        _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                        _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                        _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                        _ocr_line("Mail", x=571, y=1568, width=57, height=24),
                        _ocr_line("More", x=795, y=1568, width=70, height=25),
                    )
                ),
            )
            observation = builder.build(
                screenshot,
                request=ObservationRequest.full_runtime_default(),
            )

        self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
        self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
        # Hero carries no reviewed click outcome, so it is not a dispatchable
        # navigation selector and stays unpublished here even though its OCR
        # anchor was read.
        self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_HERO))
        # Profile-owned controls keep their measured template geometry; OCR
        # content cannot replace them.
        bag = observation.visible_elements[UiElementId.PNC_BOTTOM_NAV_BAG]
        self.assertEqual(Bounds(390, 1440, 130, 140), bag.bounds)
        self.assertEqual(VisibleElementSourceKind.TEMPLATE, bag.source_kind)
