"""Opt-in live smoke coverage for executor-owned popup recovery."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from pnc_automation.app import build_application_runner
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    TASK_OWNED_POPUP_SCREEN_TYPES,
    preferred_transient_popup_candidate,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.live_smoke_support import build_live_runtime_bundle


def _live_popup_smoke_enabled() -> bool:
    """Return whether the explicit popup-smoke opt-in flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_POPUP_SMOKE") == "1"


@unittest.skipUnless(_live_popup_smoke_enabled(), "Set PNC_RUN_LIVE_POPUP_SMOKE=1 to run live popup smoke tests.")
class LivePopupRecoverySmokeTests(unittest.TestCase):
    """Dismiss one naturally present, typed, non-task-owned popup and recapture."""

    @classmethod
    def setUpClass(cls) -> None:
        """Connect through canonical runtime wiring and perform one bounded recovery episode."""

        config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        account_id = os.getenv("PNC_LIVE_SMOKE_ACCOUNT", "testing")
        application = build_application_runner(config_path)
        script_runner = application.script_runner
        account = script_runner.config.require_account(account_id)
        connected = build_live_runtime_bundle(config_account=account, script_runner=script_runner)
        cls.observer = connected.runtime.observation_service
        cls.before = cls.observer.observe("live_popup_recovery_before")
        if not cls.before.blocking_popup:
            raise unittest.SkipTest(
                "applicability_skip: no blocking popup was naturally present on the configured active castle"
            )
        overlay = cls.before.popup_overlay
        candidate = None if overlay is None else preferred_transient_popup_candidate(overlay)
        if candidate is None or candidate.control_kind in {
            PopupControlKind.UPDATE_CONFIRM,
            PopupControlKind.RECONNECT_CONFIRM,
        }:
            raise unittest.SkipTest(
                "applicability_skip: popup smoke only actuates measured non-affirmative dismiss controls"
            )
        executor = connected.runtime.require_observed_action_executor(
            "Live popup recovery requires the canonical observed-action executor."
        )
        cls.after = executor.recover_interruption_if_required(
            cls.before,
            label_prefix="live_popup_recovery",
            observe=cls.observer.observe,
        )

    def test_popup_recovery_captured_a_new_frame(self) -> None:
        """Prove the live action was followed by a distinct fresh capture."""

        self.assertIsNotNone(self.after)
        self.assertGreater(self.after.captured_at, self.before.captured_at)
        self.assertNotEqual(self.after.frame_fingerprint, self.before.frame_fingerprint)

    def test_same_blocking_popup_did_not_survive(self) -> None:
        """Require the recovery episode to end in a non-blocking state."""

        self.assertFalse(
            self.after.blocking_popup,
            "blocked: recovery returned a remaining blocking or task-owned popup instead of a stable state",
        )
        self.assertNotIn(
            self.after.screen_type,
            {ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET, *TASK_OWNED_POPUP_SCREEN_TYPES},
        )


if __name__ == "__main__":
    unittest.main()
