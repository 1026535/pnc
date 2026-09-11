"""Top-level parallel-instance orchestration for daily maintenance."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyMaintenanceConfig,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.authoring.config.models import AppConfig


@dataclass(frozen=True, slots=True)
class DailyRunBoundary:
    """Identifies one shared maintenance and game-reset boundary for every worker."""

    maintenance_date: date
    game_reset_id: str

    def __post_init__(self) -> None:
        """Rejects an incomplete reset identity."""

        if not self.game_reset_id.strip():
            raise ValueError("DailyRunBoundary.game_reset_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class DailyCastleRunSummary:
    """Records one castle outcome without allowing a worker failure to cancel peers."""

    account_id: str
    castle_ref: str
    succeeded: bool
    message: str
    artifact_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DailyApplicationRunSummary:
    """Aggregates the isolated per-castle worker outcomes."""

    boundary: DailyRunBoundary
    castles: tuple[DailyCastleRunSummary, ...]

    @property
    def succeeded(self) -> bool:
        """Returns whether every configured castle completed successfully."""

        return all(item.succeeded for item in self.castles)


class DailyCastleRunner(Protocol):
    """Executes one castle using an instance-worker-owned connected runtime."""

    def run_castle(
        self,
        *,
        target: DailyMaintenanceTargetConfig,
        boundary: DailyRunBoundary,
    ) -> DailyCastleRunSummary:
        """Runs one target and returns its isolated summary."""


class DailyCastleRunnerFactory(Protocol):
    """Builds one runner owned exclusively by one BlueStacks instance worker."""

    def build(self, *, instance_id: str) -> DailyCastleRunner:
        """Builds one instance-bound runner."""

    def reserve_instances(self, instance_ids: tuple[str, ...]) -> AbstractContextManager[object]:
        """Reserves the complete physical instance bundle for the worker pool lifetime."""


@dataclass(slots=True)
class DailyMaintenanceApplicationService:
    """Runs instances concurrently and each instance's castles sequentially."""

    app_config: AppConfig
    daily_config: DailyMaintenanceConfig
    runner_factory: DailyCastleRunnerFactory

    def run(self, *, boundary: DailyRunBoundary) -> DailyApplicationRunSummary:
        """Executes every configured target with failure isolation between workers."""

        if not self.daily_config.automatic_runs_enabled:
            raise PermissionError("Automatic Daily runs are disabled pending canary evaluation.")
        groups = self._group_targets_by_instance()
        collected: dict[int, DailyCastleRunSummary] = {}
        indexed_targets = {
            (target.account_id, target.castle_ref): index
            for index, target in enumerate(self.daily_config.targets)
        }
        with self.runner_factory.reserve_instances(tuple(groups)):
            with ThreadPoolExecutor(max_workers=len(groups), thread_name_prefix="daily-instance") as executor:
                futures = {
                    executor.submit(self._run_instance, instance_id, targets, boundary): instance_id
                    for instance_id, targets in groups.items()
                }
                for future in as_completed(futures):
                    instance_id = futures[future]
                    try:
                        summaries = future.result()
                    except Exception as error:  # Instance construction failures are isolated and reported.
                        summaries = tuple(
                            DailyCastleRunSummary(
                                account_id=target.account_id,
                                castle_ref=target.castle_ref,
                                succeeded=False,
                                message=f"Instance worker '{instance_id}' failed: {error}",
                            )
                            for target in groups[instance_id]
                        )
                    for summary in summaries:
                        collected[indexed_targets[(summary.account_id, summary.castle_ref)]] = summary
        return DailyApplicationRunSummary(
            boundary=boundary,
            castles=tuple(collected[index] for index in sorted(collected)),
        )

    def _group_targets_by_instance(self) -> dict[str, tuple[DailyMaintenanceTargetConfig, ...]]:
        """Groups ordered targets by configured physical BlueStacks instance."""

        mutable: dict[str, list[DailyMaintenanceTargetConfig]] = {}
        for target in self.daily_config.targets:
            account = self.app_config.require_account(target.account_id)
            mutable.setdefault(account.instance_id, []).append(target)
        return {instance_id: tuple(targets) for instance_id, targets in mutable.items()}

    def _run_instance(
        self,
        instance_id: str,
        targets: tuple[DailyMaintenanceTargetConfig, ...],
        boundary: DailyRunBoundary,
    ) -> tuple[DailyCastleRunSummary, ...]:
        """Runs one instance's castle list serially through one owned runner."""

        runner = self.runner_factory.build(instance_id=instance_id)
        summaries: list[DailyCastleRunSummary] = []
        for target in targets:
            try:
                summaries.append(runner.run_castle(target=target, boundary=boundary))
            except Exception as error:  # A castle failure is recorded while later targets remain runnable.
                summaries.append(
                    DailyCastleRunSummary(
                        account_id=target.account_id,
                        castle_ref=target.castle_ref,
                        succeeded=False,
                        message=str(error),
                    )
                )
        return tuple(summaries)
