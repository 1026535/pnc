"""Mail profile observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.ocr_line import _ocr_line


class MailProfileObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail profile observation."""

    def test_observation_builder_parses_player_profile_without_current_castle(self) -> None:
        """Keeps remote profile identity separate from self-profile current-castle validation."""

        observation = _build_observation(
            request=ObservationRequest.player_profile_follow_up(),
            lines=(
                _ocr_line("Player Profile", x=240, y=38, width=180, height=24),
                _ocr_line("Enemy Bob", x=300, y=420, width=140, height=26),
                _ocr_line("Mail", x=720, y=1190, width=90, height=26),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_PLAYER_PROFILE)
        self.assertEqual(observation.profile_player_name, "Enemy Bob")
        self.assertIsNone(observation.current_castle)

    def test_observation_builder_parses_live_remote_profile_layout_without_header_text(self) -> None:
        """Recognizes the live gear-tab remote profile layout even when no Player Profile title is visible."""

        registry = build_default_selector_registry()
        expected_mail_button = registry.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).relative_bounds.materialize(  # type: ignore[union-attr]
            selector_id=UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON,
            image_size=(900, 1600),
        )
        observation = _build_observation(
            request=ObservationRequest.player_profile_follow_up(),
            lines=(
                _ocr_line("Cutie Voj", x=116, y=20, width=168, height=36),
                _ocr_line("Gear", x=48, y=108, width=86, height=30),
                _ocr_line("Gem", x=210, y=108, width=78, height=30),
                _ocr_line("Saurgem", x=352, y=108, width=144, height=30),
                _ocr_line("Warsigil", x=544, y=108, width=138, height=30),
                _ocr_line("Saurgil", x=708, y=108, width=118, height=30),
                _ocr_line("Mail", x=690, y=1338, width=80, height=34),
                _ocr_line("Achievements", x=700, y=1468, width=160, height=28),
                _ocr_line("Alliance Info", x=170, y=1468, width=176, height=28),
                _ocr_line("Settings", x=418, y=1468, width=108, height=28),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_PLAYER_PROFILE)
        self.assertEqual(observation.profile_player_name, "Cutie Voj")
        self.assertTrue(observation.has(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON))
        self.assertEqual(
            observation.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).action_point,
            expected_mail_button.action_point,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertIsNone(observation.current_castle)

    def test_observation_builder_keeps_profile_mail_button_when_live_layout_ocr_misses_mail_label(self) -> None:
        """Materializes the profile mail button from stable layout geometry when OCR misses the Mail footer label."""

        registry = build_default_selector_registry()
        expected_mail_button = registry.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).relative_bounds.materialize(  # type: ignore[union-attr]
            selector_id=UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON,
            image_size=(900, 1600),
        )
        observation = _build_observation(
            request=ObservationRequest.player_profile_follow_up(),
            lines=(
                _ocr_line("LadiesLoveCake", x=187, y=26, width=355, height=40),
                _ocr_line("Gear", x=40, y=105, width=88, height=30),
                _ocr_line("Gem", x=200, y=105, width=78, height=30),
                _ocr_line("Saurgem", x=344, y=105, width=146, height=30),
                _ocr_line("Warsigil", x=542, y=105, width=136, height=30),
                _ocr_line("Saurgil", x=700, y=105, width=118, height=30),
                _ocr_line("English", x=212, y=1208, width=102, height=28),
                _ocr_line("[AAS] LadiesLoveCake", x=360, y=1208, width=246, height=28),
                _ocr_line("Hero List", x=392, y=1398, width=118, height=28),
                _ocr_line("More Info", x=707, y=1398, width=126, height=28),
                _ocr_line("Lord Info", x=54, y=1544, width=126, height=30),
                _ocr_line("Alliance Info", x=178, y=1544, width=192, height=30),
                _ocr_line("Settings", x=426, y=1544, width=112, height=30),
                _ocr_line("Achievements", x=718, y=1544, width=170, height=30),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_PLAYER_PROFILE)
        self.assertEqual(observation.profile_player_name, "LadiesLoveCake")
        self.assertTrue(observation.has(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON))
        self.assertEqual(
            observation.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON).action_point,
            expected_mail_button.action_point,
        )
