"""One-tap, observed-completion navigation for independently recognized screens."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import time
from typing import Protocol

from pnc_automation.app.pnc.domain.action_requests import ActionRequest, TapAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
    primary_screen_type_for_home_city_object,
)
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class NavigationActuator(Protocol):
    """The existing device action executor, without its legacy retry orchestration."""

    def execute_action(self, action: ActionRequest, observation: Observation) -> bool: ...


@dataclass(frozen=True, slots=True)
class NavigationEdge:
    """A reviewed, non-spending screen transition; no caller-supplied coordinates."""

    source: ScreenType
    selector: UiElementId
    destinations: frozenset[ScreenType]

    def __post_init__(self) -> None:
        if not self.destinations or ScreenType.UNKNOWN in self.destinations or self.source == ScreenType.UNKNOWN:
            raise ValueError("Navigation edges require known source and destination screens.")
        if self.source in self.destinations:
            raise ValueError("A navigation edge must change screen identity.")


@dataclass(frozen=True, slots=True)
class NavigationPolicy:
    """Passive observation limits, independent of action count."""

    max_observations: int = 8
    max_seconds: float = 45.0
    poll_seconds: float = 0.25
    stable_observations: int = 2

    def __post_init__(self) -> None:
        if type(self.max_observations) is not int or type(self.stable_observations) is not int:
            raise ValueError("Observation budgets must be integers.")
        if not 2 <= self.stable_observations <= self.max_observations:
            raise ValueError("Navigation requires at least two stable observations within its budget.")
        if not 0 < self.max_seconds <= 120 or not 0 <= self.poll_seconds <= 2:
            raise ValueError("Invalid navigation time budget.")


@dataclass(slots=True)
class NavigationCore:
    """Own completion exactly once; never re-tap or recover an unknown interruption."""

    actuator: NavigationActuator
    observe: Callable[[str], Observation]
    edges: tuple[NavigationEdge, ...]
    policy: NavigationPolicy = field(default_factory=NavigationPolicy)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    record: Callable[[dict[str, object]], None] = lambda _: None
    _sequence: int = field(default=0, init=False)

    def transition(self, edge: NavigationEdge) -> Observation:
        """Reacquire the source, tap once, and require a stable observed destination."""
        if edge not in self.edges:
            raise ValueError("Transition is outside the reviewed navigation graph.")
        self._sequence += 1
        label = f"core_{self._sequence}"
        before = self.observe(f"{label}_source")
        if before.blocking_popup or before.screen_type != edge.source:
            raise RuntimeError("Navigation source changed or is interrupted; no action sent.")
        element = before.visible_elements.get(edge.selector)
        if element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Navigation control lacks current-frame visual evidence; no action sent.")
        self.record({"event": "pending", "source": edge.source.name, "selector": edge.selector.value,
                     "artifact": str(before.artifact_path)})
        action = TapAction(selector_id=edge.selector, reason="replacement_navigation")
        return self._execute_and_confirm(action, before, edge.destinations, label)

    def open_visible_building(
        self, target: HomeCityObjectId, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open one observed city object without atlas estimates or camera prediction."""
        destination = primary_screen_type_for_home_city_object(target)
        if destination is None or not any(edge.source == destination for edge in self.edges):
            raise ValueError("Building has no reviewed return route in this core.")
        self._sequence += 1
        label = f"core_{self._sequence}_building"
        before = observe_content(f"{label}_source")
        if before.screen_type != ScreenType.PNC_HOME_CITY or before.blocking_popup or before.spatial_surface is None:
            raise RuntimeError("Building navigation requires a freshly observed city surface.")
        candidates = [
            item for item in before.spatial_surface.objects
            if home_city_object_id_from_metadata(item.metadata) == target
        ]
        if len(candidates) != 1 or candidates[0].action_point is None:
            raise RuntimeError("Building is absent or ambiguous; no atlas tap or swipe was sent.")
        point = candidates[0].action_point
        if before.image_size is None:
            raise RuntimeError("Building observation has no image dimensions.")
        width, height = before.image_size
        if not width * 0.1 <= point[0] <= width * 0.9 or not height * 0.18 <= point[1] <= height * 0.82:
            raise RuntimeError("Observed building target overlaps the HUD; no tap sent.")
        self.record({"event": "pending_building", "target": target.value,
                     "artifact": str(before.artifact_path), "point": point})
        return self._execute_and_confirm(
            TapSpatialObjectAction(target_point=point, reason="replacement_observed_building"),
            before, frozenset({destination}), label,
        )

    def _execute_and_confirm(
        self, action: ActionRequest, before: Observation,
        destinations: frozenset[ScreenType], label: str,
    ) -> Observation:
        """Share the single completion owner for template controls and observed objects."""
        if not self.actuator.execute_action(action, before):
            raise RuntimeError("Navigation actuator did not execute the transition.")
        started = self.clock()
        stable = 0
        previous = ScreenType.UNKNOWN
        captured_at = before.captured_at
        for index in range(self.policy.max_observations):
            if self.clock() - started >= self.policy.max_seconds:
                break
            self.sleep(self.policy.poll_seconds)
            after = self.observe(f"{label}_after_{index}")
            self.record({"event": "observed", "screen": after.screen_type.name,
                         "artifact": str(after.artifact_path), "blocked": after.blocking_popup})
            if after.captured_at <= captured_at:
                raise RuntimeError("Navigation received a stale capture; completion is unproven.")
            captured_at = after.captured_at
            if self.clock() - started >= self.policy.max_seconds:
                break
            if after.blocking_popup:
                raise RuntimeError("Navigation interrupted; no recovery action or repeated tap sent.")
            if after.screen_type in destinations:
                stable = stable + 1 if after.screen_type == previous else 1
                if stable >= self.policy.stable_observations:
                    self.record({"event": "confirmed", "screen": after.screen_type.name})
                    return after
            else:
                stable = 0
                if after.screen_type not in {before.screen_type, ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
                    raise RuntimeError("Navigation reached an unexpected screen; inspect the recorded frame.")
            previous = after.screen_type
        raise RuntimeError("Navigation completion budget exhausted; the tap was not repeated.")

    def navigate(self, target: ScreenType, *, max_transitions: int = 8) -> Observation:
        """Replan through the reviewed graph after each confirmed transition."""
        if max_transitions < 1 or target == ScreenType.UNKNOWN:
            raise ValueError("Navigation needs a known target and positive transition budget.")
        current = self.observe("core_route_source")
        for _ in range(max_transitions):
            if current.blocking_popup or current.screen_type == ScreenType.UNKNOWN:
                raise RuntimeError("Cannot route from an unknown or interrupted screen.")
            if current.screen_type == target:
                return current
            edge = self._first_edge(current.screen_type, target)
            current = self.transition(edge)
        if current.screen_type != target:
            raise RuntimeError("Navigation route budget exhausted.")
        return current

    def _first_edge(self, source: ScreenType, target: ScreenType) -> NavigationEdge:
        queue = deque([(source, None)])
        visited = {source}
        while queue:
            screen, first = queue.popleft()
            for edge in self.edges:
                if edge.source != screen:
                    continue
                for destination in sorted(edge.destinations, key=lambda value: value.name):
                    if destination == target:
                        return first or edge
                    if destination not in visited:
                        visited.add(destination)
                        queue.append((destination, first or edge))
        raise RuntimeError(f"No reviewed route from {source.name} to {target.name}.")


def reviewed_navigation_edges() -> tuple[NavigationEdge, ...]:
    """Initial graph derived from September 2026 active-castle navigation evidence.

    Deliberately excludes purchases, claims, recruitment, castle selection, and
    camera coordinates. Legacy workflows remain outside this migration boundary.
    """
    screen = ScreenType
    selector = UiElementId
    quest = frozenset({screen.PNC_QUEST_MAIN, screen.PNC_QUEST_DAILY})
    edges = [
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_HOME_WORLD_SWITCH, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_HOME_NAV, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_QUEST, quest),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_BAG, frozenset({screen.PNC_BAG})),
        NavigationEdge(screen.PNC_QUEST_MAIN, selector.PNC_QUEST_TAB_DAILY, frozenset({screen.PNC_QUEST_DAILY})),
        NavigationEdge(screen.PNC_QUEST_DAILY, selector.PNC_QUEST_TAB_MAIN, frozenset({screen.PNC_QUEST_MAIN})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_MORE, frozenset({screen.PNC_MORE_MENU})),
        NavigationEdge(screen.PNC_MORE_MENU, selector.PNC_MORE_SETTINGS, frozenset({screen.PNC_SETTINGS})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_HOME_RESEARCH_BUTTON, frozenset({screen.PNC_INSTITUTE})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_COORDINATE_BAR, frozenset({screen.PNC_WORLD_COORDINATE_DIALOG})),
        NavigationEdge(screen.PNC_WORLD_COORDINATE_DIALOG, selector.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_EXPAND_BUTTON, frozenset({screen.PNC_WORLD_MAP_OVERVIEW})),
        NavigationEdge(screen.PNC_WORLD_MAP_OVERVIEW, selector.PNC_WORLD_OVERVIEW_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP_EXPANDED})),
        NavigationEdge(screen.PNC_WORLD_MAP_EXPANDED, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP})),
    ]
    for source in (
        *sorted(quest, key=lambda value: value.name), screen.PNC_BAG,
        screen.PNC_SETTINGS, screen.PNC_INSTITUTE, screen.PNC_GODDESS_STATUE,
        screen.PNC_WAREHOUSE, screen.PNC_HERO_HALL,
    ):
        edges.append(NavigationEdge(source, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})))
    return tuple(edges)
