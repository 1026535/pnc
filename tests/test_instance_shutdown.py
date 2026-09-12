"""Durable, lease-aware BlueStacks phase shutdown tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import unittest

from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.instance_shutdown import (
    BlueStacksStaleInstanceShutdownReconciler,
    InstanceShutdownIntent,
    InstanceShutdownIntentStore,
    PowerShellBlueStacksInstanceCloser,
    StaleShutdownDisposition,
)
from pnc_automation.core.config.host import (
    AccountBinding,
    BlueStacksHostConfig,
    BlueStacksInstanceBinding,
    BlueStacksMemoryPolicy,
    LiveAutomationRole,
)
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
)


@dataclass(slots=True)
class _SequencedRunningSource:
    """Returns deterministic process snapshots for reconcile and shutdown waits."""

    snapshots: tuple[tuple[BlueStacksRunningInstance, ...], ...]
    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        """Returns the next snapshot, repeating the final state."""

        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


@dataclass(slots=True)
class _RecordingStopper:
    """Records exact process shutdown requests."""

    process_ids: list[int] = field(default_factory=list)

    def stop_process(self, process_id: int) -> None:
        """Records one process id without touching the host."""

        self.process_ids.append(process_id)


class InstanceShutdownTests(unittest.TestCase):
    """Validates durable intent and abandoned-phase reconciliation."""

    def test_closer_persists_exact_intent_before_live_work(self) -> None:
        """Records enough identity to recover cleanup after an abrupt agent exit."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = root / "bluestacks.conf"
            store = InstanceShutdownIntentStore(root / "intents")
            closer = PowerShellBlueStacksInstanceCloser(
                running_instance_source=_SequencedRunningSource(((),)),
                metadata_path=metadata_path,
                intent_store=store,
                wall_time=lambda: 123.0,
                intent_id_factory=lambda: "intent-123",
            )

            closer.register_close_intent(_instance(), grace_period_seconds=5.0)

            self.assertEqual(
                store.load_all(),
                (
                    InstanceShutdownIntent(
                        display_name="testing",
                        intent_id="intent-123",
                        instance_id="bs-testing",
                        instance_key="Nougat32_1",
                        process_id=101,
                        metadata_path=str(metadata_path.resolve()),
                        requested_at=123.0,
                        grace_period_seconds=5.0,
                    ),
                ),
            )

    def test_phase_finalizer_waits_then_reacquires_before_exact_process_shutdown(self) -> None:
        """Makes the instance available during grace and validates ownership again afterward."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = root / "bluestacks.conf"
            store = InstanceShutdownIntentStore(root / "intents")
            lease_root = root / "leases"
            owner = InstanceLeaseRegistry(root=lease_root)
            lease = owner.acquire(display_name="testing", timeout_seconds=0)
            stopper = _RecordingStopper()
            now = [100.0]
            observed_competitor_claims: list[str] = []

            def wait_for_grace(seconds: float) -> None:
                competitor = InstanceLeaseRegistry(root=lease_root, wait_timeout_seconds=0)
                try:
                    acquired = competitor.acquire(display_name="testing")
                    observed_competitor_claims.append(acquired.display_name)
                finally:
                    competitor.release_all()
                now[0] += seconds

            closer = PowerShellBlueStacksInstanceCloser(
                running_instance_source=_SequencedRunningSource(
                    (
                        (_running(101),),
                        (),
                    )
                ),
                process_stopper=stopper,
                poll_interval_seconds=0,
                sleep=wait_for_grace,
                metadata_path=metadata_path,
                intent_store=store,
                wall_time=lambda: now[0],
                intent_id_factory=lambda: "intent-close",
                lease_registry_factory=lambda: InstanceLeaseRegistry(
                    root=lease_root,
                    wait_timeout_seconds=0,
                ),
            )
            intent_id = closer.register_close_intent(_instance(), grace_period_seconds=5.0)

            lease.release(
                finalizer=lambda: closer.finalize_close_intent(
                    _instance(),
                    intent_id=intent_id,
                )
            )

            self.assertEqual(observed_competitor_claims, ["testing"])
            self.assertEqual(stopper.process_ids, [101])
            self.assertEqual(store.load_all(), ())

    def test_keep_warm_task_during_grace_cancels_pending_shutdown(self) -> None:
        """Does not stop an instance claimed for newly arrived follow-up work."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = root / "bluestacks.conf"
            store = InstanceShutdownIntentStore(root / "intents")
            lease_root = root / "leases"
            owner = InstanceLeaseRegistry(root=lease_root)
            lease = owner.acquire(display_name="testing", timeout_seconds=0)
            stopper = _RecordingStopper()
            now = [100.0]
            delays: list[float] = []

            def claim_follow_up_work(seconds: float) -> None:
                delays.append(seconds)
                follow_up = InstanceLeaseRegistry(root=lease_root, wait_timeout_seconds=0)
                try:
                    follow_up.acquire(display_name="testing")
                    closer.cancel_close_intent(_instance())
                finally:
                    follow_up.release_all()
                now[0] += seconds

            closer = PowerShellBlueStacksInstanceCloser(
                running_instance_source=_SequencedRunningSource(((_running(101),),)),
                process_stopper=stopper,
                sleep=claim_follow_up_work,
                metadata_path=metadata_path,
                intent_store=store,
                wall_time=lambda: now[0],
                intent_id_factory=lambda: "intent-cancel",
                lease_registry_factory=lambda: InstanceLeaseRegistry(
                    root=lease_root,
                    wait_timeout_seconds=0,
                ),
            )
            intent_id = closer.register_close_intent(_instance(), grace_period_seconds=120.0)

            lease.release(
                finalizer=lambda: closer.finalize_close_intent(
                    _instance(),
                    intent_id=intent_id,
                )
            )

            self.assertEqual(stopper.process_ids, [])
            self.assertEqual(delays, [5.0])
            self.assertEqual(store.load_all(), ())

    def test_reconciler_does_not_close_while_an_agent_lease_is_active(self) -> None:
        """Leaves durable intent pending throughout another active task series."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = _write_metadata(root)
            store = _save_intent(root, metadata_path)
            lease_root = root / "leases"
            owner = InstanceLeaseRegistry(root=lease_root)
            owner.acquire(display_name="testing")
            stopper = _RecordingStopper()
            reconciler = _reconciler(
                root=root,
                metadata_path=metadata_path,
                store=store,
                source=_SequencedRunningSource(((_running(101),),)),
                stopper=stopper,
                lease_root=lease_root,
            )
            try:
                result = reconciler.reconcile_all()
            finally:
                owner.release_all()

            self.assertEqual(result[0].disposition, StaleShutdownDisposition.BUSY)
            self.assertEqual(stopper.process_ids, [])
            self.assertEqual(len(store.load_all()), 1)

    def test_reconciler_starts_a_grace_window_after_detecting_an_idle_abandoned_phase(self) -> None:
        """Requires one full quiescence interval before crash recovery shuts down."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = _write_metadata(root)
            store = InstanceShutdownIntentStore(root / "intents")
            store.save(
                InstanceShutdownIntent(
                    display_name="testing",
                    intent_id="intent-abandoned",
                    instance_id="bs-testing",
                    instance_key="Nougat32_1",
                    process_id=101,
                    metadata_path=str(metadata_path.resolve()),
                    requested_at=123.0,
                    grace_period_seconds=5.0,
                )
            )
            stopper = _RecordingStopper()
            now = [200.0]
            reconciler = _reconciler(
                root=root,
                metadata_path=metadata_path,
                store=store,
                source=_SequencedRunningSource(
                    (
                        (_running(101),),
                        (_running(101),),
                        (),
                    )
                ),
                stopper=stopper,
                lease_root=root / "leases",
                wall_time=lambda: now[0],
            )

            first = reconciler.reconcile_all()
            now[0] = 204.0
            second = reconciler.reconcile_all()
            now[0] = 205.0
            third = reconciler.reconcile_all()

            self.assertEqual(first[0].disposition, StaleShutdownDisposition.WAITING)
            self.assertEqual(second[0].disposition, StaleShutdownDisposition.WAITING)
            self.assertEqual(third[0].disposition, StaleShutdownDisposition.CLOSED)
            self.assertEqual(stopper.process_ids, [101])
            self.assertEqual(store.load_all(), ())

    def test_reconciler_closes_an_abandoned_exact_process_when_idle(self) -> None:
        """Reclaims an explicitly managed process after its crashed owner releases the lease."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = _write_metadata(root)
            store = _save_intent(root, metadata_path)
            stopper = _RecordingStopper()
            source = _SequencedRunningSource(
                (
                    (_running(101),),
                    (_running(101),),
                    (),
                )
            )
            reconciler = _reconciler(
                root=root,
                metadata_path=metadata_path,
                store=store,
                source=source,
                stopper=stopper,
                lease_root=root / "leases",
            )

            result = reconciler.reconcile_all()

            self.assertEqual(result[0].disposition, StaleShutdownDisposition.CLOSED)
            self.assertEqual(stopper.process_ids, [101])
            self.assertEqual(store.load_all(), ())

    def test_reconciler_never_closes_a_replacement_process(self) -> None:
        """Invalidates stale intent when the instance key now belongs to another PID."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = _write_metadata(root)
            store = _save_intent(root, metadata_path)
            stopper = _RecordingStopper()
            reconciler = _reconciler(
                root=root,
                metadata_path=metadata_path,
                store=store,
                source=_SequencedRunningSource(((_running(202),),)),
                stopper=stopper,
                lease_root=root / "leases",
            )

            result = reconciler.reconcile_all()

            self.assertEqual(result[0].disposition, StaleShutdownDisposition.BLOCKED)
            self.assertEqual(result[0].failure_phase, "identity_changed")
            self.assertEqual(stopper.process_ids, [])
            self.assertEqual(store.load_all(), ())

    def test_reconciler_never_closes_an_instance_reassigned_to_read_only(self) -> None:
        """Applies current flexible role authority before abandoned-phase cleanup."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_path = _write_metadata(root)
            store = _save_intent(root, metadata_path)
            stopper = _RecordingStopper()
            reconciler = _reconciler(
                root=root,
                metadata_path=metadata_path,
                store=store,
                source=_SequencedRunningSource(((_running(101),),)),
                stopper=stopper,
                lease_root=root / "leases",
                roles=frozenset({LiveAutomationRole.READ_ONLY}),
            )

            result = reconciler.reconcile_all()

            self.assertEqual(result[0].disposition, StaleShutdownDisposition.BLOCKED)
            self.assertEqual(result[0].failure_phase, "role_revoked")
            self.assertEqual(stopper.process_ids, [])
            self.assertEqual(store.load_all(), ())


def _reconciler(
    *,
    root: Path,
    metadata_path: Path,
    store: InstanceShutdownIntentStore,
    source: _SequencedRunningSource,
    stopper: _RecordingStopper,
    lease_root: Path,
    roles: frozenset[LiveAutomationRole] = frozenset({LiveAutomationRole.LIVE_TESTING}),
    wall_time: Callable[[], float] = lambda: 1_000.0,
) -> BlueStacksStaleInstanceShutdownReconciler:
    """Builds one deterministic reconciler with fresh dynamic role authority."""

    config = BlueStacksHostConfig(
        config_path=root / "accounts.yaml",
        metadata_path=metadata_path,
        instances=(BlueStacksInstanceBinding(id="bs-testing", display_name="testing"),),
        accounts=(
            AccountBinding(
                id="account-testing",
                instance_id="bs-testing",
                live_roles=roles,
            ),
        ),
        memory_policy=BlueStacksMemoryPolicy(enabled=True),
    )
    return BlueStacksStaleInstanceShutdownReconciler(
        config_provider=lambda: config,
        resolver=BlueStacksInstanceResolver(
            config_path=metadata_path,
            running_instance_source=source,
        ),
        intent_store=store,
        lease_registry_factory=lambda: InstanceLeaseRegistry(
            root=lease_root,
            wait_timeout_seconds=0,
        ),
        process_stopper=stopper,
        poll_interval_seconds=0,
        sleep=lambda _: None,
        wall_time=wall_time,
    )


def _save_intent(root: Path, metadata_path: Path) -> InstanceShutdownIntentStore:
    """Persists one exact test-process shutdown intent."""

    store = InstanceShutdownIntentStore(root / "intents")
    store.save(
        InstanceShutdownIntent(
            display_name="testing",
            intent_id="intent-existing",
            instance_id="bs-testing",
            instance_key="Nougat32_1",
            process_id=101,
            metadata_path=str(metadata_path.resolve()),
            requested_at=123.0,
            grace_period_seconds=5.0,
            not_before=123.0,
        )
    )
    return store


def _write_metadata(root: Path) -> Path:
    """Writes the minimum BlueStacks metadata needed for identity revalidation."""

    path = root / "bluestacks.conf"
    path.write_text(
        'bst.instance.Nougat32_1.display_name="testing"\n'
        'bst.instance.Nougat32_1.status.adb_port="5566"\n',
        encoding="utf-8",
    )
    return path


def _instance() -> BlueStacksInstance:
    """Returns one resolved test instance."""

    return BlueStacksInstance(
        id="bs-testing",
        display_name="testing",
        device_id="127.0.0.1:5566",
        app_package="com.global.tmslg",
        host_instance_key="Nougat32_1",
        process_id=101,
        started_by_resolver=True,
    )


def _running(process_id: int) -> BlueStacksRunningInstance:
    """Returns one deterministic running player process."""

    return BlueStacksRunningInstance(
        process_id=process_id,
        instance_key="Nougat32_1",
        command_line="HD-Player.exe --instance Nougat32_1",
    )


if __name__ == "__main__":
    unittest.main()
