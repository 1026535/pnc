"""Automation api mail."""

from __future__ import annotations

import unittest

from pnc_automation.app.entrypoints.api import AutomationApi

from tests.support.entrypoints.scheduled_mail.fake_application_runner import _FakeApplicationRunner


class AutomationApiMailTests(unittest.TestCase):
    """Proves automation api mail."""

    def test_python_api_run_mail_schedules_resolves_account_from_active_context(self) -> None:
        """Allows scheduled-mail runs to reuse the current bound `use_account(...)` session scope."""

        fake_runner = _FakeApplicationRunner()
        api = AutomationApi(application=fake_runner)

        with api.use_account("account_a"):
            api.run_mail_schedules(schedule_ids=["mailschedule_1"])

        self.assertEqual(fake_runner.prepare_calls, [("account_a", None)])
        self.assertEqual(
            fake_runner.mail_schedule_calls,
            [("account_a", ["mailschedule_1"], None)],
        )
