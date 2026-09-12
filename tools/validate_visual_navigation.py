"""Prove bounded read-only visual navigation on the active castle."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
import json
import logging
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.entrypoints.api import AutomationApi
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.domain.mail import MailRecipientKind, MailboxType, SendMailParams
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    castle_entry_identity_matches,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapOverviewNavigator
from pnc_automation.app.pnc.vision.navigation_selector_validator import (
    NavigationSelectorValidator,
    write_navigation_selector_validation_report,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.app.pnc.vision.observation_builder import CapturedObservation
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selector_interactions import safe_navigation_outcomes
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.image.models import Bounds

if TYPE_CHECKING:
    from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext


MAX_INPUT_ATTEMPTS = 8
MAX_PROBE_SECONDS = 600
MAX_PASSIVE_UNKNOWN_RECAPTURES = 3


class ProbeRoute(StrEnum):
    """Read-only route families exposed by the offline/live validator."""

    NAVIGATION = "navigation"
    QUEST = "quest"
    BAG = "bag"
    FIELDS = "fields"
    COORDINATES = "coordinates"
    LORD_INFO = "lord_info"
    VIP = "vip"
    CHAT = "chat"
    MAIL_HUB = "mail_hub"
    MAIL_COMPOSE = "mail_compose"
    WORLD_OVERVIEW = "world_overview"
    ALLIANCE = "alliance"
    GIFT_CENTER = "gift_center"
    NAVIGATION_SELECTORS = "navigation_selectors"


@dataclass(frozen=True, slots=True)
class ProbeRouteDeclaration:
    """Typed entry/exit contract for one route family."""

    route: ProbeRoute
    entry_screens: frozenset[ScreenType]
    destination_screens: frozenset[ScreenType]
    entry_selectors: frozenset[UiElementId]
    read_only: bool = True
    max_input_attempts: int = MAX_INPUT_ATTEMPTS


ROUTE_DECLARATIONS: Mapping[ProbeRoute, ProbeRouteDeclaration] = {
    ProbeRoute.NAVIGATION: ProbeRouteDeclaration(
        route=ProbeRoute.NAVIGATION,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        entry_selectors=frozenset(),
    ),
    ProbeRoute.NAVIGATION_SELECTORS: ProbeRouteDeclaration(
        route=ProbeRoute.NAVIGATION_SELECTORS,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        entry_selectors=frozenset(),
    ),
    ProbeRoute.QUEST: ProbeRouteDeclaration(
        route=ProbeRoute.QUEST,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}),
        entry_selectors=frozenset({UiElementId.PNC_BOTTOM_NAV_QUEST, UiElementId.PNC_QUEST_TAB_DAILY}),
    ),
    ProbeRoute.BAG: ProbeRouteDeclaration(
        route=ProbeRoute.BAG,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_BAG}),
        entry_selectors=frozenset({UiElementId.PNC_BOTTOM_NAV_BAG}),
    ),
    ProbeRoute.FIELDS: ProbeRouteDeclaration(
        route=ProbeRoute.FIELDS,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_LORD_INFO}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_LORD_INFO_SHORTCUT}),
    ),
    ProbeRoute.COORDINATES: ProbeRouteDeclaration(
        route=ProbeRoute.COORDINATES,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_WORLD_MAP}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_WORLD_SWITCH}),
    ),
    ProbeRoute.LORD_INFO: ProbeRouteDeclaration(
        route=ProbeRoute.LORD_INFO,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_LORD_INFO}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_LORD_INFO_SHORTCUT}),
    ),
    ProbeRoute.VIP: ProbeRouteDeclaration(
        route=ProbeRoute.VIP,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_VIP}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_VIP_SHORTCUT}),
    ),
    ProbeRoute.CHAT: ProbeRouteDeclaration(
        route=ProbeRoute.CHAT,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_CHAT}),
        entry_selectors=frozenset({UiElementId.PNC_CHAT_SHORTCUT}),
    ),
    ProbeRoute.MAIL_HUB: ProbeRouteDeclaration(
        route=ProbeRoute.MAIL_HUB,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_MAIL_HUB}),
        entry_selectors=frozenset({UiElementId.PNC_BOTTOM_NAV_MAIL}),
    ),
    ProbeRoute.MAIL_COMPOSE: ProbeRouteDeclaration(
        route=ProbeRoute.MAIL_COMPOSE,
        entry_screens=frozenset({
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MAILBOX_LIST,
        }),
        destination_screens=frozenset({ScreenType.PNC_MAIL_COMPOSE_POPUP}),
        entry_selectors=frozenset({UiElementId.PNC_BOTTOM_NAV_MAIL, UiElementId.PNC_MAIL_COMPOSE_BUTTON}),
        max_input_attempts=12,
    ),
    ProbeRoute.WORLD_OVERVIEW: ProbeRouteDeclaration(
        route=ProbeRoute.WORLD_OVERVIEW,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP}),
        destination_screens=frozenset({ScreenType.PNC_WORLD_MAP_OVERVIEW}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_WORLD_SWITCH, UiElementId.PNC_WORLD_EXPAND_BUTTON}),
        max_input_attempts=10,
    ),
    ProbeRoute.ALLIANCE: ProbeRouteDeclaration(
        route=ProbeRoute.ALLIANCE,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_ALLIANCE_JOIN}),
        entry_selectors=frozenset({UiElementId.PNC_BOTTOM_NAV_ALLIANCE}),
    ),
    ProbeRoute.GIFT_CENTER: ProbeRouteDeclaration(
        route=ProbeRoute.GIFT_CENTER,
        entry_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        destination_screens=frozenset({ScreenType.PNC_GIFT_CENTER}),
        entry_selectors=frozenset({UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON}),
    ),
}


PROBE_SELECTOR_SCREENS = (
    (UiElementId.PNC_POPUP_CLOSE_BUTTON, frozenset({ScreenType.PNC_POPUP})),
    (UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON, frozenset({ScreenType.PNC_VIP_DAILY_RESET})),
    (
        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
        frozenset(
            {
                ScreenType.PNC_SETTINGS,
                ScreenType.PNC_CASTLE_SELECTION,
                ScreenType.PNC_QUEST_MAIN,
                ScreenType.PNC_QUEST_DAILY,
                ScreenType.PNC_BAG,
                ScreenType.PNC_LORD_INFO,
                ScreenType.PNC_VIP,
                ScreenType.PNC_CHAT,
                ScreenType.PNC_MAIL_HUB,
                ScreenType.PNC_MAILBOX_LIST,
                ScreenType.PNC_ALLIANCE_HOME,
                ScreenType.PNC_ALLIANCE_JOIN,
                ScreenType.PNC_GIFT_CENTER,
            }
        ),
    ),
    (UiElementId.PNC_BOTTOM_NAV_MORE, frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU})),
    (UiElementId.PNC_MORE_SETTINGS, frozenset({ScreenType.PNC_MORE_MENU})),
    (UiElementId.PNC_MORE_MANAGE_CHAR, frozenset({ScreenType.PNC_SETTINGS})),
    (UiElementId.PNC_BOTTOM_NAV_QUEST, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_BOTTOM_NAV_BAG, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_BOTTOM_NAV_MAIL, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_MAIL_ROW_PLAYER_MAIL, frozenset({ScreenType.PNC_MAIL_HUB})),
    (UiElementId.PNC_MAIL_COMPOSE_BUTTON, frozenset({ScreenType.PNC_MAILBOX_LIST})),
    (UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON, frozenset({ScreenType.PNC_MAIL_COMPOSE_POPUP})),
    (UiElementId.PNC_BOTTOM_NAV_ALLIANCE, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_QUEST_TAB_MAIN, frozenset({ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY})),
    (UiElementId.PNC_QUEST_TAB_DAILY, frozenset({ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY})),
    (UiElementId.PNC_HOME_WORLD_SWITCH, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_WORLD_EXPAND_BUTTON, frozenset({ScreenType.PNC_WORLD_MAP})),
    (UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON, frozenset({ScreenType.PNC_WORLD_MAP_OVERVIEW})),
    (UiElementId.PNC_WORLD_HOME_NAV, frozenset({ScreenType.PNC_WORLD_MAP})),
    (UiElementId.PNC_HOME_LORD_INFO_SHORTCUT, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_HOME_VIP_SHORTCUT, frozenset({ScreenType.PNC_HOME_CITY})),
    (UiElementId.PNC_CHAT_SHORTCUT, frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP})),
    (UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON, frozenset({ScreenType.PNC_HOME_CITY})),
)
PROBE_SOURCE_SCREENS = frozenset(screen for _, screens in PROBE_SELECTOR_SCREENS for screen in screens)
PROBE_BACK_SCREENS = frozenset(
    {
        ScreenType.PNC_SETTINGS,
        ScreenType.PNC_CASTLE_SELECTION,
        ScreenType.PNC_QUEST_MAIN,
        ScreenType.PNC_QUEST_DAILY,
        ScreenType.PNC_BAG,
        ScreenType.PNC_LORD_INFO,
        ScreenType.PNC_VIP,
        ScreenType.PNC_CHAT,
        ScreenType.PNC_MAIL_HUB,
        ScreenType.PNC_MAILBOX_LIST,
        ScreenType.PNC_ALLIANCE_HOME,
        ScreenType.PNC_ALLIANCE_JOIN,
        ScreenType.PNC_GIFT_CENTER,
    }
)
ALLOWED_TAPS = frozenset(selector for selector, _ in PROBE_SELECTOR_SCREENS)


class _RuntimeWithFlows(Protocol):
    """Minimal typed runtime surface used by route declarations."""

    flow_planner: ScreenFlowPlanner


@dataclass(slots=True)
class _ProbeObservationCaptureService:
    """Adapts the route-owned capture callback to the validator protocol."""

    capture: Callable[[str, ObservationRequest | None], CapturedObservation]

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
    ) -> CapturedObservation:
        """Delegate capture without adding a second policy or budget owner."""

        return self.capture(label, request)


def require_probe_route(route: ProbeRoute | str) -> ProbeRoute:
    """Validate a route before creating artifacts, starting runtime, or dispatching input."""

    if isinstance(route, ProbeRoute):
        return route
    try:
        return ProbeRoute(route)
    except ValueError as error:
        raise ValueError(f"Unsupported read-only route '{route}'.") from error


def validate_navigation_selector_ids(
    selector_ids: Sequence[UiElementId],
    *,
    source_screen: ScreenType | None = None,
    catalog_path: Path | None = None,
) -> tuple[UiElementId, ...]:
    """Validate explicit navigation selectors before runtime or artifact creation."""

    requested = tuple(dict.fromkeys(selector_ids))
    if not requested:
        raise ValueError("The navigation-selectors route requires at least one selector.")
    registry = build_default_selector_registry(catalog_path=catalog_path)
    for selector_id in requested:
        selector = registry.require_supported(selector_id)
        if selector.interaction_kind != SelectorInteractionKind.NAVIGATION:
            raise ValueError(f"Selector '{selector_id.value}' is not a reviewed navigation control.")
        if selector_id not in ALLOWED_TAPS:
            raise ValueError(f"Selector '{selector_id.value}' is outside the read-only canary allowlist.")
        if not safe_navigation_outcomes(selector):
            raise ValueError(f"Selector '{selector_id.value}' has no safe reviewed navigation outcome.")
        if source_screen is not None and source_screen not in selector.screens:
            raise ValueError(
                f"Selector '{selector_id.value}' is not reviewed from source screen '{source_screen.name}'."
            )
    return requested


def validate_probe_action(action: ActionRequest) -> None:
    """Reject mutations, row selections, text input, raw taps, and unbounded waits."""

    if isinstance(action, TapAction) and action.selector_id in ALLOWED_TAPS:
        return
    if isinstance(action, KeyEventAction) and action.key_code == "KEYCODE_BACK":
        return
    if isinstance(action, WaitAction) and 0 <= action.milliseconds <= 1000:
        return
    raise ValueError("Action is outside the read-only visual-navigation allowlist.")


def _bounds_summary(bounds: Bounds | None) -> dict[str, int] | None:
    if bounds is None:
        return None
    return asdict(bounds)


def _serialize_row(entry: DetectedListEntry) -> dict[str, object]:
    """Serialize row safety and semantic identity without exposing OCR text."""

    metadata = {
        key: entry.metadata[key]
        for key in (
            "quest_id",
            "item_id",
            "resource",
            "amount",
            "owned",
            "progress_current",
            "progress_required",
            "row_state",
            "unresolved_reason",
        )
        if key in entry.metadata
    }
    return {
        "kind": entry.kind.value,
        "status": entry.row_status.value,
        "bounds": _bounds_summary(entry.bounds),
        "action_point": entry.action_point,
        "action_bounds": _bounds_summary(entry.action_bounds),
        "metadata": metadata,
    }


def _identity_summary(observation: Observation) -> dict[str, object]:
    castle = observation.current_castle
    return {
        "castle": None
        if castle is None
        else {"kingdom": castle.kingdom, "castle_name": castle.castle_name, "castle_level": castle.castle_level},
        "castle_evidence": (
            None if observation.current_castle_evidence is None else observation.current_castle_evidence.value
        ),
        "pnc_account_id": observation.current_pnc_account_id,
        "verified_pnc_account_id": observation.verified_pnc_account_id,
        "profile_player_name": observation.profile_player_name,
    }


def _verify_manage_identity(observation: Observation) -> dict[str, object]:
    """Require exact Manage Char evidence and one selected matching castle row."""

    if observation.current_castle is None:
        raise RuntimeError("Manage Char did not expose the active castle identity.")
    if observation.current_castle_evidence != CurrentCastleEvidenceKind.EXACT:
        raise RuntimeError("Manage Char active-castle evidence was not explicitly exact.")
    selected_rows = tuple(
        entry for entry in observation.entries(ListEntryKind.CASTLE) if entry.selected
    )
    matching_selected_rows = tuple(
        entry
        for entry in selected_rows
        if castle_entry_identity_matches(entry, observation.current_castle)
    )
    if len(selected_rows) != 1 or len(matching_selected_rows) != 1:
        raise RuntimeError(
            "Manage Char must expose exactly one selected castle row matching the active identity."
        )
    return {
        "evidence_kind": observation.current_castle_evidence.value,
        "selected_castle_rows": len(selected_rows),
        "matching_selected_castle_rows": len(matching_selected_rows),
    }


def _coordinate_proof(observation: Observation, *, phase: str) -> tuple[int, int]:
    """Require one concrete world coordinate from a typed spatial viewport."""

    surface = observation.spatial_surface
    coordinate = None if surface is None else surface.viewport.coordinate
    if (
        not isinstance(coordinate, tuple)
        or len(coordinate) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in coordinate)
    ):
        raise RuntimeError(f"Coordinate route lacked a concrete {phase} coordinate pair.")
    return coordinate


def _fields_identity_summary(observation: Observation) -> dict[str, str]:
    """Record a typed Lord Info name fact or an explicit read-only abstention."""

    if observation.current_castle is not None and observation.current_castle.castle_name.strip():
        return {"name_status": "observed", "name_source": "lord_info_current_castle"}
    return {
        "name_status": "abstained",
        "reason": "lord_info_current_castle_name_unavailable",
    }


def _visual_profile_ids(observation: Observation) -> tuple[str, ...]:
    """Recover matched visual profile IDs from the already-published decision."""

    return tuple(
        evidence.layout_id
        for evidence in observation.decision.evidence
        if evidence.reason.startswith("visual_anchor:") and evidence.layout_id is not None
    )


def _ocr_context_summary(
    ocr_context: ObservationOcrContext | None,
) -> tuple[dict[str, object] | None, list[dict[str, object]] | None]:
    """Serialize the canonical OCR context metrics and diagnostics for one capture."""

    if ocr_context is None:
        return None, None
    metrics = ocr_context.metrics
    return (
        {
            "requests": metrics.requests,
            "engine_calls": metrics.engine_calls,
            "processed_pixel_area": metrics.processed_pixel_area,
            "cache_hits": metrics.cache_hits,
            "fullframe_reuses": metrics.fullframe_reuses,
            "engine_seconds": metrics.engine_seconds,
        },
        [asdict(diagnostic) for diagnostic in ocr_context.read_diagnostics],
    )


def summarize(
    observation: Observation,
    *,
    ocr_context: ObservationOcrContext | None = None,
) -> dict[str, object]:
    """Persist typed decision, guard, layout, row, and identity evidence."""

    decision = observation.decision
    context_metrics, context_diagnostics = _ocr_context_summary(ocr_context)
    return {
        "screen": observation.screen_type.name,
        "guard": decision.guard.value,
        "layout_id": decision.layout_id,
        "coordinate_only": decision.coordinate_only,
        "blocking_popup": observation.blocking_popup,
        "decision_evidence": [
            {
                "screen": evidence.screen_type.name,
                "reason": evidence.reason,
                "layout_id": evidence.layout_id,
                "layout_revision": evidence.layout_revision,
            }
            for evidence in decision.evidence
        ],
        "identity": _identity_summary(observation),
        "rows": [_serialize_row(entry) for entry in observation.list_entries],
        "artifact": str(observation.artifact_path),
        "elements": [
            {"id": item.selector_id.value, "source": item.source_kind.value, "bounds": asdict(item.bounds)}
            for item in observation.visible_elements.values()
        ],
        "context_metrics": context_metrics,
        "context_diagnostics": context_diagnostics,
    }


def _route_entry_action(route: ProbeRoute, current: Observation, runtime: _RuntimeWithFlows) -> ActionRequest:
    """Build one explicit route entry action through the canonical flow owner."""

    flows = runtime.flow_planner
    if route == ProbeRoute.QUEST:
        return TapAction(
            selector_id=UiElementId.PNC_BOTTOM_NAV_QUEST,
            observe_after=True,
            reason="inspect_quest",
            follow_up_request=ObservationRequest.daily_quest_follow_up(),
        )
    if route == ProbeRoute.BAG:
        return TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_BAG, observe_after=True, reason="inspect_bag")
    if route in {ProbeRoute.FIELDS, ProbeRoute.LORD_INFO}:
        actions = flows.open_lord_info(current)
        if len(actions) != 1:
            raise RuntimeError("Lord Info route requires one canonical shortcut action.")
        return actions[0]
    if route == ProbeRoute.VIP:
        return TapAction(
            selector_id=UiElementId.PNC_HOME_VIP_SHORTCUT,
            observe_after=True,
            reason="inspect_vip",
            follow_up_request=ObservationRequest.source_screen_retry(ScreenType.PNC_VIP),
        )
    if route == ProbeRoute.CHAT:
        actions = flows.open_chat(current)
        if len(actions) != 1:
            raise RuntimeError("Chat route requires one canonical shortcut action.")
        return actions[0]
    if route == ProbeRoute.MAIL_HUB:
        actions = flows.open_mail_hub(current)
        if len(actions) != 1:
            raise RuntimeError("Mail-hub route requires one canonical bottom-nav action.")
        return actions[0]
    if route == ProbeRoute.GIFT_CENTER:
        return TapAction(
            selector_id=UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON,
            observe_after=True,
            reason="inspect_gift_center",
        )
    if route == ProbeRoute.ALLIANCE:
        actions = flows.open_alliance_home(current)
        if len(actions) != 1:
            raise RuntimeError("Alliance route requires one canonical bottom-nav action.")
        return actions[0]
    raise RuntimeError(f"Route '{route.value}' has no direct entry action.")


def run_probe(
    config: Path,
    account_id: str,
    output_root: Path,
    *,
    route: ProbeRoute | str = ProbeRoute.NAVIGATION,
    navigation_selectors: Sequence[UiElementId] = (),
    navigation_source_screen: ScreenType | None = None,
    catalog_path: Path | None = None,
) -> Path:
    """Run one bounded read-only route through canonical observation and flow helpers."""

    selected_route = require_probe_route(route)
    requested_navigation_selectors = (
        validate_navigation_selector_ids(
            navigation_selectors,
            source_screen=navigation_source_screen,
            catalog_path=catalog_path,
        )
        if selected_route == ProbeRoute.NAVIGATION_SELECTORS
        else tuple(navigation_selectors)
    )
    if selected_route != ProbeRoute.NAVIGATION_SELECTORS and navigation_selectors:
        raise ValueError("Explicit navigation selectors require the navigation-selectors route.")
    if selected_route != ProbeRoute.NAVIGATION_SELECTORS and navigation_source_screen is not None:
        raise ValueError("A navigation source screen requires the navigation-selectors route.")
    if selected_route == ProbeRoute.NAVIGATION_SELECTORS and navigation_source_screen is None:
        raise ValueError("The navigation-selectors route requires one reviewed source screen.")
    declaration = ROUTE_DECLARATIONS[selected_route]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = output_root / run_id
    directory.mkdir(parents=True, exist_ok=False)
    trace = directory / "trace.jsonl"
    summary_path = directory / "summary.json"
    summary: dict[str, object] = {
        "run_id": run_id,
        "route": selected_route.value,
        "route_declaration": {
            "entry_screens": sorted(screen.name for screen in declaration.entry_screens),
            "destination_screens": sorted(screen.name for screen in declaration.destination_screens),
            "entry_selectors": sorted(selector.value for selector in declaration.entry_selectors),
        },
        "status": "running",
        "trace": str(trace),
        "input_budget": {"max_attempts": declaration.max_input_attempts, "max_seconds": MAX_PROBE_SECONDS},
    }
    if navigation_source_screen is not None:
        summary["navigation_source_screen"] = navigation_source_screen.name
    summary_path.write_text(json.dumps(summary, indent=2))
    started = monotonic()
    action_count = 0
    capture_count = 0
    consecutive_unknown_captures = 0
    executor = None
    route_status = "passed"
    previous_logging_disable = logging.root.manager.disable
    resources = ExitStack()

    def require_time_budget() -> None:
        """Apply the route wall-clock budget to passive observations as well as inputs."""

        if monotonic() - started > MAX_PROBE_SECONDS:
            raise RuntimeError("Read-only visual navigation exhausted its time budget.")

    def input_attempts() -> int:
        if executor is None:
            return 0
        return executor.action_executor.input_attempts

    def record(entry: dict[str, object]) -> None:
        """Flush every pending or completed transition before proceeding."""

        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")

    try:
        app = build_application_runner(
            config,
            catalog_path=catalog_path,
            observation_mode=ObservationMode.DEBUG,
        )
        logging.disable(logging.CRITICAL)
        account = app.script_runner.config.require_account(account_id)
        account.require_live_role(LiveAutomationRole.SMOKE_TEST)
        resources.enter_context(AutomationApi(app).reserve_accounts((account_id,)))
        bundle = resources.enter_context(app.script_runner.build_connected_runtime_bundle(
            account=account, required_role=LiveAutomationRole.SMOKE_TEST,
        ))
        runtime = bundle.runtime
        observer = runtime.observation_service
        observer.configure_read_only_probe_mode()
        executor = runtime.require_observed_action_executor("Visual navigation requires observed execution.")
        executor.configure_read_only_probe_mode(
            allowed_selectors=ALLOWED_TAPS,
            allowed_selector_screens=PROBE_SELECTOR_SCREENS,
            allowed_back_screens=PROBE_BACK_SCREENS,
        )
        foreground_before = runtime.session.is_app_foregrounded()
        runtime.session.ensure_app_foregrounded()
        foreground_after = runtime.session.is_app_foregrounded()
        summary["runtime"] = {
            "instance_display_name": runtime.session.instance.display_name,
            "instance_id": runtime.session.instance.id,
            "foreground_before": foreground_before,
            "foreground_after": foreground_after,
            "startup_origin": "unknown",
        }
        if not foreground_after:
            raise RuntimeError("Read-only visual navigation could not verify the app foreground before input.")
        executor.action_executor.configure_input_attempt_budget(
            declaration.max_input_attempts,
            duration_seconds=MAX_PROBE_SECONDS,
        )

        def capture_observation(label: str, request: ObservationRequest | None = None):
            """Capture through the same time checked, run-prefixed path used by route steps."""
            nonlocal capture_count, consecutive_unknown_captures
            if consecutive_unknown_captures >= MAX_PASSIVE_UNKNOWN_RECAPTURES + 1:
                raise RuntimeError(
                    "Read-only visual navigation exceeded its global UNKNOWN observation budget "
                    "before the next capture."
                )
            require_time_budget()
            capture_count += 1
            capture = observer.capture_observation(
                f"visual_{run_id}_{capture_count}_{label}",
                request=request,
            )
            current = capture.observation
            if current.screen_type == ScreenType.UNKNOWN:
                consecutive_unknown_captures += 1
            else:
                consecutive_unknown_captures = 0
            record(
                {
                    "event": "observation",
                    "state": summarize(current, ocr_context=capture.ocr_context),
                    "visual_profiles": _visual_profile_ids(current),
                }
            )
            return capture

        current_capture: CapturedObservation | None = None

        def observe(label: str, request: ObservationRequest | None = None) -> Observation:
            """Capture uniquely named evidence through the canonical observation service."""

            nonlocal current_capture
            capture = capture_observation(label, request=request)
            current_capture = capture
            current = capture.observation
            return current

        current = observe("baseline")

        def step(action: ActionRequest) -> None:
            """Validate one bounded action, record intent, and retain executor evidence."""

            nonlocal current, action_count
            if (
                action_count >= declaration.max_input_attempts
                or input_attempts() >= declaration.max_input_attempts
            ):
                raise RuntimeError("Read-only visual navigation exhausted its input-attempt budget.")
            require_time_budget()
            if current.screen_type == ScreenType.UNKNOWN or current.decision.coordinate_only:
                raise RuntimeError("Visual navigation cannot dispatch input from this observation.")
            if current.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON):
                raise RuntimeError("Required update reached; the read-only probe stops before confirming.")
            validate_probe_action(action)
            action_count += 1
            action_data: dict[str, object] = {"type": type(action).__name__, "reason": action.reason}
            if isinstance(action, TapAction):
                action_data["selector"] = action.selector_id.value
            record(
                {
                    "event": "pending_action",
                    "index": action_count,
                    "action": action_data,
                    "before": summarize(
                        current,
                        ocr_context=None if current_capture is None else current_capture.ocr_context,
                    ),
                }
            )
            result = executor.execute_actions((action,), current, observe=observe)
            current = result.observation
            record(
                {
                    "event": "completed_action",
                    "index": action_count,
                    "after": summarize(
                        current,
                        ocr_context=None if current_capture is None else current_capture.ocr_context,
                    ),
                }
            )

        def reach(target: ScreenType, planner: Callable[[Observation], Sequence[ActionRequest]]) -> None:
            """Use one canonical flow increment at a time with bounded passive UNKNOWN settling."""

            nonlocal current
            unknown_recaptures = 0
            for _ in range(8):
                require_time_budget()
                if current.screen_type == ScreenType.UNKNOWN:
                    if unknown_recaptures >= MAX_PASSIVE_UNKNOWN_RECAPTURES:
                        raise RuntimeError(f"Read-only route could not classify the screen before reaching {target.name}.")
                    unknown_recaptures += 1
                    current = observe("passive_unknown_recapture", request=ObservationRequest.full_runtime_default())
                    continue
                if current.screen_type == target:
                    return
                if current.decision.coordinate_only:
                    raise RuntimeError("Coordinate-only proof cannot authorize navigation or unwind input.")
                if current.screen_type == ScreenType.PNC_POPUP or current.blocking_popup:
                    actions = runtime.flow_planner.close_blocking_popup(current)
                else:
                    actions = planner(current)
                if not actions:
                    break
                step(actions[0])
            raise RuntimeError(f"Read-only visual navigation did not reach {target.name}.")

        reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        reach(ScreenType.PNC_CASTLE_SELECTION, runtime.flow_planner.open_castle_selection)
        manage_observation = current
        identity_verification = _verify_manage_identity(manage_observation)
        active_castle = manage_observation.current_castle
        assert active_castle is not None
        summary["active_identity_verified"] = True
        summary["manage_identity"] = _identity_summary(manage_observation)
        summary["manage_identity_verification"] = identity_verification
        reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)

        if selected_route == ProbeRoute.NAVIGATION_SELECTORS:
            validator = NavigationSelectorValidator(
                selector_registry=app.script_runner.observation_builder.selector_registry,
                observation_service=_ProbeObservationCaptureService(capture_observation),
                action_executor=executor,
                screen_flows=runtime.flow_planner,
                logger=app.script_runner.logger,
                max_prepare_steps=6,
                max_recovery_steps=6,
                max_destination_settle_observations=3,
            )
            report = validator.validate(
                selector_ids=requested_navigation_selectors,
                source_screen=navigation_source_screen,
            )
            report_path = directory / "navigation_validation.yaml"
            write_navigation_selector_validation_report(report_path, report)
            for result in report.results:
                record(
                    {
                        "event": "navigation_validation_case",
                        "selector": result.selector_id.value,
                        "source_screen": result.source_screen.name,
                        "status": result.status.value,
                        "reason": result.reason,
                        "destination_screen": (
                            None if result.destination_screen is None else result.destination_screen.name
                        ),
                        "matched_target_screen": (
                            None if result.matched_target_screen is None else result.matched_target_screen.name
                        ),
                        "expected_target_screens": [screen.name for screen in result.expected_target_screens],
                    }
                )
            current = observe("navigation_validation_final")
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
            summary.update(
                navigation_selector_ids=[selector_id.value for selector_id in requested_navigation_selectors],
                navigation_report=str(report_path),
                navigation_passed=report.passed_count,
                navigation_failed=report.failed_count,
                navigation_skipped=report.skipped_count,
            )
            if report.failed_count or report.skipped_count:
                raise RuntimeError("Read-only navigation selector canary did not pass every requested case.")
        elif selected_route == ProbeRoute.QUEST:
            step(_route_entry_action(selected_route, current, runtime))
            if current.screen_type not in {ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}:
                raise RuntimeError("Quest navigation did not produce a supported Quest tab.")
            if current.screen_type == ScreenType.PNC_QUEST_MAIN:
                step(TapAction(
                    selector_id=UiElementId.PNC_QUEST_TAB_DAILY,
                    observe_after=True,
                    reason="inspect_daily_tab",
                    follow_up_request=ObservationRequest.daily_quest_follow_up(),
                ))
            if current.screen_type != ScreenType.PNC_QUEST_DAILY:
                raise RuntimeError("The Daily tab postcondition was not observed.")
            summary["quest_rows"] = [_serialize_row(entry) for entry in current.list_entries]
            summary["daily_tab_verified"] = True
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route == ProbeRoute.BAG:
            step(_route_entry_action(selected_route, current, runtime))
            if current.screen_type != ScreenType.PNC_BAG:
                raise RuntimeError("Bag navigation did not produce the typed Bag screen.")
            summary["bag_rows"] = [_serialize_row(entry) for entry in current.list_entries]
            summary["bag_verified"] = True
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route == ProbeRoute.FIELDS:
            step(_route_entry_action(selected_route, current, runtime))
            if current.screen_type != ScreenType.PNC_LORD_INFO:
                raise RuntimeError("Fields route did not produce typed Lord Info evidence.")
            summary["lord_info"] = _identity_summary(current)
            summary["fields_identity"] = _fields_identity_summary(current)
            summary["fields_verified"] = True
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route == ProbeRoute.COORDINATES:
            reach(ScreenType.PNC_WORLD_MAP, runtime.flow_planner.ensure_world_map_ready)
            p1 = observe("coordinates_p1", request=ObservationRequest.world_map_movement_proof_follow_up())
            if p1.screen_type != ScreenType.PNC_WORLD_MAP or not p1.decision.coordinate_only:
                raise RuntimeError("Coordinate route did not produce a typed coordinate-only P1 proof.")
            coordinate = _coordinate_proof(p1, phase="P1")
            p2 = observe(
                "coordinates_p2_guarded",
                request=ObservationRequest.world_map_checkpoint_analysis(expected_coordinate=coordinate),
            )
            if (
                p2.screen_type != ScreenType.PNC_WORLD_MAP
                or p2.decision.coordinate_only
                or p2.decision.guard != GuardVerdict.CLEAR
            ):
                raise RuntimeError("Coordinate route lacked a fresh guarded P2 observation before unwind.")
            if _coordinate_proof(p2, phase="P2") != coordinate:
                raise RuntimeError("Coordinate route P2 proof changed the observed coordinate before unwind.")
            summary["coordinates"] = {
                "p1": summarize(p1),
                "p2": summarize(
                    p2,
                    ocr_context=None if current_capture is None else current_capture.ocr_context,
                ),
                "coordinate": coordinate,
            }
            current = p2
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route == ProbeRoute.MAIL_COMPOSE:
            mail_params = SendMailParams(
                recipient_kind=MailRecipientKind.PLAYER,
                player_name="read_only_probe_placeholder",
                profile_route=None,
                subject="unused_read_only_probe_subject",
                body="unused_read_only_probe_body",
            )
            reach(
                ScreenType.PNC_MAIL_HUB,
                runtime.flow_planner.open_mail_hub,
            )
            mail_source = current.screen_type
            if MailboxType.PLAYER in current.empty_mailboxes:
                route_status = "applicability_skip"
                summary["applicability"] = {
                    "predicate": "observed_empty_player_mailbox",
                    "screen": current.screen_type.name,
                }
                summary["mail_compose"] = {
                    "source_screen": mail_source.name,
                    "destination_screen": None,
                    "reason": "player_mailbox_empty",
                    "source_evidence": summarize(
                        current,
                        ocr_context=None if current_capture is None else current_capture.ocr_context,
                    ),
                }
                reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
            else:
                reach(
                    ScreenType.PNC_MAILBOX_LIST,
                    lambda observation: runtime.flow_planner.open_mailbox(observation, MailboxType.PLAYER),
                )
                if current.mailbox_type != MailboxType.PLAYER:
                    raise RuntimeError("Mail-compose route did not produce the typed PLAYER mailbox.")
                compose_source = current.screen_type
                compose_actions = runtime.flow_planner.open_mail_compose(current, mail_params)
                if len(compose_actions) != 1:
                    raise RuntimeError("Mail-compose route requires one canonical compose-entry action.")
                step(compose_actions[0])
                if current.screen_type != ScreenType.PNC_MAIL_COMPOSE_POPUP:
                    raise RuntimeError("Mail-compose route did not produce the typed compose popup.")
                summary["mail_compose"] = {
                    "source_screen": compose_source.name,
                    "hub_source_screen": mail_source.name,
                    "destination_screen": current.screen_type.name,
                    "entry_selector": (
                        compose_actions[0].selector_id.value
                        if isinstance(compose_actions[0], TapAction)
                        else None
                    ),
                    "close_selector": UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON.value,
                }
                close_actions = (TapAction(
                    selector_id=UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON,
                    observe_after=True,
                    reason="close_mail_compose_read_only_probe",
                    follow_up_request=ObservationRequest.mail_navigation_follow_up(
                        ScreenType.PNC_MAILBOX_LIST,
                        ScreenType.PNC_MAIL_HUB,
                    ),
                ),)
                step(close_actions[0])
                if current.screen_type not in {ScreenType.PNC_MAIL_HUB, ScreenType.PNC_MAILBOX_LIST}:
                    raise RuntimeError("Mail-compose close did not return to a typed mail navigation screen.")
                reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
            summary["mail_compose"]["return_screen"] = current.screen_type.name
        elif selected_route == ProbeRoute.WORLD_OVERVIEW:
            reach(ScreenType.PNC_WORLD_MAP, runtime.flow_planner.ensure_world_map_ready)
            source_coordinate = _coordinate_proof(current, phase="world-overview source")
            overview_navigator = WorldMapOverviewNavigator()
            open_actions = overview_navigator.plan_open(current)
            if len(open_actions) != 1:
                raise RuntimeError("World-overview route requires one canonical overview-entry action.")
            step(open_actions[0])
            if current.screen_type != ScreenType.PNC_WORLD_MAP_OVERVIEW:
                raise RuntimeError("World-overview route did not produce the typed overview screen.")
            overview_context = overview_navigator.parse_context(current)
            if overview_context.current_viewport_coordinate != source_coordinate:
                raise RuntimeError(
                    "World-overview context changed the world coordinate during the read-only proof."
                )
            close_actions = overview_navigator.plan_close_in_place(current)
            if len(close_actions) != 1:
                raise RuntimeError("World-overview route requires one canonical in-place close action.")
            step(close_actions[0])
            closed_coordinate = _coordinate_proof(current, phase="world-overview close")
            if current.screen_type != ScreenType.PNC_WORLD_MAP or closed_coordinate != source_coordinate:
                raise RuntimeError("World-overview close did not preserve the source world coordinate.")
            summary["world_overview"] = {
                "source_screen": ScreenType.PNC_WORLD_MAP.name,
                "destination_screen": ScreenType.PNC_WORLD_MAP_OVERVIEW.name,
                "source_coordinate": source_coordinate,
                "overview_coordinate": overview_context.current_viewport_coordinate,
                "closed_coordinate": closed_coordinate,
                "map_bounds": asdict(overview_context.map_bounds),
                "map_region_bounds": asdict(overview_context.map_region_bounds),
                "open_selector": open_actions[0].selector_id.value,
                "close_selector": close_actions[0].selector_id.value,
            }
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route in {ProbeRoute.LORD_INFO, ProbeRoute.VIP, ProbeRoute.CHAT, ProbeRoute.MAIL_HUB, ProbeRoute.GIFT_CENTER}:
            step(_route_entry_action(selected_route, current, runtime))
            if selected_route == ProbeRoute.LORD_INFO:
                expected = ScreenType.PNC_LORD_INFO
            elif selected_route == ProbeRoute.VIP:
                expected = ScreenType.PNC_VIP
                if current.screen_type == ScreenType.PNC_VIP_DAILY_RESET:
                    step(TapAction(
                        selector_id=UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
                        observe_after=True,
                        reason="close_vip_daily_reset",
                    ))
            elif selected_route == ProbeRoute.CHAT:
                expected = ScreenType.PNC_CHAT
            elif selected_route == ProbeRoute.MAIL_HUB:
                expected = ScreenType.PNC_MAIL_HUB
            else:
                expected = ScreenType.PNC_GIFT_CENTER
            if current.screen_type != expected:
                raise RuntimeError(f"{selected_route.value} route did not produce {expected.name}.")
            summary[f"{selected_route.value}_verified"] = True
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        elif selected_route == ProbeRoute.ALLIANCE:
            step(_route_entry_action(selected_route, current, runtime))
            if current.screen_type == ScreenType.PNC_ALLIANCE_JOIN:
                route_status = "applicability_skip"
                summary["applicability"] = {
                    "predicate": "observed_pnc_alliance_join",
                    "screen": current.screen_type.name,
                }
            elif current.screen_type == ScreenType.PNC_ALLIANCE_HOME:
                summary["alliance_verified"] = True
            else:
                raise RuntimeError("Alliance route reached an unavailable or unrecognized screen.")
            reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)

        final_identity_match = current.current_castle_match(active_castle)
        if final_identity_match.status.value == "mismatch":
            raise RuntimeError("Observed castle identity changed during the read-only proof.")
        summary["final_identity_verification"] = {
            "status": final_identity_match.status.value,
            "evidence_kind": (
                None
                if final_identity_match.evidence_kind is None
                else final_identity_match.evidence_kind.value
            ),
        }
        summary.update(
            status=route_status,
            actions=input_attempts(),
            route_steps=action_count,
            input_attempts=input_attempts(),
            final=summarize(
                current,
                ocr_context=None if current_capture is None else current_capture.ocr_context,
            ),
        )
    except Exception as error:
        summary.update(
            status="failed",
            actions=input_attempts(),
            route_steps=action_count,
            input_attempts=input_attempts(),
            error_type=type(error).__name__,
        )
        record({"event": "failure", "error_type": type(error).__name__})
        summary_path.write_text(json.dumps(summary, indent=2))
        raise RuntimeError(f"Read-only proof failed; inspect {summary_path}") from error
    finally:
        try:
            resources.close()
        finally:
            logging.disable(previous_logging_disable)
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary_path


def main() -> int:
    """Parse one opt-in live read-only route, with testing as the default target."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--account", default="testing")
    parser.add_argument("--output-dir", type=Path, default=Path(".local-data/artifacts/screen_recognition/live"))
    parser.add_argument("--route", choices=tuple(route.value for route in ProbeRoute), default=ProbeRoute.NAVIGATION.value)
    arguments = parser.parse_args()
    print(run_probe(arguments.config, arguments.account, arguments.output_dir, route=arguments.route))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
