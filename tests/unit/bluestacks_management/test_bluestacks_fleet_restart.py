"""Whole-fleet BlueStacks maintenance restart tests.

Cohesion exception: one fleet-restart transaction matrix shares fake host sources,
stopper, and launcher across snapshot, lease, identity, and failure boundaries.
"""

from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pnc_automation.bluestacks_management.fleet_restart import (
    BlueStacksFleetRestarter,
    current_maintenance_pre_stop_deadline,
    is_maintenance_window,
)
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseRegistry
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
    BlueStacksRunningInstance,
)


@dataclass
class _MutableSource:
    running: tuple[BlueStacksRunningInstance, ...]

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        return self.running


@dataclass
class _Stopper:
    source: _MutableSource
    stopped: list[int]
    failures: frozenset[int] = frozenset()
    fail_after_stop: frozenset[int] = frozenset()
    preserve_processes: frozenset[int] = frozenset()

    def stop_process(self, process_id: int) -> None:
        if process_id in self.failures:
            if process_id in self.fail_after_stop:
                self.source.running = tuple(item for item in self.source.running if item.process_id != process_id)
            raise RuntimeError(f"stop failed for {process_id}")
        self.stopped.append(process_id)
        if process_id in self.preserve_processes:
            return
        self.source.running = tuple(item for item in self.source.running if item.process_id != process_id)


@dataclass
class _FailingCallSource:
    """Injects one bounded discovery failure while retaining the mutable fixture state."""

    source: _MutableSource
    fail_on_calls: frozenset[int]
    error_message: str = "discovery failed"
    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        self.calls += 1
        if self.calls in self.fail_on_calls:
            raise RuntimeError(f"{self.error_message} on call {self.calls}")
        return self.source.list_running_instances()


@dataclass
class _MutatingSource:
    """Applies one deterministic source-side event immediately before a snapshot."""

    source: _MutableSource
    event_on_call: int
    event: Callable[[], None]
    calls: int = 0

    def list_running_instances(self) -> tuple[BlueStacksRunningInstance, ...]:
        self.calls += 1
        if self.calls == self.event_on_call:
            self.event()
        return self.source.list_running_instances()


@dataclass
class _Launcher:
    source: _MutableSource
    launched: list[str]
    failures: frozenset[str] = frozenset()
    preserve_processes: frozenset[str] = frozenset()

    def launch_instance(self, instance_key: str) -> None:
        if instance_key in self.failures:
            raise RuntimeError(f"launch failed for {instance_key}")
        self.launched.append(instance_key)
        if instance_key in self.preserve_processes:
            return
        self.source.running += (_running(instance_key=instance_key, process_id=200 + len(self.launched)),)


class BlueStacksFleetRestarterTests(unittest.TestCase):
    """Locks the scheduled restart to the open configured subset."""

    def test_restarts_only_instances_open_at_the_initial_snapshot(self) -> None:
        """A configured but closed instance remains closed after fleet maintenance."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(result.display_names, ("testing",))
            self.assertEqual(stopper.stopped, [101])
            self.assertEqual(launcher.launched, ["Nougat32"])
            self.assertNotIn("Pie64", launcher.launched)

    def test_empty_running_snapshot_is_a_noop(self) -> None:
        """The maintenance boundary does not start any closed configured instance."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(())
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(result.display_names, ())
            self.assertEqual(stopper.stopped, [])
            self.assertEqual(launcher.launched, [])

    def test_stop_failure_does_not_prevent_later_stops_and_recovery(self) -> None:
        """Continues the bundle and recovers every instance whose stop succeeded."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            stopper = _Stopper(source=source, stopped=[], failures=frozenset({101}))
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(stopper.stopped, [102])
            self.assertEqual(launcher.launched, ["Pie64"])
            self.assertEqual(result.failures[0].phase, "stop")
            self.assertEqual(result.failures[0].display_name, "testing")

    def test_launch_failure_does_not_prevent_later_relaunches(self) -> None:
        """Attempts recovery for every successfully stopped instance after one launch error."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[], failures=frozenset({"Nougat32"}))
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(stopper.stopped, [101, 102])
            self.assertEqual(launcher.launched, ["Pie64"])
            self.assertEqual(result.failures[0].phase, "launch")
            self.assertEqual(result.failures[0].display_name, "testing")

    def test_stop_wait_failure_with_old_process_present_withholds_relaunch(self) -> None:
        """Never launches an instance whose stop request did not remove its old process identity."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            stopper = _Stopper(source=source, stopped=[], preserve_processes=frozenset({101}))
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(stopper.stopped, [101, 102])
            self.assertEqual(launcher.launched, ["Pie64"])
            self.assertEqual(result.display_names, ("main",))
            self.assertEqual(
                [failure.phase for failure in result.failures if failure.display_name == "testing"],
                ["stop_wait", "stop_revalidation"],
            )

    def test_discovery_error_for_later_target_does_not_abandon_earlier_recovery(self) -> None:
        """A per-target enumeration failure still allows a previously stopped target to relaunch."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            failing_source = _FailingCallSource(
                source=source,
                fail_on_calls=frozenset({5}),
                error_message="secret-sentinel",
            )
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(
                root=root,
                source=source,
                stopper=stopper,
                launcher=launcher,
                resolver_source=failing_source,
            )

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, ["Nougat32"])
            self.assertEqual(result.display_names, ("testing",))
            self.assertEqual(
                [(failure.display_name, failure.phase) for failure in result.failures],
                [("main", "stop_revalidation")],
            )
            self.assertNotIn("secret-sentinel", result.failures[0].message)
            self.assertNotIn("secret-sentinel", repr(result.failures[0].details))

    def test_stop_error_after_process_disappears_still_recovers(self) -> None:
        """A stop command error is not treated as fatal when revalidation proves the PID is gone."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(
                source=source,
                stopped=[],
                failures=frozenset({101}),
                fail_after_stop=frozenset({101}),
            )
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing",), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, ["Nougat32"])
            self.assertEqual(result.display_names, ("testing",))
            self.assertEqual(result.failures[0].phase, "stop")

    def test_transient_discovery_error_during_stop_confirmation_recovers_disappeared_process(self) -> None:
        """A dying-process discovery error is retried by the confirmation path before relaunch."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            failing_source = _FailingCallSource(source=source, fail_on_calls=frozenset({3, 4}))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(
                root=root,
                source=source,
                stopper=stopper,
                launcher=launcher,
                resolver_source=failing_source,
            )

            result = restarter.restart_running(("testing",), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, ["Nougat32"])
            self.assertEqual(result.display_names, ("testing",))
            self.assertEqual(result.failures[0].phase, "stop_wait")

    def test_deadline_applies_to_each_new_stop_after_an_earlier_stop(self) -> None:
        """A late target is not newly stopped after the pre-stop safety cutoff."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)
            toronto = ZoneInfo("America/Toronto")
            clock = iter(
                (
                    datetime(2026, 9, 11, 1, 57, tzinfo=toronto),
                    datetime(2026, 9, 11, 1, 57, tzinfo=toronto),
                    datetime(2026, 9, 11, 1, 59, tzinfo=toronto),
                )
            )
            restarter.now = lambda: next(clock)

            result = restarter.restart_running(
                ("testing", "main"),
                lease_timeout_seconds=0,
                pre_stop_deadline=datetime(2026, 9, 11, 1, 58, tzinfo=toronto),
            )

            self.assertEqual(stopper.stopped, [101])
            self.assertEqual(launcher.launched, ["Nougat32"])
            self.assertEqual(result.failures[0].display_name, "main")
            self.assertEqual(result.failures[0].phase, "pre_stop_deadline")

    def test_deadline_is_rechecked_after_running_process_revalidation(self) -> None:
        """A discovery call that crosses the cutoff cannot race into a stop request."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)
            toronto = ZoneInfo("America/Toronto")
            clock = iter(
                (
                    datetime(2026, 9, 11, 1, 57, tzinfo=toronto),
                    datetime(2026, 9, 11, 1, 59, tzinfo=toronto),
                )
            )
            restarter.now = lambda: next(clock)

            result = restarter.restart_running(
                ("testing",),
                lease_timeout_seconds=0,
                pre_stop_deadline=datetime(2026, 9, 11, 1, 58, tzinfo=toronto),
            )

            self.assertEqual(stopper.stopped, [])
            self.assertEqual(launcher.launched, [])
            self.assertEqual(result.failures[0].phase, "pre_stop_deadline")

    def test_late_external_relaunch_is_not_duplicated(self) -> None:
        """A process that appears after stop confirmation wins over a new launch request."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))

            def late_launch() -> None:
                source.running = (_running(instance_key="Nougat32", process_id=202),)

            source_with_event = _MutatingSource(source=source, event_on_call=5, event=late_launch)
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(
                root=root,
                source=source,
                stopper=stopper,
                launcher=launcher,
                resolver_source=source_with_event,
            )

            result = restarter.restart_running(("testing",), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, [])
            self.assertEqual(result.display_names, ())
            self.assertEqual(result.failures[0].phase, "launch_revalidation")

    def test_latest_metadata_mapping_blocks_redirected_relaunch(self) -> None:
        """A changed display-to-instance mapping cannot redirect the original recovery intent."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            host_config = root / "bluestacks.conf"

            def redirect_metadata() -> None:
                host_config.write_text(
                    'bst.instance.Pie64.display_name="testing"\n'
                    'bst.instance.Pie64.status.adb_port="5556"\n',
                    encoding="utf-8",
                )

            source_with_event = _MutatingSource(source=source, event_on_call=4, event=redirect_metadata)
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(
                root=root,
                source=source,
                stopper=stopper,
                launcher=launcher,
                resolver_source=source_with_event,
            )

            result = restarter.restart_running(("testing",), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, [])
            self.assertEqual(result.display_names, ())
            self.assertEqual(result.failures[0].phase, "launch_revalidation")

    def test_launch_wait_failure_is_reported_without_hiding_successful_later_relaunch(self) -> None:
        """Continues recovery while reporting a relaunch that never becomes running."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource(
                (
                    _running(instance_key="Nougat32", process_id=101),
                    _running(instance_key="Pie64", process_id=102),
                )
            )
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[], preserve_processes=frozenset({"Nougat32"}))
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            result = restarter.restart_running(("testing", "main"), lease_timeout_seconds=0)

            self.assertEqual(launcher.launched, ["Nougat32", "Pie64"])
            self.assertEqual(result.display_names, ("main",))
            self.assertEqual(result.failures[0].phase, "launch_wait")

    def test_post_lease_runtime_mapping_must_remain_unique(self) -> None:
        """Rejects an ambiguous host mapping after the complete lease bundle is acquired."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            host_config = root / "bluestacks.conf"
            host_config.write_text(
                'bst.instance.Nougat32.display_name="testing"\n'
                'bst.instance.Nougat32.status.adb_port="5555"\n'
                'bst.instance.Pie64.display_name="testing"\n'
                'bst.instance.Pie64.status.adb_port="5556"\n',
                encoding="utf-8",
            )
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            resolver = BlueStacksInstanceResolver(
                config_path=host_config,
                running_instance_source=source,
                instance_launcher=launcher,
            )
            restarter = BlueStacksFleetRestarter(
                resolver=resolver,
                process_stopper=stopper,
                lease_registry_factory=lambda: InstanceLeaseRegistry(root=root / "leases"),
                state_poll_interval_seconds=0,
            )

            with self.assertRaisesRegex(Exception, "not uniquely mapped"):
                restarter.restart_running(("testing",), lease_timeout_seconds=0)

    def test_pre_stop_deadline_blocks_waited_fleet_before_any_stop(self) -> None:
        """Never begins a stop after the daily-run safety boundary."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)
            toronto = ZoneInfo("America/Toronto")
            restarter.now = lambda: datetime(2026, 9, 11, 1, 59, tzinfo=toronto)

            result = restarter.restart_running(
                ("testing",),
                lease_timeout_seconds=0,
                pre_stop_deadline=datetime(2026, 9, 11, 1, 58, tzinfo=toronto),
            )

            self.assertEqual(stopper.stopped, [])
            self.assertEqual(launcher.launched, [])
            self.assertEqual(result.failures[0].phase, "pre_stop_deadline")

    def test_default_style_naive_clock_is_safe_against_aware_deadline(self) -> None:
        """A datetime.now-style naive injected clock is interpreted in Toronto."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)
            restarter.now = lambda: datetime(2026, 9, 11, 1, 59)

            result = restarter.restart_running(
                ("testing",),
                lease_timeout_seconds=0,
                pre_stop_deadline=datetime(
                    2026,
                    9,
                    11,
                    1,
                    58,
                    tzinfo=ZoneInfo("America/Toronto"),
                ),
            )

            self.assertEqual(stopper.stopped, [])
            self.assertEqual(result.failures[0].phase, "pre_stop_deadline")

    def test_default_clock_is_callable_on_deadline_path(self) -> None:
        """Constructing the restarter with its default clock supports deadline evaluation."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = _MutableSource((_running(instance_key="Nougat32", process_id=101),))
            stopper = _Stopper(source=source, stopped=[])
            launcher = _Launcher(source=source, launched=[])
            restarter = self._restarter(root=root, source=source, stopper=stopper, launcher=launcher)

            self.assertTrue(callable(restarter.now))
            result = restarter.restart_running(
                ("testing",),
                lease_timeout_seconds=0,
                pre_stop_deadline=restarter.now(),
            )

            self.assertEqual(stopper.stopped, [])
            self.assertEqual(result.failures[0].phase, "pre_stop_deadline")

    def test_maintenance_window_clock_contract(self) -> None:
        """The explicit window and pre-stop deadline distinguish all scheduler states."""

        toronto = ZoneInfo("America/Toronto")
        in_window = datetime(2026, 9, 11, 1, 56, tzinfo=toronto)
        after_deadline = datetime(2026, 9, 11, 1, 59, tzinfo=toronto)
        delayed = datetime(2026, 9, 11, 2, 0, tzinfo=toronto)

        self.assertTrue(is_maintenance_window(in_window))
        self.assertTrue(is_maintenance_window(after_deadline))
        self.assertFalse(is_maintenance_window(delayed))
        self.assertEqual(
            current_maintenance_pre_stop_deadline(in_window),
            datetime(2026, 9, 11, 1, 58, tzinfo=toronto),
        )
        self.assertIsNone(current_maintenance_pre_stop_deadline(delayed))

    @staticmethod
    def _restarter(
        *,
        root: Path,
        source: _MutableSource,
        stopper: _Stopper,
        launcher: _Launcher,
        resolver_source: object | None = None,
    ) -> BlueStacksFleetRestarter:
        host_config = root / "bluestacks.conf"
        host_config.write_text(
            'bst.instance.Nougat32.display_name="testing"\n'
            'bst.instance.Nougat32.status.adb_port="5555"\n'
            'bst.instance.Pie64.display_name="main"\n'
            'bst.instance.Pie64.status.adb_port="5556"\n',
            encoding="utf-8",
        )
        resolver = BlueStacksInstanceResolver(
            config_path=host_config,
            running_instance_source=source if resolver_source is None else resolver_source,
            instance_launcher=launcher,
        )
        return BlueStacksFleetRestarter(
            resolver=resolver,
            process_stopper=stopper,
            lease_registry_factory=lambda: InstanceLeaseRegistry(root=root / "leases"),
            state_poll_interval_seconds=0,
        )


def _running(*, instance_key: str, process_id: int) -> BlueStacksRunningInstance:
    return BlueStacksRunningInstance(
        process_id=process_id,
        instance_key=instance_key,
        command_line=f'HD-Player.exe --instance "{instance_key}"',
        working_set_bytes=1024,
    )


if __name__ == "__main__":
    unittest.main()
