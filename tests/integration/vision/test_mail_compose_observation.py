"""Mail compose observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine

from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.build_observation import _build_observation
from tests.support.pnc.mail.ocr_line import _ocr_line
from tests.support.pnc.mail.fake_ocr_service import _FakeOcrService


def _parse_legacy_compose_fields(*, image: Image.Image, lines: tuple[OcrLine, ...]):
    """Exercise the preserved field parser without claiming visual qualification."""

    context = ObservationOcrContext(image, _FakeOcrService(lines=lines), None, "legacy-compose-fields")
    context.require_bounded_regions()
    return PncObservationEnricher(
        selector_registry=build_default_selector_registry(),
    )._build_mail_compose_additions(
        image=image, lines=lines, include_fields=True, ocr_context=context, ocr_regions={},
    )


class MailComposeObservationTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail compose observation."""

    def test_observation_builder_parses_mail_compose_popup_field_states(self) -> None:
        """Builds the compose popup plus canonical shared text-field state from OCR-backed field regions."""

        registry = build_default_selector_registry()
        image_size = (900, 1600)
        target_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]
        subject_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]
        body_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]

        observation = _build_observation(
            request=ObservationRequest.mail_compose_follow_up(),
            accepted_screen=ScreenType.PNC_MAIL_COMPOSE_POPUP,
            layout_id="mail_compose_semantic",
            semantic_parser=_parse_legacy_compose_fields,
            lines=(
                _ocr_line("Edit Mail", x=305, y=240, width=180, height=24),
                _ocr_line("Send", x=782, y=1380, width=70, height=22),
                _ocr_line("Enemy Bob", x=target_region.x + 10, y=target_region.y + 8, width=120, height=22),
                _ocr_line("Greetings", x=subject_region.x + 10, y=subject_region.y + 8, width=120, height=22),
                _ocr_line("Welcome to automation.", x=body_region.x + 10, y=body_region.y + 12, width=220, height=24),
            ),
            image_size=image_size,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD).text,
            "Enemy Bob",
        )
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).text,
            "Greetings",
        )
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).text,
            "Welcome to automation.",
        )

    def test_observation_builder_parses_centered_live_like_mail_compose_popup(self) -> None:
        """Recognizes the centered live Edit Mail modal instead of leaving the compose popup as unknown."""

        observation = _build_observation(
            request=ObservationRequest.mail_compose_follow_up(),
            accepted_screen=ScreenType.PNC_MAIL_COMPOSE_POPUP,
            layout_id="mail_compose_centered",
            lines=(
                _ocr_line("Edit Mail", x=363, y=378, width=179, height=41),
                _ocr_line("Alliance Mail", x=170, y=498, width=200, height=30),
                _ocr_line("Can enter up to 1000 characters", x=86, y=670, width=390, height=28),
                _ocr_line("Send", x=405, y=1109, width=92, height=40),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD).text,
            "Alliance Mail",
        )
        # No subject placeholder is visible in this centered capture; OCR
        # absence is an unknown field state, not proof of emptiness.
        self.assertIsNone(observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).empty)
        self.assertTrue(observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).empty)
        self.assertTrue(observation.has(UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON))
