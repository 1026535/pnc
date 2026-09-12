"""Cross-process ownership tests for emulator instance leases."""

from __future__ import annotations

import tempfile
import json
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from pnc_automation.core.errors import InstanceBusyError
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry

from tests.support.paths import REPOSITORY_ROOT


class InstanceLeaseRegistryTests(unittest.TestCase):
    """Validates fail-fast native locking and process-local re-entrancy."""

    def test_same_registry_ref_counts_one_process_lease(self) -> None:
        """Allows nested runtime objects to release independently without dropping ownership early."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            registry = InstanceLeaseRegistry(root=Path(temporary_directory))
            try:
                first = registry.acquire(display_name="testing")
                second = registry.acquire(display_name="TESTING")
                self.assertIsNot(first, second)
                first.release()
                with self.assertRaises(InstanceBusyError):
                    competitor = InstanceLeaseRegistry(root=Path(temporary_directory), wait_timeout_seconds=0)
                    try:
                        competitor.acquire(display_name="testing")
                    finally:
                        competitor.release_all()
                second.release()
                reacquired = InstanceLeaseRegistry(root=Path(temporary_directory), wait_timeout_seconds=0)
                try:
                    self.assertEqual(reacquired.acquire(display_name="testing").display_name, "testing")
                finally:
                    reacquired.release_all()
            finally:
                registry.release_all()

    def test_reacquisition_after_contention_writes_one_readable_owner_document(self) -> None:
        """Replaces owner metadata when a waiting process-shaped registry reacquires the lock."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            owner = InstanceLeaseRegistry(root=root)
            contender = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            owner_lease = owner.acquire(display_name="testing")
            lock_path = owner_lease.path
            try:
                with self.assertRaises(InstanceBusyError):
                    contender.acquire(display_name="testing")
                owner_lease.release()
                reacquired = contender.acquire(display_name="testing")
                try:
                    with lock_path.open("rb") as handle:
                        handle.seek(1)
                        metadata = json.loads(handle.read().decode("utf-8"))
                    self.assertEqual(metadata["display_name"], "testing")
                    self.assertIsInstance(metadata["pid"], int)
                    self.assertEqual(set(metadata), {"acquired_at", "display_name", "pid"})
                finally:
                    reacquired.release()
            finally:
                owner.release_all()
                contender.release_all()

    def test_reacquisition_replaces_owner_metadata_without_appending_json(self) -> None:
        """Keeps the lock diagnostic as one readable JSON document after reuse."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry = InstanceLeaseRegistry(root=root)
            first = registry.acquire(display_name="testing")
            lock_path = first.path
            first.release()
            second = registry.acquire(display_name="testing")
            try:
                with lock_path.open("rb") as handle:
                    handle.seek(1)
                    metadata = json.loads(handle.read().decode("utf-8"))
                self.assertEqual(metadata["display_name"], "testing")
                self.assertIsInstance(metadata["pid"], int)
                self.assertEqual(metadata["acquired_at"], metadata["acquired_at"].strip())
            finally:
                second.release()

    def test_competing_registry_fails_without_waiting(self) -> None:
        """Rejects another process-shaped registry while the instance lock is held."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            owner = InstanceLeaseRegistry(root=root)
            competitor = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            try:
                owner.acquire(display_name="serious_stuff")
                with self.assertRaisesRegex(InstanceBusyError, "owned by another PNC process") as raised:
                    competitor.acquire(display_name="serious_stuff")
                self.assertEqual(raised.exception.details["display_name"], "serious_stuff")
                self.assertIsInstance(raised.exception.details["owner_pid"], int)
            finally:
                competitor.release_all()
                owner.release_all()

    def test_failed_bundle_releases_every_partial_lock(self) -> None:
        """Prevents hold-and-wait deadlock when a later sorted instance is busy."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            owner = InstanceLeaseRegistry(root=root)
            competitor = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            observer = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            try:
                owner.acquire(display_name="z_busy")
                with self.assertRaises(InstanceBusyError):
                    competitor.acquire_many(("a_available", "z_busy"))
                recovered = observer.acquire(display_name="a_available")
                self.assertEqual(recovered.display_name, "a_available")
            finally:
                observer.release_all()
                competitor.release_all()
                owner.release_all()

    def test_released_instance_can_be_acquired_again(self) -> None:
        """Relies on native lock release rather than stale metadata after a process exits."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = InstanceLeaseRegistry(root=root)
            second = InstanceLeaseRegistry(root=root)
            first.acquire(display_name="157_farm")
            first.release_all()
            try:
                lease = second.acquire(display_name="157_farm")
                self.assertEqual(lease.display_name, "157_farm")
            finally:
                second.release_all()

    def test_waiting_registry_acquires_instance_after_owner_releases(self) -> None:
        """Waits boundedly instead of failing while a healthy owner is finishing."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            owner = InstanceLeaseRegistry(root=root)
            waiter = InstanceLeaseRegistry(
                root=root,
                wait_timeout_seconds=1,
                poll_interval_seconds=0.01,
            )
            owner.acquire(display_name="testing")
            release_thread = threading.Thread(
                target=lambda: (time.sleep(0.05), owner.release_all()),
            )
            release_thread.start()
            try:
                lease = waiter.acquire(display_name="testing")
                self.assertEqual(lease.display_name, "testing")
            finally:
                release_thread.join()
                waiter.release_all()

    def test_child_process_crash_releases_temp_lease(self) -> None:
        """Confirms native temp-root locking is released when an owner process exits abruptly."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            child_script = (
                "import os, sys; "
                "from pathlib import Path; "
                "from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry; "
                "registry = InstanceLeaseRegistry(root=Path(sys.argv[1]), wait_timeout_seconds=0); "
                "registry.acquire(display_name='testing'); "
                "os._exit(17)"
            )
            child = subprocess.run(
                [sys.executable, "-c", child_script, str(root)],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(child.returncode, 17)
            competitor = InstanceLeaseRegistry(root=root, wait_timeout_seconds=0)
            try:
                self.assertEqual(competitor.acquire(display_name="testing").display_name, "testing")
            finally:
                competitor.release_all()


if __name__ == "__main__":
    unittest.main()
