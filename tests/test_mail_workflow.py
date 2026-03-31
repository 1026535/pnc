"""Mail workflow tests covering params, flows, OCR enrichment, and archive persistence."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.collect_mail_task import CollectMailTask
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.authoring.config.models import AccountConfig, CastleIdentity, CredentialSource, DefaultsConfig, ResolvedCredentials
from pnc_automation.core.errors import ScriptValidationError, SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, KeyEventAction, LaunchAppAction, SwipeAction, TapAction, TapPointAction
from pnc_automation.app.pnc.domain.chat import ChatEntryKind, visible_player_chat_entries, visible_unsupported_chat_entries
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveMode,
    MailboxType,
    MailRecipientKind,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder, PillowSelectorEngine
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import Region, build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import PillowTemplateMatcher
from tests.test_support import FakeObservationService, FakeSession, build_logger, build_png_bytes, make_entry, make_observation


class MailWorkflowTests(unittest.TestCase):
    """Validates the mail-domain implementation from parsing to persistence."""

    def setUp(self) -> None:
        """Builds shared runtime inputs used across mail workflow tests."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.flows = ScreenFlowPlanner()
        self.logger = build_logger()

    def test_send_mail_task_parses_direct_player_params(self) -> None:
        """Accepts the canonical player-mail task shape with one explicit player name."""

        task = SendMailTask()

        params = task.parse_params(
            {
                "recipient_kind": "player",
                "player_name": "Enemy Bob",
                "subject": "Hello",
                "body": "Welcome to the kingdom.",
            }
        )

        self.assertEqual(
            params,
            SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="Welcome to the kingdom.",
            ),
        )

    def test_send_mail_task_rejects_invalid_recipient_shapes(self) -> None:
        """Rejects alliance/player payloads that violate the canonical recipient contract."""

        task = SendMailTask()

        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "alliance",
                    "player_name": "Should Fail",
                    "subject": "Hello",
                    "body": "World",
                }
            )
        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "subject": "Hello",
                    "body": "World",
                }
            )

    def test_send_mail_task_rejects_invalid_profile_route_shapes(self) -> None:
        """Rejects profile routes whose player-name requirements do not match the supported route kind."""

        task = SendMailTask()

        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "profile_route": {"kind": "player_territory", "player_name": "Enemy Bob"},
                    "subject": "Hello",
                    "body": "World",
                }
            )
        with self.assertRaises(ScriptValidationError):
            task.parse_params(
                {
                    "recipient_kind": "player",
                    "profile_route": {"kind": "chat_message"},
                    "subject": "Hello",
                    "body": "World",
                }
            )

    def test_collect_mail_task_parses_deduplicated_mailboxes(self) -> None:
        """Collapses duplicate mailbox names while preserving canonical ordering."""

        task = CollectMailTask()

        params = task.parse_params(
            {
                "mailboxes": ["player", "alliance", "player"],
                "archive_mode": "both",
                "limit_per_mailbox": 7,
                "only_new": True,
            }
        )

        self.assertEqual(
            params,
            CollectMailParams(
                mailboxes=(MailboxType.PLAYER, MailboxType.ALLIANCE),
                archive_mode=MailArchiveMode.BOTH,
                limit_per_mailbox=7,
                only_new=True,
            ),
        )

    def test_action_executor_clears_existing_mail_subject_field_before_typing(self) -> None:
        """Uses the generic observed text-field state to replace mail subject content in place."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            visible_ids=(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,),
            text_field_states={
                UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
                    text="Existing Subject",
                    empty=False,
                )
            },
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
                text="Updated Subject",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.key_events[0], "KEYCODE_MOVE_END")
        self.assertGreaterEqual(executor.session.key_events.count("KEYCODE_DEL"), 24)
        self.assertEqual(executor.session.texts, ["Updated Subject"])

    def test_action_executor_enters_multiline_mail_body(self) -> None:
        """Uses the shared multiline policy for the compose body instead of rejecting newlines outright."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,),
            text_field_states={
                UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD: ObservedTextFieldState(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
                    text=None,
                    empty=True,
                )
            },
        )

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
                text="First line\nSecond line",
                replace_existing=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.texts, ["First line", "Second line"])
        self.assertEqual(executor.session.key_events, ["KEYCODE_ENTER"])

    def test_open_mail_hub_uses_bottom_nav_mail(self) -> None:
        """Uses the shared mail bottom-nav selector to open the canonical mail hub."""

        actions = self.flows.open_mail_hub(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST),
        )

    def test_open_mail_hub_uses_visible_bottom_nav_from_world_map(self) -> None:
        """Uses the visible Mail bottom nav directly when world-adjacent screens already expose it."""

        actions = self.flows.open_mail_hub(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST),
        )

    def test_open_mail_hub_from_unknown_only_recovers_to_game_first(self) -> None:
        """Keeps mail-hub navigation incremental when starting from an unknown screen."""

        actions = self.flows.open_mail_hub(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_HOME")
        self.assertIsInstance(actions[1], LaunchAppAction)

    def test_open_mailbox_from_mail_hub_taps_requested_category(self) -> None:
        """Uses the requested mailbox category row instead of duplicating hub-specific navigation logic."""

        actions = self.flows.open_mailbox(
            make_observation(
                ScreenType.PNC_MAIL_HUB,
                visible_ids=(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL,),
            ),
            MailboxType.PLAYER,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAILBOX_LIST, ScreenType.PNC_MAIL_HUB),
        )

    def test_open_mailbox_from_home_only_opens_mail_hub_first(self) -> None:
        """Keeps mailbox navigation incremental so the task can observe mail-hub no-op states cleanly."""

        actions = self.flows.open_mailbox(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_MAIL,),
            ),
            MailboxType.PLAYER,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MAIL)

    def test_open_player_profile_from_alliance_member_uses_manage_then_personal_info(self) -> None:
        """Uses one manage-popup increment from the member list so the popup origin can be re-observed."""

        observation = make_observation(
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            list_entries=(make_entry(ListEntryKind.ALLIANCE_MEMBER, title="Enemy Bob", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP))

    def test_open_player_profile_from_alliance_member_requires_exact_case_before_tapping(self) -> None:
        """Keeps alliance-member route matching case-sensitive and continues the shared search when casing differs."""

        observation = make_observation(
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            list_entries=(make_entry(ListEntryKind.ALLIANCE_MEMBER, title="LadiesLoveCake", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="ladieslovecake",
            ),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "search_alliance_member_reset_to_top")

    def test_open_player_profile_from_home_with_chat_route_first_opens_chat(self) -> None:
        """Lets the shared route flow acquire chat from home instead of requiring caller-side setup."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_SHORTCUT)

    def test_open_player_profile_from_chat_popup_taps_profile_button(self) -> None:
        """Continues the chat-message route from its intermediate popup without restarting navigation."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
                visible_ids=(UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())

    def test_open_player_profile_from_home_with_alliance_member_route_first_opens_alliance_home(self) -> None:
        """Lets the shared route flow acquire alliance navigation from home before member-list entry."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)

    def test_open_alliance_home_from_unknown_only_recovers_to_game_first(self) -> None:
        """Keeps alliance-home navigation incremental when starting from an unknown screen."""

        actions = self.flows.open_alliance_home(make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_HOME")
        self.assertIsInstance(actions[1], LaunchAppAction)

    def test_open_alliance_home_uses_visible_bottom_nav_from_world_map(self) -> None:
        """Uses the visible Alliance bottom nav directly when world-adjacent screens already expose it."""

        actions = self.flows.open_alliance_home(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            )
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_ALLIANCE_HOME,
                ScreenType.PNC_ALLIANCE_JOIN,
            ),
        )

    def test_open_player_profile_from_alliance_home_with_alliance_member_route_opens_member_list(self) -> None:
        """Owns alliance-member list acquisition once the shared route flow is already on alliance home."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_HOME,
                visible_ids=(UiElementId.PNC_ALLIANCE_TILE_MEMBER,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_TILE_MEMBER)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_ALLIANCE_MEMBER_LIST,
                ScreenType.PNC_ALLIANCE_HOME,
            ),
        )

    def test_open_player_profile_from_member_manage_popup_taps_personal_info(self) -> None:
        """Continues the alliance-member route from its intermediate manage popup without backing out."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
                visible_ids=(UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())

    def test_open_player_profile_from_chat_message_uses_player_popup_then_profile_button(self) -> None:
        """Uses one popup-opening increment from chat so the popup origin is re-observed before profile navigation."""

        observation = make_observation(
            ScreenType.PNC_CHAT,
            list_entries=(make_entry(ListEntryKind.CHAT_MESSAGE, title="Enemy Bob", action_point=(170, 70)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.CHAT_MESSAGE,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP))

    def test_open_player_profile_from_might_rank_uses_visible_rank_entry(self) -> None:
        """Uses the visible ranked-player row action point instead of duplicating rank-screen tap logic."""

        observation = make_observation(
            ScreenType.PNC_MIGHT_RANK,
            list_entries=(make_entry(ListEntryKind.RANKED_PLAYER, title="Enemy Bob", action_point=(190, 80)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.player_profile_follow_up())

    def test_open_player_profile_from_might_rank_requires_exact_case_before_tapping(self) -> None:
        """Keeps Might Rank route matching case-sensitive and continues the shared search when casing differs."""

        observation = make_observation(
            ScreenType.PNC_MIGHT_RANK,
            list_entries=(make_entry(ListEntryKind.RANKED_PLAYER, title="LadiesLoveCake", action_point=(190, 80)),),
        )

        actions = self.flows.open_player_profile(
            observation,
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="ladieslovecake",
            ),
            runtime_state={},
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], SwipeAction)
        self.assertEqual(actions[0].reason, "search_might_rank_reset_to_top")

    def test_open_player_profile_from_home_with_might_rank_route_first_opens_alliance_home(self) -> None:
        """Lets the shared route flow acquire alliance home before opening the Might Rank route screen."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_ALLIANCE)

    def test_open_player_profile_from_alliance_home_with_might_rank_route_opens_rank_screen(self) -> None:
        """Owns Might Rank screen acquisition once the shared route flow reaches alliance home."""

        actions = self.flows.open_player_profile(
            make_observation(
                ScreenType.PNC_ALLIANCE_HOME,
                visible_ids=(UiElementId.PNC_ALLIANCE_TILE_RANK,),
            ),
            route=PlayerProfileRoute(
                kind=PlayerProfileRouteKind.MIGHT_RANK,
                player_name="Enemy Bob",
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_ALLIANCE_TILE_RANK)
        self.assertEqual(
            actions[0].follow_up_request,
            ObservationRequest.mail_navigation_follow_up(
                ScreenType.PNC_MIGHT_RANK,
                ScreenType.PNC_ALLIANCE_HOME,
            ),
        )

    def test_open_mail_compose_from_player_profile_taps_mail_button(self) -> None:
        """Uses the shared player-profile compose route for personal mail sends."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.PLAYER,
            player_name=None,
            profile_route=PlayerProfileRoute(kind=PlayerProfileRouteKind.PLAYER_TERRITORY),
            subject="Hello",
            body="World",
        )

        actions = self.flows.open_mail_compose(
            make_observation(
                ScreenType.PNC_PLAYER_PROFILE,
                visible_ids=(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON,),
            ),
            params,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_compose_follow_up())

    def test_open_mail_compose_from_player_mailbox_only_taps_compose(self) -> None:
        """Uses one compose-opening increment from the player mailbox so the compose popup is observed before target entry."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.PLAYER,
            player_name="Enemy Bob",
            profile_route=None,
            subject="Hello",
            body="World",
        )

        actions = self.flows.open_mail_compose(
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BUTTON,),
            ),
            params,
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_COMPOSE_BUTTON)
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.mail_compose_follow_up())

    def test_send_mail_verify_replans_when_direct_player_compose_target_still_needs_manual_entry(self) -> None:
        """Replans for target entry instead of failing as soon as the direct-player compose popup opens."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAILBOX_LIST, mailbox_type=MailboxType.PLAYER),
            after=make_observation(
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                text_field_states={
                    UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD: ObservedTextFieldState(
                        selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                        text="",
                        empty=True,
                    )
                },
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertIn("needs the requested player target typed", result.message)

    def test_send_mail_verify_prefers_observed_profile_header_name_over_route_lookup_name(self) -> None:
        """Uses the opened profile header as the authoritative target once a profile-route send reaches compose."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name=None,
                profile_route=PlayerProfileRoute(
                    kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                    player_name="Cutie",
                ),
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(
                ScreenType.PNC_PLAYER_PROFILE,
                profile_player_name="Cutie Voj",
            ),
            after=make_observation(
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                text_field_states={
                    UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD: ObservedTextFieldState(
                        selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                        text="Cutie Voj",
                        empty=False,
                    )
                },
            ),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertEqual(context.runtime_state["expected_profile_target"], "Cutie Voj")

    def test_send_mail_verify_mail_plan_opens_ambiguous_same_recipient_row_for_thread_confirmation(self) -> None:
        """Promotes a same-recipient mailbox row to thread confirmation instead of accepting it as proof."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"

        actions = task.plan(
            context,
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapPointAction)
        self.assertEqual(context.runtime_state["send_mail_phase"], "verify_thread")

    def test_send_mail_verify_succeeds_when_matching_sent_row_is_visible(self) -> None:
        """Accepts mailbox-only verification only when the visible row already contains strong subject/body evidence."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.ALLIANCE,
                player_name=None,
                profile_route=None,
                subject="Test",
                body="test",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAIL_HUB),
            after=make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.ALLIANCE,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Alliance", subtitle="Test test"),),
            ),
        )

        self.assertEqual(result.status.value, "success")
        self.assertIn("located in the reopened mailbox", result.message)

    def test_send_mail_verify_succeeds_when_ambiguous_row_opens_matching_thread(self) -> None:
        """Allows ambiguous mailbox rows to succeed once the opened thread confirms the just-sent content."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"
        mailbox = make_observation(
            ScreenType.PNC_MAILBOX_LIST,
            mailbox_type=MailboxType.PLAYER,
            list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
        )

        actions = task.plan(context, mailbox)
        result = task.verify(
            context,
            before=mailbox,
            after=make_observation(
                ScreenType.PNC_MAIL_THREAD,
                list_entries=(
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Fresh hello"),
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="New message"),
                ),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(result.status.value, "success")
        self.assertIn("confirmed in the reopened mailbox thread", result.message)

    def test_send_mail_verify_fails_when_ambiguous_row_opens_wrong_thread(self) -> None:
        """Fails when a same-recipient mailbox row leads to a thread whose content does not match the send."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Fresh hello",
                body="New message",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["send_mail_phase"] = "verify_mailbox"
        mailbox = make_observation(
            ScreenType.PNC_MAILBOX_LIST,
            mailbox_type=MailboxType.PLAYER,
            list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="Older preview"),),
        )

        actions = task.plan(context, mailbox)
        result = task.verify(
            context,
            before=mailbox,
            after=make_observation(
                ScreenType.PNC_MAIL_THREAD,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="Completely unrelated history"),),
            ),
        )

        self.assertEqual(len(actions), 1)
        self.assertEqual(result.status.value, "failed")
        self.assertTrue(result.retryable)
        self.assertIn("did not contain the expected sent subject or body", result.message)

    def test_send_mail_verify_replans_when_direct_player_compose_stays_on_mail_hub_once(self) -> None:
        """Retries once when the direct player compose tap stays on the hub before the popup opens."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAIL_HUB),
            after=make_observation(ScreenType.PNC_MAIL_HUB),
        )

        self.assertEqual(result.status.value, "replan")
        self.assertIn("Mail hub", result.message)

    def test_send_mail_verify_fails_when_direct_player_compose_stays_on_mail_hub_twice(self) -> None:
        """Fails cleanly after two unchanged hub-compose attempts so the task does not spin indefinitely."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="Enemy Bob",
                profile_route=None,
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        context.runtime_state["direct_player_compose_open_attempts"] = 1

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_MAIL_HUB),
            after=make_observation(ScreenType.PNC_MAIL_HUB),
        )

        self.assertEqual(result.status.value, "failed")
        self.assertTrue(result.retryable)
        self.assertIn("did not open from the Mail hub", result.message)

    def test_send_mail_verify_fails_when_alliance_profile_route_source_opens_mail_from_home(self) -> None:
        """Fails fast when the supposed alliance source selector routes into Mail instead of alliance navigation."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name=None,
                profile_route=PlayerProfileRoute(
                    kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                    player_name="Cutie Voj",
                ),
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_HOME_CITY),
            after=make_observation(ScreenType.PNC_MAIL_HUB),
        )

        self.assertEqual(result.status.value, "failed")
        self.assertIn("opened Mail instead of Alliance", result.message)
        self.assertFalse(result.retryable)

    def test_send_mail_verify_retries_once_before_failing_when_alliance_mail_stays_on_alliance_home(self) -> None:
        """Stops the alliance-mail compose loop after one retry when the tab tap never opens compose."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.ALLIANCE,
                player_name=None,
                profile_route=None,
                subject="Notice",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        first = task.verify(
            context,
            before=make_observation(ScreenType.PNC_ALLIANCE_HOME),
            after=make_observation(ScreenType.PNC_ALLIANCE_HOME),
        )
        second = task.verify(
            context,
            before=make_observation(ScreenType.PNC_ALLIANCE_HOME),
            after=make_observation(ScreenType.PNC_ALLIANCE_HOME),
        )

        self.assertEqual(first.status.value, "replan")
        self.assertIn("retrying once", first.message)
        self.assertEqual(second.status.value, "failed")
        self.assertIn("two compose-entry attempts", second.message)
        self.assertTrue(second.retryable)

    def test_send_mail_verify_fails_fast_when_alliance_mail_is_campaign_gated(self) -> None:
        """Surfaces the alliance-home status banner instead of looping forever on a gated mail tab."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.ALLIANCE,
                player_name=None,
                profile_route=None,
                subject="Notice",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_ALLIANCE_HOME),
            after=make_observation(
                ScreenType.PNC_ALLIANCE_HOME,
                visible_ids=(UiElementId.PNC_STATUS_BANNER,),
            ),
        )

        self.assertEqual(result.status.value, "failed")
        self.assertIn("Alliance Mail is unavailable", result.message)

    def test_send_mail_verify_fails_fast_when_campaign_gate_banner_arrives_on_unknown_follow_up(self) -> None:
        """Treats the Campaign Ch.3 banner as a known failure even when the coarse follow-up screen is still unknown."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.ALLIANCE,
                player_name=None,
                profile_route=None,
                subject="Notice",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        after = Observation(
            screen_type=ScreenType.UNKNOWN,
            visible_elements={
                UiElementId.PNC_STATUS_BANNER: VisibleElement(
                    selector_id=UiElementId.PNC_STATUS_BANNER,
                    bounds=Bounds(x=10, y=10, width=120, height=24),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.OCR,
                    extracted_text="Please clear Campaign Ch.3 first",
                )
            },
            image_size=(200, 100),
        )

        result = task.verify(
            context,
            before=make_observation(ScreenType.PNC_ALLIANCE_HOME),
            after=after,
        )

        self.assertEqual(result.status.value, "failed")
        self.assertEqual(
            result.message,
            "Alliance Mail is unavailable from Alliance home until Campaign Ch.3 is cleared.",
        )
        self.assertFalse(result.retryable)

    def test_send_mail_plan_searches_list_backed_profile_route_before_failing_missing_target(self) -> None:
        """Uses bounded route-list search steps when a list-backed profile target is not yet visible."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name=None,
                profile_route=PlayerProfileRoute(
                    kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                    player_name="Cutie Voj",
                ),
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )
        observation = make_observation(
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            list_entries=(make_entry(ListEntryKind.ALLIANCE_MEMBER, title="Enemy Bob"),),
        )

        first_actions = task.plan(context, observation)
        second_actions = task.plan(context, observation)
        third_actions = task.plan(context, observation)
        fourth_actions = task.plan(context, observation)
        fifth_actions = task.plan(context, observation)
        sixth_actions = task.plan(context, observation)

        self.assertEqual(len(first_actions), 1)
        self.assertIsInstance(first_actions[0], SwipeAction)
        self.assertEqual(first_actions[0].direction, "down")
        self.assertEqual(first_actions[0].reason, "search_alliance_member_reset_to_top")
        self.assertEqual(first_actions[0].follow_up_request, ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_MEMBER_LIST))
        self.assertEqual(first_actions[0].start_x_ratio, 0.5)
        self.assertEqual(first_actions[0].end_x_ratio, 0.5)
        self.assertEqual(first_actions[0].start_y_ratio, 0.40625)
        self.assertEqual(first_actions[0].end_y_ratio, 0.78125)
        self.assertEqual(len(second_actions), 1)
        self.assertEqual(second_actions[0].direction, "down")
        self.assertEqual(len(third_actions), 1)
        self.assertEqual(third_actions[0].direction, "down")
        self.assertEqual(len(fourth_actions), 1)
        self.assertEqual(fourth_actions[0].direction, "down")
        self.assertEqual(len(fifth_actions), 1)
        self.assertEqual(fifth_actions[0].direction, "down")
        self.assertEqual(len(sixth_actions), 1)
        self.assertEqual(sixth_actions[0].direction, "up")
        self.assertEqual(sixth_actions[0].reason, "search_alliance_member_scan_forward")
        self.assertEqual(sixth_actions[0].start_y_ratio, 0.78125)
        self.assertEqual(sixth_actions[0].end_y_ratio, 0.28125)

    def test_send_mail_plan_recovers_from_unknown_via_canonical_navigation_instead_of_waiting(self) -> None:
        """Uses the shared recovery/navigation flows from unknown screens instead of looping on wait actions."""

        task = SendMailTask()
        context = _make_task_context(
            self,
            params=SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name=None,
                profile_route=PlayerProfileRoute(
                    kind=PlayerProfileRouteKind.ALLIANCE_MEMBER,
                    player_name="Cutie Voj",
                ),
                subject="Hello",
                body="World",
            ),
            task_id=TaskId.SEND_MAIL,
        )

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].reason, "recover_unknown_mail_screen")

    def test_action_executor_uses_explicit_swipe_ratios_when_present(self) -> None:
        """Resolves selector-independent swipe geometry from explicit normalized start/end ratios when provided."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="down",
                start_x_ratio=0.5,
                start_y_ratio=0.25,
                end_x_ratio=0.5,
                end_y_ratio=0.75,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(executor.session.swipes, [(100, 25, 100, 75, 500)])

    def test_action_executor_stops_mail_sequence_after_unexpected_follow_up_screen(self) -> None:
        """Stops a multi-step mail action sequence when the previous observed follow-up missed its expected screen."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_MAILBOX_LIST,
                    mailbox_type=MailboxType.PLAYER,
                )
            ]
        )

        result = executor.execute_actions(
            [
                TapAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_BUTTON,
                    reason="open_player_mail_compose",
                    observe_after=True,
                    follow_up_request=ObservationRequest.mail_compose_follow_up(),
                ),
                InputTextAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
                    text="Enemy Bob",
                    replace_existing=True,
                ),
            ],
            make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                visible_ids=(UiElementId.PNC_MAIL_COMPOSE_BUTTON,),
            ),
            observe=fake_observer.observe,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(executor.session.texts, [])
        self.assertEqual(fake_observer.requests, [ObservationRequest.mail_compose_follow_up()])

    def test_mail_compose_follow_up_keeps_compose_origin_screens_visible_on_compose_miss(self) -> None:
        """Lets compose-entry follow-ups preserve every supported source screen when the popup does not open."""

        request = ObservationRequest.mail_compose_follow_up()

        self.assertEqual(
            request.candidate_screen_types,
            frozenset(
                {
                    ScreenType.PNC_MAIL_COMPOSE_POPUP,
                    ScreenType.PNC_ALLIANCE_HOME,
                    ScreenType.PNC_PLAYER_PROFILE,
                }
            ),
        )
        self.assertEqual(request.ocr_screen_types, request.candidate_screen_types)

    def test_send_mail_flow_from_compose_enters_subject_body_and_sends(self) -> None:
        """Builds the canonical compose-send action sequence from an already-open popup."""

        params = SendMailParams(
            recipient_kind=MailRecipientKind.ALLIANCE,
            player_name=None,
            profile_route=None,
            subject="Rally",
            body="Join now.",
        )

        actions = self.flows.send_mail(make_observation(ScreenType.PNC_MAIL_COMPOSE_POPUP), params)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], InputTextAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD)
        self.assertIsInstance(actions[1], InputTextAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON)

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

    def test_observation_builder_parses_mail_compose_popup_field_states(self) -> None:
        """Builds the compose popup plus canonical shared text-field state from OCR-backed field regions."""

        registry = build_default_selector_registry()
        image_size = (900, 1600)
        target_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]
        subject_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]
        body_region = registry.require(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).relative_bounds.materialize_region(image_size=image_size)  # type: ignore[union-attr]

        observation = _build_observation(
            request=ObservationRequest.mail_compose_follow_up(),
            lines=(
                _ocr_line("Edit Mail", x=305, y=42, width=180, height=24),
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
            lines=(
                _ocr_line("Edit Mail", x=363, y=378, width=179, height=41),
                _ocr_line("Alliance Mail", x=130, y=498, width=200, height=30),
                _ocr_line("Can enter up to 1000 characters", x=86, y=670, width=390, height=28),
                _ocr_line("Send", x=405, y=1109, width=92, height=40),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD).text,
            "Alliance Mail",
        )
        self.assertTrue(observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).empty)
        self.assertTrue(observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).empty)
        self.assertTrue(observation.has(UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON))

    def test_observation_builder_parses_visible_chat_message_entries(self) -> None:
        """Builds visible chat sender entries so the chat-message profile route can stay inside shared flow planning."""

        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=260, width=180, height=24),
                _ocr_line("Hello there", x=160, y=292, width=200, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "Enemy Bob")
        self.assertEqual(chat_entries[0].subtitle_text, "Hello there")
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.PLAYER.value)
        self.assertEqual(chat_entries[0].metadata["message_text"], "Hello there")

    def test_observation_builder_marks_announcement_rows_without_promoting_them_to_player_chat(self) -> None:
        """Keeps announcement rows visible for diagnostics while excluding them from player-chat projections."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=260, width=180, height=24),
                _ocr_line("Hello there", x=160, y=292, width=200, height=24),
                _ocr_line("System Message", x=120, y=380, width=220, height=24),
                _ocr_line("Castle battle begins soon", x=160, y=412, width=340, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)
        player_entries = visible_player_chat_entries(chat_entries)

        self.assertEqual(len(chat_entries), 2)
        self.assertEqual(chat_entries[1].metadata["chat_entry_kind"], ChatEntryKind.ANNOUNCEMENT.value)
        self.assertEqual([entry.sender_name for entry in player_entries], ["Enemy Bob"])

    def test_observation_builder_marks_sender_only_single_line_chat_rows_as_unsupported(self) -> None:
        """Leaves sender-only OCR rows unsupported so chat archiving can fail fast instead of dropping them silently."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=360, width=180, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 1)

    def test_observation_builder_marks_malformed_single_line_chat_rows_as_unsupported(self) -> None:
        """Leaves merged OCR rows unsupported when they do not match the trusted `Sender: message` player format."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob - Hello there", x=120, y=360, width=320, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 1)

    def test_observation_builder_keeps_explicit_system_message_rows_as_announcements(self) -> None:
        """Keeps the brown System Message row family classified as announcements instead of player chat."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("System Message", x=120, y=360, width=220, height=24),
                _ocr_line("Battle begins soon", x=160, y=392, width=300, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.ANNOUNCEMENT.value)
        self.assertEqual(chat_entries[0].title_text, "System Message")
        self.assertEqual(chat_entries[0].subtitle_text, "Battle begins soon")

    def test_observation_builder_does_not_create_false_player_rows_from_announcement_only_chat(self) -> None:
        """Treats announcement-only Kingdom Chat windows as non-player content so transcript deltas stay quiet."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("System Message", x=120, y=360, width=220, height=24),
                _ocr_line("The Apex Match World Championship has ended!", x=160, y=392, width=420, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(len(visible_player_chat_entries(observation.entries(ListEntryKind.CHAT_MESSAGE))), 0)

    def test_observation_builder_merges_split_sender_and_message_fragments_into_one_player_row(self) -> None:
        """Merges one isolated sender label with the adjacent message block when the attachment is unique."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=360, width=180, height=24),
                _ocr_line("it's a mystery", x=170, y=424, width=220, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "[DMG]Toast.")
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.PLAYER.value)
        self.assertEqual(chat_entries[0].metadata["message_text"], "it's a mystery")

    def test_observation_builder_keeps_titled_and_tagged_player_rows_archivable(self) -> None:
        """Accepts optional title and alliance-tag prefixes as normal player sender evidence."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("[Ruler][RST]Queen Bee", x=120, y=260, width=260, height=24),
                _ocr_line("Good luck all", x=160, y=292, width=220, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=380, width=180, height=24),
                _ocr_line("Still normal player chat", x=160, y=412, width=280, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual([entry.title_text for entry in chat_entries], ["[Ruler][RST]Queen Bee", "[DMG]Toast."])
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_keeps_autogenerated_player_style_rows_and_admin_rows_archivable(self) -> None:
        """Keeps player-chrome broadcasts and blue-bubble Admin rows in the player archive bucket."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Admin", x=120, y=260, width=140, height=24),
                _ocr_line("I obtained legendary hero Phoenix (Tap to Join)", x=160, y=292, width=520, height=24),
                _ocr_line("Cutie Voj", x=120, y=380, width=160, height=24),
                _ocr_line("I crafted Mythic Hammer! (Tap to view)", x=160, y=412, width=430, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual([entry.title_text for entry in chat_entries], ["Admin", "Cutie Voj"])
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_drops_bottom_clipped_sender_only_boundary_fragments(self) -> None:
        """Skips bottom-edge sender fragments that are visibly clipped instead of failing an otherwise valid snapshot."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Enemy Bob", x=120, y=1120, width=180, height=24),
                _ocr_line("Hello there", x=160, y=1152, width=220, height=24),
                _ocr_line("[DMG]Toast.", x=120, y=1450, width=180, height=24),
            ),
            image_size=(900, 1600),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].title_text, "Enemy Bob")
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 0)

    def test_observation_builder_marks_interior_message_only_fragments_as_unsupported(self) -> None:
        """Keeps interior message-only OCR fragments fail-fast when no trustworthy sender can be attached."""

        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("just some floating message text", x=200, y=360, width=300, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 1)
        self.assertEqual(chat_entries[0].metadata["chat_entry_kind"], ChatEntryKind.UNSUPPORTED.value)
        self.assertEqual(chat_entries[0].metadata["unsupported_reason"], "message_only")

    def test_observation_builder_archives_emoji_only_rows_with_controlled_placeholders(self) -> None:
        """Maps confidently image-only emoji rows onto the canonical placeholder vocabulary."""

        image = _build_chat_fixture_image()
        _draw_chat_emoji(image, top=330, kind="happy")
        _draw_chat_emoji(image, top=520, kind="eyes")
        _draw_chat_emoji(image, top=710, kind="generic")
        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            image=image,
            lines=(
                _ocr_line("Chat", x=250, y=40, width=120, height=24),
                _ocr_line("Kingdom", x=180, y=96, width=120, height=24),
                _ocr_line("Alliance", x=520, y=96, width=120, height=24),
                _ocr_line("Happy Bot", x=120, y=290, width=180, height=24),
                _ocr_line("Eyes Bot", x=120, y=480, width=180, height=24),
                _ocr_line("Mystery Bot", x=120, y=670, width=180, height=24),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(
            [entry.metadata["message_text"] for entry in chat_entries],
            ["[happy emoji]", "[eyes emoji]", "[emoji]"],
        )
        self.assertTrue(all(entry.metadata["chat_entry_kind"] == ChatEntryKind.PLAYER.value for entry in chat_entries))

    def test_observation_builder_normalizes_live_march_24_kingdom_chat_failure_shape(self) -> None:
        """Covers the March 24, 2026 live OCR shape so split rows, timestamps, and sticker rows normalize safely."""

        image = Image.open(
            Path(__file__).resolve().parents[1]
            / "artifacts"
            / "2026-03-24"
            / "serious_stuff"
            / "20260324T143723Z_collect_kingdom_chat_failure_result.png"
        )
        observation = _build_observation(
            request=ObservationRequest.chat_transcript_observation(),
            image=image,
            image_size=image.size,
            lines=(
                _ocr_line("Chat", x=107, y=10, width=70, height=33),
                _ocr_line("Kingdom", x=123, y=70, width=85, height=24),
                _ocr_line("Alliance", x=391, y=68, width=75, height=26),
                _ocr_line("[Deceiver] [DMG]   Sonny Corinthos", x=109, y=165, width=253, height=16),
                _ocr_line("plscometome", x=112, y=198, width=115, height=17),
                _ocr_line("[MIR]yJeTalO", x=109, y=270, width=107, height=18),
                _ocr_line("ABOTAyMarOyTOTyTKTOeCTbAaXeHe3HarOTKaKW3", x=110, y=304, width=382, height=17),
                _ocr_line("3ayeroBceHayaocb)", x=111, y=327, width=169, height=15),
                _ocr_line("2026-03-2410:00", x=196, y=382, width=149, height=17),
                _ocr_line("SystemMessage", x=103, y=431, width=123, height=21),
                _ocr_line("The Apex Match World Championship has ended!", x=112, y=465, width=362, height=19),
                _ocr_line("Congrats to Xo-xo-xo.from Kingdom 297 on winning", x=111, y=487, width=391, height=20),
                _ocr_line("theworldchampion title!", x=112, y=511, width=185, height=15),
                _ocr_line("2026-03-2410:37", x=196, y=567, width=148, height=17),
                _ocr_line("[DMG]  Toast.", x=108, y=618, width=100, height=18),
                _ocr_line("it'samystery", x=109, y=650, width=102, height=21),
                _ocr_line("[DMG]p2o2i2u2ueu3u47484", x=108, y=724, width=220, height=17),
            ),
        )

        chat_entries = observation.entries(ListEntryKind.CHAT_MESSAGE)

        self.assertEqual(len(chat_entries), 5)
        self.assertEqual(
            [entry.metadata["chat_entry_kind"] for entry in chat_entries],
            [
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.ANNOUNCEMENT.value,
                ChatEntryKind.PLAYER.value,
                ChatEntryKind.PLAYER.value,
            ],
        )
        self.assertEqual(chat_entries[2].title_text, "SystemMessage")
        self.assertEqual(chat_entries[4].metadata["message_text"], "[sticker]")
        self.assertEqual(len(visible_unsupported_chat_entries(chat_entries)), 0)

    def test_observation_builder_groups_alliance_member_rows_without_promoting_stats_or_actions(self) -> None:
        """Extracts one member entry per alliance row instead of treating stats and action labels as names."""

        observation = _build_observation(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
            lines=(
                _ocr_line("Alliance Member", x=240, y=42, width=220, height=24),
                _ocr_line("Enemy Bob", x=130, y=320, width=180, height=26),
                _ocr_line("145,022,677", x=310, y=358, width=160, height=24),
                _ocr_line("Manage", x=720, y=338, width=110, height=24),
                _ocr_line("Cutie Voj", x=130, y=488, width=170, height=26),
                _ocr_line("64,132,585", x=312, y=526, width=150, height=24),
                _ocr_line("Manage", x=720, y=506, width=110, height=24),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_MEMBER_LIST)
        entries = observation.entries(ListEntryKind.ALLIANCE_MEMBER)
        self.assertEqual([entry.title_text for entry in entries], ["Enemy Bob", "Cutie Voj"])
        self.assertEqual(entries[0].action_point, (775, 350))
        self.assertEqual(entries[1].action_point, (775, 518))

    def test_observation_builder_parses_centered_alliance_member_manage_popup(self) -> None:
        """Recognizes the centered alliance-member manage popup instead of leaving it as unknown."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP),
            lines=(
                _ocr_line("Manage", x=360, y=408, width=170, height=48),
                _ocr_line("Cutie Voj", x=392, y=496, width=130, height=38),
                _ocr_line("Personal Info", x=352, y=606, width=196, height=33),
                _ocr_line("Send", x=408, y=722, width=85, height=40),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON))

    def test_observation_builder_parses_empty_mailbox(self) -> None:
        """Treats the No report yet state as a valid mailbox instead of classifying it as unknown."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            lines=(
                _ocr_line("Player Mail", x=310, y=42, width=170, height=24),
                _ocr_line("Manage", x=720, y=44, width=90, height=22),
                _ocr_line("Mark all as read", x=560, y=44, width=150, height=22),
                _ocr_line("No report yet", x=300, y=730, width=180, height=26),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(observation.mailbox_type, MailboxType.PLAYER)
        self.assertTrue(observation.mailbox_empty)

    def test_observation_builder_parses_date_first_alliance_mail_row_without_promoting_footer_controls(self) -> None:
        """Keeps the visible alliance-mail thread row and ignores the footer action bar on the live mailbox layout."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.ALLIANCE),
            lines=(
                _ocr_line("Alliance Mail", x=183, y=17, width=292, height=52),
                _ocr_line("2026/03/22 14:46:46", x=617, y=130, width=257, height=26),
                _ocr_line("[AAS] pine cobaye 1", x=193, y=151, width=271, height=35),
                _ocr_line("(All Allies)Test", x=194, y=184, width=175, height=32),
                _ocr_line("(All Allies)test", x=196, y=220, width=169, height=27),
                _ocr_line("Mark All as", x=352, y=1475, width=193, height=39),
                _ocr_line("Read", x=402, y=1511, width=96, height=41),
                _ocr_line("Mail", x=136, y=1522, width=62, height=33),
                _ocr_line("Manage", x=678, y=1523, width=108, height=35),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
        self.assertEqual(observation.mailbox_type, MailboxType.ALLIANCE)
        entries = observation.entries(ListEntryKind.MAIL_THREAD)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title_text, "[AAS] pine cobaye 1")
        self.assertEqual(entries[0].subtitle_text, "(All Allies)Test (All Allies)test")
        self.assertEqual(entries[0].metadata["date_text"], "2026/03/22 14:46:46")

    def test_mailbox_observation_uses_requested_mailbox_type(self) -> None:
        """Rejects mismatched mailbox OCR so narrow mailbox follow-ups actually verify the requested mailbox."""

        observation = _build_observation(
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            lines=(
                _ocr_line("Alliance Mail", x=183, y=17, width=292, height=52),
                _ocr_line("[AAS] pine cobaye 1", x=193, y=151, width=271, height=35),
                _ocr_line("(All Allies)Test", x=194, y=184, width=175, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_keeps_mail_hub_out_of_compose_popup(self) -> None:
        """Does not promote the shared Mail hub into compose-popup state when only the generic Mail header is visible."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(),
            lines=(
                _ocr_line("Mail", x=310, y=42, width=110, height=24),
                _ocr_line("Player Mail", x=220, y=317, width=155, height=39),
                _ocr_line("No report yet", x=670, y=320, width=188, height=35),
                _ocr_line("Alliance Mail", x=221, y=481, width=176, height=32),
                _ocr_line("No report yet", x=670, y=480, width=189, height=38),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_HUB)
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON))
        player_mail = observation.require(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL)
        self.assertIsNotNone(player_mail.action_point)
        self.assertGreaterEqual(player_mail.action_point[0], 800)

    def test_observation_builder_parses_live_like_alliance_home_instead_of_mail_hub(self) -> None:
        """Classifies alliance home from its tiles and bottom tabs instead of misreading Alliance Mail as the mail hub."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MAIL_HUB),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Tech", x=482, y=991, width=198, height=33),
                _ocr_line("Rank", x=479, y=1136, width=82, height=35),
                _ocr_line("AllianceMember", x=484, y=1284, width=251, height=30),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Alliance Mail'Alliance Help", x=270, y=1530, width=379, height=35),
                _ocr_line("Operations", x=682, y=1534, width=154, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_TERRITORY))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_RANK))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_TILE_MEMBER))
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL))
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL))

    def test_observation_builder_does_not_treat_bottom_tab_alliance_mail_as_mail_hub(self) -> None:
        """Rejects the lower alliance-home tab label as mail-hub evidence when no mailbox rows are present."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MAIL_HUB),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Mail", x=270, y=1532, width=175, height=32),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL))

    def test_observation_builder_tolerates_alliance_mail_ocr_typo_on_alliance_home(self) -> None:
        """Keeps the alliance mail tab actionable when OCR reads Mail as Mait on alliance home."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Tech", x=482, y=991, width=198, height=33),
                _ocr_line("AllianceMember", x=482, y=1282, width=254, height=35),
                _ocr_line("Alliance Mait", x=270, y=1532, width=178, height=32),
                _ocr_line("Alliance Help", x=467, y=1532, width=182, height=33),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Operations", x=683, y=1534, width=153, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL))

    def test_observation_builder_parses_alliance_home_status_banner(self) -> None:
        """Carries the transient alliance-home status banner so tasks can fail with the live gate reason."""

        observation = _build_observation(
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_ALLIANCE_HOME),
            lines=(
                _ocr_line("Alliance", x=182, y=17, width=183, height=54),
                _ocr_line("Please clear Campaign Ch.3 first", x=194, y=454, width=512, height=39),
                _ocr_line("Alliance Territory", x=49, y=842, width=253, height=40),
                _ocr_line("Alliance Mait", x=270, y=1532, width=178, height=32),
                _ocr_line("Alliance Help", x=467, y=1532, width=182, height=33),
                _ocr_line("Alliance Shop", x=51, y=1533, width=168, height=32),
                _ocr_line("Operations", x=683, y=1534, width=153, height=33),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_HOME)
        self.assertTrue(observation.has(UiElementId.PNC_STATUS_BANNER))

    def test_observation_builder_surfaces_alliance_status_banner_even_when_screen_stays_unknown(self) -> None:
        """Preserves the Campaign Ch.3 banner for compose follow-up handling even when alliance-home chrome is incomplete."""

        observation = _build_observation(
            request=ObservationRequest.mail_compose_follow_up(),
            lines=(
                _ocr_line("Please clear Campaign Ch.3 first", x=194, y=454, width=512, height=39),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertTrue(observation.has(UiElementId.PNC_STATUS_BANNER))

    def test_observation_builder_keeps_chat_send_button_out_of_mail_compose_popup(self) -> None:
        """Does not treat the shared chat Send button as compose-popup evidence without a mail header."""

        observation = _build_observation(
            request=ObservationRequest.runtime_default(),
            lines=(
                _ocr_line("Chat", x=240, y=38, width=100, height=26),
                _ocr_line("Kingdom", x=210, y=118, width=120, height=34),
                _ocr_line("Alliance", x=650, y=118, width=120, height=34),
                _ocr_line("Enemy Bob", x=180, y=900, width=130, height=24),
                _ocr_line("Hello there", x=185, y=945, width=140, height=24),
                _ocr_line("Send", x=770, y=1530, width=88, height=36),
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)

    def test_collect_mail_task_archives_a_visible_thread(self) -> None:
        """Persists metadata, text, and screenshot evidence through the canonical archive store."""

        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot_path = Path(temp_directory) / "thread.png"
            screenshot_path.write_bytes(build_png_bytes())
            task = CollectMailTask()
            context = _make_task_context(
                self,
                params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.BOTH),
                task_id=TaskId.COLLECT_MAIL,
                mail_archive_store=MailArchiveStore(root=Path(temp_directory) / "mail"),
                target_castle=CastleIdentity(kingdom="K230", castle_name="Main"),
            )
            mailbox_observation = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", action_point=(120, 90)),),
            )
            thread_observation = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Greetings"),
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Welcome to automation."),
                ),
                artifact_path=screenshot_path,
            )

            actions = task.plan(context, mailbox_observation)
            result = task.verify(context, mailbox_observation, thread_observation)

            self.assertEqual(len(actions), 1)
            self.assertEqual(result.status.value, "replan")
            archived_files = sorted((Path(temp_directory) / "mail").rglob("*"))
            self.assertTrue(any(path.name == "metadata.json" for path in archived_files))
            self.assertTrue(any(path.name == "thread.txt" for path in archived_files))
            self.assertTrue(any(path.name == "thread.png" for path in archived_files))
            self.assertTrue(any("Main" in path.parts for path in archived_files))

    def test_collect_mail_task_scrolls_to_collect_more_than_the_first_visible_window(self) -> None:
        """Continues mailbox traversal across windows until the requested per-mailbox limit is reached."""

        with tempfile.TemporaryDirectory() as temp_directory:
            task = CollectMailTask()
            context = _make_task_context(
                self,
                params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT, limit_per_mailbox=2),
                task_id=TaskId.COLLECT_MAIL,
                mail_archive_store=MailArchiveStore(root=Path(temp_directory) / "mail"),
                target_castle=CastleIdentity(kingdom="K230", castle_name="Main"),
            )
            first_mailbox = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="One", action_point=(120, 90)),),
            )
            second_mailbox = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Alice", subtitle="Two", action_point=(140, 110)),),
            )
            first_thread = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="First collected thread"),),
            )
            second_thread = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="Second collected thread"),),
            )

            first_actions = task.plan(context, first_mailbox)
            first_result = task.verify(context, first_mailbox, first_thread)
            scroll_actions = task.plan(context, first_mailbox)
            scroll_result = task.verify(context, first_mailbox, second_mailbox)
            second_actions = task.plan(context, second_mailbox)
            second_result = task.verify(context, second_mailbox, second_thread)
            done_actions = task.plan(context, second_mailbox)
            done_result = task.verify(context, second_mailbox, second_mailbox)

            self.assertEqual(len(first_actions), 1)
            self.assertIsInstance(first_actions[0], TapPointAction)
            self.assertEqual(first_result.status.value, "replan")
            self.assertEqual(len(scroll_actions), 1)
            self.assertIsInstance(scroll_actions[0], SwipeAction)
            self.assertEqual(scroll_result.status.value, "replan")
            self.assertEqual(len(second_actions), 1)
            self.assertIsInstance(second_actions[0], TapPointAction)
            self.assertEqual(second_result.status.value, "replan")
            self.assertEqual(done_actions, [])
            self.assertEqual(done_result.status.value, "success")

    def test_collect_mail_task_uses_lord_info_flow_to_resolve_active_castle_before_archiving(self) -> None:
        """Uses the shared self-profile flow to resolve the active castle instead of archiving under an account-level fallback."""

        task = CollectMailTask()
        context = _make_task_context(
            self,
            params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT),
            task_id=TaskId.COLLECT_MAIL,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.open_lord_info(observation))

    def test_collect_mail_task_fails_fast_when_active_castle_cannot_be_resolved_from_mailbox_screen(self) -> None:
        """Rejects archive work from a mailbox screen when neither the active castle nor an explicit target is available."""

        task = CollectMailTask()
        context = _make_task_context(
            self,
            params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT),
            task_id=TaskId.COLLECT_MAIL,
        )

        with self.assertRaises(SelectorResolutionError):
            task.plan(
                context,
                make_observation(
                    ScreenType.PNC_MAILBOX_LIST,
                    mailbox_type=MailboxType.PLAYER,
                ),
            )

    def test_mail_archive_store_reuses_existing_fingerprint(self) -> None:
        """Skips duplicate archive creation when the same fingerprint already exists for the mailbox."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = MailArchiveStore(root=Path(temp_directory) / "mail")
            screenshot_path = Path(temp_directory) / "source.png"
            screenshot_path.write_bytes(build_png_bytes())
            record = _mail_archive_record()

            first = store.persist(
                record=record,
                archive_mode=MailArchiveMode.BOTH,
                screenshot_source_path=screenshot_path,
                skip_existing=True,
            )
            second = store.persist(
                record=record,
                archive_mode=MailArchiveMode.BOTH,
                screenshot_source_path=screenshot_path,
                skip_existing=True,
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.directory, second.directory)


def _make_task_context(
    case: MailWorkflowTests,
    *,
    params: object,
    task_id: TaskId,
    mail_archive_store: MailArchiveStore | None = None,
    target_castle: CastleIdentity | None = None,
) -> TaskContext:
    """Builds one task context for mail task tests."""

    return TaskContext(
        account=case.account,
        castle_roster_provider=lambda: None,
        defaults=case.defaults,
        step=ScriptStep(task=task_id),
        params=params,
        flows=case.flows,
        logger=case.logger,
        target_castle=target_castle,
        mail_archive_store=mail_archive_store,
    )


def _build_observation(
    *,
    request: ObservationRequest,
    lines: tuple[OcrLine, ...],
    image_size: tuple[int, int] = (900, 1600),
    image: Image.Image | None = None,
):
    """Builds one synthetic OCR-backed observation using the default selector registry."""

    active_image = image.copy() if image is not None else _build_chat_fixture_image(image_size=image_size)
    payload = _encode_png(active_image)
    with tempfile.TemporaryDirectory() as temp_directory:
        screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=Path(temp_directory) / "artifacts"))
        screenshot = screenshot_service.capture(
            _FakeScreenshotSession(payload),
            artifact_directory="mail_test",
            label="synthetic",
        )
        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
                ocr_service=UnavailableOcrService(),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=_FakeOcrService(lines=lines),
                selector_registry=build_default_selector_registry(),
            ),
        )
        return builder.build(screenshot, request=request)


def _build_chat_fixture_image(*, image_size: tuple[int, int] = (900, 1600)) -> Image.Image:
    """Builds the shared dark chat-surface image used by OCR-only and icon-placeholder tests."""

    return Image.new("RGB", image_size, (18, 30, 72))


def _draw_chat_emoji(image: Image.Image, *, top: int, kind: str) -> None:
    """Draws one deterministic non-text chat icon used by the placeholder-classifier tests."""

    draw = ImageDraw.Draw(image)
    if kind == "happy":
        box = (170, top, 230, top + 60)
        draw.ellipse(box, fill=(250, 210, 48))
        draw.ellipse((184, top + 18, 194, top + 28), fill=(20, 20, 20))
        draw.ellipse((206, top + 18, 216, top + 28), fill=(20, 20, 20))
        draw.arc((186, top + 26, 214, top + 48), start=20, end=160, fill=(20, 20, 20), width=3)
        return
    if kind == "eyes":
        draw.ellipse((166, top + 10, 198, top + 42), fill=(245, 245, 245))
        draw.ellipse((202, top + 10, 234, top + 42), fill=(245, 245, 245))
        draw.ellipse((178, top + 20, 188, top + 30), fill=(20, 20, 20))
        draw.ellipse((214, top + 20, 224, top + 30), fill=(20, 20, 20))
        return
    draw.polygon(
        ((180, top + 8), (220, top + 20), (232, top + 54), (200, top + 66), (168, top + 50)),
        fill=(175, 90, 220),
    )


def _mail_archive_record() -> MailArchiveRecord:
    """Builds one deterministic mail archive record for store tests."""

    from datetime import UTC, datetime
    from pnc_automation.app.pnc.domain.mail import MailArchiveRecord, MailboxType, MailThreadFingerprint

    return MailArchiveRecord(
        account_id="account_a",
        pnc_account_id="user@example.com",
        active_castle="Main",
        mailbox_type=MailboxType.PLAYER,
        sender_name="Enemy Bob",
        thread_timestamp_text="1 min ago",
        fingerprint=MailThreadFingerprint("deadbeef"),
        captured_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        normalized_thread_text="Greetings\nWelcome to automation.",
    )


class _FakeScreenshotSession:
    """Returns a deterministic screenshot payload for synthetic vision tests."""

    def __init__(self, payload: bytes) -> None:
        """Stores the screenshot payload returned by capture."""

        self._payload = payload

    def capture_screenshot_bytes(self) -> bytes:
        """Returns the pre-seeded screenshot bytes."""

        return self._payload


class _FakeOcrService:
    """Returns deterministic OCR lines for synthetic mail screen parsing tests."""

    def __init__(self, *, lines: tuple[OcrLine, ...]) -> None:
        """Stores the OCR lines returned for every synthetic screenshot."""

        self._lines = lines

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns pre-seeded OCR output, optionally clipped to the requested region."""

        return OcrResult(lines=self.read_lines(image, region), words=())

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns the pre-seeded OCR lines, optionally restricted to one region."""

        del image
        if region is None:
            return self._lines
        filtered: list[OcrLine] = []
        for line in self._lines:
            if line.bounds.x < region.x or line.bounds.y < region.y:
                continue
            if line.bounds.x + line.bounds.width > region.x + region.width:
                continue
            if line.bounds.y + line.bounds.height > region.y + region.height:
                continue
            filtered.append(line)
        return tuple(filtered)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))


def _ocr_line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one deterministic OCR line for synthetic mail screen tests."""

    return OcrLine(text=text, bounds=Region(x=x, y=y, width=width, height=height), confidence=0.99)


def _encode_png(image: Image.Image) -> bytes:
    """Encodes one PIL image as PNG bytes."""

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()

