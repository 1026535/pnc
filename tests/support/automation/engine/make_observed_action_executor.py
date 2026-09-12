"""Synthetic make_observed_action_executor fixture."""

from __future__ import annotations

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutor,
    ObservedActionExecutionPolicy,
)
from pnc_automation.app.pnc.vision.selectors import (
    SelectorRegistry,
    build_default_selector_registry,
)

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger



def _make_observed_action_executor(
    session: FakeSession,
    *,
    registry: SelectorRegistry | None = None,
    policy: ObservedActionExecutionPolicy | None = None,
) -> ObservedActionExecutor:
    """Builds the shared observed-action executor used by runner and executor tests."""

    canonical_registry = build_default_selector_registry()
    if registry is None:
        resolved_registry = canonical_registry
    else:
        custom_ids = {selector.id for selector in registry.all()}
        resolved_registry = SelectorRegistry(
            selectors=(
                *registry.all(),
                *(selector for selector in canonical_registry.all() if selector.id not in custom_ids),
            ),
            surfaces=registry.all_surfaces(),
        )
    return ObservedActionExecutor(
        selector_registry=resolved_registry,
        action_executor=ActionExecutor(
            selector_registry=resolved_registry,
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        ),
        logger=build_logger(),
        policy=ObservedActionExecutionPolicy() if policy is None else policy,
        sleep=lambda _: None,
    )
