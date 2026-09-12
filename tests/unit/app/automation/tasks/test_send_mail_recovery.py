"""Send mail recovery."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.send_mail_task import SendMailTask
from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, SwipeAction
from pnc_automation.app.pnc.domain.mail import (
    MailRecipientKind,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.make_task_context import _make_task_context


class SendMailRecoveryTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves send mail recovery."""

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
