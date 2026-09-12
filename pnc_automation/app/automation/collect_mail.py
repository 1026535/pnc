"""Typed collect-mail workflow on the replacement navigation core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveRecord,
    MailboxAvailability,
    MailboxType,
    compute_mail_thread_fingerprint,
    mail_thread_row_key,
    normalize_mail_thread_text,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.enums.mail import MailArchiveMode
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.errors import TaskVerificationError


@dataclass(frozen=True, slots=True)
class CollectMailMailboxResult:
    """Reports one requested mailbox's bounded collection outcome."""

    mailbox: MailboxType
    availability: MailboxAvailability
    processed_count: int
    archived_count: int
    skipped_existing_count: int
    scroll_count: int

    def __post_init__(self) -> None:
        """Rejects malformed mailbox identity, availability, or counters."""

        if not isinstance(self.mailbox, MailboxType):
            raise TypeError("CollectMailMailboxResult.mailbox must be a MailboxType.")
        if not isinstance(self.availability, MailboxAvailability):
            raise TypeError("CollectMailMailboxResult.availability must be a MailboxAvailability.")
        for field_name in ("processed_count", "archived_count", "skipped_existing_count", "scroll_count"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"CollectMailMailboxResult.{field_name} must be a non-negative integer.")
        if self.archived_count + self.skipped_existing_count != self.processed_count:
            raise ValueError(
                "CollectMailMailboxResult archived_count + skipped_existing_count must equal processed_count."
            )
        if self.availability == MailboxAvailability.UNAVAILABLE and any(
            value != 0
            for value in (
                self.processed_count,
                self.archived_count,
                self.skipped_existing_count,
                self.scroll_count,
            )
        ):
            raise ValueError("An unavailable mailbox must report zero for every counter.")


@dataclass(frozen=True, slots=True)
class CollectMailResult:
    """Aggregates ordered mailbox collection outcomes and their deterministic totals."""

    mailboxes: tuple[CollectMailMailboxResult, ...]

    def __post_init__(self) -> None:
        """Requires one ordered result for each unique requested mailbox."""

        if type(self.mailboxes) is not tuple:
            raise TypeError("CollectMailResult.mailboxes must be an immutable tuple.")
        if not self.mailboxes:
            raise ValueError("CollectMailResult.mailboxes cannot be empty.")
        if any(not isinstance(result, CollectMailMailboxResult) for result in self.mailboxes):
            raise TypeError("CollectMailResult.mailboxes must contain CollectMailMailboxResult values.")
        mailbox_types = tuple(result.mailbox for result in self.mailboxes)
        if len(set(mailbox_types)) != len(mailbox_types):
            raise ValueError("CollectMailResult.mailboxes cannot contain duplicate mailbox identities.")

    @property
    def mailbox_results(self) -> tuple[CollectMailMailboxResult, ...]:
        """Returns the ordered per-mailbox results under an explicit alias."""

        return self.mailboxes

    @property
    def total_processed_count(self) -> int:
        """Returns the number of opened thread rows across requested mailboxes."""

        return sum(result.processed_count for result in self.mailboxes)

    @property
    def total_archived_count(self) -> int:
        """Returns the number of newly persisted archive records."""

        return sum(result.archived_count for result in self.mailboxes)

    @property
    def total_skipped_existing_count(self) -> int:
        """Returns the number of existing or in-run duplicate rows skipped."""

        return sum(result.skipped_existing_count for result in self.mailboxes)

    @property
    def total_scroll_count(self) -> int:
        """Returns the number of bounded mailbox swipes issued."""

        return sum(result.scroll_count for result in self.mailboxes)

    @property
    def processed_count(self) -> int:
        """Returns the aggregate processed count using the per-mailbox field name."""

        return self.total_processed_count

    @property
    def archived_count(self) -> int:
        """Returns the aggregate archived count using the per-mailbox field name."""

        return self.total_archived_count

    @property
    def skipped_existing_count(self) -> int:
        """Returns the aggregate skipped count using the per-mailbox field name."""

        return self.total_skipped_existing_count

    @property
    def scroll_count(self) -> int:
        """Returns the aggregate scroll count using the per-mailbox field name."""

        return self.total_scroll_count


@dataclass(frozen=True, slots=True)
class CollectMailWorkflow(CoreWorkflow[CollectMailResult]):
    """Collects visible mail through constrained core operations and canonical archive storage."""

    params: CollectMailParams
    account_id: str
    pnc_account_id: str
    active_castle: str
    archive_store: MailArchiveStore

    _spec: ClassVar[WorkflowSpec] = WorkflowSpec(
        name="collect_mail",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
    )

    def __post_init__(self) -> None:
        """Rejects missing workflow identity and storage dependencies before navigation."""

        if not isinstance(self.params, CollectMailParams):
            raise TypeError("CollectMailWorkflow.params must be CollectMailParams.")
        if type(self.params.mailboxes) is not tuple or not self.params.mailboxes:
            raise ValueError("CollectMailWorkflow.params.mailboxes must be a non-empty tuple.")
        if any(not isinstance(mailbox, MailboxType) for mailbox in self.params.mailboxes):
            raise TypeError("CollectMailWorkflow.params.mailboxes must contain MailboxType values.")
        if len(set(self.params.mailboxes)) != len(self.params.mailboxes):
            raise ValueError("CollectMailWorkflow.params.mailboxes cannot contain duplicates.")
        if not isinstance(self.params.archive_mode, MailArchiveMode):
            raise TypeError("CollectMailWorkflow.params.archive_mode must be a MailArchiveMode.")
        if type(self.params.limit_per_mailbox) is not int or self.params.limit_per_mailbox <= 0:
            raise ValueError("CollectMailWorkflow.params.limit_per_mailbox must be positive.")
        if type(self.params.only_new) is not bool:
            raise TypeError("CollectMailWorkflow.params.only_new must be a boolean.")
        for field_name in ("account_id", "pnc_account_id", "active_castle"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(f"CollectMailWorkflow.{field_name} must be a non-empty string.")
        if not isinstance(self.archive_store, MailArchiveStore):
            raise TypeError("CollectMailWorkflow.archive_store must be a MailArchiveStore.")

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the non-spending Home-to-Home workflow contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> CollectMailResult:
        """Collects each requested mailbox, leaving final Home confirmation to the runner."""

        context.navigate(ScreenType.PNC_MAIL_HUB)
        results: list[CollectMailMailboxResult] = []
        seen_fingerprints: set[str] = set()
        for mailbox in self.params.mailboxes:
            availability = context.open_mailbox(mailbox)
            if not isinstance(availability, MailboxAvailability):
                raise TaskVerificationError(
                    "Mail hub returned an untyped mailbox availability disposition.",
                    mailbox=mailbox.value,
                )
            if availability == MailboxAvailability.UNAVAILABLE:
                results.append(
                    CollectMailMailboxResult(
                        mailbox=mailbox,
                        availability=availability,
                        processed_count=0,
                        archived_count=0,
                        skipped_existing_count=0,
                        scroll_count=0,
                    )
                )
                continue
            listing = self._require_mailbox_list(
                context.observe_content(expected_screen=ScreenType.PNC_MAILBOX_LIST),
                mailbox,
            )
            mailbox_result = self._collect_mailbox(
                context,
                mailbox=mailbox,
                listing=listing,
                seen_fingerprints=seen_fingerprints,
            )
            results.append(mailbox_result)
            context.navigate(ScreenType.PNC_MAIL_HUB)
        return CollectMailResult(mailboxes=tuple(results))

    def _collect_mailbox(
        self,
        context: WorkflowContext,
        *,
        mailbox: MailboxType,
        listing: Observation,
        seen_fingerprints: set[str],
    ) -> CollectMailMailboxResult:
        """Processes visible rows and bounded scroll windows for one available mailbox."""

        processed_count = 0
        archived_count = 0
        skipped_existing_count = 0
        scroll_count = 0
        seen_row_keys: set[str] = set()
        current = listing
        max_scrolls = max(self.params.limit_per_mailbox, 1)
        while processed_count < self.params.limit_per_mailbox:
            rows, signature = self._validated_rows(current, mailbox)
            candidate = next(
                (entry for entry in rows if mail_thread_row_key(entry) not in seen_row_keys),
                None,
            )
            if candidate is not None:
                row_key = mail_thread_row_key(candidate)
                context.open_mail_thread(row_key)
                thread = context.observe_content(expected_screen=ScreenType.PNC_MAIL_THREAD)
                self._require_mail_thread(thread, mailbox)
                archived, skipped = self._archive_thread(
                    thread,
                    candidate,
                    mailbox=mailbox,
                    seen_fingerprints=seen_fingerprints,
                )
                processed_count += 1
                archived_count += archived
                skipped_existing_count += skipped
                seen_row_keys.add(row_key)
                context.navigate(ScreenType.PNC_MAILBOX_LIST)
                current = self._require_mailbox_list(
                    context.observe_content(expected_screen=ScreenType.PNC_MAILBOX_LIST),
                    mailbox,
                )
                continue
            if current.mailbox_empty is True:
                break
            if scroll_count >= max_scrolls:
                break
            after_scroll = context.scroll_mailbox()
            scroll_count += 1
            after = self._require_mailbox_list(after_scroll, mailbox)
            after_rows, after_signature = self._validated_rows(after, mailbox)
            del after_rows
            if not after_signature or after_signature == signature:
                break
            current = after
        return CollectMailMailboxResult(
            mailbox=mailbox,
            availability=MailboxAvailability.AVAILABLE,
            processed_count=processed_count,
            archived_count=archived_count,
            skipped_existing_count=skipped_existing_count,
            scroll_count=scroll_count,
        )

    def _archive_thread(
        self,
        thread: Observation,
        row: DetectedListEntry,
        *,
        mailbox: MailboxType,
        seen_fingerprints: set[str],
    ) -> tuple[int, int]:
        """Normalizes one opened thread and persists or counts its canonical fingerprint."""

        if self.params.archive_mode in {MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH}:
            artifact_path = thread.artifact_path
            if artifact_path is None or not artifact_path.is_file():
                raise TaskVerificationError(
                    "Screenshot archive mode requires an existing persisted thread artifact before persistence.",
                    archive_mode=self.params.archive_mode.value,
                    artifact_path=None if artifact_path is None else str(artifact_path),
                )
        sender_name = (row.title_text or "").strip()
        if not sender_name:
            raise TaskVerificationError(
                "Opened mail thread row has no sender identity.",
                artifact_path=None if thread.artifact_path is None else str(thread.artifact_path),
            )
        messages = thread.entries(ListEntryKind.MAIL_MESSAGE)
        normalized_thread_text = normalize_mail_thread_text(tuple(entry.title_text or "" for entry in messages))
        if not normalized_thread_text:
            raise TaskVerificationError(
                "Opened mail thread exposed no non-empty message text.",
                artifact_path=None if thread.artifact_path is None else str(thread.artifact_path),
            )
        timestamp_text = next(
            (
                value
                for entry in messages
                if isinstance((value := entry.metadata.get("timestamp_text")), str) and value.strip()
            ),
            None,
        )
        fingerprint = compute_mail_thread_fingerprint(
            mailbox_type=mailbox,
            sender_name=sender_name,
            timestamp_text=timestamp_text,
            normalized_thread_text=normalized_thread_text,
        )
        if fingerprint.value in seen_fingerprints:
            return 0, 1
        seen_fingerprints.add(fingerprint.value)
        if self.params.only_new and self.archive_store.has_fingerprint(
            active_castle=self.active_castle,
            mailbox_type=mailbox.value,
            fingerprint=fingerprint.value,
        ):
            return 0, 1
        stored = self.archive_store.persist(
            record=MailArchiveRecord(
                account_id=self.account_id,
                pnc_account_id=self.pnc_account_id,
                active_castle=self.active_castle,
                mailbox_type=mailbox,
                sender_name=sender_name,
                thread_timestamp_text=timestamp_text,
                fingerprint=fingerprint,
                captured_at=thread.captured_at,
                normalized_thread_text=normalized_thread_text,
                source_artifact_paths=()
                if thread.artifact_path is None
                else (thread.artifact_path,),
            ),
            archive_mode=self.params.archive_mode,
            screenshot_source_path=thread.artifact_path,
            skip_existing=self.params.only_new,
        )
        return (1, 0) if stored.created else (0, 1)

    @staticmethod
    def _require_mailbox_list(observation: Observation, mailbox: MailboxType) -> Observation:
        """Requires exact typed mailbox identity and availability metadata."""

        if observation.mailbox_type != mailbox:
            raise TaskVerificationError(
                "Mailbox list content identified a different mailbox.",
                expected_mailbox=mailbox.value,
                observed_mailbox=None
                if observation.mailbox_type is None
                else observation.mailbox_type.value,
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
        if type(observation.mailbox_empty) is not bool:
            raise TaskVerificationError(
                "Mailbox list content did not expose typed mailbox_empty metadata.",
                mailbox=mailbox.value,
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
        return observation

    @staticmethod
    def _validated_rows(
        observation: Observation,
        mailbox: MailboxType,
    ) -> tuple[tuple[DetectedListEntry, ...], tuple[str, ...]]:
        """Validates every visible thread identity and returns its ordered signature."""

        rows = observation.entries(ListEntryKind.MAIL_THREAD)
        keys: list[str] = []
        for entry in rows:
            key = mail_thread_row_key(entry)
            if not key:
                raise TaskVerificationError(
                    "Mailbox list contains a thread row without a canonical identity.",
                    mailbox=mailbox.value,
                    artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
                )
            if key in keys:
                raise TaskVerificationError(
                    "Mailbox list contains ambiguous duplicate thread identities.",
                    mailbox=mailbox.value,
                    row_key=key,
                    artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
                )
            keys.append(key)
        return rows, tuple(keys)

    @staticmethod
    def _require_mail_thread(observation: Observation, mailbox: MailboxType) -> None:
        """Requires exact thread mailbox identity and at least one typed message entry."""

        if observation.mailbox_type != mailbox:
            raise TaskVerificationError(
                "Mail thread content identified a different mailbox.",
                expected_mailbox=mailbox.value,
                observed_mailbox=None
                if observation.mailbox_type is None
                else observation.mailbox_type.value,
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
        if not observation.entries(ListEntryKind.MAIL_MESSAGE):
            raise TaskVerificationError(
                "Opened mail thread did not expose a typed message entry.",
                mailbox=mailbox.value,
                artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
            )
