"""Public Python convenience API layered over the canonical runner contract."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pnc_automation.automation.observation_mode import ObservationMode
from pnc_automation.app import ApplicationRunner, build_application_runner
from pnc_automation.automation.runner import RunResult, StepRunResult
from pnc_automation.automation.task import TaskId
from pnc_automation.config.models import CastleIdentity

_ACTIVE_SESSION: ContextVar["_ActiveSession | None"] = ContextVar("pnc_automation_active_session", default=None)
_DEFAULT_API: "AutomationApi | None" = None


@dataclass(frozen=True, slots=True)
class _ActiveSession:
    """Carries the currently active Python session scope for direct task calls."""

    api: "AutomationApi"
    account_id: str


@dataclass(slots=True)
class AutomationSession:
    """Context manager that prepares one account session and exposes bound task helpers."""

    api: "AutomationApi"
    account_id: str
    castle: CastleIdentity | None = None
    preparation_result: RunResult | None = None
    _token: Token[_ActiveSession | None] | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "AutomationSession":
        """Prepares the account session and exposes it as the active direct-call scope."""

        self.preparation_result = self.api.prepare_account_session(account_id=self.account_id, castle=self.castle)
        self._token = _ACTIVE_SESSION.set(_ActiveSession(api=self.api, account_id=self.account_id))
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Leaves the active scope without logging out or restoring a previous castle."""

        del exc_type, exc, traceback
        if self._token is not None:
            _ACTIVE_SESSION.reset(self._token)
            self._token = None

    def building_upgrade(
        self,
        *,
        priority: list[str] | None = None,
        allow_speedups: bool = False,
    ) -> StepRunResult:
        """Runs one direct building-upgrade step against the prepared session."""

        return self.api.building_upgrade(
            account_id=self.account_id,
            priority=priority,
            allow_speedups=allow_speedups,
        )

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
    ) -> StepRunResult:
        """Runs one direct mail-collection step against the prepared session."""

        return self.api.collect_mail(
            account_id=self.account_id,
            mailboxes=mailboxes,
            archive_mode=archive_mode,
            limit_per_mailbox=limit_per_mailbox,
            only_new=only_new,
        )

    def collect_kingdom_chat(self) -> StepRunResult:
        """Runs one direct Kingdom Chat heartbeat poll against the prepared session."""

        return self.api.collect_kingdom_chat(account_id=self.account_id)


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

        return self.application.prepare_account_session(account_id=account_id, castle=castle)

    def use_account(
        self,
        account_id: str,
        *,
        castle: CastleIdentity | None = None,
    ) -> AutomationSession:
        """Returns a context manager that prepares one account session on entry."""

        return AutomationSession(api=self, account_id=account_id, castle=castle)

    def run_task(
        self,
        *,
        account_id: str | None = None,
        task_id: TaskId,
        params: dict[str, Any] | None = None,
    ) -> StepRunResult:
        """Runs one direct task call against the selected account using current-castle semantics."""

        return self.application.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=task_id,
            params=params,
        )

    def building_upgrade(
        self,
        *,
        account_id: str | None = None,
        priority: list[str] | None = None,
        allow_speedups: bool = False,
    ) -> StepRunResult:
        """Runs one direct building-upgrade step using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.BUILDING_UPGRADE,
            params={
                "priority": ["castle", "wall", "academy", "barracks"] if priority is None else list(priority),
                "allow_speedups": allow_speedups,
            },
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
    ) -> StepRunResult:
        """Runs one direct collect_mail task using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.COLLECT_MAIL,
            params={
                "mailboxes": list(mailboxes),
                "archive_mode": archive_mode,
                "limit_per_mailbox": limit_per_mailbox,
                "only_new": only_new,
            },
        )

    def collect_kingdom_chat(self, *, account_id: str | None = None) -> StepRunResult:
        """Runs one direct collect_kingdom_chat task using current-castle semantics."""

        return self.run_task(
            account_id=self._resolve_account_id(account_id),
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            params={},
        )

    def _resolve_account_id(self, account_id: str | None) -> str:
        """Returns an explicit account id or the currently active context-scoped account."""

        if account_id is not None:
            return account_id
        active_session = _ACTIVE_SESSION.get()
        if active_session is None or active_session.api is not self:
            raise RuntimeError(
                "Direct task calls require either an explicit account_id or an active use_account(...) context."
            )
        return active_session.account_id


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


def use_account(account_id: str, *, castle: CastleIdentity | None = None) -> AutomationSession:
    """Returns a context manager backed by the default application configuration."""

    return _default_api().use_account(account_id, castle=castle)


def building_upgrade(
    *,
    account_id: str | None = None,
    priority: list[str] | None = None,
    allow_speedups: bool = False,
) -> StepRunResult:
    """Runs one direct building-upgrade step through the default application facade."""

    return _default_api().building_upgrade(
        account_id=account_id,
        priority=priority,
        allow_speedups=allow_speedups,
    )


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
) -> StepRunResult:
    """Runs one direct collect_mail step through the default application facade."""

    return _default_api().collect_mail(
        account_id=account_id,
        mailboxes=mailboxes,
        archive_mode=archive_mode,
        limit_per_mailbox=limit_per_mailbox,
        only_new=only_new,
    )


def collect_kingdom_chat(*, account_id: str | None = None) -> StepRunResult:
    """Runs one direct Kingdom Chat heartbeat poll through the default application facade."""

    return _default_api().collect_kingdom_chat(account_id=account_id)


def _default_api() -> AutomationApi:
    """Returns the lazily built default API facade for module-level convenience calls."""

    global _DEFAULT_API
    if _DEFAULT_API is None:
        _DEFAULT_API = build_api()
    return _DEFAULT_API
