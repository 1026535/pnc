"""Offline concurrency tests for the daily-maintenance application service."""

from __future__ import annotations

from contextlib import nullcontext
import threading
import time
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace
from datetime import date

from pnc_automation.app.automation.daily_maintenance.application_service import (
    DailyApplicationRunSummary,
    DailyCastleRunSummary,
    DailyMaintenanceApplicationService,
    DailyRunBoundary,
)
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyMaintenanceConfig,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    AppConfig,
    CastleIdentity,
    DefaultsConfig,
    RuntimeConfig,
)
from pnc_automation.core.infra.emulator.models import BlueStacksInstanceConfig
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.core.errors import InstanceBusyError


class DailyApplicationServiceTests(unittest.TestCase):
    """Proves per-instance parallelism, serialization, and failure isolation."""

    def test_disabled_service_never_builds_workers(self) -> None:
        """Enforces the disabled gate even when callers bypass the CLI."""

        factory = _RecordingFactory()
        service = self._service(factory)
        service.daily_config = replace(service.daily_config, automatic_runs_enabled=False)
        with self.assertRaisesRegex(PermissionError, "disabled"):
            service.run(boundary=DailyRunBoundary(date(2026, 9, 8), "reset-2026-09-08"))
        self.assertEqual({}, factory.order_by_instance)

    def test_instances_overlap_but_castles_on_one_instance_do_not(self) -> None:
        """Runs two instance workers concurrently while preserving target order within each."""

        factory = _RecordingFactory()
        summary = self._service(factory).run(
            boundary=DailyRunBoundary(date(2026, 9, 4), "reset-2026-09-04")
        )
        self.assertIsInstance(summary, DailyApplicationRunSummary)
        self.assertTrue(summary.succeeded)
        self.assertTrue(factory.overlapped.wait(timeout=0.1))
        self.assertEqual(["a1/c1", "a1/c2"], factory.order_by_instance["i1"])
        self.assertEqual(1, factory.maximum_active_by_instance["i1"])

    def test_one_instance_factory_failure_does_not_cancel_the_other(self) -> None:
        """Reports every target on a failed worker while retaining peer success."""

        factory = _RecordingFactory(failing_instance="i1")
        summary = self._service(factory).run(
            boundary=DailyRunBoundary(date(2026, 9, 4), "reset-2026-09-04")
        )
        self.assertFalse(summary.succeeded)
        self.assertFalse(summary.castles[0].succeeded)
        self.assertFalse(summary.castles[1].succeeded)
        self.assertTrue(summary.castles[2].succeeded)

    def test_multi_instance_pool_reserves_complete_bundle_before_workers(self) -> None:
        """Keeps competitors excluded while the service-owned bundle spans worker execution."""

        with tempfile.TemporaryDirectory() as temp_directory:
            registry = InstanceLeaseRegistry(root=Path(temp_directory) / "leases", wait_timeout_seconds=0)
            factory = _RecordingFactory(lease_registry=registry)
            service = self._service(factory)

            summary = service.run(
                boundary=DailyRunBoundary(date(2026, 9, 4), "reset-2026-09-04")
            )

        self.assertTrue(summary.succeeded)
        self.assertEqual(factory.reserved_instance_ids, ("i1", "i2"))
        self.assertEqual(factory.competitor_blocked, {"One", "Two"})

    @staticmethod
    def _service(factory: _RecordingFactory) -> DailyMaintenanceApplicationService:
        """Builds one isolated two-instance service fixture."""

        instances = (
            BlueStacksInstanceConfig(id="i1", display_name="One", app_package="game"),
            BlueStacksInstanceConfig(id="i2", display_name="Two", app_package="game"),
        )
        accounts = (
            AccountConfig(id="a1", instance_id="i1", pnc_account_id="p1"),
            AccountConfig(id="a2", instance_id="i2", pnc_account_id="p2"),
        )
        app_config = AppConfig(
            config_path=_path("accounts.yaml"),
            castle_roster_path=_path("castles.yaml"),
            castle_targets_path=_path("targets.yaml"),
            mail_definitions_path=_path("mail.yaml"),
            mail_schedules_path=_path("schedules.yaml"),
            artifact_root=_path("artifacts"),
            archive_root=_path("archive"),
            defaults=DefaultsConfig(),
            runtime=RuntimeConfig(),
            instances=instances,
            accounts=accounts,
        )
        targets = (
            _target("a1", "c1"),
            _target("a1", "c2"),
            _target("a2", "c3"),
        )
        return DailyMaintenanceApplicationService(
            app_config=app_config,
            daily_config=DailyMaintenanceConfig("America/Toronto", 2, 0, targets, automatic_runs_enabled=True),
            runner_factory=factory,
        )


class _RecordingFactory:
    """Builds fake instance runners and records concurrency invariants."""

    def __init__(
        self,
        failing_instance: str | None = None,
        *,
        lease_registry: InstanceLeaseRegistry | None = None,
    ) -> None:
        """Initializes synchronized recording state."""

        self.failing_instance = failing_instance
        self.lease_registry = lease_registry
        self.instance_display_names = {"i1": "One", "i2": "Two"}
        self.reserved_instance_ids: tuple[str, ...] = ()
        self.competitor_blocked: set[str] = set()
        self.lock = threading.Lock()
        self.active_instances = 0
        self.active_by_instance: dict[str, int] = {}
        self.maximum_active_by_instance: dict[str, int] = {}
        self.order_by_instance: dict[str, list[str]] = {}
        self.overlapped = threading.Event()

    def build(self, *, instance_id: str) -> _RecordingRunner:
        """Builds one fake runner or raises the configured worker failure."""

        if instance_id == self.failing_instance:
            raise RuntimeError("factory failure")
        return _RecordingRunner(self, instance_id)

    def reserve_instances(self, instance_ids: tuple[str, ...]):
        """Provides the typed fleet reservation boundary for offline worker tests."""

        self.reserved_instance_ids = instance_ids
        if self.lease_registry is not None:
            return self.lease_registry.acquire_bundle(
                tuple(self.instance_display_names[instance_id] for instance_id in instance_ids)
            )
        return nullcontext()

    def verify_competitor_blocked(self, instance_id: str) -> None:
        """Confirms a second registry cannot enter while the service bundle is held."""

        if self.lease_registry is None:
            return
        display_name = self.instance_display_names[instance_id]
        competitor = InstanceLeaseRegistry(root=self.lease_registry.root, wait_timeout_seconds=0)
        try:
            competitor.acquire(display_name=display_name)
        except InstanceBusyError:
            with self.lock:
                self.competitor_blocked.add(display_name)
        else:
            competitor.release_all()


class _RecordingRunner:
    """Records one serial fake castle execution."""

    def __init__(self, factory: _RecordingFactory, instance_id: str) -> None:
        """Stores shared recording state."""

        self.factory = factory
        self.instance_id = instance_id

    def run_castle(self, *, target, boundary) -> DailyCastleRunSummary:
        """Records concurrency, waits briefly, and returns success."""

        del boundary
        self.factory.verify_competitor_blocked(self.instance_id)
        with self.factory.lock:
            self.factory.active_instances += 1
            active = self.factory.active_by_instance.get(self.instance_id, 0) + 1
            self.factory.active_by_instance[self.instance_id] = active
            self.factory.maximum_active_by_instance[self.instance_id] = max(
                active,
                self.factory.maximum_active_by_instance.get(self.instance_id, 0),
            )
            self.factory.order_by_instance.setdefault(self.instance_id, []).append(
                f"{target.account_id}/{target.castle_ref}"
            )
            if self.factory.active_instances >= 2:
                self.factory.overlapped.set()
        time.sleep(0.02)
        with self.factory.lock:
            self.factory.active_instances -= 1
            self.factory.active_by_instance[self.instance_id] -= 1
        return DailyCastleRunSummary(target.account_id, target.castle_ref, True, "ok")


def _target(account_id: str, castle_ref: str) -> DailyMaintenanceTargetConfig:
    """Builds one no-capability target for orchestration tests."""

    return DailyMaintenanceTargetConfig(
        account_id=account_id,
        castle_ref=castle_ref,
        castle=CastleIdentity("K1", castle_ref),
        capabilities=(),
    )


def _path(value: str):
    """Builds a compact pathlib value without repeating imports in fixtures."""

    from pathlib import Path

    return Path(value)


if __name__ == "__main__":
    unittest.main()
