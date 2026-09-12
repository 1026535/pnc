"""Synthetic AutomationFrameworkFixtures fixture."""

from __future__ import annotations

from collections.abc import Sequence

from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutionPolicy,
)
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import (
    ClickDefinition,
    ClickOutcome,
    DetectionKind,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
)

from tests.support.automation.session import FakeSession
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class AutomationFrameworkFixtures:
    """Shared setup only; deliberately not a TestCase."""

    def setUp(self) -> None:
        """Builds shared account and defaults inputs for framework tests."""

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
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)

    def _make_selector_registry(
        self,
        *,
        selector_id: UiElementId = UiElementId.PNC_BOTTOM_NAV_MORE,
        source_screen: ScreenType = ScreenType.PNC_HOME_CITY,
        target_screen: ScreenType = ScreenType.PNC_MORE_MENU,
        verification_selectors: Sequence[UiElementId] = (UiElementId.PNC_MORE_SETTINGS,),
        interaction_kind: SelectorInteractionKind = SelectorInteractionKind.NAVIGATION,
        safe_to_click: bool = True,
    ) -> SelectorRegistry:
        """Builds the minimal selector registry required for one observed-action test."""

        return SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=selector_id,
                    screens=(source_screen,),
                    detection_kind=DetectionKind.SEMANTIC,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=interaction_kind,
                    click=ClickDefinition(),
                    click_outcomes=(
                        ClickOutcome(
                            target_screen=target_screen,
                            verification_selectors=tuple(verification_selectors),
                            safe_to_click=safe_to_click,
                        ),
                    ),
                ),
            )
        )

    def _execute_observed_tap(
        self,
        *,
        registry: SelectorRegistry,
        before: Observation,
        queued_observations: Sequence[Observation],
        selector_id: UiElementId = UiElementId.PNC_BOTTOM_NAV_MORE,
        policy: ObservedActionExecutionPolicy | None = None,
    ) -> tuple[object, FakeObservationService, FakeSession]:
        """Executes one selector-backed tap through the shared observed-action executor."""

        fake_observer = FakeObservationService(observations=list(queued_observations))
        fake_session = FakeSession()
        executor = _make_observed_action_executor(
            fake_session,
            registry=registry,
            policy=ObservedActionExecutionPolicy() if policy is None else policy,
        )
        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=selector_id,
                    reason="test_navigation_tap",
                    observe_after=True,
                ),
            ),
            before,
            observe=fake_observer.observe,
        )
        return execution, fake_observer, fake_session
