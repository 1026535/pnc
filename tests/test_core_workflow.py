"""Offline tests for replacement-core lifecycle and Daily status behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.daily_maintenance.daily_quest_status import (
    DailyQuestStatusResult,
    DailyQuestStatusWorkflow,
)
from pnc_automation.app.entrypoints.cli import main
from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflowRunner,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, Observation, ListEntryKind
from pnc_automation.app.pnc.domain.mail import MailboxAvailability, MailboxType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.vision.image.models import Bounds


class CoreWorkflowTests(unittest.TestCase):
    """Covers lifecycle gates, freshness, bounded status, and explicit recovery."""

    def test_daily_status_succeeds_with_one_visible_known_row_and_returns_home(self) -> None:
        """Reports typed status after Daily content and confirmed Home exit."""

        runtime = _FakeRuntime(_daily_observation(_entry("hero_arena")))

        result = CoreWorkflowRunner(runtime).run(DailyQuestStatusWorkflow())

        self.assertTrue(result.succeeded)
        self.assertEqual([ScreenType.PNC_HOME_CITY, ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_HOME_CITY], runtime.navigation.targets)
        self.assertEqual("visible_viewport", result.value.coverage)
        self.assertEqual("hero_arena", result.value.viewport.rows[0].quest_id.value)

    def test_daily_status_succeeds_with_unknown_title_evidence(self) -> None:
        """Preserves a future or noisy title as reportable unknown evidence."""

        runtime = _FakeRuntime(_daily_observation(_entry(None, title="Future Daily Quest")))

        result = CoreWorkflowRunner(runtime).run(DailyQuestStatusWorkflow())

        self.assertEqual((), result.value.viewport.rows)
        self.assertEqual(("Future Daily Quest",), result.value.viewport.unknown_titles)

    def test_empty_visible_viewport_fails_before_exit_without_replay(self) -> None:
        """Rejects an empty parse and never automatically navigates Home afterward."""

        runtime = _FakeRuntime(_daily_observation())

        with self.assertRaises(TaskVerificationError):
            CoreWorkflowRunner(runtime).run(DailyQuestStatusWorkflow())

        self.assertEqual([ScreenType.PNC_HOME_CITY, ScreenType.PNC_QUEST_DAILY], runtime.navigation.targets)
        self.assertEqual("workflow_failed", runtime.events[-1]["event"])
        self.assertNotIn("message", runtime.events[-1])

    def test_final_home_failure_is_propagated_without_retry(self) -> None:
        """Does not replay or finally recover when the reviewed exit cannot be confirmed."""

        runtime = _FakeRuntime(_daily_observation(_entry("hero_arena")), fail_exit=True)

        with self.assertRaisesRegex(RuntimeError, "exit unavailable"):
            CoreWorkflowRunner(runtime).run(DailyQuestStatusWorkflow())

        self.assertEqual(
            [ScreenType.PNC_HOME_CITY, ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_HOME_CITY],
            runtime.navigation.targets,
        )
        self.assertEqual(1, runtime.navigation.exit_attempts)

    def test_resource_changing_workflow_is_denied_before_capture_or_action(self) -> None:
        """Rejects future mutating effects before touching the connected runtime."""

        runtime = _FakeRuntime(_daily_observation(_entry("hero_arena")))
        workflow = _ResourceChangingWorkflow()

        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime).run(workflow)

        self.assertEqual([], runtime.navigation.targets)
        self.assertEqual(0, runtime.observation_count)

    def test_content_capture_rejects_stale_and_blocking_frames(self) -> None:
        """Requires a fresh non-blocking typed Daily frame after navigation."""

        stale = _daily_observation(_entry("hero_arena"))
        stale_runtime = _FakeRuntime(stale, content_timestamp=stale.captured_at)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            CoreWorkflowRunner(stale_runtime).run(_ContentOnlyWorkflow())

        blocked = _daily_observation(_entry("hero_arena"), blocking_popup=True)
        blocked_runtime = _FakeRuntime(blocked)
        with self.assertRaisesRegex(RuntimeError, "blocking popup"):
            CoreWorkflowRunner(blocked_runtime).run(_ContentOnlyWorkflow())

    def test_recovery_is_explicit_and_uses_only_reviewed_navigation(self) -> None:
        """Recovery delegates to the graph and propagates unknown-screen failure."""

        runtime = _FakeRuntime(_daily_observation(_entry("hero_arena")), fail_recovery=True)

        with self.assertRaisesRegex(RuntimeError, "unknown screen"):
            CoreWorkflowRunner(runtime).recover_to_home()

        self.assertEqual([ScreenType.PNC_HOME_CITY], runtime.navigation.targets)

    def test_workflow_spec_rejects_string_effects(self) -> None:
        """Prevents a mistyped effect from bypassing the read-only gate."""

        with self.assertRaises(TypeError):
            WorkflowSpec(
                name="bad",
                entry_screen=ScreenType.PNC_HOME_CITY,
                exit_screen=ScreenType.PNC_HOME_CITY,
                effect="read_only",
            )

    def test_cli_serializes_typed_daily_status_result(self) -> None:
        """Routes the command through ApplicationRunner and emits structured JSON."""

        result = CoreWorkflowRunner(_FakeRuntime(_daily_observation(_entry("hero_arena")))).run(
            DailyQuestStatusWorkflow()
        )
        application = Mock()
        application.run_daily_quest_status.return_value = result

        with (
            patch("pnc_automation.app.entrypoints.cli.build_application_runner", return_value=application),
            patch("builtins.print") as output,
        ):
            exit_code = main(["daily-quest-status", "--config", "accounts.yaml", "--account", "account"])

        self.assertEqual(0, exit_code)
        application.run_daily_quest_status.assert_called_once_with(account_id="account")
        document = json.loads(output.call_args.args[0])
        self.assertEqual("daily_quest_status", document["workflow_name"])
        self.assertEqual("visible_viewport", document["value"]["coverage"])

    def test_mail_context_delegates_once_and_does_not_replay_after_failure(self) -> None:
        """Keeps mail-specific operations constrained to one core call each."""

        runtime = Mock()
        runtime.observation_count = 0
        runtime.last_observation = None
        runtime.navigation.open_mailbox.return_value = MailboxAvailability.UNAVAILABLE
        context = WorkflowContext(runtime, last_observation=_home_observation(datetime.now(UTC)))

        self.assertEqual(
            context.open_mailbox(MailboxType.PLAYER),
            MailboxAvailability.UNAVAILABLE,
        )
        runtime.navigation.open_mailbox.assert_called_once()
        runtime.navigation.scroll_mailbox.side_effect = RuntimeError("scroll failed")
        with self.assertRaisesRegex(RuntimeError, "scroll failed"):
            context.scroll_mailbox()
        runtime.navigation.scroll_mailbox.assert_called_once()


class _ContentOnlyWorkflow:
    """Requests one fresh Daily content frame for freshness tests."""

    spec = WorkflowSpec(
        name="content_only",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.READ_ONLY,
    )

    def execute(self, context: WorkflowContext) -> Observation:
        context.navigate(ScreenType.PNC_QUEST_DAILY)
        return context.observe_content(expected_screen=ScreenType.PNC_QUEST_DAILY)


class _ResourceChangingWorkflow:
    """Represents a future mutating workflow that must not enter this runner."""

    spec = WorkflowSpec(
        name="mutating",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.RESOURCE_CHANGING,
    )

    def execute(self, context: WorkflowContext) -> None:
        del context
        raise AssertionError("The mutation body must never execute.")


@dataclass(slots=True)
class _FakeNavigation:
    content: Observation
    fail_exit: bool = False
    fail_recovery: bool = False
    targets: list[ScreenType] = None
    exit_attempts: int = 0

    def __post_init__(self) -> None:
        self.targets = []

    def navigate(self, target: ScreenType) -> Observation:
        self.targets.append(target)
        if target == ScreenType.PNC_HOME_CITY and self.fail_recovery:
            raise RuntimeError("unknown screen")
        if target == ScreenType.PNC_HOME_CITY and len(self.targets) > 1:
            self.exit_attempts += 1
            if self.fail_exit:
                raise RuntimeError("exit unavailable")
            return _home_observation(self.content.captured_at + timedelta(seconds=len(self.targets)))
        if target == ScreenType.PNC_QUEST_DAILY:
            return _daily_observation(
                *self.content.list_entries,
                captured_at=self.content.captured_at + timedelta(seconds=1),
            )
        return _home_observation(self.content.captured_at)


@dataclass
class _FakeRuntime:
    content: Observation
    fail_exit: bool = False
    fail_recovery: bool = False
    content_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        self.navigation = _FakeNavigation(
            self.content,
            fail_exit=self.fail_exit,
            fail_recovery=self.fail_recovery,
        )
        self.observation_count = 0
        self.last_observation = None
        self.events: list[dict[str, object]] = []
        self.trace_path = Path("trace.jsonl")

    def record(self, entry: dict[str, object]) -> None:
        self.events.append(entry)

    def observe(self, label: str, *, include_content: bool = False) -> Observation:
        del label, include_content
        self.observation_count += 1
        captured_at = self.content_timestamp or self.content.captured_at + timedelta(seconds=2)
        self.last_observation = _daily_observation(
            *self.content.list_entries,
            captured_at=captured_at,
            blocking_popup=self.content.blocking_popup,
        )
        return self.last_observation


def _home_observation(captured_at: datetime) -> Observation:
    """Builds a typed Home frame for lifecycle tests."""

    return Observation(
        screen_type=ScreenType.PNC_HOME_CITY,
        visible_elements={},
        captured_at=captured_at,
    )


def _daily_observation(
    *entries: DetectedListEntry,
    captured_at: datetime | None = None,
    blocking_popup: bool = False,
) -> Observation:
    """Builds a typed Daily frame with deterministic timestamps."""

    return Observation(
        screen_type=ScreenType.PNC_QUEST_DAILY,
        visible_elements={},
        list_entries=entries,
        image_size=(540, 960),
        captured_at=captured_at or datetime(2026, 9, 10, tzinfo=UTC),
        blocking_popup=blocking_popup,
    )


def _entry(quest_id: str | None, *, title: str | None = None) -> DetectedListEntry:
    """Builds one typed visible Daily row fixture."""

    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=Bounds(9, 372, 518, 99),
        title_text=title or quest_id,
        metadata={
            "quest_id": quest_id,
            "row_state": "go",
            "coordinate_provenance": "visual_geometry",
            "observation_fingerprint": f"fingerprint-{quest_id or 'unknown'}",
        },
    )


if __name__ == "__main__":
    unittest.main()
