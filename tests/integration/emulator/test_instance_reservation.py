"""Host-only integration tests for agent-scoped long instance reservations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.bluestacks_management.instance_reservation import (
    RESERVATION_RECEIPT_ENV,
    InstanceReservation,
    InstanceReservationError,
    InstanceReservationStore,
)
from pnc_automation.core.errors import ConfigurationError, InstanceBusyError, InstanceReservedError
from tests.support.paths import REPOSITORY_ROOT

_CHILD_ACQUIRE = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
    registry = InstanceLeaseRegistry(root=Path(sys.argv[1]), wait_timeout_seconds=0)
    try:
        registry.acquire(display_name=sys.argv[2])
    except Exception as error:
        print(type(error).__name__)
        sys.exit(3)
    else:
        print("ACQUIRED")
    finally:
        registry.release_all()
    """
)


class InstanceReservationTests(unittest.TestCase):
    """Proves durable claim ownership, conflicts, expiry, and rollback without ADB."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)
        self.root = Path(self._temp_dir.name)
        self.now = [1_000.0]
        self.store = InstanceReservationStore(lease_root=self.root, now=lambda: self.now[0])
        os.environ.pop(RESERVATION_RECEIPT_ENV, None)

    def tearDown(self) -> None:
        os.environ.pop(RESERVATION_RECEIPT_ENV, None)

    def _registry(self) -> InstanceLeaseRegistry:
        """Builds one process-shaped registry sharing the injected-time store."""

        return InstanceLeaseRegistry(
            root=self.root,
            wait_timeout_seconds=0,
            reservation_store=self.store,
        )

    def _claim(
        self,
        names: tuple[str, ...] = ("Instance A",),
        *,
        scope_id: str = "scope-1",
        label: str = "agent-a",
        duration_seconds: float | None = 600.0,
    ):
        """Claims through one claimant registry and returns its claim handle."""

        return self._registry().claim_reservation(
            names,
            scope_id=scope_id,
            owner_label=label,
            duration_seconds=duration_seconds,
        )

    def _inject_record(
        self,
        names: tuple[str, ...],
        *,
        scope_id: str = "foreign-scope",
        expires_at: float = 9_999.0,
    ) -> None:
        """Writes a foreign record directly, simulating another owner's claim."""

        record = InstanceReservation(
            scope_id=scope_id,
            owner_label="foreign-agent",
            generation="deadbeef" * 4,
            capability_digest="0" * 64,
            instances=names,
            claimed_at=100.0,
            expires_at=expires_at,
            pid=os.getpid(),
        )
        with self.store.metadata_lock():
            self.store.save((record,))

    def test_claim_survives_process_exit_and_receipt_owner_acquires(self) -> None:
        """Claim in A exits; B with the receipt acquires; unrelated C conflicts before any ADB use."""

        config_path = self.root / "accounts.yaml"
        config_path.write_text(
            "instances:\n  - id: one\n    display_name: Instance A\n",
            encoding="utf-8",
        )
        claim = subprocess.run(
            [
                sys.executable,
                "-m",
                "pnc_automation.bluestacks_management",
                "claim-reservation",
                "--lease-root",
                str(self.root),
                "--config",
                str(config_path),
                "--instance",
                "Instance A",
                "--scope-id",
                "scope-a",
                "--label",
                "agent-a",
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(claim.returncode, 0, claim.stderr)
        receipt_path = json.loads(claim.stdout)["receipt_path"]
        self.assertTrue(Path(receipt_path).exists())

        env = {**os.environ, RESERVATION_RECEIPT_ENV: receipt_path}
        owner = subprocess.run(
            [sys.executable, "-c", _CHILD_ACQUIRE, str(self.root), "Instance A"],
            cwd=REPOSITORY_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(owner.returncode, 0, owner.stderr + owner.stdout)
        self.assertIn("ACQUIRED", owner.stdout)

        foreign_env = {key: value for key, value in os.environ.items() if key != RESERVATION_RECEIPT_ENV}
        foreign = subprocess.run(
            [sys.executable, "-c", _CHILD_ACQUIRE, str(self.root), "Instance A"],
            cwd=REPOSITORY_ROOT,
            env=foreign_env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(foreign.returncode, 3, foreign.stderr + foreign.stdout)
        self.assertIn("InstanceReservedError", foreign.stdout)

    def test_foreign_reservation_conflicts_before_native_lock_attempt(self) -> None:
        """The admission precheck rejects before touching any native instance lock."""

        self._claim()
        registry = self._registry()
        with patch.object(
            InstanceLeaseRegistry,
            "_acquire_once",
            side_effect=AssertionError("native lock attempted"),
        ):
            with self.assertRaises(InstanceReservedError):
                registry.acquire(display_name="Instance A")

    def test_owner_acquires_and_reenters_under_receipt(self) -> None:
        """The receipt owner admits ordinary task leases and reentry under its claim."""

        claim = self._claim()
        with patch.dict(os.environ, {RESERVATION_RECEIPT_ENV: str(claim.receipt_path)}):
            registry = self._registry()
            first = registry.acquire(display_name="Instance A")
            second = registry.acquire(display_name="Instance A")
            self.assertEqual(first.display_name, second.display_name)
            registry.release_all()

    def test_same_process_reentry_cannot_bypass_foreign_reservation(self) -> None:
        """A reservation published after admission still rejects the holder's reentry."""

        registry = self._registry()
        registry.acquire(display_name="Instance A")
        self._inject_record(("Instance A",))
        with self.assertRaises(InstanceReservedError):
            registry.acquire(display_name="Instance A")
        registry.release_all()

    def test_expired_reservation_blocks_new_claim_until_task_release(self) -> None:
        """A held task lock stays authoritative after the long record expires."""

        self._claim(duration_seconds=100.0)
        self.now[0] = 1_500.0
        holder = self._registry()
        holder.acquire(display_name="Instance A")  # Expired reservations admit new work.
        with self.assertRaises(InstanceBusyError):
            self._claim(scope_id="scope-2", label="agent-b")
        holder.release_all()
        reclaim = self._claim(scope_id="scope-2", label="agent-b")
        self.assertEqual(reclaim.reservation.scope_id, "scope-2")

    def test_stale_receipt_cannot_renew_release_or_acquire_replacement(self) -> None:
        """Stale credentials fail against a replacement generation on every surface."""

        stale = self._claim(scope_id="scope-1")
        self._registry().release_reservation(stale.receipt_path)
        replacement = self._claim(scope_id="scope-1", label="agent-b")

        with self.assertRaises(InstanceReservationError):
            self._registry().renew_reservation(stale.receipt_path)
        with self.assertRaises(InstanceReservationError):
            self._registry().release_reservation(stale.receipt_path)
        self.assertEqual(self.store.load()[0].generation, replacement.reservation.generation)
        with patch.dict(os.environ, {RESERVATION_RECEIPT_ENV: str(stale.receipt_path)}):
            with self.assertRaises(InstanceReservedError):
                self._registry().acquire(display_name="Instance A")

    def test_bundle_claim_rolls_back_when_one_member_is_task_busy(self) -> None:
        """A multi-instance claim frees every acquired member after a conflict."""

        holder = self._registry()
        holder.acquire(display_name="Instance B")
        with self.assertRaises(InstanceBusyError):
            self._claim(("Instance A", "Instance B"))
        observer = self._registry()
        observer.acquire(display_name="Instance A")
        self.assertEqual(self.store.load(), ())
        holder.release_all()
        observer.release_all()

    def test_task_bundle_rolls_back_when_member_reserved_mid_acquire(self) -> None:
        """A reservation published during admission rolls back newly taken locks."""

        registry = self._registry()
        real_acquire_once = InstanceLeaseRegistry._acquire_once

        def acquire_then_publish(lease_registry, *, lease_key: str, display_name: str):
            lease = real_acquire_once(lease_registry, lease_key=lease_key, display_name=display_name)
            if display_name == "Instance A":
                self._inject_record(("Instance B",))
            return lease

        with patch.object(InstanceLeaseRegistry, "_acquire_once", new=acquire_then_publish):
            with self.assertRaises(InstanceReservedError):
                registry.acquire_many(("Instance A", "Instance B"))

        observer = self._registry()
        observer.acquire(display_name="Instance A")
        observer.release_all()

    def test_renew_extends_live_claim_and_late_renewal_fails(self) -> None:
        """Renewal requires a live matching generation; expiry revokes it."""

        claim = self._claim(duration_seconds=100.0)
        renewed = self._registry().renew_reservation(claim.receipt_path, duration_seconds=50.0)
        self.assertEqual(renewed.expires_at, 1_050.0)
        self.now[0] = 2_000.0
        with self.assertRaises(InstanceReservationError):
            self._registry().renew_reservation(claim.receipt_path)

    def test_expired_reservation_does_not_block_task_acquire(self) -> None:
        """Expiry admits ordinary task work without any renewal."""

        self._claim(duration_seconds=10.0)
        self.now[0] = 2_000.0
        registry = self._registry()
        registry.acquire(display_name="Instance A")
        registry.release_all()

    def test_release_is_idempotent_and_removes_the_whole_scope(self) -> None:
        """Release frees every bundle member and repeated release is harmless."""

        claim = self._claim(("Instance A", "Instance B"))
        released = self._registry().release_reservation(claim.receipt_path)
        self.assertIsNotNone(released)
        self.assertEqual(self.store.load(), ())
        self.assertIsNone(self._registry().release_reservation(claim.receipt_path))
        registry = self._registry()
        registry.acquire(display_name="Instance B")
        registry.release_all()

    def test_concurrent_claim_and_task_have_exactly_one_winner(self) -> None:
        """A claim racing an ordinary task lease serializes to one admission."""

        claim_result: list[object] = []
        acquire_result: list[object] = []

        def run_claim() -> None:
            try:
                claim_result.append(self._claim(scope_id="scope-race"))
            except Exception as error:
                claim_result.append(error)

        def run_acquire() -> None:
            registry = self._registry()
            try:
                acquire_result.append(registry.acquire(display_name="Instance A"))
            except Exception as error:
                acquire_result.append(error)

        threads = [threading.Thread(target=run_claim), threading.Thread(target=run_acquire)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        winners = [
            outcome
            for outcome in (*claim_result, *acquire_result)
            if not isinstance(outcome, Exception)
        ]
        losers = [outcome for outcome in (*claim_result, *acquire_result) if isinstance(outcome, Exception)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(losers), 1)
        for outcome in acquire_result:
            if hasattr(outcome, "release"):
                outcome.release()

    def test_concurrent_claims_have_exactly_one_winner(self) -> None:
        """Two racing claims over the same instance admit one owner."""

        outcomes: list[object] = []

        def run_claim(scope_id: str) -> None:
            try:
                outcomes.append(self._claim(scope_id=scope_id))
            except Exception as error:
                outcomes.append(error)

        threads = [
            threading.Thread(target=run_claim, args=("scope-1",)),
            threading.Thread(target=run_claim, args=("scope-2",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(len(self.store.load()), 1)

    def test_unrelated_instance_is_not_blocked(self) -> None:
        """A reservation only covers its declared bundle."""

        self._claim()
        registry = self._registry()
        registry.acquire(display_name="Instance B")
        registry.release_all()

    def test_malformed_snapshot_fails_closed(self) -> None:
        """Corrupt authoritative state refuses admission instead of guessing."""

        self.store.lease_root.mkdir(parents=True, exist_ok=True)
        self.store.snapshot_path.write_bytes(b'{"version": 1, "reservations": "bogus"}')
        with self.assertRaises(ConfigurationError):
            self._registry().acquire(display_name="Instance A")

    def test_snapshot_rejects_string_instances_and_bool_version(self) -> None:
        """Persisted instances must be a list and version the exact integer 1."""

        self.store.lease_root.mkdir(parents=True, exist_ok=True)
        record = {
            "scope_id": "foreign",
            "owner_label": "agent",
            "generation": "g",
            "capability_digest": "0" * 64,
            "instances": "Instance A",
            "claimed_at": 100.0,
            "expires_at": 9_999.0,
            "pid": os.getpid(),
        }
        self.store.snapshot_path.write_bytes(
            json.dumps({"version": 1, "reservations": [record]}).encode("utf-8")
        )
        with self.assertRaises(ConfigurationError):
            self.store.load()

        self.store.snapshot_path.write_bytes(
            json.dumps({"version": True, "reservations": []}).encode("utf-8")
        )
        with self.assertRaises(ConfigurationError):
            self.store.load()

    def test_receipt_rejects_bool_version(self) -> None:
        """A receipt must carry the exact integer schema version, not a bool."""

        self.store.receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = self.store.receipts_dir / "bogus.json"
        receipt_path.write_bytes(
            json.dumps(
                {
                    "version": True,
                    "scope_id": "scope-1",
                    "generation": "g",
                    "capability": "c",
                }
            ).encode("utf-8")
        )
        with self.assertRaises(InstanceReservationError):
            self.store.read_receipt(receipt_path)

    def test_status_reports_reservation_and_task_lock_states(self) -> None:
        """Status exposes both dimensions and derived claimability without ADB."""

        self._claim(("Instance A", "Instance B"), duration_seconds=100.0)
        holder = self._registry()
        holder.acquire(display_name="Instance C")

        status = {entry.display_name: entry for entry in self._registry().reservation_status(
            ("Instance A", "Instance B", "Instance C", "Instance D")
        )}
        self.assertEqual(status["Instance A"].reservation_state, "active")
        self.assertEqual(status["Instance A"].task_lock_state, "idle")
        self.assertFalse(status["Instance A"].claimable)
        self.assertEqual(status["Instance A"].scope_id, "scope-1")
        self.assertEqual(status["Instance B"].reservation_state, "active")
        self.assertEqual(status["Instance C"].reservation_state, "none")
        self.assertEqual(status["Instance C"].task_lock_state, "busy")
        self.assertFalse(status["Instance C"].claimable)
        self.assertEqual(status["Instance D"].reservation_state, "none")
        self.assertEqual(status["Instance D"].task_lock_state, "idle")
        self.assertTrue(status["Instance D"].claimable)

        self.now[0] = 2_000.0
        status = {entry.display_name: entry for entry in self._registry().reservation_status(("Instance A",))}
        self.assertEqual(status["Instance A"].reservation_state, "expired")
        self.assertTrue(status["Instance A"].claimable)
        holder.release_all()

    def test_status_and_errors_never_expose_capability_material(self) -> None:
        """Snapshots, status, and conflict errors carry digests, never capabilities."""

        claim = self._claim()
        capability = self.store.read_receipt(claim.receipt_path).capability
        snapshot_text = self.store.snapshot_path.read_text(encoding="utf-8")
        self.assertNotIn(capability, snapshot_text)
        self.assertIn(claim.reservation.capability_digest, snapshot_text)

        status = self._registry().reservation_status(("Instance A",))[0]
        self.assertNotIn(capability, repr(status))
        try:
            self._registry().acquire(display_name="Instance A")
        except InstanceReservedError as error:
            self.assertNotIn(capability, str(error))
            self.assertNotIn(capability, repr(error.details))
        else:
            self.fail("Foreign admission unexpectedly succeeded.")

    def test_claim_rejects_invalid_inputs(self) -> None:
        """Bundle, label, and duration validation happens before any lock attempt."""

        registry = self._registry()
        with self.assertRaises(ValueError):
            registry.claim_reservation(("Instance A", "instance a"), scope_id="s", owner_label="l")
        with self.assertRaises(ValueError):
            registry.claim_reservation(("Instance A",), scope_id=" ", owner_label="l")
        with self.assertRaises(ValueError):
            registry.claim_reservation(("Instance A",), scope_id="s", owner_label="l", duration_seconds=0)
        self.assertEqual(self.store.load(), ())


if __name__ == "__main__":
    unittest.main()
