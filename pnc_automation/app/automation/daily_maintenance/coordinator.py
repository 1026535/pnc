"""Canonical per-castle Daily Quest coordinator."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NoReturn, Protocol

from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CoordinateProvenance,
    DailyQuestDisposition,
    DailyQuestId,
    DailyQuestRow,
    DailyQuestRowState,
    DailyTargetOutcome,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    NormalizedBounds,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation, RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.text.normalization import normalize_ocr_text


@dataclass(frozen=True, slots=True)
class DailyQuestViewport:
    """Represents one stable Daily list viewport."""

    rows: tuple[DailyQuestRow, ...]
    unknown_titles: tuple[str, ...] = ()
    bottom_marker: bool = False
    artifact_path: str | None = None

    @property
    def geometry_signature(self) -> tuple[tuple[object, ...], ...]:
        """Returns the semantic geometry compared across stability observations."""

        return tuple(
            (
                row.quest_id,
                row.state,
                row.bounds.x,
                row.bounds.y,
                row.bounds.width,
                row.bounds.height,
            )
            for row in self.rows
        )


@dataclass(frozen=True, slots=True)
class DailyMaintenanceResult:
    """Summarizes one castle's coordinator run."""

    checkpoint: DailyTaskCheckpoint
    outcomes: tuple[DailyTargetOutcome, ...]
    unknown_titles: tuple[str, ...]
    scanned_viewports: int


@dataclass(frozen=True, slots=True)
class DailyReadOnlySurvey:
    """Summarizes a full non-mutating Daily list traversal."""

    rows: tuple[DailyQuestRow, ...]
    unknown_titles: tuple[str, ...]
    scanned_viewports: int
    artifact_paths: tuple[str, ...]


class DailyQuestSession(Protocol):
    """Defines navigation and observation operations owned by the connected runtime adapter."""

    def open_daily_quest(self) -> None:
        """Reaches and proves the typed Daily Quest screen."""

    def observe_daily_quest(self, label: str) -> Observation:
        """Returns one fresh typed Daily Quest observation."""

    def scroll_daily_quest(self, *, adjusted: bool) -> None:
        """Scrolls the Daily list once, using the adjusted retry gesture when requested."""

    def return_to_home(self) -> None:
        """Returns through the in-game gold controls and proves Home."""


class DailyRowClaimExecutor(Protocol):
    """Claims one freshly resolved row through durable mutation journaling."""

    def claim(
        self,
        *,
        row: DailyQuestRow,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Claims one row and returns the persisted checkpoint plus observed outcome."""


class DailyCapabilityExecutor(Protocol):
    """Executes one enabled capability through its canonical task owner."""

    def execute(
        self,
        *,
        row: DailyQuestRow,
        target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
    ) -> tuple[DailyTaskCheckpoint, DailyTargetOutcome]:
        """Executes and verifies one capability without recursively invoking a runner."""


@dataclass(slots=True)
class DailyMaintenanceCoordinator:
    """Owns one castle's claim-first Daily lifecycle and durable progress."""

    session: DailyQuestSession
    claim_executor: DailyRowClaimExecutor
    capability_executor: DailyCapabilityExecutor
    journal_store: DailyRunJournalStore
    catalog: DailyQuestCatalog
    max_viewports: int = 40
    max_reopens: int = 80

    @classmethod
    def for_read_only(
        cls, *, session: DailyQuestSession, journal_store: DailyRunJournalStore,
        catalog: DailyQuestCatalog,
    ) -> DailyMaintenanceCoordinator:
        """Builds the canonical survey coordinator with both mutation seams forbidden."""

        forbidden = ForbiddenDailyMutationExecutor()
        return cls(session, forbidden, forbidden, journal_store, catalog)

    def survey_read_only(self) -> DailyReadOnlySurvey:
        """Traverses the Daily list without claiming or following any Go action."""

        rows_by_fingerprint: dict[str, DailyQuestRow] = {}
        unknown_titles: list[str] = []
        artifact_paths: list[str] = []
        scanned_viewports = 0
        self.session.open_daily_quest()
        viewport = self._observe_stable_viewport(label_prefix="daily_survey_0")
        while True:
            scanned_viewports += 1
            for row in viewport.rows:
                rows_by_fingerprint[row.observation_fingerprint] = row
            for title in viewport.unknown_titles:
                if title not in unknown_titles:
                    unknown_titles.append(title)
            if viewport.artifact_path is not None and viewport.artifact_path not in artifact_paths:
                artifact_paths.append(viewport.artifact_path)
            if viewport.bottom_marker:
                break
            if scanned_viewports >= self.max_viewports:
                raise TaskVerificationError(
                    "Read-only Daily Quest survey exceeded its bounded viewport budget.",
                    max_viewports=self.max_viewports,
                )
            viewport = self._advance_viewport(previous=viewport, scanned_viewports=scanned_viewports)
        self.session.return_to_home()
        return DailyReadOnlySurvey(
            rows=tuple(rows_by_fingerprint.values()),
            unknown_titles=tuple(unknown_titles),
            scanned_viewports=scanned_viewports,
            artifact_paths=tuple(artifact_paths),
        )

    def run(
        self,
        *,
        target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
    ) -> DailyMaintenanceResult:
        """Runs one bounded Daily sweep, resuming committed work without mutation replay."""

        self._validate_target_checkpoint(target=target, checkpoint=checkpoint)
        current_checkpoint = checkpoint
        outcomes: list[DailyTargetOutcome] = []
        unknown_titles: list[str] = []
        scanned_viewports = 0
        reopens = 0
        deferred_quest_ids: set[DailyQuestId] = set()
        self.session.open_daily_quest()
        while True:
            viewport = self._observe_stable_viewport(label_prefix=f"daily_viewport_{scanned_viewports}")
            scanned_viewports += 1
            for title in viewport.unknown_titles:
                if title not in unknown_titles:
                    unknown_titles.append(title)

            claim_row = next(
                (
                    row for row in viewport.rows
                    if row.row_status == RowRecognitionStatus.COMPLETE
                    and row.state == DailyQuestRowState.CLAIM
                ),
                None,
            )
            if claim_row is not None:
                current_checkpoint, outcome = self.claim_executor.claim(
                    row=claim_row,
                    checkpoint=current_checkpoint,
                )
                outcomes.append(outcome)
                current_checkpoint = replace(current_checkpoint, last_typed_screen=ScreenType.PNC_QUEST_DAILY)
                self.journal_store.save(current_checkpoint)
                if outcome.status == DailyTargetOutcomeStatus.PENDING_CLARIFICATION:
                    break
                reopens = self._reopen_daily(reopens)
                continue

            actionable = self._select_actionable_row(
                viewport=viewport,
                target=target,
                checkpoint=current_checkpoint,
                deferred_quest_ids=deferred_quest_ids,
            )
            if actionable is not None:
                current_checkpoint = replace(current_checkpoint, current_quest_id=actionable.quest_id)
                self.journal_store.save(current_checkpoint)
                current_checkpoint, outcome = self.capability_executor.execute(
                    row=actionable,
                    target=target,
                    checkpoint=current_checkpoint,
                )
                outcomes.append(outcome)
                if outcome.status in {
                    DailyTargetOutcomeStatus.SUCCESS,
                    DailyTargetOutcomeStatus.APPLICABILITY_SKIP,
                }:
                    current_checkpoint = self.journal_store.mark_completed(current_checkpoint, actionable.quest_id)
                elif outcome.status == DailyTargetOutcomeStatus.WAITING_COOLDOWN:
                    deferred_quest_ids.add(actionable.quest_id)
                    current_checkpoint = replace(current_checkpoint, current_quest_id=None)
                    self.journal_store.save(current_checkpoint)
                if outcome.status == DailyTargetOutcomeStatus.PENDING_CLARIFICATION:
                    current_checkpoint = replace(current_checkpoint, current_quest_id=None)
                    self.journal_store.save(current_checkpoint)
                    break
                reopens = self._reopen_daily(reopens)
                continue

            if viewport.bottom_marker:
                break
            if scanned_viewports >= self.max_viewports:
                raise TaskVerificationError(
                    "Daily Quest scan exceeded its bounded viewport budget.",
                    account_id=target.account_id,
                    castle_ref=target.castle_ref,
                    max_viewports=self.max_viewports,
                )
            viewport = self._advance_viewport(previous=viewport, scanned_viewports=scanned_viewports)
            scanned_viewports += 1
            if viewport.bottom_marker and not self._has_pending_rows(
                viewport,
                target,
                current_checkpoint,
                deferred_quest_ids=deferred_quest_ids,
            ):
                break

        self.session.return_to_home()
        current_checkpoint = replace(current_checkpoint, current_quest_id=None, last_typed_screen=ScreenType.PNC_HOME_CITY)
        self.journal_store.save(current_checkpoint)
        return DailyMaintenanceResult(
            checkpoint=current_checkpoint,
            outcomes=tuple(outcomes),
            unknown_titles=tuple(unknown_titles),
            scanned_viewports=scanned_viewports,
        )

    def _observe_stable_viewport(self, *, label_prefix: str) -> DailyQuestViewport:
        """Requires two agreeing observations, with one bounded animation reread."""

        first = daily_viewport_from_observation(self.session.observe_daily_quest(f"{label_prefix}_1"))
        second = daily_viewport_from_observation(self.session.observe_daily_quest(f"{label_prefix}_2"))
        if first.geometry_signature != second.geometry_signature:
            first, second = second, daily_viewport_from_observation(
                self.session.observe_daily_quest(f"{label_prefix}_settled")
            )
            if first.geometry_signature != second.geometry_signature:
                raise TaskVerificationError(
                    "Daily Quest row geometry was not stable within the bounded observation reread.",
                    first_artifact_path=first.artifact_path,
                    second_artifact_path=second.artifact_path,
                )
        return second

    def _advance_viewport(self, *, previous: DailyQuestViewport, scanned_viewports: int) -> DailyQuestViewport:
        """Scrolls once and uses exactly one adjusted retry when the viewport is unchanged."""

        self.session.scroll_daily_quest(adjusted=False)
        current = self._observe_stable_viewport(label_prefix=f"daily_scroll_{scanned_viewports}")
        if current.geometry_signature != previous.geometry_signature:
            return current
        if current.bottom_marker:
            return current
        self.session.scroll_daily_quest(adjusted=True)
        retried = self._observe_stable_viewport(label_prefix=f"daily_scroll_{scanned_viewports}_adjusted")
        if retried.geometry_signature == previous.geometry_signature and not retried.bottom_marker:
            return replace(retried, bottom_marker=True)
        return retried

    def _select_actionable_row(
        self,
        *,
        viewport: DailyQuestViewport,
        target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
        deferred_quest_ids: set[DailyQuestId] | None = None,
    ) -> DailyQuestRow | None:
        """Returns the first enabled uncommitted Go row and never executes claim-only work."""

        enabled = {policy.quest_id for policy in target.capabilities}
        for row in viewport.rows:
            definition = self.catalog.require(row.quest_id)
            if definition.disposition != DailyQuestDisposition.ENABLED:
                continue
            if (
                row.quest_id not in enabled
                or row.quest_id in checkpoint.completed_quest_ids
                or row.quest_id in (deferred_quest_ids or set())
            ):
                continue
            if row.row_status == RowRecognitionStatus.COMPLETE and row.state == DailyQuestRowState.GO:
                return row
        return None

    def _has_pending_rows(
        self,
        viewport: DailyQuestViewport,
        target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
        deferred_quest_ids: set[DailyQuestId] | None = None,
    ) -> bool:
        """Returns whether the current bottom viewport still contains coordinator work."""

        return any(
            row.row_status == RowRecognitionStatus.COMPLETE
            and row.state == DailyQuestRowState.CLAIM
            for row in viewport.rows
        ) or self._select_actionable_row(
            viewport=viewport,
            target=target,
            checkpoint=checkpoint,
            deferred_quest_ids=deferred_quest_ids,
        ) is not None

    def _reopen_daily(self, reopens: int) -> int:
        """Reopens Daily after one mutation and enforces a non-cyclic bound."""

        next_count = reopens + 1
        if next_count > self.max_reopens:
            raise TaskVerificationError(
                "Daily Quest coordinator exceeded its bounded reopen budget.",
                max_reopens=self.max_reopens,
            )
        self.session.open_daily_quest()
        return next_count

    @staticmethod
    def _validate_target_checkpoint(
        *,
        target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
    ) -> None:
        """Rejects cross-target resume before any connected action."""

        if checkpoint.account_id != target.account_id or checkpoint.castle != target.castle:
            raise ValueError("Daily checkpoint does not match the requested account and castle target.")


def daily_viewport_from_observation(observation: Observation) -> DailyQuestViewport:
    """Converts one typed observation into coordinator rows and unknown-title evidence."""

    if observation.screen_type != ScreenType.PNC_QUEST_DAILY:
        raise TaskVerificationError(
            "Daily Quest observation classified as an unexpected screen.",
            screen_type=observation.screen_type,
            artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
        )
    if observation.image_size is None:
        raise TaskVerificationError("Daily Quest observation is missing screenshot dimensions.")
    image_width, image_height = observation.image_size
    rows: list[DailyQuestRow] = []
    unknown_titles: list[str] = []
    for entry in observation.entries(ListEntryKind.DAILY_QUEST):
        raw_quest_id = entry.metadata.get("quest_id")
        if raw_quest_id is None:
            if entry.title_text:
                unknown_titles.append(entry.title_text)
            continue
        try:
            quest_id = DailyQuestId(str(raw_quest_id))
            state = DailyQuestRowState(str(entry.require_metadata("row_state")))
            provenance = CoordinateProvenance(str(entry.require_metadata("coordinate_provenance")))
        except ValueError as error:
            raise TaskVerificationError("Daily Quest row contains invalid typed metadata.") from error
        rows.append(
            DailyQuestRow(
                quest_id=quest_id,
                normalized_title=normalize_ocr_text(entry.title_text or quest_id.value),
                state=state,
                bounds=NormalizedBounds(
                    x=entry.bounds.x / image_width,
                    y=entry.bounds.y / image_height,
                    width=entry.bounds.width / image_width,
                    height=entry.bounds.height / image_height,
                ),
                observation_fingerprint=str(entry.require_metadata("observation_fingerprint")),
                progress_current=_optional_int(entry.metadata.get("progress_current")),
                progress_required=_optional_int(entry.metadata.get("progress_required")),
                coordinate_provenance=provenance,
                row_status=entry.row_status,
            )
        )
    return DailyQuestViewport(
        rows=tuple(rows),
        unknown_titles=tuple(unknown_titles),
        bottom_marker=bool(any(entry.metadata.get("bottom_marker") is True for entry in observation.entries(ListEntryKind.DAILY_QUEST))),
        artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
    )


class ForbiddenDailyMutationExecutor:
    """Fails closed if a read-only survey accidentally enters an execution branch."""

    def claim(self, *, row: DailyQuestRow, checkpoint: DailyTaskCheckpoint) -> NoReturn:
        """Rejects reward mutations from a survey-only coordinator."""

        raise PermissionError("Read-only Daily survey cannot claim rewards.")

    def execute(
        self, *, row: DailyQuestRow, target: DailyMaintenanceTargetConfig,
        checkpoint: DailyTaskCheckpoint,
    ) -> NoReturn:
        """Rejects feature mutations from a survey-only coordinator."""

        raise PermissionError("Read-only Daily survey cannot execute capabilities.")


def _optional_int(value: object) -> int | None:
    """Returns an optional integer metadata value without accepting booleans."""

    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TaskVerificationError("Daily Quest progress metadata must be an integer or null.")
    return value
