"""RosterRefreshFixtures internal-boundary setup."""

from __future__ import annotations

from pnc_automation.app.automation.engine.task import TaskId, TaskResult
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.automation.tasks.refresh_castle_roster_task import RefreshCastleRosterTask
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class RosterRefreshFixtures(FlowAndTaskFixtures):
    """Offline workflow fixture; deliberately not a TestCase."""

    def _make_castle_selection_observation(self, castles: tuple[CastleIdentity, ...]) -> Observation:
        """Builds one Manage Char observation from an ordered tuple of castle identities."""

        return make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=tuple(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={
                        "kingdom": castle.kingdom,
                        "castle_level": castle.castle_level,
                    },
                )
                for castle in castles
            ),
        )

    def _run_refresh_scan(
        self,
        *,
        store: CastleRosterStore,
        windows: tuple[tuple[CastleIdentity, ...], ...],
    ) -> tuple[TaskResult, CastleRosterStore, TaskContext]:
        """Runs one synthetic refresh scan across the provided ordered Manage Char windows."""

        task = RefreshCastleRosterTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.REFRESH_CASTLE_ROSTER,
            castle_roster_provider=lambda: store.get(self.account.pnc_account_id),
            castle_roster_store=store,
        )
        current_window = self._make_castle_selection_observation(windows[0])
        task.verify(context, current_window, current_window)
        for next_window in windows[1:]:
            next_observation = self._make_castle_selection_observation(next_window)
            task.verify(context, current_window, next_observation)
            current_window = next_observation
        result = task.verify(context, current_window, current_window)
        return result, store, context
