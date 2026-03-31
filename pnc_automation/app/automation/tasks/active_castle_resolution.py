"""Shared active-castle resolution helpers for archive-backed tasks."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import ActionRequest
from pnc_automation.app.pnc.domain.observation import Observation, castle_names_match, resolve_unambiguous_castle_identity
from pnc_automation.app.pnc.enums.screen_type import ScreenType

_ACTIVE_CASTLE_IDENTITY_STATE_KEY = "active_castle_identity"
_ACTIVE_CASTLE_NAME_STATE_KEY = "active_castle_name"


def remember_active_castle_identity(context: TaskContext, observation: Observation) -> CastleIdentity | None:
    """Caches the best exact active-castle identity available from task state or the current observation."""

    cached = context.runtime_state.get(_ACTIVE_CASTLE_IDENTITY_STATE_KEY)
    if isinstance(cached, CastleIdentity):
        return cached
    if context.target_castle is not None:
        context.runtime_state[_ACTIVE_CASTLE_IDENTITY_STATE_KEY] = context.target_castle
        context.runtime_state[_ACTIVE_CASTLE_NAME_STATE_KEY] = context.target_castle.castle_name
        return context.target_castle
    if observation.current_castle is not None and observation.current_castle.kingdom.strip() != "":
        context.runtime_state[_ACTIVE_CASTLE_IDENTITY_STATE_KEY] = observation.current_castle
        context.runtime_state[_ACTIVE_CASTLE_NAME_STATE_KEY] = observation.current_castle.castle_name
        return observation.current_castle
    if observation.current_castle_name is not None:
        resolved = _resolve_castle_name(context, observation.current_castle_name)
        if resolved is not None:
            context.runtime_state[_ACTIVE_CASTLE_IDENTITY_STATE_KEY] = resolved
            context.runtime_state[_ACTIVE_CASTLE_NAME_STATE_KEY] = resolved.castle_name
            return resolved
    roster = context.castle_roster
    if roster is not None and len(roster.castles) == 1:
        context.runtime_state[_ACTIVE_CASTLE_IDENTITY_STATE_KEY] = roster.castles[0]
        context.runtime_state[_ACTIVE_CASTLE_NAME_STATE_KEY] = roster.castles[0].castle_name
        return roster.castles[0]
    return None


def remember_active_castle_name(context: TaskContext, observation: Observation) -> str | None:
    """Caches the best active-castle label available for archive paths that only need the castle name."""

    cached_name = context.runtime_state.get(_ACTIVE_CASTLE_NAME_STATE_KEY)
    if isinstance(cached_name, str) and cached_name.strip() != "":
        return cached_name
    exact_castle = remember_active_castle_identity(context, observation)
    if exact_castle is not None:
        return exact_castle.castle_name
    if observation.current_castle_name is not None and observation.current_castle_name.strip() != "":
        context.runtime_state[_ACTIVE_CASTLE_NAME_STATE_KEY] = observation.current_castle_name.strip()
        return observation.current_castle_name.strip()
    return None


def plan_active_castle_resolution(
    context: TaskContext,
    observation: Observation,
    *,
    task_label: str,
    purpose: str,
    require_exact_identity: bool,
) -> list[ActionRequest]:
    """Plans or validates the shared Lord-Info resolution path used by archive-backed tasks."""

    resolved = (
        remember_active_castle_identity(context, observation)
        if require_exact_identity
        else remember_active_castle_name(context, observation)
    )
    if resolved is not None:
        return []
    if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
        return context.flows.open_lord_info(observation)
    if observation.screen_type == ScreenType.PNC_LORD_INFO:
        if observation.current_castle_name is None or observation.current_castle_name.strip() == "":
            raise SelectorResolutionError(
                f"{task_label} reached Lord Info but could not resolve the active castle name.",
                screen_type=observation.screen_type,
            )
        if require_exact_identity and _resolve_castle_name(context, observation.current_castle_name) is None:
            raise SelectorResolutionError(
                f"{task_label} could not resolve the active castle to one canonical configured identity.",
                screen_type=observation.screen_type,
                current_castle_name=observation.current_castle_name,
            )
        return context.flows.ensure_home_city(observation)
    raise SelectorResolutionError(
        f"{task_label} requires an explicit castle target, a single-castle roster, or a home-adjacent screen so it can validate the active castle before {purpose}.",
        screen_type=observation.screen_type,
    )


def require_active_castle_identity(context: TaskContext, observation: Observation, *, task_label: str) -> CastleIdentity:
    """Returns the canonical active-castle identity or fails fast when it cannot be resolved exactly."""

    resolved = remember_active_castle_identity(context, observation)
    if resolved is not None:
        return resolved
    raise SelectorResolutionError(
        f"{task_label} could not resolve the active castle required for archive persistence.",
        screen_type=observation.screen_type,
    )


def require_active_castle_name(context: TaskContext, observation: Observation, *, task_label: str) -> str:
    """Returns the canonical active-castle label or fails fast when it cannot be resolved."""

    resolved = remember_active_castle_name(context, observation)
    if resolved is not None:
        return resolved
    raise SelectorResolutionError(
        f"{task_label} could not resolve the active castle required for archive persistence.",
        screen_type=observation.screen_type,
    )


def _resolve_castle_name(context: TaskContext, castle_name: str) -> CastleIdentity | None:
    """Resolves one observed castle name to an exact configured identity when it is unambiguous."""

    normalized_name = castle_name.strip()
    if normalized_name == "":
        return None
    if context.target_castle is not None and castle_names_match(context.target_castle.castle_name, normalized_name):
        return context.target_castle
    roster = context.castle_roster
    if roster is None:
        return None
    matching_castles = tuple(castle for castle in roster.castles if castle_names_match(castle.castle_name, normalized_name))
    return resolve_unambiguous_castle_identity(matching_castles, preferred_name=normalized_name)
