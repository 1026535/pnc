"""Task that logs into the configured P&C account when required."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pnc_automation.automation.task import BaseAutomationTask, TaskId, TaskResult
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.errors import TaskVerificationError
from pnc_automation.pnc.action_requests import ActionRequest, InputTextAction, TapAction
from pnc_automation.pnc.observation import Observation
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
        }

    def plan(self, context: TaskContext, observation: Observation) -> list[ActionRequest]:
        """Inputs credentials only when the login screen is visible."""

        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_LOADING}:
            return []
        credentials = context.account.credentials
        if credentials is None:
            raise TaskVerificationError(
                f"Account '{context.account.id}' cannot execute login without configured credentials.",
                account_id=context.account.id,
            )
        return [
            TapAction(selector_id=UiElementId.PNC_LOGIN_USERNAME_FIELD, reason="focus_username"),
            InputTextAction(text=credentials.username, reason="input_username"),
            TapAction(selector_id=UiElementId.PNC_LOGIN_PASSWORD_FIELD, reason="focus_password"),
            InputTextAction(text=credentials.password, reason="input_password"),
            TapAction(
                selector_id=UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                reason="submit_login",
                observe_after=True,
            ),
        ]

    def verify(self, context: TaskContext, before: Observation, after: Observation) -> TaskResult:
        """Succeeds once the account leaves the login screen for an in-game state."""

        if after.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_LOADING}:
            return TaskResult.success("Login completed or was already satisfied.")
        return TaskResult.failure("Login did not reach a verified in-game state.", retryable=True)
