"""Focused offline tests for the typed castle-roster refresh port."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult, WorkflowContext
from pnc_automation.app.pnc.domain.castles import (
    CastleIdentity,
    CastleRosterOrdering,
    PncAccountCastleRosterConfig,
)
from pnc_automation.app.automation.refresh_castle_roster import (
    RefreshCastleRosterPolicy,
    RefreshCastleRosterWorkflow,
)
from pnc_automation.app.pnc.domain.castle_roster_scan import castle_roster_scan_identity_key
from pnc_automation.app.entrypoints import api as api_module
from pnc_automation.app.entrypoints.api import AutomationApi, AutomationSession
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.core.errors import TaskVerificationError
from tests.support.pnc.observations import make_entry, make_observation


class RefreshCastleRosterWorkflowTests(unittest.TestCase):
    """Covers complete scans, overlap validation, stability, and no-write failures."""

    def test_full_scan_merges_overlaps_levels_and_preserves_other_accounts(self) -> None:
        """Replaces stale membership while preserving observed ordering and cached level hints."""

        alpha = CastleIdentity("K1", "Alpha", 3)
        bravo = CastleIdentity("K2", "Bravo", 4)
        charlie = CastleIdentity("K3", "Charlie", 5)
        delta = CastleIdentity("K4", "Delta", 6)
        other = CastleIdentity("K9", "Other", 9)
        active = bravo
        with TemporaryDirectory() as temporary_directory:
            store = CastleRosterStore(
                path=Path(temporary_directory) / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="account",
                        castles=(alpha, bravo, CastleIdentity("K8", "Stale", 8)),
                    ),
                    PncAccountCastleRosterConfig(pnc_account_id="other", castles=(other,)),
                ),
            )
            top = _window((alpha, bravo, charlie), current=active)
            advancing = _window((charlie, delta))
            confirming = _window((CastleIdentity("K3", "Charlie", 7), delta))
            context = _FakeContext(top, down=(top, top), up=(advancing, confirming, confirming))

            result = RefreshCastleRosterWorkflow(
                account_id="account",
                pnc_account_id="account",
                active_castle=active,
                roster_store=store,
            ).execute(context)

            self.assertEqual((alpha, bravo, CastleIdentity("K3", "Charlie", 7), delta), result.castles)
            self.assertEqual("full_scan", result.coverage)
            self.assertEqual(2, result.top_swipe_count)
            self.assertEqual(3, result.scan_swipe_count)
            self.assertEqual(2, result.window_count)
            refreshed = store.get("account")
            self.assertIsNotNone(refreshed)
            self.assertEqual((alpha, bravo, CastleIdentity("K3", "Charlie", 7), delta), refreshed.castles)
            self.assertEqual(CastleRosterOrdering.FULL_SCAN, refreshed.ordering)
            self.assertEqual((other,), store.get("other").castles)

    def test_scan_normalizes_overlapping_names_and_active_identity(self) -> None:
        """Matches OCR whitespace, punctuation, and case drift while preserving observed names."""

        top_gimme = CastleIdentity("K1", "Gimme Cookies")
        top_toast = CastleIdentity("K2", "not Toast")
        top_hellound = CastleIdentity("K3", "Lv.6 hellound")
        next_toast = CastleIdentity("K2", "notToast")
        next_hellound = CastleIdentity("K3", "Lv.6 hellound")
        bottom_hellound = CastleIdentity("K3", "Lv-6hellound")
        bottom_new = CastleIdentity("K4", "New Castle")
        active = CastleIdentity("K1", "gimmecookies")
        with TemporaryDirectory() as temporary_directory:
            store = CastleRosterStore(path=Path(temporary_directory) / "castles.yaml")
            top = _window((top_gimme, top_toast, top_hellound), current=active)
            advancing = _window((next_toast, next_hellound))
            bottom = _window((bottom_hellound, bottom_new))
            context = _FakeContext(top, down=(top, top), up=(advancing, bottom, bottom, bottom))

            result = RefreshCastleRosterWorkflow("account", "account", active, store).execute(context)

            self.assertEqual(
                (top_gimme, next_toast, bottom_hellound, bottom_new),
                result.castles,
            )
            self.assertEqual(
                castle_roster_scan_identity_key(top_gimme),
                castle_roster_scan_identity_key(active),
            )

    def test_cached_level_hint_matches_normalized_spelling(self) -> None:
        """Uses a cached level hint when OCR changes only the castle-name spelling."""

        cached = CastleIdentity("K1", "Gimme Cookies", 9)
        observed = CastleIdentity("K1", "gimmecookies")
        active = CastleIdentity("K1", "GIMME COOKIES")
        with TemporaryDirectory() as temporary_directory:
            store = CastleRosterStore(path=Path(temporary_directory) / "castles.yaml")
            store.sync("account", (cached,))
            top = _window((observed,), current=active)
            context = _FakeContext(top, down=(top, top), up=(top, top, top))

            result = RefreshCastleRosterWorkflow("account", "account", active, store).execute(context)

            self.assertEqual((CastleIdentity("K1", "gimmecookies", 9),), result.castles)

    def test_true_name_or_kingdom_difference_breaks_overlap(self) -> None:
        """Keeps true identity changes fail-closed despite tolerant OCR name matching."""

        active = CastleIdentity("K1", "Gimme Cookies")
        cases = (
            (CastleIdentity("K1", "Gimme Cookie"), "name"),
            (CastleIdentity("K2", "gimmecookies"), "kingdom"),
        )
        for next_row, label in cases:
            with self.subTest(label=label), TemporaryDirectory() as temporary_directory:
                path = Path(temporary_directory) / "castles.yaml"
                store = CastleRosterStore(path=path)
                store.sync("account", (active,))
                before_bytes = path.read_bytes()
                top = _window((active,), current=active)
                advancing = _window((next_row,))
                context = _FakeContext(top, down=(top, top), up=(advancing,))

                with self.assertRaises(TaskVerificationError):
                    RefreshCastleRosterWorkflow("account", "account", active, store).execute(context)

                self.assertEqual(before_bytes, path.read_bytes())

    def test_same_window_normalized_duplicate_is_rejected(self) -> None:
        """Rejects two rows collapsing to one kingdom/name scan identity."""

        active = CastleIdentity("K1", "Gimme Cookies")
        duplicate = CastleIdentity("K1", "gimmecookies")
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (active,))
            before_bytes = path.read_bytes()
            top = _window((active, duplicate), current=active)
            context = _FakeContext(top, down=(top, top), up=(top, top))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", active, store).execute(context)

            self.assertEqual(before_bytes, path.read_bytes())

    def test_top_and_end_require_two_unchanged_windows(self) -> None:
        """Does not accept a one-frame stall at either scan boundary."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        active = alpha
        with TemporaryDirectory() as temporary_directory:
            store = CastleRosterStore(path=Path(temporary_directory) / "castles.yaml")
            initial = _window((bravo,))
            top = _window((alpha, bravo), current=active)
            end = _window((bravo,), current=None)
            context = _FakeContext(initial, down=(top, top, top), up=(end, end, end))

            result = RefreshCastleRosterWorkflow(
                account_id="account",
                pnc_account_id="account",
                active_castle=active,
                roster_store=store,
            ).execute(context)

            self.assertEqual(3, result.top_swipe_count)
            self.assertEqual(3, result.scan_swipe_count)

    def test_gap_fails_before_write(self) -> None:
        """Rejects an advancing window without a suffix/prefix overlap and preserves bytes."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        charlie = CastleIdentity("K3", "Charlie", 3)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            original = (CastleIdentity("K9", "Cached", 9),)
            store.sync("account", original)
            before_bytes = path.read_bytes()
            top = _window((alpha, bravo), current=alpha)
            advancing = _window((charlie,))
            context = _FakeContext(top, down=(top, top), up=(advancing,))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store).execute(context)

            self.assertEqual(original, store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_global_cycle_fails_before_write(self) -> None:
        """Rejects a later window that reintroduces any earlier identity after an overlap."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        charlie = CastleIdentity("K3", "Charlie", 3)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            original = (alpha,)
            store.sync("account", original)
            before_bytes = path.read_bytes()
            first = _window((alpha, bravo), current=alpha)
            second = _window((bravo, charlie))
            loop = _window((charlie, alpha))
            context = _FakeContext(first, down=(first, first), up=(second, loop))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store).execute(context)

            self.assertEqual(original, store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_empty_window_fails_before_write(self) -> None:
        """Rejects an empty visible roster window without changing the cache."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (bravo,))
            before_bytes = path.read_bytes()
            top = _window((alpha,), current=alpha)
            empty = make_observation(ScreenType.PNC_CASTLE_SELECTION)
            context = _FakeContext(top, down=(top, top), up=(empty,))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store).execute(context)

            self.assertEqual((bravo,), store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_plain_active_row_without_exact_evidence_fails_before_write(self) -> None:
        """Requires exact selected-row evidence even when the active identity is listed plainly."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        charlie = CastleIdentity("K3", "Charlie", 3)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (bravo,))
            before_bytes = path.read_bytes()
            top = _window((alpha, bravo))
            advancing = _window((bravo, charlie))
            context = _FakeContext(top, down=(top, top), up=(advancing, advancing, advancing))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store).execute(context)

            self.assertEqual((bravo,), store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_wrong_selected_identity_fails_before_write(self) -> None:
        """Rejects exact evidence for a different selected castle even when that row is visible."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (alpha,))
            before_bytes = path.read_bytes()
            top = _window((alpha, bravo), current=bravo)
            context = _FakeContext(top, down=(top, top), up=(top, top))

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store).execute(context)

            self.assertEqual((alpha,), store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_top_budget_exhaustion_fails_before_write(self) -> None:
        """Rejects an unproven top after consuming the downward swipe budget."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (alpha,))
            before_bytes = path.read_bytes()
            top = _window((alpha,), current=alpha)
            moved = _window((bravo,))
            context = _FakeContext(top, down=(moved,), up=())
            policy = RefreshCastleRosterPolicy(max_swipes_per_direction=1)

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store, policy).execute(context)

            self.assertEqual((alpha,), store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_forward_budget_exhaustion_fails_before_write(self) -> None:
        """Rejects an unproven end after consuming the upward scan budget."""

        alpha = CastleIdentity("K1", "Alpha", 1)
        bravo = CastleIdentity("K2", "Bravo", 2)
        charlie = CastleIdentity("K3", "Charlie", 3)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "castles.yaml"
            store = CastleRosterStore(path=path)
            store.sync("account", (alpha,))
            before_bytes = path.read_bytes()
            top = _window((alpha, bravo), current=alpha)
            advancing = _window((bravo, charlie))
            context = _FakeContext(top, down=(top, top), up=(advancing,))
            policy = RefreshCastleRosterPolicy(max_swipes_per_direction=1)

            with self.assertRaises(TaskVerificationError):
                RefreshCastleRosterWorkflow("account", "account", alpha, store, policy).execute(context)

            self.assertEqual((alpha,), store.get("account").castles)
            self.assertEqual(before_bytes, path.read_bytes())

    def test_invalid_scroll_direction_is_rejected_without_capture(self) -> None:
        """Rejects malformed context directions before touching navigation or observation."""

        runtime = Mock()
        runtime.observation_count = 0
        runtime.last_observation = None
        context = WorkflowContext(runtime, last_observation=make_observation(ScreenType.PNC_HOME_CITY))

        with self.assertRaises(ValueError):
            context.scroll_castle_roster("sideways")  # type: ignore[arg-type]

        runtime.navigation.scroll_castle_roster.assert_not_called()
        runtime.observe.assert_not_called()

    def test_scroll_rejects_stale_content_from_core_boundary(self) -> None:
        """Rejects a scroll completion that does not advance the content timestamp."""

        initial = make_observation(ScreenType.PNC_CASTLE_SELECTION, list_entries=(_row("Alpha", "K1"),))
        runtime = Mock()
        runtime.observation_count = 0
        runtime.last_observation = initial

        def observe(_label: str, *, include_content: bool = False) -> Observation:
            del include_content
            runtime.observation_count += 1
            return initial

        runtime.observe.side_effect = observe
        runtime.navigation.scroll_castle_roster.side_effect = (
            lambda _direction, observe_content: observe_content("castle_roster_scroll")
        )
        context = WorkflowContext(runtime, last_observation=initial)

        with self.assertRaisesRegex(RuntimeError, "stale"):
            context.scroll_castle_roster("up")

        runtime.navigation.scroll_castle_roster.assert_called_once()
        runtime.observe.assert_called_once_with("castle_roster_scroll", include_content=True)


class RefreshCastleRosterApplicationTests(unittest.TestCase):
    """Covers the typed application and reservation forwarding boundaries."""

    def test_application_validates_store_before_connecting_and_closes_runtime(self) -> None:
        """Requires CastleRosterStore before runtime construction and closes after workflow failure."""

        account = type("Account", (), {"id": "account", "pnc_account_id": "pnc", "artifact_directory_name": "account"})()
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        script_runner.castle_roster_store = None
        with patch("pnc_automation.app.entrypoints.app.build_core_runtime") as factory:
            with self.assertRaisesRegex(RuntimeError, "CastleRosterStore"):
                ApplicationRunner(script_runner).run_refresh_castle_roster(account_id="account")
        factory.assert_not_called()

    def test_application_preflights_active_castle_forwards_default_role_and_closes(self) -> None:
        """Builds one typed workflow from the exact preflight identity and closes its runtime."""

        account = SimpleNamespace(id="account", pnc_account_id="pnc", artifact_directory_name="account")
        active = CastleIdentity("K1", "Active", 22)
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        with TemporaryDirectory() as temporary_directory:
            roster_store = CastleRosterStore(path=Path(temporary_directory) / "castles.yaml")
            script_runner.castle_roster_store = roster_store
            runtime = Mock()
            runtime.preflight_active_castle_identity.return_value = active
            expected = Mock(spec=CoreWorkflowResult)

            class _Runner:
                @classmethod
                def __class_getitem__(cls, _item):
                    return cls

                def __init__(self, passed_runtime) -> None:
                    self.passed_runtime = passed_runtime

                def run(self, workflow):
                    self.workflow = workflow
                    return expected

            with (
                patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime) as factory,
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                result = ApplicationRunner(script_runner).run_refresh_castle_roster(account_id="account")

            self.assertIs(expected, result)
            factory.assert_called_once_with(
                script_runner,
                account,
                "account",
                required_role=LiveAutomationRole.LIVE_TESTING,
            )
            runtime.preflight_active_castle_identity.assert_called_once_with()
            runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_preflight_fails_without_replay(self) -> None:
        """Closes a connected runtime after active-castle preflight fails without retrying it."""

        account = SimpleNamespace(id="account", pnc_account_id="pnc", artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        with TemporaryDirectory() as temporary_directory:
            script_runner.castle_roster_store = CastleRosterStore(Path(temporary_directory) / "castles.yaml")
            runtime = Mock()
            runtime.preflight_active_castle_identity.side_effect = RuntimeError("preflight failed")
            with (
                patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner") as runner_factory,
            ):
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    ApplicationRunner(script_runner).run_refresh_castle_roster(account_id="account")

            runner_factory.assert_not_called()
            runtime.preflight_active_castle_identity.assert_called_once_with()
            runtime.close.assert_called_once_with()

    def test_application_closes_runtime_when_workflow_fails_without_replay(self) -> None:
        """Closes a connected runtime after the typed workflow fails without replaying the workflow."""

        account = SimpleNamespace(id="account", pnc_account_id="pnc", artifact_directory_name="account")
        active = CastleIdentity("K1", "Active", 22)
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        with TemporaryDirectory() as temporary_directory:
            script_runner.castle_roster_store = CastleRosterStore(Path(temporary_directory) / "castles.yaml")
            runtime = Mock()
            runtime.preflight_active_castle_identity.return_value = active

            class _Runner:
                @classmethod
                def __class_getitem__(cls, _item):
                    return cls

                def __init__(self, _runtime) -> None:
                    self.run_count = 0

                def run(self, _workflow):
                    self.run_count += 1
                    raise RuntimeError("workflow failed")

            with (
                patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=runtime),
                patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
            ):
                with self.assertRaisesRegex(RuntimeError, "workflow failed"):
                    ApplicationRunner(script_runner).run_refresh_castle_roster(account_id="account")

            runtime.preflight_active_castle_identity.assert_called_once_with()
            runtime.close.assert_called_once_with()

    def test_direct_api_session_and_module_helper_use_typed_reservation(self) -> None:
        """Routes direct, bound, and module calls to the typed app method exactly once."""

        application = Mock()
        result = Mock(spec=CoreWorkflowResult)
        application.run_refresh_castle_roster.return_value = result
        api = AutomationApi(application=application)

        self.assertIs(result, api.refresh_castle_roster(account_id="account"))
        application.run_refresh_castle_roster.assert_called_once_with(account_id="account")
        application.reserve_accounts.assert_called_once_with(("account",))
        application.reserve_accounts.return_value.close.assert_called_once_with()

        application.reset_mock()
        application.run_refresh_castle_roster.return_value = result
        self.assertIs(result, AutomationSession(api=api, account_id="account").refresh_castle_roster())
        application.run_refresh_castle_roster.assert_called_once_with(account_id="account")
        application.reserve_accounts.assert_called_once_with(("account",))

        default_api = Mock()
        default_api.refresh_castle_roster.return_value = result
        with patch.object(api_module, "_default_api", return_value=default_api):
            self.assertIs(result, api_module.refresh_castle_roster(account_id="account"))
        default_api.refresh_castle_roster.assert_called_once_with(account_id="account")


class _FakeContext:
    """Minimal constrained-context double that exposes only reviewed workflow operations."""

    def __init__(self, initial: Observation, *, down: tuple[Observation, ...], up: tuple[Observation, ...]) -> None:
        self.initial = initial
        self._down = list(down)
        self._up = list(up)
        self.targets: list[ScreenType] = []

    def navigate(self, target: ScreenType) -> Observation:
        self.targets.append(target)
        return self.initial

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        if expected_screen != ScreenType.PNC_CASTLE_SELECTION:
            raise AssertionError(expected_screen)
        return self.initial

    def scroll_castle_roster(self, direction: str) -> Observation:
        values = self._down if direction == "down" else self._up
        if not values:
            raise AssertionError(f"No fake {direction} observation remains.")
        return values.pop(0)


def _window(castles: tuple[CastleIdentity, ...], *, current: CastleIdentity | None = None) -> Observation:
    entries = []
    for castle in castles:
        metadata = {"kingdom": castle.kingdom}
        if castle.castle_level is not None:
            metadata["castle_level"] = castle.castle_level
        entries.append(make_entry(ListEntryKind.CASTLE, title=castle.castle_name, metadata=metadata))
    return make_observation(
        ScreenType.PNC_CASTLE_SELECTION,
        list_entries=tuple(entries),
        current_castle=current,
        current_castle_evidence=None if current is None else CurrentCastleEvidenceKind.EXACT,
    )


def _row(title: str, kingdom: str) -> DetectedListEntry:
    """Builds one unlevelled castle row for context freshness tests."""

    return make_entry(ListEntryKind.CASTLE, title=title, metadata={"kingdom": kingdom})


if __name__ == "__main__":
    unittest.main()
