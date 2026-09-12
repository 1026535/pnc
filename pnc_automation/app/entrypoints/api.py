"""Public Python convenience API layered over the canonical runner contract."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any, TypeVar

from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.app import ApplicationRunner, build_application_runner
from pnc_automation.app.automation.collect_mail import CollectMailResult
from pnc_automation.app.automation.collect_kingdom_chat import CollectKingdomChatResult
from pnc_automation.app.automation.refresh_castle_roster import RefreshCastleRosterResult
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.script_runner import require_successful_preparation
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.automation.open_building import OpenBuildingResult
from pnc_automation.app.pnc.domain.building_priority_input import resolve_building_priority_values
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseBundle
from pnc_automation.core.infra.emulator.session import (
    BlueStacksSessionCleanupMode,
    BlueStacksSessionCleanupPolicy,
)
from pnc_automation.core.lifecycle import close_preserving_error

_ACTIVE_SESSION: ContextVar["_ActiveSession | None"] = ContextVar("pnc_automation_active_session", default=None)
_ACTIVE_RESERVATION: ContextVar["_ActiveReservation | None"] = ContextVar(
    "pnc_automation_active_reservation",
    default=None,
)
_DEFAULT_API: "AutomationApi | None" = None
TResult = TypeVar("TResult")


@dataclass(frozen=True, slots=True)
class _ActiveSession:
    """Carries the currently active Python session scope for direct task calls."""

    api: "AutomationApi"
    account_id: str


@dataclass(frozen=True, slots=True)
class _ActiveReservation:
    """Carries the account bundle protected by the current workflow scope."""

    api: "AutomationApi"
    account_ids: frozenset[str]
    session_cleanup_policy: BlueStacksSessionCleanupPolicy


@dataclass(slots=True)
class AutomationReservation:
    """Context manager that holds a complete account reservation across a workflow."""

    api: "AutomationApi"
    account_ids: tuple[str, ...]
    session_cleanup_policy: BlueStacksSessionCleanupPolicy = field(
        default_factory=BlueStacksSessionCleanupPolicy.keep_warm,
    )
    _reservation: InstanceLeaseBundle | None = field(default=None, init=False, repr=False)
    _token: Token[_ActiveReservation | None] | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "AutomationReservation":
        """Acquires the complete bundle before any workflow operation starts."""

        if self._reservation is not None:
            raise RuntimeError("An automation reservation cannot be entered twice without being closed.")
        active_reservation = _ACTIVE_RESERVATION.get()
        if active_reservation is not None:
            if active_reservation.api is not self.api:
                raise RuntimeError(
                    "Live calls cannot switch AutomationApi instances while a workflow reservation is active."
                )
            undeclared_accounts = frozenset(self.account_ids) - active_reservation.account_ids
            if undeclared_accounts:
                names = ", ".join(sorted(undeclared_accounts))
                raise RuntimeError(
                    f"Cannot expand an active workflow reservation to undeclared accounts: {names}. "
                    f"Declare the complete account bundle before entering the workflow."
                )
        reservation = self.api.application.reserve_accounts(self.account_ids)
        try:
            token = _ACTIVE_RESERVATION.set(
                _ActiveReservation(
                    api=self.api,
                    account_ids=frozenset(self.account_ids),
                    session_cleanup_policy=self.session_cleanup_policy,
                )
            )
        except BaseException as error:
            close_preserving_error(
                reservation.close,
                error,
                message="Workflow reservation setup and cleanup both failed.",
            )
            raise
        self._reservation = reservation
        self._token = token
        return self

    def close(self) -> None:
        """Restores the previous workflow scope and releases the physical reservation."""

        token = self._token
        self._token = None
        if token is not None:
            _ACTIVE_RESERVATION.reset(token)
        reservation = self._reservation
        self._reservation = None
        if reservation is not None:
            reservation.close()

    def __exit__(self, _exception_type: object, _exception: object, _traceback: object) -> None:
        """Releases the complete workflow reservation on normal or exceptional exit."""

        active_error = _exception if isinstance(_exception, BaseException) else None
        close_preserving_error(
            self.close,
            active_error,
            message="Reserved workflow and BlueStacks phase cleanup both failed.",
        )


@dataclass(slots=True)
class AutomationSession:
    """Context manager that prepares one account session and exposes bound task helpers."""

    api: "AutomationApi"
    account_id: str
    castle: CastleIdentity | None = None
    session_cleanup_policy: BlueStacksSessionCleanupPolicy = field(
        default_factory=BlueStacksSessionCleanupPolicy.keep_warm,
    )
    preparation_result: RunResult | None = None
    _reservation: AutomationReservation | None = field(default=None, init=False, repr=False)
    _token: Token[_ActiveSession | None] | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "AutomationSession":
        """Prepares the account session and exposes it as the active direct-call scope."""

        if self._reservation is not None:
            raise RuntimeError("An automation session cannot be entered twice without being closed.")
        reservation = self.api.reserve_accounts(
            (self.account_id,),
            session_cleanup_policy=self.session_cleanup_policy,
        )
        try:
            reservation.__enter__()
            self.preparation_result = require_successful_preparation(
                self.api.prepare_account_session(
                    account_id=self.account_id,
                    castle=self.castle,
                )
            )
            self._reservation = reservation
            self._token = _ACTIVE_SESSION.set(_ActiveSession(api=self.api, account_id=self.account_id))
            return self
        except BaseException as error:
            close_preserving_error(
                reservation.close,
                error,
                message="Account preparation and BlueStacks phase cleanup both failed.",
            )
            raise

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Leaves the active scope without logging out or restoring a previous castle."""

        del exc_type, traceback
        try:
            if self._token is not None:
                _ACTIVE_SESSION.reset(self._token)
                self._token = None
        finally:
            reservation = self._reservation
            self._reservation = None
            if reservation is not None:
                active_error = exc if isinstance(exc, BaseException) else None
                close_preserving_error(
                    reservation.close,
                    active_error,
                    message="Account workflow and BlueStacks phase cleanup both failed.",
                )

    def building_upgrade(
        self,
        *,
        priority: list[str] | None = None,
        priority_file: str | None = None,
        allow_speedups: bool = False,
        prerequisite_mode: str = "fail",
        allow_premium_material_purchases: bool = False,
    ) -> StepRunResult:
        """Runs one direct building-upgrade step against the prepared session."""

        return self.api.building_upgrade(
            account_id=self.account_id,
            priority=priority,
            priority_file=priority_file,
            allow_speedups=allow_speedups,
            prerequisite_mode=prerequisite_mode,
            allow_premium_material_purchases=allow_premium_material_purchases,
        )

    def building_construct(self, *, building: str) -> StepRunResult:
        """Runs one direct building-construction step against the prepared session."""

        return self.api.building_construct(account_id=self.account_id, building=building)

    def open_building(self, *, building: str) -> CoreWorkflowResult[OpenBuildingResult]:
        """Runs one direct open-building step against the prepared session."""

        return self.api.open_building(account_id=self.account_id, building=building)

    def research(self, *, priority: list[str] | None = None) -> StepRunResult:
        """Runs one direct research step against the prepared session."""

        return self.api.research(account_id=self.account_id, priority=priority)

    def gathering(
        self,
        *,
        preferred_resources: list[str] | None = None,
        max_parallel_marches: int = 2,
    ) -> StepRunResult:
        """Runs one direct gathering step against the prepared session."""

        return self.api.gathering(
            account_id=self.account_id,
            preferred_resources=preferred_resources,
            max_parallel_marches=max_parallel_marches,
        )

    def campaign(self, *, enabled_modes: list[str] | None = None) -> StepRunResult:
        """Runs one direct campaign step against the prepared session."""

        return self.api.campaign(account_id=self.account_id, enabled_modes=enabled_modes)

    def send_alliance_chat_message(self, *, message: str) -> StepRunResult:
        """Runs one direct alliance-chat step against the prepared session."""

        return self.api.send_alliance_chat_message(account_id=self.account_id, message=message)

    def send_world_chat_message(self, *, message: str) -> StepRunResult:
        """Runs one direct world-chat step against the prepared session."""

        return self.api.send_world_chat_message(account_id=self.account_id, message=message)

    def send_mail(
        self,
        *,
        recipient_kind: str,
        subject: str,
        body: str,
        player_name: str | None = None,
        profile_route: dict[str, object] | None = None,
    ) -> StepRunResult:
        """Runs one direct mail-send step against the prepared session."""

        return self.api.send_mail(
            account_id=self.account_id,
            recipient_kind=recipient_kind,
            subject=subject,
            body=body,
            player_name=player_name,
            profile_route=profile_route,
        )

    def send_alliance_mail(self, *, subject: str, body: str) -> StepRunResult:
        """Runs one direct alliance-mail step against the prepared session."""

        return self.api.send_alliance_mail(account_id=self.account_id, subject=subject, body=body)

    def send_personal_mail(
        self,
        *,
        subject: str,
        body: str,
        profile_route: dict[str, object],
    ) -> StepRunResult:
        """Runs one direct profile-route personal-mail step against the prepared session."""

        return self.api.send_personal_mail(
            account_id=self.account_id,
            subject=subject,
            body=body,
            profile_route=profile_route,
        )

    def collect_mail(
        self,
        *,
        mailboxes: list[str],
        archive_mode: str = "both",
        limit_per_mailbox: int = 25,
        only_new: bool = True,
    ) -> CoreWorkflowResult[CollectMailResult]:
        """Runs one typed replacement-core mail collection against the prepared session."""

        return self.api.collect_mail(
            account_id=self.account_id,
            mailboxes=mailboxes,
            archive_mode=archive_mode,
            limit_per_mailbox=limit_per_mailbox,
            only_new=only_new,
        )

    def collect_kingdom_chat(self) -> CoreWorkflowResult[CollectKingdomChatResult]:
        """Runs one typed replacement-core Kingdom Chat poll against the prepared session."""

        return self.api.collect_kingdom_chat(account_id=self.account_id)

    def refresh_castle_roster(self) -> CoreWorkflowResult[RefreshCastleRosterResult]:
        """Runs one typed replacement-core full castle-roster scan for the prepared session."""

        return self.api.refresh_castle_roster(account_id=self.account_id)

    def run_mail_schedules(
        self,
        *,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
    ) -> RunResult:
        """Runs authored scheduled mail against the prepared session's bound account."""

        return self.api.run_mail_schedules(
            account_id=self.account_id,
            schedule_ids=schedule_ids,
            scheduled_for_utc=scheduled_for_utc,
        )


@dataclass(frozen=True, slots=True)
class AutomationApi:
    """High-level Python facade that forwards into the canonical application runner."""

    application: ApplicationRunner

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
    ) -> RunResult:
        """Runs the shared session-preparation path for one account and optional castle target."""

        self._require_account_in_active_reservation(account_id)
        cleanup_policy = self._cleanup_policy_for(account_id)
        if cleanup_policy is None:
            return self.application.prepare_account_session(account_id=account_id, castle=castle)
        return self.application.prepare_account_session(
            account_id=account_id,
            castle=castle,
            session_cleanup_policy=cleanup_policy,
        )

    def reserve_accounts(
        self,
        account_ids: tuple[str, ...],
        *,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> AutomationReservation:
        """Returns a scope that holds every physical instance used by a workflow."""

        return AutomationReservation(
            api=self,
            account_ids=tuple(account_ids),
            session_cleanup_policy=session_cleanup_policy or BlueStacksSessionCleanupPolicy.keep_warm(),
        )

    def use_account(
        self,
        account_id: str,
        *,
        castle: CastleIdentity | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> AutomationSession:
        """Returns a context manager that prepares one account session on entry."""

        return AutomationSession(
            api=self,
            account_id=account_id,
            castle=castle,
            session_cleanup_policy=session_cleanup_policy or BlueStacksSessionCleanupPolicy.keep_warm(),
        )

    def run_task(
        self,
        *,
        account_id: str | None = None,
        task_id: TaskId,
        params: dict[str, Any] | None = None,
    ) -> StepRunResult:
        """Runs one direct task call against the selected account using current-castle semantics."""

        resolved_account_id = self._resolve_account_id(account_id)
        cleanup_policy = self._cleanup_policy_for(resolved_account_id)
        if cleanup_policy is None:
            return self.application.run_task(
                account_id=resolved_account_id,
                task_id=task_id,
                params=params,
            )
        return self.application.run_task(
            account_id=resolved_account_id,
            task_id=task_id,
            params=params,
            session_cleanup_policy=cleanup_policy,
        )

    def building_upgrade(
        self,
        *,
        account_id: str | None = None,
        priority: list[str] | None = None,
        priority_file: str | None = None,
        allow_speedups: bool = False,
        prerequisite_mode: str = "fail",
        allow_premium_material_purchases: bool = False,
    ) -> StepRunResult:
        """Runs one direct building-upgrade step using current-castle semantics."""

        resolved_priority = resolve_building_priority_values(priority=priority, priority_file=priority_file)
        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.BUILDING_UPGRADE,
            params={
                "priority": resolved_priority,
                "allow_speedups": allow_speedups,
                "prerequisite_mode": prerequisite_mode,
                "allow_premium_material_purchases": allow_premium_material_purchases,
            },
        )

    def building_construct(
        self,
        *,
        account_id: str | None = None,
        building: str,
    ) -> StepRunResult:
        """Constructs one exact building using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.BUILDING_CONSTRUCT,
            params={"building": building},
        )

    def open_building(
        self,
        *,
        account_id: str | None = None,
        building: str,
    ) -> CoreWorkflowResult[OpenBuildingResult]:
        """Runs one direct open-building step using current-castle semantics."""

        resolved_account_id = self._resolve_account_id(account_id)
        return self._run_with_account_reservation(
            resolved_account_id,
            lambda: self.application.run_open_building(
                account_id=resolved_account_id,
                building=building,
                session_cleanup_policy=self._cleanup_policy_for(resolved_account_id),
            ),
        )

    def research(
        self,
        *,
        account_id: str | None = None,
        priority: list[str] | None = None,
    ) -> StepRunResult:
        """Runs one direct research step using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.RESEARCH,
            params={"priority": ["economy", "development", "military"] if priority is None else list(priority)},
        )

    def gathering(
        self,
        *,
        account_id: str | None = None,
        preferred_resources: list[str] | None = None,
        max_parallel_marches: int = 2,
    ) -> StepRunResult:
        """Runs one direct gathering step using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.GATHERING,
            params={
                "preferred_resources": ["food", "wood"] if preferred_resources is None else list(preferred_resources),
                "max_parallel_marches": max_parallel_marches,
            },
        )

    def campaign(
        self,
        *,
        account_id: str | None = None,
        enabled_modes: list[str] | None = None,
    ) -> StepRunResult:
        """Runs one direct campaign step using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.CAMPAIGN,
            params={"enabled_modes": ["standard"] if enabled_modes is None else list(enabled_modes)},
        )

    def send_alliance_chat_message(
        self,
        *,
        account_id: str | None = None,
        message: str,
    ) -> StepRunResult:
        """Runs one direct alliance-chat send using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.SEND_ALLIANCE_CHAT_MESSAGE,
            params={"message": message},
        )

    def send_world_chat_message(
        self,
        *,
        account_id: str | None = None,
        message: str,
    ) -> StepRunResult:
        """Runs one direct world-chat send using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.SEND_WORLD_CHAT_MESSAGE,
            params={"message": message},
        )

    def send_mail(
        self,
        *,
        account_id: str | None = None,
        recipient_kind: str,
        subject: str,
        body: str,
        player_name: str | None = None,
        profile_route: dict[str, object] | None = None,
    ) -> StepRunResult:
        """Runs one canonical send_mail task using current-castle semantics."""

        params: dict[str, Any] = {
            "recipient_kind": recipient_kind,
            "subject": subject,
            "body": body,
        }
        if player_name is not None:
            params["player_name"] = player_name
        if profile_route is not None:
            params["profile_route"] = profile_route
        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.SEND_MAIL,
            params=params,
        )

    def send_alliance_mail(
        self,
        *,
        account_id: str | None = None,
        subject: str,
        body: str,
    ) -> StepRunResult:
        """Runs one direct alliance-mail convenience wrapper over the canonical send_mail task."""

        return self.send_mail(
            account_id=self._resolve_account_id(account_id),
            recipient_kind="alliance",
            subject=subject,
            body=body,
        )

    def send_personal_mail(
        self,
        *,
        account_id: str | None = None,
        subject: str,
        body: str,
        profile_route: dict[str, object],
    ) -> StepRunResult:
        """Runs one direct profile-route personal-mail convenience wrapper over send_mail."""

        return self.send_mail(
            account_id=self._resolve_account_id(account_id),
            recipient_kind="player",
            subject=subject,
            body=body,
            profile_route=profile_route,
        )

    def collect_mail(
        self,
        *,
        account_id: str | None = None,
        mailboxes: list[str],
        archive_mode: str = "both",
        limit_per_mailbox: int = 25,
        only_new: bool = True,
    ) -> CoreWorkflowResult[CollectMailResult]:
        """Runs one typed replacement-core collect_mail workflow using current-castle semantics."""

        resolved_account_id = self._resolve_account_id(account_id)
        return self._run_with_account_reservation(
            resolved_account_id,
            lambda: self.application.run_collect_mail(
                account_id=resolved_account_id,
                params={
                    "mailboxes": list(mailboxes),
                    "archive_mode": archive_mode,
                    "limit_per_mailbox": limit_per_mailbox,
                    "only_new": only_new,
                },
                session_cleanup_policy=self._cleanup_policy_for(resolved_account_id),
            ),
        )

    def collect_kingdom_chat(
        self,
        *,
        account_id: str | None = None,
    ) -> CoreWorkflowResult[CollectKingdomChatResult]:
        """Runs one typed replacement-core Kingdom Chat poll using current-castle semantics."""

        resolved_account_id = self._resolve_account_id(account_id)
        return self._run_with_account_reservation(
            resolved_account_id,
            lambda: self.application.run_collect_kingdom_chat(
                account_id=resolved_account_id,
                session_cleanup_policy=self._cleanup_policy_for(resolved_account_id),
            ),
        )

    def refresh_castle_roster(
        self,
        *,
        account_id: str | None = None,
    ) -> CoreWorkflowResult[RefreshCastleRosterResult]:
        """Runs one typed replacement-core full roster scan using current-castle semantics."""

        resolved_account_id = self._resolve_account_id(account_id)
        return self._run_with_account_reservation(
            resolved_account_id,
            lambda: self.application.run_refresh_castle_roster(
                account_id=resolved_account_id,
                session_cleanup_policy=self._cleanup_policy_for(resolved_account_id),
            ),
        )

    def run_mail_schedules(
        self,
        *,
        account_id: str | None = None,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
    ) -> RunResult:
        """Runs the authored scheduled-mail expansion path for the selected account."""

        resolved_account_id = self._resolve_account_id(account_id)
        cleanup_policy = self._cleanup_policy_for(resolved_account_id)
        if cleanup_policy is None:
            return self.application.run_mail_schedules(
                account_id=resolved_account_id,
                schedule_ids=None if schedule_ids is None else list(schedule_ids),
                scheduled_for_utc=scheduled_for_utc,
            )
        return self.application.run_mail_schedules(
            account_id=resolved_account_id,
            schedule_ids=None if schedule_ids is None else list(schedule_ids),
            scheduled_for_utc=scheduled_for_utc,
            session_cleanup_policy=cleanup_policy,
        )

    def _cleanup_policy_for(self, account_id: str) -> BlueStacksSessionCleanupPolicy | None:
        """Returns the active outer phase policy for one declared account."""

        active_reservation = _ACTIVE_RESERVATION.get()
        if (
            active_reservation is None
            or active_reservation.api is not self
            or account_id not in active_reservation.account_ids
        ):
            return None
        policy = active_reservation.session_cleanup_policy
        if policy.mode is BlueStacksSessionCleanupMode.KEEP_WARM:
            return None
        return policy

    def _resolve_account_id(self, account_id: str | None) -> str:
        """Returns an explicit account id or the currently active context-scoped account."""

        active_reservation = _ACTIVE_RESERVATION.get()
        if active_reservation is not None:
            if active_reservation.api is not self:
                raise RuntimeError(
                    "Live calls cannot switch AutomationApi instances while a workflow reservation is active."
                )
            if account_id is not None:
                self._require_account_in_active_reservation(account_id)
                return account_id
            active_session = _ACTIVE_SESSION.get()
            if active_session is not None and active_session.api is self:
                return active_session.account_id
            if len(active_reservation.account_ids) == 1:
                return next(iter(active_reservation.account_ids))
            raise RuntimeError(
                "A multi-account workflow reservation requires an explicit account_id for each live call."
            )
        if account_id is not None:
            return account_id
        active_session = _ACTIVE_SESSION.get()
        if active_session is None or active_session.api is not self:
            raise RuntimeError(
                "Direct task calls require either an explicit account_id or an active use_account(...) context."
            )
        return active_session.account_id

    def _require_account_in_active_reservation(self, account_id: str) -> None:
        """Rejects live calls that escape the currently declared workflow account bundle."""

        active_reservation = _ACTIVE_RESERVATION.get()
        if active_reservation is None:
            return
        if active_reservation.api is not self:
            raise RuntimeError(
                "Live calls cannot switch AutomationApi instances while a workflow reservation is active."
            )
        if account_id not in active_reservation.account_ids:
            raise RuntimeError(
                f"Account '{account_id}' is outside the active workflow reservation. "
                f"Declare its complete account bundle before entering the workflow."
            )

    def _run_with_account_reservation(
        self,
        account_id: str,
        operation: Callable[[], TResult],
    ) -> TResult:
        """Runs one live call under its active bundle or a temporary account lease."""

        active_reservation = _ACTIVE_RESERVATION.get()
        if active_reservation is not None:
            self._require_account_in_active_reservation(account_id)
            return operation()
        reservation = self.application.reserve_accounts((account_id,))
        try:
            return operation()
        finally:
            reservation.close()


def build_api(
    config_path: str | Path = "config/accounts.yaml",
    *,
    verbose: bool = False,
    catalog_path: Path | None = None,
    observation_mode: ObservationMode | None = None,
) -> AutomationApi:
    """Builds one Python automation facade from the canonical application runner."""

    return AutomationApi(
        application=build_application_runner(
            config_path=config_path,
            verbose=verbose,
            catalog_path=catalog_path,
            observation_mode=observation_mode,
        )
    )


def use_account(
    account_id: str,
    *,
    castle: CastleIdentity | None = None,
    session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
) -> AutomationSession:
    """Returns a context manager backed by the default application configuration."""

    return _default_api().use_account(
        account_id,
        castle=castle,
        session_cleanup_policy=session_cleanup_policy,
    )


def reserve_accounts(
    account_ids: tuple[str, ...],
    *,
    session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
) -> AutomationReservation:
    """Returns a workflow reservation backed by the default application facade."""

    return _default_api().reserve_accounts(
        account_ids,
        session_cleanup_policy=session_cleanup_policy,
    )


def building_upgrade(
    *,
    account_id: str | None = None,
    priority: list[str] | None = None,
    priority_file: str | None = None,
    allow_speedups: bool = False,
    prerequisite_mode: str = "fail",
    allow_premium_material_purchases: bool = False,
) -> StepRunResult:
    """Runs one direct building-upgrade step through the default application facade."""

    return _default_api().building_upgrade(
        account_id=account_id,
        priority=priority,
        priority_file=priority_file,
        allow_speedups=allow_speedups,
        prerequisite_mode=prerequisite_mode,
        allow_premium_material_purchases=allow_premium_material_purchases,
    )


def building_construct(*, account_id: str | None = None, building: str) -> StepRunResult:
    """Runs one direct building-construction step through the default facade."""

    return _default_api().building_construct(account_id=account_id, building=building)


def open_building(
    *, account_id: str | None = None, building: str
) -> CoreWorkflowResult[OpenBuildingResult]:
    """Runs one direct open-building step through the default application facade."""

    return _default_api().open_building(account_id=account_id, building=building)


def research(*, account_id: str | None = None, priority: list[str] | None = None) -> StepRunResult:
    """Runs one direct research step through the default application facade."""

    return _default_api().research(account_id=account_id, priority=priority)


def gathering(
    *,
    account_id: str | None = None,
    preferred_resources: list[str] | None = None,
    max_parallel_marches: int = 2,
) -> StepRunResult:
    """Runs one direct gathering step through the default application facade."""

    return _default_api().gathering(
        account_id=account_id,
        preferred_resources=preferred_resources,
        max_parallel_marches=max_parallel_marches,
    )


def campaign(*, account_id: str | None = None, enabled_modes: list[str] | None = None) -> StepRunResult:
    """Runs one direct campaign step through the default application facade."""

    return _default_api().campaign(account_id=account_id, enabled_modes=enabled_modes)


def send_alliance_chat_message(*, account_id: str | None = None, message: str) -> StepRunResult:
    """Runs one direct alliance-chat send through the default application facade."""

    return _default_api().send_alliance_chat_message(account_id=account_id, message=message)


def send_world_chat_message(*, account_id: str | None = None, message: str) -> StepRunResult:
    """Runs one direct world-chat send through the default application facade."""

    return _default_api().send_world_chat_message(account_id=account_id, message=message)


def send_mail(
    *,
    account_id: str | None = None,
    recipient_kind: str,
    subject: str,
    body: str,
    player_name: str | None = None,
    profile_route: dict[str, object] | None = None,
) -> StepRunResult:
    """Runs one direct send_mail step through the default application facade."""

    return _default_api().send_mail(
        account_id=account_id,
        recipient_kind=recipient_kind,
        subject=subject,
        body=body,
        player_name=player_name,
        profile_route=profile_route,
    )


def send_alliance_mail(*, account_id: str | None = None, subject: str, body: str) -> StepRunResult:
    """Runs one direct alliance-mail send through the default application facade."""

    return _default_api().send_alliance_mail(account_id=account_id, subject=subject, body=body)


def send_personal_mail(
    *,
    account_id: str | None = None,
    subject: str,
    body: str,
    profile_route: dict[str, object],
) -> StepRunResult:
    """Runs one direct profile-route personal-mail send through the default application facade."""

    return _default_api().send_personal_mail(
        account_id=account_id,
        subject=subject,
        body=body,
        profile_route=profile_route,
    )


def collect_mail(
    *,
    account_id: str | None = None,
    mailboxes: list[str],
    archive_mode: str = "both",
    limit_per_mailbox: int = 25,
    only_new: bool = True,
) -> CoreWorkflowResult[CollectMailResult]:
    """Runs one typed replacement-core collect_mail workflow through the default facade."""

    return _default_api().collect_mail(
        account_id=account_id,
        mailboxes=mailboxes,
        archive_mode=archive_mode,
        limit_per_mailbox=limit_per_mailbox,
        only_new=only_new,
    )


def collect_kingdom_chat(
    *,
    account_id: str | None = None,
) -> CoreWorkflowResult[CollectKingdomChatResult]:
    """Runs one typed replacement-core Kingdom Chat poll through the default facade."""

    return _default_api().collect_kingdom_chat(account_id=account_id)


def refresh_castle_roster(
    *,
    account_id: str | None = None,
) -> CoreWorkflowResult[RefreshCastleRosterResult]:
    """Runs one typed replacement-core full roster scan through the default facade."""

    return _default_api().refresh_castle_roster(account_id=account_id)


def run_mail_schedules(
    *,
    account_id: str | None = None,
    schedule_ids: list[str] | None = None,
    scheduled_for_utc: datetime | None = None,
) -> RunResult:
    """Runs authored scheduled mail through the default application facade."""

    return _default_api().run_mail_schedules(
        account_id=account_id,
        schedule_ids=schedule_ids,
        scheduled_for_utc=scheduled_for_utc,
    )


def _default_api() -> AutomationApi:
    """Returns the lazily built default API facade for module-level convenience calls."""

    global _DEFAULT_API
    if _DEFAULT_API is None:
        _DEFAULT_API = build_api()
    return _DEFAULT_API
