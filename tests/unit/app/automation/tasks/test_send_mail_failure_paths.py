"""Send mail failure paths."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.app.pnc.domain.mail import (
    MailRecipientKind,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.make_task_context import _make_task_context


class SendMailFailurePathsTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves send mail failure paths."""

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
            decision=ScreenDecision(
                base_screen=ScreenType.UNKNOWN,
                effective_screen=ScreenType.UNKNOWN,
                guard=GuardVerdict.UNRESOLVED,
                evidence=(ScreenEvidence(ScreenType.UNKNOWN, "test"),),
            ),
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
