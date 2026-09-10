"""Exactly-once Hero Hall free-single recruitment for Daily maintenance."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationDispatcher,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

HERO_HALL_FREE_SINGLE_TARGET = 5
HERO_HALL_FREE_SINGLE_COOLDOWN_SECONDS = 300


@dataclass(frozen=True, slots=True)
class HeroHallState:
    """Represents the typed Hero Hall facts needed for one free single."""

    free_single_available: bool
    daily_attempts_remaining: int | None
    cooldown_seconds_remaining: int | None
    artifact_path: str | None = None

    @classmethod
    def from_observation(cls, observation: Observation) -> "HeroHallState":
        """Builds Hero Hall state from typed screen evidence and catalog-backed controls."""

        if observation.screen_type != ScreenType.PNC_HERO_HALL:
            raise ValueError(f"Hero Hall state requires PNC_HERO_HALL, got '{observation.screen_type}'.")
        banner = observation.get(UiElementId.PNC_HERO_HALL_RECRUIT_BANNER)
        banner_text = "" if banner is None or banner.extracted_text is None else banner.extracted_text
        return cls(
            free_single_available=observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON),
            daily_attempts_remaining=_parse_daily_attempts(banner_text),
            cooldown_seconds_remaining=_parse_cooldown_seconds(banner_text),
            artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
        )


class HeroHallSession(Protocol):
    """Defines the connected observations and one safe Hero Hall mutation."""

    def observe_hero_hall(self, label: str) -> Observation:
        """Returns one fresh typed Hero Hall observation."""

    def recruit_free_single(self) -> None:
        """Dispatches exactly one freshly observed free 1x recruit."""

    def daily_requirement_completed(self) -> bool:
        """Returns whether the Daily Hero Hall requirement is freshly proven complete."""

    def artifact_paths(self) -> tuple[str, ...]:
        """Returns captured Hero Hall and Daily evidence paths in observation order."""


@dataclass(slots=True)
class HeroHallRecruitmentExecutor:
    """Runs five free singles as individually journaled, cooldown-aware increments."""

    session: HeroHallSession
    dispatcher: JournaledMutationDispatcher
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC)
    target_count: int = HERO_HALL_FREE_SINGLE_TARGET
    cooldown_seconds: int = HERO_HALL_FREE_SINGLE_COOLDOWN_SECONDS

    def __post_init__(self) -> None:
        """Rejects policies that could exceed the finalized canary contract."""

        if self.target_count != HERO_HALL_FREE_SINGLE_TARGET:
            raise ValueError("Hero Hall target_count must be exactly five free singles.")
        if self.cooldown_seconds != HERO_HALL_FREE_SINGLE_COOLDOWN_SECONDS:
            raise ValueError("Hero Hall cooldown_seconds must be exactly 300 seconds.")

    def execute(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Executes or resumes one free single without waiting inside the mutation executor."""

        intents = tuple(
            intent for intent in checkpoint.mutation_intents
            if intent.quest_id == DailyQuestId.HERO_HALL
        )
        committed_count = sum(intent.state == MutationIntentState.COMMITTED for intent in intents)
        if committed_count > self.target_count:
            raise ValueError("Hero Hall journal contains more committed singles than the five-single target.")

        unresolved = tuple(
            intent for intent in intents
            if intent.state in {MutationIntentState.DISPATCHED, MutationIntentState.RECONCILED}
        )
        if len(unresolved) > 1:
            return checkpoint, self._pending("Multiple Hero Hall singles are unresolved; no replay.", intents)
        if unresolved:
            checkpoint, result = self._reconcile_existing(
                checkpoint=checkpoint,
                intent=unresolved[0],
            )
            if result.pending_clarification:
                return checkpoint, self._pending("Hero Hall single result is ambiguous; no replay.", intents)
            if result.committed:
                committed_count += 1
                intents = tuple(
                    intent for intent in checkpoint.mutation_intents
                    if intent.quest_id == DailyQuestId.HERO_HALL
                )

        if committed_count >= self.target_count:
            return self._finish_if_daily_complete(checkpoint=checkpoint, intents=intents)

        cooldown = _remaining_cooldown(intents=intents, now=self.now())
        if cooldown > 0:
            return checkpoint, DailyTargetOutcome(
                quest_id=DailyQuestId.HERO_HALL,
                status=DailyTargetOutcomeStatus.WAITING_COOLDOWN,
                message=f"Hero Hall is waiting {cooldown} seconds before the next free single.",
                artifact_paths=self._artifacts(intents),
            )

        before = HeroHallState.from_observation(self.session.observe_hero_hall("hero_hall_recruit_pre"))
        if not before.free_single_available:
            if before.daily_attempts_remaining == 0:
                return checkpoint, DailyTargetOutcome(
                    quest_id=DailyQuestId.HERO_HALL,
                    status=DailyTargetOutcomeStatus.FAILED,
                    message="Hero Hall free-single target cannot continue: no daily attempts remain.",
                    artifact_paths=self._artifacts(intents, before.artifact_path),
                )
            return checkpoint, DailyTargetOutcome(
                quest_id=DailyQuestId.HERO_HALL,
                status=DailyTargetOutcomeStatus.WAITING_COOLDOWN,
                message="Hero Hall has not exposed the next free single yet.",
                artifact_paths=self._artifacts(intents, before.artifact_path),
            )

        operation_id = f"hero-hall-recruit-{committed_count + 1:03d}"
        operation = MutationOperation(
            operation_id=operation_id,
            quest_id=DailyQuestId.HERO_HALL,
            expected_precondition="Hero Hall Recruit tab exposes the free 1x single",
            expected_postcondition="one Hero Hall free single is consumed and its cooldown is recorded",
            metadata={
                "before_daily_attempts_remaining": before.daily_attempts_remaining,
            },
        )

        def reconcile() -> MutationReconciliation:
            """Accepts only a fresh attempt decrement or a typed cooldown transition."""

            after = HeroHallState.from_observation(self.session.observe_hero_hall("hero_hall_recruit_post"))
            consumed = _single_consumed(before=before, after=after)
            ready_at = _next_ready_at(
                now=self.now(),
                observed_cooldown_seconds=after.cooldown_seconds_remaining,
                fallback_seconds=self.cooldown_seconds,
            )
            return MutationReconciliation(
                postcondition_proven=consumed,
                original_precondition_proven=not consumed,
                artifact_paths=self._artifacts(intents, before.artifact_path, after.artifact_path),
                metadata={"next_ready_at": ready_at.isoformat()},
            )

        result = self.dispatcher.execute(
            checkpoint=checkpoint,
            operation=operation,
            dispatch=self.session.recruit_free_single,
            reconcile=reconcile,
        )
        if not result.committed:
            return result.checkpoint, self._pending(
                "Hero Hall free-single result is ambiguous; no replay.",
                tuple(intent for intent in result.checkpoint.mutation_intents if intent.quest_id == DailyQuestId.HERO_HALL),
            )
        committed_count += 1
        intents = tuple(
            intent for intent in result.checkpoint.mutation_intents
            if intent.quest_id == DailyQuestId.HERO_HALL
        )
        if committed_count == self.target_count:
            return self._finish_if_daily_complete(checkpoint=result.checkpoint, intents=intents)
        return result.checkpoint, DailyTargetOutcome(
            quest_id=DailyQuestId.HERO_HALL,
            status=DailyTargetOutcomeStatus.WAITING_COOLDOWN,
            message=(
                f"Hero Hall free single {committed_count}/{self.target_count} committed; "
                f"the next single is eligible after {self.cooldown_seconds} seconds."
            ),
            artifact_paths=result.artifact_paths,
        )

    def _reconcile_existing(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        intent: MutationIntent,
    ):
        """Reconciles one dispatched Hero Hall single without sending a second tap."""

        def reconcile() -> MutationReconciliation:
            """Uses one fresh Hero Hall state to distinguish consumed from unchanged."""

            after = HeroHallState.from_observation(self.session.observe_hero_hall(f"{intent.operation_id}_reconcile"))
            before_remaining = intent.metadata.get("before_daily_attempts_remaining")
            consumed = (
                isinstance(before_remaining, int)
                and after.daily_attempts_remaining is not None
                and after.daily_attempts_remaining == before_remaining - 1
            ) or (
                not after.free_single_available
                and after.cooldown_seconds_remaining is not None
                and after.cooldown_seconds_remaining > 0
            ) or (before_remaining is None and not after.free_single_available)
            ready_at = _next_ready_at(
                now=self.now(),
                observed_cooldown_seconds=after.cooldown_seconds_remaining,
                fallback_seconds=self.cooldown_seconds,
            )
            return MutationReconciliation(
                postcondition_proven=consumed,
                original_precondition_proven=not consumed,
                artifact_paths=self._artifacts((intent,), after.artifact_path),
                metadata={"next_ready_at": ready_at.isoformat()},
            )

        result = self.dispatcher.reconcile_existing(
            checkpoint=checkpoint,
            operation_id=intent.operation_id,
            reconcile=reconcile,
        )
        return result.checkpoint, result

    def _finish_if_daily_complete(
        self,
        *,
        checkpoint: DailyTaskCheckpoint,
        intents: tuple[MutationIntent, ...],
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Requires Daily completion after the fifth observed free single."""

        if not self.session.daily_requirement_completed():
            return checkpoint, self._pending(
                "Five Hero Hall singles were consumed, but Daily completion was not proven.",
                intents,
            )
        return checkpoint, DailyTargetOutcome(
            quest_id=DailyQuestId.HERO_HALL,
            status=DailyTargetOutcomeStatus.SUCCESS,
            message="Five Hero Hall free singles and the Daily requirement were proven complete.",
            artifact_paths=self._artifacts(intents),
        )

    def _pending(self, message: str, intents: tuple[MutationIntent, ...]) -> DailyTargetOutcome:
        """Builds one non-replayable pending outcome with all known evidence."""

        return DailyTargetOutcome(
            quest_id=DailyQuestId.HERO_HALL,
            status=DailyTargetOutcomeStatus.PENDING_CLARIFICATION,
            message=message,
            artifact_paths=self._artifacts(intents),
        )

    def _artifacts(self, intents: tuple[MutationIntent, ...], *extra: str | None) -> tuple[str, ...]:
        """Returns journaled and current-session evidence without duplicates."""

        paths: list[str] = []
        for intent in intents:
            for path in intent.metadata.get("artifact_paths", []):
                if isinstance(path, str) and path not in paths:
                    paths.append(path)
        for path in (*extra, *self.session.artifact_paths()):
            if path is not None and path not in paths:
                paths.append(path)
        return tuple(paths)


def _single_consumed(*, before: HeroHallState, after: HeroHallState) -> bool:
    """Returns whether one free single is proven consumed by typed transition evidence."""

    if before.daily_attempts_remaining is not None and after.daily_attempts_remaining is not None:
        return after.daily_attempts_remaining == before.daily_attempts_remaining - 1
    return before.free_single_available and not after.free_single_available


def _remaining_cooldown(*, intents: tuple[MutationIntent, ...], now: datetime) -> int:
    """Returns the persisted cooldown remaining after the latest committed single."""

    committed = [intent for intent in intents if intent.state == MutationIntentState.COMMITTED]
    if not committed:
        return 0
    raw = committed[-1].metadata.get("next_ready_at")
    if not isinstance(raw, str):
        return 0
    try:
        ready_at = datetime.fromisoformat(raw)
    except ValueError:
        return 0
    if ready_at.tzinfo is None:
        ready_at = ready_at.replace(tzinfo=UTC)
    return max(0, int((ready_at - now).total_seconds()))


def _next_ready_at(*, now: datetime, observed_cooldown_seconds: int | None, fallback_seconds: int) -> datetime:
    """Persists the observed game cooldown while retaining the reviewed fallback contract."""

    delay = observed_cooldown_seconds if observed_cooldown_seconds is not None else fallback_seconds
    return now + timedelta(seconds=max(0, delay))


def _parse_daily_attempts(text: str) -> int | None:
    """Parses the visible Daily attempts counter without deriving click geometry from OCR."""

    match = re.search(r"daily\s*attempts?\s*[:：]\s*(\d+)", text, flags=re.IGNORECASE)
    return None if match is None else int(match.group(1))


def _parse_cooldown_seconds(text: str) -> int | None:
    """Parses common Hero Hall countdown forms when the game exposes one."""

    clock = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", text)
    if clock is not None:
        hours_or_minutes = int(clock.group(1))
        minutes_or_seconds = int(clock.group(2))
        if clock.group(3) is None:
            return hours_or_minutes * 60 + minutes_or_seconds
        return hours_or_minutes * 3600 + minutes_or_seconds * 60 + int(clock.group(3))
    minutes = re.search(r"(\d+)\s*m", text, flags=re.IGNORECASE)
    seconds = re.search(r"(\d+)\s*s", text, flags=re.IGNORECASE)
    if minutes is None and seconds is None:
        return None
    return (0 if minutes is None else int(minutes.group(1)) * 60) + (0 if seconds is None else int(seconds.group(1)))
