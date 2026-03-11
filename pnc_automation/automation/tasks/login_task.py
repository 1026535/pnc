"""Task that logs into the configured P&C account when required."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, InputTextAction, TapAction, WaitAction
from pnc_automation.pnc.observation import ListEntryKind, Observation, castle_entry_identity_matches
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


class LoginTask(BaseAutomationTask):
    """Logs in using the configured account credentials."""

    id = TaskId.LOGIN

    def parse_params(self, params: Mapping[str, Any]) -> None:
        """Rejects unsupported parameters for login."""

        self._require_no_params(params)
        return None

    def is_applicable(self, context: TaskContext, observation: Observation) -> bool:
        """Allows login handling only on supported login or already-logged states."""

        return observation.screen_type in {
            ScreenType.PNC_LOGIN,
            ScreenType.PNC_ACCOUNT_SWITCH,
            ScreenType.PNC_LOADING,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans the next bootstrap action for loading, account-switch, or login states."""

        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
            if self._configured_account_is_verified(context, observation):
                return []
            if context.castle_roster is None:
                raise TaskVerificationError(
                    "Login reached home city without verified account evidence and no trusted castle roster snapshot is available.",
                    account_id=context.account.id,
                    pnc_account_id=context.account.pnc_account_id,
                )
            return context.flows.open_castle_selection(observation)
        if observation.screen_type == ScreenType.PNC_CASTLE_SELECTION:
            return []
        if observation.screen_type == ScreenType.PNC_LOADING:
            if observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON):
                return [
                    TapAction(
                        selector_id=UiElementId.PNC_LOADING_RECONNECT_BUTTON,
                        reason="reconnect_loading_screen",
                        observe_after=True,
                    )
                ]
            return [WaitAction(milliseconds=1000, reason="wait_for_loading_screen", observe_after=True)]
        if observation.screen_type == ScreenType.PNC_ACCOUNT_SWITCH:
            return self._plan_account_switch(context, observation)
        if observation.screen_type != ScreenType.PNC_LOGIN:
            raise TaskVerificationError(
                f"Login task cannot plan from unsupported screen '{observation.screen_type}'.",
                screen_type=observation.screen_type,
                account_id=context.account.id,
            )
        credentials = context.account.credentials
        if credentials is None:
            raise TaskVerificationError(
                f"Account '{context.account.id}' cannot execute login without configured credentials.",
                account_id=context.account.id,
            )
        return [
            InputTextAction(
                selector_id=UiElementId.PNC_LOGIN_USERNAME_FIELD,
                text=credentials.username,
                reason="input_username",
            ),
            InputTextAction(
                selector_id=UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                text=credentials.password,
                reason="input_password",
            ),
            TapAction(
                selector_id=UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                reason="submit_login",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the expected account reaches a verified in-game state."""

        account_mismatch = self._detect_account_mismatch(context, after)
        if account_mismatch is not None:
            return account_mismatch
        if after.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_CASTLE_SELECTION}:
            if (
                self._configured_account_is_verified(context, after)
                or self._configured_account_is_verified(context, before)
                or self._login_submission_proves_account(context, before)
            ):
                return TaskResult.success("Login completed or was already satisfied.")
            roster_verification = self._verify_castle_roster_snapshot(after)
            if roster_verification is not None:
                return roster_verification
            return TaskResult.failure(
                "Login reached an in-game screen without verified account ownership evidence.",
            )
        if after.screen_type == ScreenType.PNC_MORE_MENU:
            return TaskResult.replan("Login opened the More menu and still needs to reach Manage Char for verification.")
        if after.screen_type in {ScreenType.PNC_LOADING, ScreenType.PNC_ACCOUNT_SWITCH}:
            return TaskResult.replan("Login is still resolving through a bootstrap transition.")
        if after.screen_type == ScreenType.PNC_LOGIN:
            if self._configured_account_is_verified(context, after):
                return TaskResult.replan("Login still shows the configured account and needs another bootstrap increment.")
            return TaskResult.failure("Login screen is still visible after credential entry.", retryable=True)
        return TaskResult.failure("Login did not reach a verified in-game state.")

    def _configured_account_is_verified(self, context: TaskContext, observation: Observation) -> bool:
        """Returns whether one observation carries trusted ownership proof for the configured account."""

        expected_account_id = context.account.pnc_account_id
        if observation.verified_pnc_account_id == expected_account_id:
            return True
        return (
            observation.screen_type in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}
            and observation.current_pnc_account_id == expected_account_id
        )

    def _login_submission_proves_account(self, context: TaskContext, observation: Observation) -> bool:
        """Returns whether the previous increment explicitly submitted the configured login credentials."""

        return (
            observation.screen_type == ScreenType.PNC_LOGIN
            and observation.current_pnc_account_id in {None, context.account.pnc_account_id}
        )

    def _detect_account_mismatch(self, context: TaskContext, observation: Observation) -> TaskResult | None:
        """Returns a recoverable or terminal mismatch result when the observation proves another account."""

        observed_account_id = observation.current_pnc_account_id
        expected_account_id = context.account.pnc_account_id
        if observed_account_id in {None, expected_account_id}:
            return None
        message = (
            f"Observed account '{observed_account_id}' does not match configured account '{expected_account_id}'."
        )
        if observation.screen_type in {ScreenType.PNC_ACCOUNT_SWITCH, ScreenType.PNC_LOGIN}:
            return TaskResult.replan(message)
        return TaskResult.failure(message)

    def _verify_castle_roster_snapshot(self, observation: Observation) -> TaskResult | None:
        """Returns roster-backed verification when the visible roster window matches the trusted cache snapshot."""

        if observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            return None
        roster_snapshot = observation.castle_roster_snapshot
        visible_castles = observation.entries(ListEntryKind.CASTLE)
        if roster_snapshot is None or not visible_castles:
            return None
        matched_castles = 0
        for entry in visible_castles:
            if any(castle_entry_identity_matches(entry, castle) for castle in roster_snapshot.castles):
                matched_castles += 1
                continue
            return TaskResult.failure(
                "Visible castle roster does not match the configured account's trusted cached roster.",
            )
        if matched_castles == 0:
            return None
        return TaskResult.success("Login verified against the trusted cached castle roster.")

    def _plan_account_switch(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Plans the account-switch action required to continue with the configured account."""

        observed_account_id = observation.current_pnc_account_id
        expected_account_id = context.account.pnc_account_id
        if observed_account_id == expected_account_id:
            if not observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON):
                raise TaskVerificationError(
                    "Account-switch screen matched the configured account but no continue action is visible.",
                    account_id=context.account.id,
                    pnc_account_id=expected_account_id,
                )
            return [
                TapAction(
                    selector_id=UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON,
                    reason="continue_with_expected_account",
                    observe_after=True,
                )
            ]
        if not context.account.login_enabled:
            raise TaskVerificationError(
                f"Account '{context.account.id}' cannot correct a mismatched account-switch state without configured credentials.",
                account_id=context.account.id,
                observed_account_id=observed_account_id,
                expected_account_id=expected_account_id,
            )
        if not observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON):
            raise TaskVerificationError(
                "Account-switch screen cannot be corrected because no change-account action is visible.",
                account_id=context.account.id,
                observed_account_id=observed_account_id,
                expected_account_id=expected_account_id,
            )
        return [
            TapAction(
                selector_id=UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON,
                reason="change_to_expected_account",
                observe_after=True,
            )
        ]
