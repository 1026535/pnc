"""One-tap, observed-completion navigation for independently recognized screens."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
import time
from typing import Literal, Protocol

from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    InputTextAction,
    KeyEventAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
    primary_screen_type_for_home_city_object,
)
from pnc_automation.app.pnc.domain.castle_roster_scan import castle_roster_window_signature
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    DetectedSpatialObject,
    ListEntryKind,
    Observation,
    SpatialSurfaceType,
    VisibleElementSourceKind,
    RowRecognitionStatus,
    castle_entry_matches,
    castle_entry_identity_matches,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.chat import (
    ChatChannel,
    chat_channel_selector_id,
    count_matching_player_chat_entries,
    parse_chat_message_params,
)
from pnc_automation.app.pnc.domain.mail import (
    MailboxAvailability,
    MailboxType,
    mailbox_category_selector_id,
    mail_thread_row_key,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    home_city_scan_step_budget,
    home_city_scan_steps,
)

_MAX_CASTLE_ROSTER_SWIPES = 6


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
    observe_ready: Callable[[str], Observation] | None = None
    _sequence: int = field(default=0, init=False)

    def transition(self, edge: NavigationEdge) -> Observation:
        """Reacquire the source, tap once, and require a stable observed destination."""
        if edge not in self.edges:
            raise ValueError("Transition is outside the reviewed navigation graph.")
        self._sequence += 1
        label = f"core_{self._sequence}"
        before = self._observe_source(f"{label}_source")
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
        destination = _require_reviewed_building_route(target=target, edges=self.edges)
        self._sequence += 1
        label = f"core_{self._sequence}_building"
        before = observe_content(f"{label}_source")
        resolved = _resolve_observed_building_target(before, target=target)
        if resolved is None:
            raise RuntimeError("Building is absent or ambiguous; no further gesture or building tap was sent.")
        _observed_object, point = resolved
        if not _is_hud_safe_building_point(point, image_size=before.image_size):
            raise RuntimeError("Observed building target overlaps the HUD; no tap sent.")
        self.record({"event": "pending_building", "target": target.value,
                     "artifact": str(before.artifact_path), "point": point})
        return self._execute_and_confirm(
            TapSpatialObjectAction(target_point=point, reason="replacement_observed_building"),
            before, frozenset({destination}), label,
        )

    def open_building(
        self, target: HomeCityObjectId, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Use a reviewed in-game focus route, then require an observed object.

        The idle Research Queue Go control focuses Institute in the city. It
        does not prove the building opened or authorize a predicted camera tap.
        Other supported buildings use the bounded observed Home-city scan when
        they are not visible in the current frame.
        """
        _require_reviewed_building_route(target=target, edges=self.edges)
        if target == HomeCityObjectId.INSTITUTE:
            self.navigate(ScreenType.PNC_RESEARCH_QUEUE)
            focus = next((
                edge for edge in self.edges
                if edge.source == ScreenType.PNC_RESEARCH_QUEUE
                and edge.selector == UiElementId.PNC_RESEARCH_QUEUE_GO
            ), None)
            if focus is None:
                raise ValueError("Institute focus route is missing from the reviewed graph.")
            self.transition(focus)
            return self.open_visible_building(target, observe_content=observe_content)

        self._sequence += 1
        scan_label = f"core_{self._sequence}_building_scan_source"
        current = observe_content(scan_label)
        _require_home_city_surface(current)
        return self._open_building_after_home_scan(
            target=target,
            current=current,
            observe_content=observe_content,
        )

    def _open_building_after_home_scan(
        self,
        *,
        target: HomeCityObjectId,
        current: Observation,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Searches the measured Home scan sequence, then reacquires the target before tapping."""

        previous_captured_at = current.captured_at
        scan_steps = home_city_scan_steps()
        scan_budget = home_city_scan_step_budget()
        for step_index in range(scan_budget + 1):
            if step_index > 0 and current.captured_at <= previous_captured_at:
                raise RuntimeError("Home-city scan received a stale capture; no further gesture was sent.")
            resolved = _resolve_observed_building_target(current, target=target)
            if resolved is not None and _is_hud_safe_building_point(
                resolved[1], image_size=current.image_size
            ):
                return self._open_reacquired_building(
                    target=target,
                    source=current,
                    observe_content=observe_content,
                )

            if step_index == scan_budget:
                break
            action = scan_steps[step_index % len(scan_steps)]
            self.record(
                {
                    "event": "pending_building_scan",
                    "target": target.value,
                    "step": step_index + 1,
                    "action": action.reason,
                    "artifact": None if current.artifact_path is None else str(current.artifact_path),
                }
            )
            after = self._execute_content_and_confirm(
                action,
                current,
                frozenset({ScreenType.PNC_HOME_CITY}),
                f"core_{self._sequence}_building_scan_{step_index + 1}",
                _observe_home_city_scan_content(observe_content),
                completion_predicate=lambda observation: observation.spatial_surface is not None,
            )
            previous_captured_at = current.captured_at
            current = after
        raise RuntimeError("Home-city scan exhausted its canonical gesture budget without finding a safe observed building target.")

    def _open_reacquired_building(
        self,
        *,
        target: HomeCityObjectId,
        source: Observation,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Reacquires one safe target frame before delegating the single visible-building tap."""

        def observe_reacquired(label: str) -> Observation:
            observation = observe_content(label)
            if observation.captured_at <= source.captured_at:
                raise RuntimeError("Building target reacquisition received a stale capture; no further tap was sent.")
            return observation

        return self.open_visible_building(target, observe_content=observe_reacquired)

    def open_mailbox(
        self, mailbox: MailboxType, *, observe_content: Callable[[str], Observation],
    ) -> MailboxAvailability:
        """Open one typed mail category after proving its fresh hub availability."""
        if not isinstance(mailbox, MailboxType):
            raise ValueError("Mailbox navigation requires a MailboxType value.")
        self._sequence += 1
        label = f"core_{self._sequence}_mailbox"
        hub = observe_content(f"{label}_hub")
        if hub.blocking_popup or hub.screen_type != ScreenType.PNC_MAIL_HUB:
            raise RuntimeError("Mailbox navigation requires a freshly observed, unblocked mail hub.")
        candidates = tuple(
            entry
            for entry in hub.entries(ListEntryKind.MAILBOX_CATEGORY)
            if entry.metadata.get("mailbox_type") == mailbox.value
        )
        if len(candidates) != 1:
            raise RuntimeError("Requested mailbox category is missing or ambiguous; no tap sent.")
        available = candidates[0].metadata.get("available")
        if type(available) is not bool:
            raise RuntimeError("Requested mailbox category has no typed availability disposition; no tap sent.")
        if not available:
            self.record({"event": "mailbox_unavailable", "mailbox": mailbox.value})
            return MailboxAvailability.UNAVAILABLE
        selector = mailbox_category_selector_id(mailbox)
        edge = next(
            (
                candidate
                for candidate in self.edges
                if candidate.source == ScreenType.PNC_MAIL_HUB and candidate.selector == selector
            ),
            None,
        )
        if edge is None:
            raise ValueError("Requested mailbox category is missing from the reviewed navigation graph.")
        self.transition(edge)
        return MailboxAvailability.AVAILABLE

    def open_mail_thread(
        self, row_key: str, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Open exactly one freshly observed mailbox thread row by its canonical identity."""
        if not isinstance(row_key, str) or row_key.strip() == "":
            raise ValueError("Mail thread navigation requires a non-empty canonical row key.")
        self._sequence += 1
        label = f"core_{self._sequence}_mail_thread"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_MAILBOX_LIST:
            raise RuntimeError("Mail thread navigation requires a freshly observed, unblocked mailbox list.")
        candidates = tuple(
            entry
            for entry in before.entries(ListEntryKind.MAIL_THREAD)
            if mail_thread_row_key(entry) == row_key
        )
        if len(candidates) != 1 or candidates[0].action_point is None:
            raise RuntimeError("Mail thread row is absent, ambiguous, or lacks an observed action point; no tap sent.")
        point = candidates[0].action_point
        self.record({"event": "pending_mail_thread", "artifact": str(before.artifact_path), "row_key": row_key})
        return self._execute_and_confirm(
            TapPointAction(x=point[0], y=point[1], reason="replacement_open_mail_thread"),
            before,
            frozenset({ScreenType.PNC_MAIL_THREAD}),
            label,
        )

    def select_chat_channel(
        self, channel: ChatChannel, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one observed chat tab and require fresh frames confirming its channel."""

        if not isinstance(channel, ChatChannel):
            raise ValueError("Chat channel selection requires a ChatChannel value.")
        self._sequence += 1
        label = f"core_{self._sequence}_chat_channel"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_CHAT:
            raise RuntimeError("Chat channel selection requires a freshly observed, unblocked Chat screen.")
        if before.active_chat_channel == channel:
            return before
        selector = chat_channel_selector_id(channel)
        element = before.visible_elements.get(selector)
        if element is None or element.source_kind != VisibleElementSourceKind.TEMPLATE:
            raise RuntimeError("Chat channel control lacks current-frame visual evidence; no action sent.")
        self.record({"event": "pending_chat_channel", "channel": channel.value,
                     "selector": selector.value, "artifact": str(before.artifact_path)})
        return self._execute_content_and_confirm(
            SelectChatChannelAction(channel=channel, reason="replacement_select_chat_channel"),
            before,
            frozenset({ScreenType.PNC_CHAT}),
            label,
            observe_content,
            completion_predicate=lambda observation: observation.active_chat_channel == channel,
        )

    def send_chat_message(
        self,
        channel: ChatChannel,
        message: str,
        active_castle: CastleIdentity,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Send one validated chat message through fresh observed controls."""

        if (
            not isinstance(channel, ChatChannel)
            or channel not in {ChatChannel.WORLD, ChatChannel.ALLIANCE}
        ):
            raise ValueError("Chat sending requires a supported ChatChannel value.")
        params = parse_chat_message_params(
            {"message": message},
            task_label="send_chat_message",
        )
        if not isinstance(active_castle, CastleIdentity):
            raise ValueError("Chat sending requires a CastleIdentity.")
        self._sequence += 1
        label = f"core_{self._sequence}_chat_send"
        before = observe_content(f"{label}_source")
        _require_chat_send_source(before)
        if before.active_chat_channel == channel:
            requested = before
        else:
            requested = self.select_chat_channel(
                channel,
                observe_content=_guard_chat_empty_selection_observer(observe_content),
            )
            _require_chat_send_source(requested, channel=channel)
        baseline = count_matching_player_chat_entries(
            requested.entries(ListEntryKind.CHAT_MESSAGE),
            message=params.message,
            castle=active_castle,
        )
        send_observe_content = _guard_chat_send_observer(observe_content, channel=channel)
        if _chat_focused_empty_ready(requested, channel=channel):
            focused = requested
        else:
            input_element = requested.get(UiElementId.PNC_CHAT_INPUT_FIELD)
            if input_element is None or input_element.source_kind != VisibleElementSourceKind.TEMPLATE:
                raise RuntimeError(
                    "Chat sending requires current-frame template input and focused-empty controls; no action sent."
                )
            focused = self._execute_content_and_confirm(
                TapAction(
                    selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                    reason="replacement_focus_chat_input",
                ),
                requested,
                frozenset({ScreenType.PNC_CHAT}),
                f"{label}_focus",
                send_observe_content,
                completion_predicate=lambda observation: _chat_focused_empty_ready(
                    observation, channel=channel
                ),
            )
        typed = self._execute_content_and_confirm(
            InputTextAction(
                text=params.message,
                selector_id=None,
                replace_existing=False,
                reason="replacement_type_chat_message",
            ),
            focused,
            frozenset({ScreenType.PNC_CHAT}),
            f"{label}_type",
            send_observe_content,
            completion_predicate=lambda observation: _chat_typed_message_ready(
                observation, params.message, channel=channel
            ),
        )
        return self._execute_content_and_confirm(
            TapAction(
                selector_id=UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON,
                reason="replacement_submit_chat_message",
            ),
            typed,
            frozenset({ScreenType.PNC_CHAT}),
            f"{label}_submit",
            send_observe_content,
            completion_predicate=lambda observation: _chat_receipt_ready(
                observation,
                channel=channel,
                message=params.message,
                active_castle=active_castle,
                baseline=baseline,
            ),
        )

    def scroll_mailbox(
        self, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Scroll one freshly observed mailbox list and require a fresh list frame."""
        self._sequence += 1
        label = f"core_{self._sequence}_mailbox_scroll"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_MAILBOX_LIST:
            raise RuntimeError("Mailbox scrolling requires a freshly observed, unblocked mailbox list.")
        return self._execute_content_and_confirm(
            SwipeAction(
                direction="up",
                distance_ratio=0.58,
                duration_ms=450,
                reason="replacement_scroll_mailbox",
            ),
            before,
            frozenset({ScreenType.PNC_MAILBOX_LIST}),
            label,
            observe_content,
        )

    def open_research_node(
        self, title: str, category: ResearchCategory, *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one fresh Development node and prove its normal detail control."""

        if category != ResearchCategory.DEVELOPMENT or not isinstance(title, str) or not title.strip():
            raise ValueError("Research selection requires one named Development node.")
        self._sequence += 1
        label = f"core_{self._sequence}_research_node"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_RESEARCH_TREE or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or not any(evidence.reason == "visual_anchor:research_tree_development" for evidence in source.decision.evidence)
        ):
            raise RuntimeError("Research node selection requires the proved Development grid.")
        matches = tuple(
            entry for entry in source.entries(ListEntryKind.RESEARCH)
            if entry.title_text == title and entry.metadata.get("category") == category.value
        )
        if (
            len(matches) != 1 or matches[0].row_status != RowRecognitionStatus.COMPLETE
            or matches[0].metadata.get("research_progress_state") != "incomplete"
            or matches[0].metadata.get("research_access_state") != "available"
            or matches[0].action_point is None or matches[0].action_bounds is None
            or not matches[0].action_bounds.contains_point(matches[0].action_point)
            or not matches[0].bounds.contains_bounds(matches[0].action_bounds)
        ):
            raise RuntimeError("Research node is missing, changed or ambiguous; no tap sent.")
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.RESEARCH, title_text=title,
                metadata_key="category", metadata_value=category.value,
                use_action_point=True, reason="open_research_candidate",
            ),
            source, frozenset({ScreenType.PNC_RESEARCH_TREE}), label, observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and any(evidence.reason == "visual_anchor:research_tree_node_detail" for evidence in frame.decision.evidence)
                and _template_control(frame, UiElementId.PNC_RESEARCH_START_BUTTON)
            ),
        )

    def scroll_research_tree(
        self, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Scroll one proved Development grid and retain fresh content evidence."""

        self._sequence += 1
        label = f"core_{self._sequence}_research_scroll"
        before = observe_content(f"{label}_source")
        if (
            before.screen_type != ScreenType.PNC_RESEARCH_TREE
            or before.blocking_popup
            or before.decision.guard != GuardVerdict.CLEAR
            or not any(
                evidence.reason == "visual_anchor:research_tree_development"
                for evidence in before.decision.evidence
            )
        ):
            raise RuntimeError("Research scrolling requires the proved Development grid.")
        return self._execute_content_and_confirm(
            SwipeAction(
                reason="replacement_scan_development_research",
                start_x_ratio=0.5,
                start_y_ratio=0.82,
                end_x_ratio=0.5,
                end_y_ratio=0.32,
                duration_ms=450,
            ),
            before,
            frozenset({ScreenType.PNC_RESEARCH_TREE}),
            label,
            observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and any(
                    evidence.reason == "visual_anchor:research_tree_development"
                    for evidence in frame.decision.evidence
                )
            ),
        )

    def close_research_detail(
        self, *, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Close one idle Development detail and prove the restored grid."""

        self._sequence += 1
        label = f"core_{self._sequence}_research_detail_back"
        source = observe_content(f"{label}_source")
        if (
            source.screen_type != ScreenType.PNC_RESEARCH_TREE
            or source.blocking_popup
            or source.decision.guard != GuardVerdict.CLEAR
            or not any(
                evidence.reason == "visual_anchor:research_tree_node_detail"
                for evidence in source.decision.evidence
            )
            or not _template_control(source, UiElementId.PNC_RESEARCH_START_BUTTON)
        ):
            raise RuntimeError("Research detail Back requires one proved idle detail.")
        return self._execute_content_and_confirm(
            KeyEventAction(
                key_code="KEYCODE_BACK",
                reason="close_unfunded_research_detail",
            ),
            source,
            frozenset({ScreenType.PNC_RESEARCH_TREE}),
            label,
            observe_content,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and any(
                    evidence.reason == "visual_anchor:research_tree_development"
                    for evidence in frame.decision.evidence
                )
            ),
        )

    def scroll_daily_quest(
        self, *, adjusted: bool, observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Perform one existing Daily-list gesture and prove fresh Daily completion."""

        if type(adjusted) is not bool:
            raise ValueError("Daily scrolling requires a boolean adjusted flag.")
        self._sequence += 1
        label = f"core_{self._sequence}_daily_scroll"
        before = observe_content(f"{label}_source")
        if before.screen_type != ScreenType.PNC_QUEST_DAILY or before.blocking_popup:
            raise RuntimeError("Daily scrolling requires an unblocked Daily screen.")
        return self._execute_content_and_confirm(
            SwipeAction(
                reason="daily_scroll_adjusted" if adjusted else "daily_scroll",
                start_x_ratio=0.5, start_y_ratio=0.82 if adjusted else 0.80,
                end_x_ratio=0.5, end_y_ratio=0.49 if adjusted else 0.44,
                duration_ms=420 if adjusted else 350,
            ),
            before, frozenset({ScreenType.PNC_QUEST_DAILY}), label, observe_content,
        )

    def scroll_resource_inventory(
        self, *, upward: bool, adjusted: bool, fine: bool = False,
        observe_content: Callable[[str], Observation],
        confirm_scroll: Callable[[], Observation],
    ) -> Observation:
        """Swipe the selected Resource list once; its scanner owns stable row completion."""

        if any(type(flag) is not bool for flag in (upward, adjusted, fine)):
            raise ValueError("Resource scrolling requires boolean gesture flags.")
        self._sequence += 1
        before = observe_content(f"core_{self._sequence}_resource_scroll_source")
        require_resource_inventory_surface(before)
        low = 0.64 if fine else (0.78 if adjusted else 0.85)
        high = 0.46 if fine else (0.42 if adjusted else 0.32)
        if not self.actuator.execute_action(
            SwipeAction(
                reason=("resource_inventory_focus_scroll" if fine else
                        "resource_inventory_scroll_adjusted" if adjusted else "resource_inventory_scroll"),
                start_x_ratio=0.5, end_x_ratio=0.5,
                start_y_ratio=high if upward else low,
                end_y_ratio=low if upward else high,
                duration_ms=420 if adjusted else 350,
            ), before,
        ):
            raise RuntimeError("Navigation actuator did not execute the Resource scroll.")
        started = self.clock()
        after = confirm_scroll()
        if self.clock() - started >= self.policy.max_seconds:
            raise RuntimeError("Resource scroll completion budget exhausted; the gesture was not repeated.")
        require_resource_inventory_surface(after)
        if after.captured_at <= before.captured_at:
            raise RuntimeError("Resource scroll completion received a stale capture.")
        return after

    def scroll_castle_roster(
        self,
        direction: Literal["up", "down"],
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Scroll the Manage Characters roster once without selecting a row."""

        if direction not in {"up", "down"}:
            raise ValueError("Castle-roster scrolling requires direction 'up' or 'down'.")
        self._sequence += 1
        label = f"core_{self._sequence}_castle_roster_scroll"
        before = observe_content(f"{label}_source")
        if before.blocking_popup or before.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise RuntimeError(
                "Castle-roster scrolling requires a freshly observed, unblocked Manage Characters screen."
            )
        return self._execute_content_and_confirm(
            SwipeAction(
                direction=direction,
                distance_ratio=0.58,
                duration_ms=450,
                reason="replacement_scan_active_castle",
            ),
            before,
            frozenset({ScreenType.PNC_CASTLE_SELECTION}),
            label,
            observe_content,
        )

    def select_castle(
        self,
        target: CastleIdentity,
        *,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Select one exact observed Manage Characters row with bounded live scanning."""

        if not isinstance(target, CastleIdentity):
            raise ValueError("Castle selection requires a CastleIdentity target.")
        self._sequence += 1
        label = f"core_{self._sequence}_castle_select"
        current = observe_content(f"{label}_source")
        for direction in ("down", "up"):
            seen_windows: set[tuple[tuple[str, str], ...]] = set()
            for step_index in range(_MAX_CASTLE_ROSTER_SWIPES + 1):
                self._require_castle_selection_source(current)
                signature = castle_roster_window_signature(current)
                if signature in seen_windows:
                    break
                seen_windows.add(signature)
                candidates = _matching_castle_entries(current, target)
                if len(candidates) > 1:
                    raise RuntimeError(
                        "Requested castle row is ambiguous; no further gesture or building tap was sent."
                    )
                if candidates:
                    if not castle_entry_matches(candidates[0], target):
                        raise RuntimeError(
                            "Requested castle row has a mismatched level; no further gesture or building tap was sent."
                        )
                    if candidates[0].selected:
                        self.record(
                            {
                                "event": "castle_already_selected",
                                "target": target.castle_name,
                                "kingdom": target.kingdom,
                                "artifact": None if current.artifact_path is None else str(current.artifact_path),
                            }
                        )
                        return current
                    return self._select_visible_castle(
                        target=target,
                        source=current,
                        label=label,
                        observe_content=observe_content,
                    )
                if step_index == _MAX_CASTLE_ROSTER_SWIPES:
                    break
                current = self.scroll_castle_roster(direction, observe_content=observe_content)
        raise RuntimeError(
            "Requested castle row was not found within the bounded roster scan; no further gesture or building tap was sent."
        )

    @staticmethod
    def _require_castle_selection_source(observation: Observation) -> None:
        """Reject an interrupted or unexpected roster frame before scanning it."""

        if observation.blocking_popup or observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise RuntimeError(
                "Castle selection requires a freshly observed, unblocked Manage Characters screen."
            )

    def _select_visible_castle(
        self,
        *,
        target: CastleIdentity,
        source: Observation,
        label: str,
        observe_content: Callable[[str], Observation],
    ) -> Observation:
        """Reacquire one target row, then tap its current observed action point once."""

        reacquired = observe_content(f"{label}_reacquire")
        if reacquired.captured_at <= source.captured_at:
            raise RuntimeError("Castle selection reacquired a stale roster frame; no castle selection tap was sent.")
        self._require_castle_selection_source(reacquired)
        candidates = _matching_castle_entries(reacquired, target)
        if len(candidates) != 1:
            raise RuntimeError(
                "Requested castle row changed or became ambiguous; no castle selection tap was sent."
            )
        entry = candidates[0]
        if not castle_entry_matches(entry, target):
            raise RuntimeError(
                "Requested castle row changed to a mismatched level; no castle selection tap was sent."
            )
        if entry.selected:
            self.record(
                {
                    "event": "castle_already_selected",
                    "target": target.castle_name,
                    "kingdom": target.kingdom,
                    "artifact": None if reacquired.artifact_path is None else str(reacquired.artifact_path),
                }
            )
            return reacquired
        if entry.action_point is None:
            raise RuntimeError(
                "Requested castle row has no observed action point; no castle selection tap was sent."
            )
        if (
            not isinstance(entry.action_point, tuple)
            or len(entry.action_point) != 2
            or any(type(value) is not int for value in entry.action_point)
            or not entry.bounds.contains_point(entry.action_point)
        ):
            raise RuntimeError(
                "Requested castle row has a malformed action point; no castle selection tap was sent."
            )
        self.record(
            {
                "event": "pending_castle_select",
                "target": target.castle_name,
                "kingdom": target.kingdom,
                "artifact": None if reacquired.artifact_path is None else str(reacquired.artifact_path),
            }
        )
        return self._execute_content_and_confirm(
            TapListEntryAction(
                entry_kind=ListEntryKind.CASTLE,
                title_text=entry.title_text,
                metadata_key="kingdom",
                metadata_value=target.kingdom,
                selected=False,
                use_action_point=True,
                reason="replacement_select_castle",
            ),
            reacquired,
            frozenset({ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY}),
            label,
            observe_content,
            completion_predicate=lambda observation: (
                observation.screen_type == ScreenType.PNC_HOME_CITY
                or _selected_castle_observed(observation, target=target)
            ),
        )

    def _execute_content_and_confirm(
        self,
        action: ActionRequest,
        before: Observation,
        destinations: frozenset[ScreenType],
        label: str,
        observe_content: Callable[[str], Observation],
        *,
        completion_predicate: Callable[[Observation], bool] | None = None,
    ) -> Observation:
        """Execute one bounded content action without replaying a failed gesture."""
        if not self.actuator.execute_action(action, before):
            raise RuntimeError("Navigation actuator did not execute the content action.")
        return self.confirm_content_after_action(
            before, destinations, label, observe_content,
            completion_predicate=completion_predicate,
        )

    def confirm_content_after_action(
        self, before: Observation, destinations: frozenset[ScreenType], label: str,
        observe_content: Callable[[str], Observation], *,
        completion_predicate: Callable[[Observation], bool] | None = None,
    ) -> Observation:
        """Passively confirm one already dispatched action without issuing another."""

        started = self.clock()
        stable = 0
        previous = ScreenType.UNKNOWN
        previous_completed = False
        captured_at = before.captured_at
        for index in range(self.policy.max_observations):
            if self.clock() - started >= self.policy.max_seconds:
                break
            self.sleep(self.policy.poll_seconds)
            after = observe_content(f"{label}_after_{index}")
            self.record({"event": "observed", "screen": after.screen_type.name,
                         "artifact": str(after.artifact_path), "blocked": after.blocking_popup})
            if after.captured_at <= captured_at:
                raise RuntimeError("Content action received a stale capture; completion is unproven.")
            captured_at = after.captured_at
            if self.clock() - started >= self.policy.max_seconds:
                break
            if after.blocking_popup:
                raise RuntimeError("Content action was interrupted; no recovery action or repeated gesture sent.")
            completed = after.screen_type in destinations and (
                completion_predicate is None or completion_predicate(after)
            )
            if completed:
                stable = stable + 1 if previous_completed and after.screen_type == previous else 1
                if stable >= self.policy.stable_observations:
                    self.record({"event": "confirmed", "screen": after.screen_type.name})
                    return after
            else:
                stable = 0
                if after.screen_type not in {before.screen_type, ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
                    raise RuntimeError("Content action reached an unexpected screen; inspect the recorded frame.")
            previous = after.screen_type
            previous_completed = completed
        raise RuntimeError("Content action completion budget exhausted; the gesture was not repeated.")

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
        current = self._observe_source("core_route_source")
        for _ in range(max_transitions):
            if current.blocking_popup or current.screen_type == ScreenType.UNKNOWN:
                raise RuntimeError("Cannot route from an unknown or interrupted screen.")
            if current.screen_type == target:
                return current
            if _is_research_detail_route_source(current):
                current = self._close_research_detail_for_route(current)
                continue
            edge = self._first_edge(current.screen_type, target)
            current = self.transition(edge)
        if current.screen_type != target:
            raise RuntimeError("Navigation route budget exhausted.")
        return current

    def _close_research_detail_for_route(self, source: Observation) -> Observation:
        """Normalize a proved detail to its grid before graph-based routing."""

        self._sequence += 1
        label = f"core_{self._sequence}_research_detail_route_back"
        return self._execute_content_and_confirm(
            KeyEventAction(
                key_code="KEYCODE_BACK",
                reason="close_research_detail_for_route",
            ),
            source,
            frozenset({ScreenType.PNC_RESEARCH_TREE}),
            label,
            self._observe_source,
            completion_predicate=lambda frame: (
                frame.decision.guard == GuardVerdict.CLEAR
                and any(
                    evidence.reason == "visual_anchor:research_tree_development"
                    for evidence in frame.decision.evidence
                )
            ),
        )

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

    def _observe_source(self, label: str) -> Observation:
        """Capture a reviewed edge source through the optional loading-ready boundary."""

        if self.observe_ready is not None:
            return self.observe_ready(label)
        return self.observe(label)


def require_resource_inventory_surface(observation: Observation) -> None:
    """Require B's selected Resource anchor before inventory observation or a list action."""

    if (
        observation.screen_type != ScreenType.PNC_BAG
        or observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
        or not _template_control(observation, UiElementId.PNC_BAG_SUBTAB_RESOURCE)
    ):
        raise RuntimeError("Resource inventory requires a guarded Bag with the selected Resource tab.")


def _require_reviewed_building_route(
    *,
    target: HomeCityObjectId,
    edges: tuple[NavigationEdge, ...],
) -> ScreenType:
    """Returns a modeled building endpoint after proving its reviewed return edge exists."""

    destination = primary_screen_type_for_home_city_object(target)
    if destination is None or not any(edge.source == destination for edge in edges):
        raise ValueError("Building has no reviewed return route in this core.")
    return destination


def _require_home_city_surface(observation: Observation) -> None:
    """Requires one fresh, unblocked Home observation with the canonical spatial surface."""

    if (
        observation.screen_type != ScreenType.PNC_HOME_CITY
        or observation.blocking_popup
        or observation.spatial_surface is None
        or observation.spatial_surface.surface_type != SpatialSurfaceType.HOME_CITY_SURFACE
    ):
        raise RuntimeError("Building navigation requires a freshly observed, unblocked city surface.")


def _selected_castle_observed(observation: Observation, *, target: CastleIdentity) -> bool:
    """Returns whether exactly one observed target row is marked selected."""

    if observation.blocking_popup or observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
        return False
    matches = _matching_castle_entries(observation, target)
    return len(matches) == 1 and matches[0].selected and castle_entry_matches(matches[0], target)


def _matching_castle_entries(
    observation: Observation,
    target: CastleIdentity,
) -> tuple[DetectedListEntry, ...]:
    """Returns all observed castle rows with the exact kingdom/name identity."""

    return tuple(
        entry
        for entry in observation.entries(ListEntryKind.CASTLE)
        if entry.title_text is not None and castle_entry_identity_matches(entry, target)
    )


def _resolve_observed_building_target(
    observation: Observation,
    *,
    target: HomeCityObjectId,
) -> tuple[DetectedSpatialObject, tuple[int, int]] | None:
    """Finds one exact observed target and validates its point and image dimensions."""

    _require_home_city_surface(observation)
    candidates = [
        item
        for item in observation.spatial_surface.objects
        if home_city_object_id_from_metadata(item.metadata) == target
    ]
    if len(candidates) > 1:
        raise RuntimeError("Building is absent or ambiguous; no further gesture or building tap was sent.")
    image_size = _require_building_image_size(observation)
    if not candidates:
        return None
    candidate = candidates[0]
    if candidate.action_point is None:
        raise RuntimeError("Observed building target has no action point; no further gesture or building tap was sent.")
    if (
        not isinstance(candidate.action_point, tuple)
        or len(candidate.action_point) != 2
        or any(type(value) is not int for value in candidate.action_point)
        or not (0 <= candidate.action_point[0] < image_size[0])
        or not (0 <= candidate.action_point[1] < image_size[1])
    ):
        raise RuntimeError(
            "Observed building target has a malformed or out-of-image action point; "
            "no further gesture or building tap was sent."
        )
    return candidate, candidate.action_point


def _require_building_image_size(observation: Observation) -> tuple[int, int]:
    """Returns positive screenshot dimensions required for observed building validation."""

    image_size = observation.image_size
    if (
        not isinstance(image_size, tuple)
        or len(image_size) != 2
        or any(type(value) is not int or value <= 0 for value in image_size)
    ):
        raise RuntimeError(
            "Building observation has no valid image dimensions; "
            "no further gesture or building tap was sent."
        )
    return image_size


def _is_hud_safe_building_point(
    point: tuple[int, int],
    *,
    image_size: tuple[int, int] | None,
) -> bool:
    """Returns whether one observed point stays inside the shared HUD-safe tap band."""

    width, height = image_size if image_size is not None else (0, 0)
    if width <= 0 or height <= 0:
        raise RuntimeError("Building observation has no valid image dimensions; no building tap was sent.")
    return (
        width * 0.18 <= point[0] <= width * 0.82
        and height * 0.18 <= point[1] <= height * 0.58
    )


def _observe_home_city_scan_content(
    observe_content: Callable[[str], Observation],
) -> Callable[[str], Observation]:
    """Wraps scan follow-up capture with strict Home surface validation."""

    def observe(label: str) -> Observation:
        observation = observe_content(label)
        _require_home_city_surface(observation)
        return observation

    return observe


def _template_control(observation: Observation, selector_id: UiElementId) -> bool:
    """Return whether one selector was matched by a current-frame template."""

    element = observation.get(selector_id)
    return element is not None and element.source_kind == VisibleElementSourceKind.TEMPLATE


def _is_research_detail_route_source(observation: Observation) -> bool:
    """Return whether a proved idle or active detail may be closed with Back."""

    if (
        observation.screen_type != ScreenType.PNC_RESEARCH_TREE
        or observation.blocking_popup
        or observation.decision.guard != GuardVerdict.CLEAR
    ):
        return False
    reasons = {evidence.reason for evidence in observation.decision.evidence}
    if "visual_anchor:research_tree_node_detail_active" in reasons:
        return True
    return (
        "visual_anchor:research_tree_node_detail" in reasons
        and _template_control(observation, UiElementId.PNC_RESEARCH_START_BUTTON)
    )


def _require_chat_send_source(
    observation: Observation,
    *,
    channel: ChatChannel | None = None,
) -> None:
    """Require an unblocked Chat frame with explicit empty-draft template evidence."""

    supported_active_channel = observation.active_chat_channel in {
        ChatChannel.WORLD,
        ChatChannel.ALLIANCE,
    }
    if (
        observation.screen_type != ScreenType.PNC_CHAT
        or observation.blocking_popup
        or not supported_active_channel
        or (channel is not None and observation.active_chat_channel != channel)
    ):
        channel_text = "" if channel is None else f" {channel.value}"
        raise RuntimeError(
            f"Chat sending requires a fresh, unblocked{channel_text} Chat frame; no action sent."
        )
    if observation.chat_draft_empty is not True:
        raise RuntimeError("Chat draft is not explicitly empty; no focus or text action sent.")
    if not (
        _template_control(observation, UiElementId.PNC_CHAT_INPUT_FIELD)
        or _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT)
    ):
        raise RuntimeError("Chat draft emptiness lacks positive template evidence; no action sent.")


def _guard_chat_send_observer(
    observe_content: Callable[[str], Observation],
    *,
    channel: ChatChannel,
) -> Callable[[str], Observation]:
    """Reject interruption and channel drift before send completion can authorize another action."""

    def observe(label: str) -> Observation:
        observation = observe_content(label)
        if observation.screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            raise RuntimeError("Chat send observed an unknown or loading frame; completion is unproven.")
        if observation.blocking_popup:
            raise RuntimeError("Chat send was interrupted by a blocking popup; no repeated action sent.")
        if observation.screen_type != ScreenType.PNC_CHAT or observation.active_chat_channel != channel:
            raise RuntimeError("Chat send observed the wrong channel or screen; completion is unproven.")
        return observation

    return observe


def _guard_chat_empty_selection_observer(
    observe_content: Callable[[str], Observation],
) -> Callable[[str], Observation]:
    """Keep every channel-selection frame within the pre-switch empty-draft contract."""

    def observe(label: str) -> Observation:
        observation = observe_content(label)
        _require_chat_send_source(observation)
        return observation

    return observe


def _chat_focused_empty_ready(observation: Observation, *, channel: ChatChannel) -> bool:
    """Require focused placeholder, gold return control, channel, and OCR empty state."""

    return (
        observation.screen_type == ScreenType.PNC_CHAT
        and not observation.blocking_popup
        and observation.active_chat_channel == channel
        and observation.chat_draft_empty is True
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT)
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON)
    )


def _chat_typed_message_ready(observation: Observation, message: str, *, channel: ChatChannel) -> bool:
    """Require exact OCR draft text and the still-visible focused send control."""

    return (
        observation.screen_type == ScreenType.PNC_CHAT
        and not observation.blocking_popup
        and observation.active_chat_channel == channel
        and observation.chat_draft_empty is False
        and observation.chat_draft_text == message
        and _template_control(observation, UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON)
    )


def _chat_receipt_ready(
    observation: Observation,
    *,
    channel: ChatChannel,
    message: str,
    active_castle: CastleIdentity,
    baseline: int,
) -> bool:
    """Require a fresh empty draft and a strictly increased canonical own-row count."""

    if (
        observation.screen_type != ScreenType.PNC_CHAT
        or observation.blocking_popup
        or observation.active_chat_channel != channel
        or observation.chat_draft_empty is not True
    ):
        return False
    receipt_count = count_matching_player_chat_entries(
        observation.entries(ListEntryKind.CHAT_MESSAGE),
        message=message,
        castle=active_castle,
    )
    return receipt_count > baseline


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
        NavigationEdge(screen.PNC_CAMPAIGN_MAP, selector.PNC_CAMPAIGN_HOME_PORTAL, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_CAMPAIGN_CHAPTER, selector.PNC_CAMPAIGN_BACK_BUTTON, frozenset({screen.PNC_CAMPAIGN_MAP})),
        NavigationEdge(screen.PNC_CAMPAIGN_STAGE, selector.PNC_CAMPAIGN_CLOSE_BUTTON, frozenset({screen.PNC_CAMPAIGN_CHAPTER})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_QUEST, quest),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_BAG, frozenset({screen.PNC_BAG})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_MAIL, frozenset({screen.PNC_MAIL_HUB})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_CHAT_SHORTCUT, frozenset({screen.PNC_CHAT})),
        NavigationEdge(
            screen.PNC_CHAT,
            selector.PNC_BACK_BUTTON_TOP_LEFT,
            frozenset({screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP}),
        ),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_MAIL_ROW_PLAYER_MAIL, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_MAIL_HUB, selector.PNC_MAIL_ROW_ALLIANCE_MAIL, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_MAILBOX_LIST, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_MAIL_HUB})),
        NavigationEdge(screen.PNC_MAIL_THREAD, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_MAILBOX_LIST})),
        NavigationEdge(screen.PNC_QUEST_MAIN, selector.PNC_QUEST_TAB_DAILY, frozenset({screen.PNC_QUEST_DAILY})),
        NavigationEdge(screen.PNC_QUEST_DAILY, selector.PNC_QUEST_TAB_MAIN, frozenset({screen.PNC_QUEST_MAIN})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_BOTTOM_NAV_MORE, frozenset({screen.PNC_MORE_MENU})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_BOTTOM_NAV_MORE, frozenset({screen.PNC_MORE_MENU})),
        NavigationEdge(screen.PNC_MORE_MENU, selector.PNC_MORE_SETTINGS, frozenset({screen.PNC_SETTINGS})),
        NavigationEdge(screen.PNC_MORE_MENU, selector.PNC_MORE_RANK, frozenset({screen.PNC_RANK_HUB})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_MORE_MANAGE_CHAR, frozenset({screen.PNC_CASTLE_SELECTION})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_RANK, frozenset({screen.PNC_RANK_HUB})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_PREFERENCES, frozenset({screen.PNC_SETTINGS_PREFERENCES})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_SETTINGS_NOTIFICATIONS, frozenset({screen.PNC_NOTIFICATIONS})),
        NavigationEdge(screen.PNC_SETTINGS, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_RANK_HUB, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_SETTINGS, screen.PNC_HOME_CITY, screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_HOME_CITY, selector.PNC_HOME_RESEARCH_BUTTON, frozenset({screen.PNC_RESEARCH_QUEUE})),
        NavigationEdge(screen.PNC_RESEARCH_QUEUE, selector.PNC_RESEARCH_QUEUE_CLOSE, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_RESEARCH_QUEUE, selector.PNC_RESEARCH_QUEUE_GO, frozenset({screen.PNC_HOME_CITY})),
        NavigationEdge(screen.PNC_INSTITUTE, selector.PNC_INSTITUTE_DEVELOPMENT_BUTTON, frozenset({screen.PNC_RESEARCH_TREE})),
        NavigationEdge(screen.PNC_RESEARCH_TREE, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_INSTITUTE})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_COORDINATE_BAR, frozenset({screen.PNC_WORLD_COORDINATE_DIALOG})),
        NavigationEdge(screen.PNC_WORLD_COORDINATE_DIALOG, selector.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_EXPAND_BUTTON, frozenset({screen.PNC_WORLD_MAP_OVERVIEW})),
        NavigationEdge(screen.PNC_WORLD_MAP_OVERVIEW, selector.PNC_WORLD_OVERVIEW_CLOSE_BUTTON, frozenset({screen.PNC_WORLD_MAP})),
        NavigationEdge(screen.PNC_WORLD_MAP_OVERVIEW, selector.PNC_WORLD_OVERVIEW_WORLD_ICON, frozenset({screen.PNC_WORLD_KINGDOM_LIST})),
        NavigationEdge(screen.PNC_WORLD_KINGDOM_LIST, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_WORLD_MAP_OVERVIEW})),
        NavigationEdge(screen.PNC_WORLD_MAP, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP_EXPANDED})),
        NavigationEdge(screen.PNC_WORLD_MAP_EXPANDED, selector.PNC_WORLD_HUD_TOGGLE, frozenset({screen.PNC_WORLD_MAP})),
    ]
    # Back returns to the actual parent. Rank and the Settings hub can have
    # different parents; their measured destination is used for replanning.
    for source in (screen.PNC_CASTLE_SELECTION, screen.PNC_SETTINGS_PREFERENCES, screen.PNC_NOTIFICATIONS):
        edges.append(NavigationEdge(source, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_SETTINGS})))
    for source in (
        *sorted(quest, key=lambda value: value.name), screen.PNC_BAG,
        screen.PNC_INSTITUTE, screen.PNC_GODDESS_STATUE,
        screen.PNC_WAREHOUSE, screen.PNC_HERO_HALL, screen.PNC_CASTLE,
    ):
        edges.append(NavigationEdge(source, selector.PNC_BACK_BUTTON_TOP_LEFT, frozenset({screen.PNC_HOME_CITY})))
    return tuple(edges)
