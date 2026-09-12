"""Hero observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class HeroObservationTests(unittest.TestCase):
    """Proves hero observation."""

    def test_observation_builder_types_hero_showdown_audit_screens(self) -> None:
        """Types every reviewed Arena audit destination from semantic OCR evidence."""

        versus = _build_observation_from_ocr_lines(
            (
                _ocr_line("Versus Center", x=280, y=20, width=340, height=40),
                _ocr_line("Arena", x=180, y=1450, width=100, height=35),
                _ocr_line("Hero Showdown", x=260, y=260, width=300, height=40),
            )
        )
        intro = _build_observation_from_ocr_lines(
            (
                _ocr_line("Elemental Fluctuation Intro", x=180, y=210, width=540, height=40),
                _ocr_line("Confirm", x=390, y=1040, width=120, height=35),
            )
        )
        formation = _build_observation_from_ocr_lines(
            (_ocr_line("Save Form", x=350, y=1490, width=200, height=40),)
        )
        ranking = _build_observation_from_ocr_lines(
            (
                _ocr_line("Hero Showdown", x=180, y=20, width=300, height=40),
                _ocr_line("Current rank: 5635", x=220, y=120, width=300, height=35),
                _ocr_line("Challenge", x=350, y=1450, width=200, height=40),
            )
        )

        self.assertEqual(versus.screen_type, ScreenType.PNC_VERSUS_CENTER)
        self.assertEqual(
            versus.require(UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertEqual(intro.screen_type, ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO)
        self.assertEqual(
            intro.require(UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_CONFIRM_BUTTON).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertEqual(formation.screen_type, ScreenType.PNC_HERO_FORMATION)
        self.assertEqual(
            formation.require(UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertEqual(ranking.screen_type, ScreenType.PNC_HERO_SHOWDOWN_RANKING)
        self.assertEqual(
            ranking.require(UiElementId.PNC_HERO_SHOWDOWN_CHALLENGE_BUTTON).source_kind,
            VisibleElementSourceKind.OCR,
        )

    def test_observation_builder_types_hero_hall_free_recruit_control(self) -> None:
        """Classifies Hero Hall and exposes only the free single recruit control."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Hero Hall", x=300, y=24, width=280, height=42),
                _ocr_line("Recruit", x=165, y=142, width=130, height=36),
                _ocr_line("Exchange", x=600, y=142, width=150, height=36),
                _ocr_line("Daily attempts: 5", x=117, y=1104, width=260, height=32),
                _ocr_line("Free", x=123, y=1176, width=75, height=32),
            )
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
        banner = observation.require(UiElementId.PNC_HERO_HALL_RECRUIT_BANNER)
        recruit = observation.require(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON)
        self.assertEqual(banner.extracted_text, "Daily attempts: 5")
        self.assertIsNone(recruit.extracted_text)
        self.assertEqual(recruit.source_kind, VisibleElementSourceKind.GEOMETRY)
        self.assertIsNone(recruit.action_point)
        self.assertEqual(recruit.bounds.center(), (239, 1200))
        self.assertFalse(observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_10X_BUTTON))

    def test_observation_builder_does_not_treat_hero_hall_cooldown_as_free_control(self) -> None:
        """Keeps the paid Recruit 1x geometry unavailable while the free timer is running."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Hero Hall", x=300, y=24, width=280, height=42),
                _ocr_line("Recruit", x=165, y=142, width=130, height=36),
                _ocr_line("Exchange", x=600, y=142, width=150, height=36),
                _ocr_line("Free in 00:08:31", x=73, y=1104, width=148, height=17),
            )
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
        self.assertEqual(
            observation.require(UiElementId.PNC_HERO_HALL_RECRUIT_BANNER).extracted_text,
            "Free in 00:08:31",
        )
        self.assertFalse(observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON))
