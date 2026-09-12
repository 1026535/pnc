"""Typed full-scan refresh of the castle roster through the replacement core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.castle_roster_scan import (
    CastleRosterScanState,
    castle_roster_scan_identity_key,
    castle_roster_window_castles,
    castle_roster_window_signature,
)
from pnc_automation.app.pnc.domain.observation import CurrentCastleEvidenceKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.core.errors import TaskVerificationError


@dataclass(frozen=True, slots=True)
class RefreshCastleRosterPolicy:
    """Bounds and stability requirements for a deterministic roster scan."""

    max_swipes_per_direction: int = 10
    stable_window_count: int = 2

    def __post_init__(self) -> None:
        """Rejects budgets that could permit an unbounded or one-frame decision."""

        if type(self.max_swipes_per_direction) is not int or self.max_swipes_per_direction <= 0:
            raise ValueError("RefreshCastleRosterPolicy.max_swipes_per_direction must be a positive integer.")
        if type(self.stable_window_count) is not int or self.stable_window_count != 2:
            raise ValueError("RefreshCastleRosterPolicy.stable_window_count must be exactly two.")


@dataclass(frozen=True, slots=True)
class RefreshCastleRosterResult:
    """Reports the immutable full-scan roster after Home exit is confirmed by the runner."""

    castles: tuple[CastleIdentity, ...]
    captured_at: datetime
    coverage: Literal["full_scan"] = "full_scan"
    top_swipe_count: int = 0
    scan_swipe_count: int = 0
    window_count: int = 1

    def __post_init__(self) -> None:
        """Rejects incomplete roster results and invalid scan counters."""

        if not isinstance(self.castles, tuple) or not self.castles:
            raise ValueError("RefreshCastleRosterResult.castles must be a non-empty tuple.")
        if any(not isinstance(castle, CastleIdentity) for castle in self.castles):
            raise TypeError("RefreshCastleRosterResult.castles must contain CastleIdentity values.")
        keys = tuple(castle_roster_scan_identity_key(castle) for castle in self.castles)
        if len(keys) != len(set(keys)):
            raise ValueError("RefreshCastleRosterResult.castles cannot contain duplicate identities.")
        if not isinstance(self.captured_at, datetime):
            raise TypeError("RefreshCastleRosterResult.captured_at must be a datetime.")
        if self.coverage != "full_scan":
            raise ValueError("RefreshCastleRosterResult.coverage must be 'full_scan'.")
        for field_name in ("top_swipe_count", "scan_swipe_count", "window_count"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"RefreshCastleRosterResult.{field_name} must be a non-negative integer.")
        if self.window_count == 0:
            raise ValueError("RefreshCastleRosterResult.window_count must be positive.")

@dataclass(frozen=True, slots=True)
class RefreshCastleRosterWorkflow(CoreWorkflow[RefreshCastleRosterResult]):
    """Scans the complete roster without selecting a castle."""

    account_id: str
    pnc_account_id: str
    active_castle: CastleIdentity
    roster_store: CastleRosterStore
    policy: RefreshCastleRosterPolicy = RefreshCastleRosterPolicy()

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="refresh_castle_roster",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
    )

    def __post_init__(self) -> None:
        """Rejects missing identities and persistence dependencies before navigation."""

        if not isinstance(self.account_id, str) or not self.account_id.strip():
            raise ValueError("RefreshCastleRosterWorkflow.account_id cannot be empty.")
        if not isinstance(self.pnc_account_id, str) or not self.pnc_account_id.strip():
            raise ValueError("RefreshCastleRosterWorkflow.pnc_account_id cannot be empty.")
        if not isinstance(self.active_castle, CastleIdentity):
            raise TypeError("RefreshCastleRosterWorkflow.active_castle must be a CastleIdentity.")
        if not isinstance(self.roster_store, CastleRosterStore):
            raise TypeError("RefreshCastleRosterWorkflow.roster_store must be a CastleRosterStore.")
        if not isinstance(self.policy, RefreshCastleRosterPolicy):
            raise TypeError("RefreshCastleRosterWorkflow.policy must be a RefreshCastleRosterPolicy.")

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the reviewed non-spending Home-to-Home workflow contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> RefreshCastleRosterResult:
        """Scans, validates, and persists one complete ordered roster before returning its result."""

        cached_roster = self.roster_store.get(self.pnc_account_id)
        level_hints = (
            {}
            if cached_roster is None
            else {
                castle_roster_scan_identity_key(castle): castle.castle_level
                for castle in cached_roster.castles
            }
        )
        scan_state = CastleRosterScanState(level_hints=level_hints)

        context.navigate(ScreenType.PNC_CASTLE_SELECTION)
        current = context.observe_content(expected_screen=ScreenType.PNC_CASTLE_SELECTION)
        self._validate_window(current)
        current_signature = castle_roster_window_signature(current)
        top_swipes, current = self._seek_top(context, current, current_signature)

        # The last stable frame is the top window and is the first scan window.
        current_castles = self._validate_window(current)
        current_signature = castle_roster_window_signature(current)
        scan_state.record_window_signature(current_signature)
        scan_state.record_window(current_castles)
        exact_active_evidence_seen = self._has_exact_active_evidence(current)
        window_count = 1
        scan_swipes = 0
        unchanged_count = 0

        while True:
            if scan_swipes >= self.policy.max_swipes_per_direction:
                raise TaskVerificationError(
                    "Castle roster refresh exhausted its upward scan budget before two unchanged windows proved the end.",
                    scan_swipes=scan_swipes,
                )
            next_observation = context.scroll_castle_roster("up")
            scan_swipes += 1
            next_castles = self._validate_window(next_observation)
            next_signature = castle_roster_window_signature(next_observation)
            if next_signature == current_signature:
                scan_state.record_window(next_castles)
                exact_active_evidence_seen = exact_active_evidence_seen or self._has_exact_active_evidence(
                    next_observation
                )
                unchanged_count += 1
                current = next_observation
                if unchanged_count >= self.policy.stable_window_count:
                    break
                continue

            unchanged_count = 0
            if next_signature in scan_state.seen_windows:
                raise TaskVerificationError(
                    "Castle roster refresh repeated a previously scanned roster window.",
                    window_signature=next_signature,
                )
            self._require_ordered_overlap(
                current_castles,
                next_castles,
                seen_keys=set(scan_state.ordered_indexes),
            )
            scan_state.record_window_signature(next_signature)
            scan_state.record_window(next_castles)
            exact_active_evidence_seen = exact_active_evidence_seen or self._has_exact_active_evidence(
                next_observation
            )
            window_count += 1
            current = next_observation
            current_castles = next_castles
            current_signature = next_signature

        active_key = castle_roster_scan_identity_key(self.active_castle)
        if active_key not in scan_state.ordered_indexes or not exact_active_evidence_seen:
            raise TaskVerificationError(
                "Castle roster refresh did not encounter exact evidence for the preflight active castle; no cache write was attempted.",
                active_castle=active_key,
            )
        castles = tuple(scan_state.ordered_castles)
        if not castles:
            raise TaskVerificationError("Castle roster refresh produced an empty scan; no cache write was attempted.")
        self.roster_store.replace_full_scan(self.pnc_account_id, castles)
        return RefreshCastleRosterResult(
            castles=castles,
            captured_at=next_observation.captured_at,
            top_swipe_count=top_swipes,
            scan_swipe_count=scan_swipes,
            window_count=window_count,
        )

    def _seek_top(
        self,
        context: WorkflowContext,
        current: Observation,
        current_signature: tuple[tuple[str, str], ...],
    ) -> tuple[int, Observation]:
        """Seeks the top with two unchanged nonempty windows and a bounded cycle guard."""

        seen_signatures = {current_signature}
        unchanged_count = 0
        swipes = 0
        while unchanged_count < self.policy.stable_window_count:
            if swipes >= self.policy.max_swipes_per_direction:
                raise TaskVerificationError(
                    "Castle roster refresh exhausted its downward top-seek budget before two unchanged windows proved the top.",
                    top_swipes=swipes,
                )
            next_observation = context.scroll_castle_roster("down")
            swipes += 1
            self._validate_window(next_observation)
            next_signature = castle_roster_window_signature(next_observation)
            if next_signature == current_signature:
                unchanged_count += 1
            else:
                if next_signature in seen_signatures:
                    raise TaskVerificationError(
                        "Castle roster refresh encountered a nonconsecutive repeated window while seeking the top.",
                        window_signature=next_signature,
                    )
                seen_signatures.add(next_signature)
                current_signature = next_signature
                unchanged_count = 0
            current = next_observation
        return swipes, current

    def _validate_window(self, observation: Observation) -> tuple[CastleIdentity, ...]:
        """Requires one fresh, unblocked, typed roster window and matching current-castle evidence."""

        if observation.blocking_popup:
            raise TaskVerificationError("Castle roster refresh encountered a blocking popup; no cache write was attempted.")
        if observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            raise TaskVerificationError(
                "Castle roster refresh reached an unexpected screen; no cache write was attempted.",
                screen_type=observation.screen_type,
            )
        castles = castle_roster_window_castles(observation)
        keys = tuple(castle_roster_scan_identity_key(castle) for castle in castles)
        if len(keys) != len(set(keys)):
            raise TaskVerificationError(
                "Castle roster refresh found duplicate identities in one visible window; no cache write was attempted.",
                window_signature=keys,
            )
        if observation.current_castle is not None:
            if observation.resolved_current_castle_evidence != CurrentCastleEvidenceKind.EXACT:
                raise TaskVerificationError(
                    "Castle roster refresh received non-exact current-castle evidence; no cache write was attempted."
                )
            current_key = castle_roster_scan_identity_key(observation.current_castle)
            if current_key not in keys:
                raise TaskVerificationError(
                    "Castle roster refresh current-castle evidence was not present in the visible row window; no cache write was attempted.",
                    observed_castle=current_key,
                    window_signature=keys,
                )
            if current_key != castle_roster_scan_identity_key(self.active_castle):
                raise TaskVerificationError(
                    "Castle roster refresh current-castle evidence disagreed with preflight identity; no cache write was attempted.",
                    observed_castle=current_key,
                    expected_castle=castle_roster_scan_identity_key(self.active_castle),
                )
        return castles

    def _has_exact_active_evidence(self, observation: Observation) -> bool:
        """Returns whether this scan frame identifies the preflight castle exactly."""

        return (
            observation.current_castle is not None
            and observation.resolved_current_castle_evidence == CurrentCastleEvidenceKind.EXACT
            and castle_roster_scan_identity_key(observation.current_castle)
            == castle_roster_scan_identity_key(self.active_castle)
        )

    @staticmethod
    def _require_ordered_overlap(
        previous: tuple[CastleIdentity, ...],
        current: tuple[CastleIdentity, ...],
        *,
        seen_keys: set[tuple[str, str]],
    ) -> None:
        """Requires a suffix/prefix overlap and rejects repeats beyond that advancing overlap."""

        previous_keys = tuple(castle_roster_scan_identity_key(castle) for castle in previous)
        current_keys = tuple(castle_roster_scan_identity_key(castle) for castle in current)
        overlap_length = 0
        for length in range(1, min(len(previous_keys), len(current_keys)) + 1):
            if previous_keys[-length:] == current_keys[:length]:
                overlap_length = length
        if overlap_length == 0:
            raise TaskVerificationError(
                "Castle roster refresh found a gap without an ordered suffix/prefix overlap; no cache write was attempted.",
                previous_window=previous_keys,
                current_window=current_keys,
            )
        if any(key in seen_keys for key in current_keys[overlap_length:]):
            raise TaskVerificationError(
                "Castle roster refresh found an order contradiction after the advancing overlap; no cache write was attempted.",
                previous_window=previous_keys,
                current_window=current_keys,
            )
