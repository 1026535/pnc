"""Production-stack regressions for reviewed mail and world-map controls."""

from __future__ import annotations

import unittest
import json
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.mail import MailboxType, MailRecipientKind, SendMailParams
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapOverviewNavigator
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import Region, build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.test_support import FakeSession, make_captured_frame, make_observation, build_logger


class _DeterministicOcr:
    """Returns fixed OCR lines while preserving region clipping semantics."""

    def __init__(self, lines: tuple[OcrLine, ...]) -> None:
        self.lines = lines

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        del image
        if region is None:
            return self.lines
        return tuple(
            line
            for line in self.lines
            if line.bounds.x >= region.x
            and line.bounds.y >= region.y
            and line.bounds.x + line.bounds.width <= region.x + region.width
            and line.bounds.y + line.bounds.height <= region.y + region.height
        )

    def read_text(self, image: Image.Image, region: Region) -> str:
        return "\n".join(line.text for line in self.read_lines(image, region))


def _line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    return OcrLine(text=text, bounds=Region(x=x, y=y, width=width, height=height), confidence=0.99)


def _build_observation(
    lines: tuple[OcrLine, ...],
    *,
    image_size: tuple[int, int] = (900, 1600),
    image: Image.Image | None = None,
    request: ObservationRequest | None = None,
):
    """Builds one capture through the production selector, classifier, and enricher stack."""

    image = Image.new("RGB", image_size, (15, 28, 68)) if image is None else image.copy()
    screenshot = SimpleNamespace(
        image=image,
        artifact=SimpleNamespace(path=Path("review_navigation_controls.png"), captured_at=None),
        frame_ref=make_captured_frame(b"review-navigation-controls").frame_ref,
    )
    registry = build_default_selector_registry()
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=_DeterministicOcr(lines),
    )
    return builder.build(screenshot, request=request or ObservationRequest.full_runtime_default())


def _mail_hub_lines(*, scale: float = 1.0) -> tuple[OcrLine, ...]:
    def scaled(value: int) -> int:
        return int(value * scale)

    return (
        _line("Mail", x=scaled(310), y=scaled(42), width=scaled(110), height=scaled(24)),
        _line("Player Mail", x=scaled(220), y=scaled(317), width=scaled(155), height=scaled(39)),
        _line("No report yet", x=scaled(670), y=scaled(320), width=scaled(188), height=scaled(35)),
        _line("Alliance Mail", x=scaled(221), y=scaled(481), width=scaled(176), height=scaled(32)),
        _line("No report yet", x=scaled(670), y=scaled(480), width=scaled(189), height=scaled(38)),
    )


def _chat_decoration_fixture() -> tuple[Image.Image, tuple[OcrLine, ...]]:
    fixture_root = Path(__file__).parent / "data" / "screen_recognition"
    image = Image.open(fixture_root / "chat_decoration_review.png").convert("RGB")
    payload = json.loads((fixture_root / "chat_decoration_review_ocr.json").read_text(encoding="utf-8"))
    lines = tuple(
        _line(
            item["text"],
            x=item["bounds"]["x"],
            y=item["bounds"]["y"],
            width=item["bounds"]["width"],
            height=item["bounds"]["height"],
        )
        for item in payload["unidentified_ocr_lines"]
    )
    return image, lines


def _world_overview_fixture() -> tuple[Image.Image, tuple[OcrLine, ...]]:
    fixture_root = Path(__file__).parent / "data" / "screen_recognition"
    image = Image.open(fixture_root / "world_overview_review.png").convert("RGB")
    payload = json.loads((fixture_root / "world_overview_review_ocr.json").read_text(encoding="utf-8"))
    lines = tuple(
        _line(
            item["text"],
            x=item["bounds"]["x"],
            y=item["bounds"]["y"],
            width=item["bounds"]["width"],
            height=item["bounds"]["height"],
        )
        for item in payload["unidentified_ocr_lines"]
    )
    return image, lines


class ReviewNavigationControlsTests(unittest.TestCase):
    """Keeps guarded controls tied to reviewed screen identity and geometry."""

    def test_player_mailbox_compose_is_produced_and_dispatched(self) -> None:
        observation = _build_observation(
            (
                _line("Player Mail", x=183, y=17, width=292, height=52),
                _line("Manage", x=678, y=44, width=108, height=35),
                _line("No report yet", x=300, y=730, width=180, height=26),
            ),
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(observation.mailbox_type, MailboxType.PLAYER)
        self.assertTrue(observation.mailbox_empty)
        compose = observation.require(UiElementId.PNC_MAIL_COMPOSE_BUTTON)
        self.assertEqual(compose.action_point, (819, 240))

        action = ScreenFlowPlanner().open_mail_compose(
            observation,
            SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="World",
            ),
        )[0]
        self.assertIsInstance(action, TapAction)
        self.assertEqual(action.selector_id, UiElementId.PNC_MAIL_COMPOSE_BUTTON)

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
        executor.execute_action(action, observation)
        self.assertEqual(session.taps, [(819, 240)])

    def test_mail_hub_has_no_compose_and_empty_player_refuses_before_input(self) -> None:
        observation = _build_observation(_mail_hub_lines())

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_HUB)
        self.assertEqual(observation.empty_mailboxes, frozenset({MailboxType.PLAYER, MailboxType.ALLIANCE}))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_BUTTON))

        session = FakeSession()
        with self.assertRaises(SelectorResolutionError):
            ScreenFlowPlanner().open_mail_compose(
                observation,
                SendMailParams(
                    recipient_kind=MailRecipientKind.PLAYER,
                    player_name="Enemy Bob",
                    profile_route=None,
                    subject="Hello",
                    body="World",
                ),
            )
        self.assertEqual(session.taps, [])
        self.assertEqual(session.texts, [])

    def test_mail_hub_empty_label_is_scoped_to_its_category(self) -> None:
        observation = _build_observation(
            (
                _line("Mail", x=310, y=42, width=110, height=24),
                _line("Player Mail", x=220, y=317, width=155, height=39),
                _line("Alliance Mail", x=221, y=481, width=176, height=32),
                _line("No report yet", x=670, y=480, width=189, height=38),
            )
        )
        self.assertEqual(observation.empty_mailboxes, frozenset({MailboxType.ALLIANCE}))
        self.assertNotIn(MailboxType.PLAYER, observation.empty_mailboxes)

    def test_non_player_mailboxes_and_unreviewed_mail_hub_lack_compose(self) -> None:
        alliance_mailbox = _build_observation(
            (
                _line("Alliance Mail", x=183, y=17, width=292, height=52),
                _line("No report yet", x=300, y=730, width=180, height=26),
            ),
            request=ObservationRequest.mailbox_observation(MailboxType.ALLIANCE),
        )
        self.assertEqual(alliance_mailbox.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertFalse(alliance_mailbox.has(UiElementId.PNC_MAIL_COMPOSE_BUTTON))

        unreviewed_hub = _build_observation(_mail_hub_lines(scale=0.8), image_size=(720, 1280))
        self.assertEqual(unreviewed_hub.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(unreviewed_hub.has(UiElementId.PNC_MAIL_COMPOSE_BUTTON))

    def test_reviewed_world_map_expand_is_planned_and_dispatched(self) -> None:
        observation = _build_observation(
            (
                _line("X:253", x=73, y=67, width=71, height=24),
                _line("Y:447", x=177, y=67, width=69, height=24),
                _line("Home", x=63, y=1563, width=76, height=28),
                _line("Hero", x=213, y=1567, width=62, height=25),
                _line("Quest", x=331, y=1571, width=69, height=20),
                _line("Mail", x=533, y=1568, width=55, height=24),
                _line("Alliance", x=666, y=1567, width=100, height=26),
                _line("More", x=795, y=1568, width=70, height=25),
            )
        )
        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_EXPAND_BUTTON))

        action = WorldMapOverviewNavigator().plan_open(observation)[0]
        self.assertIsInstance(action, TapAction)
        self.assertEqual(action.selector_id, UiElementId.PNC_WORLD_EXPAND_BUTTON)

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
        executor.execute_action(action, observation)
        self.assertEqual(session.taps, [(58, 1184)])

    def test_unreviewed_world_map_popup_and_unknown_do_not_authorize_expand(self) -> None:
        unreviewed = _build_observation(
            (
                _line("X:253", x=58, y=55, width=56, height=19),
                _line("Y:447", x=142, y=54, width=56, height=19),
                _line("Home", x=50, y=1250, width=61, height=22),
                _line("Hero", x=170, y=1254, width=50, height=20),
                _line("Quest", x=265, y=1256, width=56, height=16),
                _line("Mail", x=426, y=1254, width=44, height=19),
                _line("Alliance", x=533, y=1254, width=59, height=21),
                _line("More", x=636, y=1254, width=56, height=20),
            ),
            image_size=(720, 1280),
        )
        self.assertEqual(unreviewed.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(unreviewed.has(UiElementId.PNC_WORLD_EXPAND_BUTTON))
        with self.assertRaises(SelectorResolutionError):
            WorldMapOverviewNavigator().plan_open(unreviewed)

        for blocked in (
            make_observation(ScreenType.PNC_POPUP, blocking_popup=True),
            make_observation(ScreenType.UNKNOWN),
        ):
            with self.subTest(screen_type=blocked.screen_type), self.assertRaises(SelectorResolutionError):
                WorldMapOverviewNavigator().plan_open(blocked)

    def test_chat_decoration_fixture_does_not_authorize_world_expand_or_mail_compose(self) -> None:
        image, lines = _chat_decoration_fixture()
        observation = _build_observation(lines, image=image, image_size=image.size)

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_EXPAND_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_BUTTON))

    def test_reviewed_world_overview_fixture_excludes_its_close_x_from_popup_guard(self) -> None:
        image, lines = _world_overview_fixture()
        observation = _build_observation(lines, image=image, image_size=image.size)

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)
        self.assertFalse(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_world_overview_additional_close_x_remains_unresolved(self) -> None:
        image, lines = _world_overview_fixture()
        draw = ImageDraw.Draw(image)
        draw.line((874, 53, 891, 69), fill=(255, 255, 255), width=3)
        draw.line((891, 53, 874, 69), fill=(255, 255, 255), width=3)

        observation = _build_observation(lines, image=image, image_size=image.size)

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_strong_update_popup_stays_blocked_when_overview_pixels_are_present(self) -> None:
        image, overview_lines = _world_overview_fixture()
        lines = (
            *overview_lines,
            _line("New version detected. Tap Confirm to update.", x=59, y=385, width=408, height=19),
            _line("Confirm", x=234, y=800, width=73, height=20),
        )
        observation = _build_observation(lines, image=image, image_size=image.size)

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))

    def test_close_x_without_overview_header_is_fail_safe(self) -> None:
        image, _ = _world_overview_fixture()
        observation = _build_observation((), image=image, image_size=image.size)

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))


if __name__ == "__main__":
    unittest.main()
