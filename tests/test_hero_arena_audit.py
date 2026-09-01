"""Tests for the guarded Hero Arena recurrence audit."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pnc_automation.app.automation.audits.hero_arena_audit import (
    HeroArenaEntryAuditor,
    find_existing_hero_arena_audit_summary,
    hero_arena_audit_label,
)
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutionPolicy,
    ObservedActionExecutor,
)
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import FakeObservationService, FakeSession, build_logger, make_observation


class HeroArenaEntryAuditorTests(unittest.TestCase):
    """Verifies safe branching and fail-closed behavior for Arena gate observations."""

    def test_run_records_intro_and_formation_then_returns_to_versus(self) -> None:
        """Records both gates without tapping Save Formation or Challenge."""

        service = FakeObservationService(
            observations=[
                self._versus_observation(),
                self._intro_observation(Path("intro.png")),
                self._formation_observation(Path("formation.png")),
                self._versus_observation(Path("returned.png")),
            ]
        )
        session = FakeSession()

        result = self._build_auditor(service=service, session=session).run(label_prefix="entry")

        self.assertTrue(result.elemental_intro_appeared)
        self.assertTrue(result.hero_formation_gate_appeared)
        self.assertEqual(result.destination_screen, ScreenType.PNC_HERO_FORMATION)
        self.assertEqual(result.final_screen, ScreenType.PNC_VERSUS_CENTER)
        self.assertEqual(result.evidence_artifact_paths, (Path("intro.png"), Path("formation.png"), Path("returned.png")))
        self.assertEqual(session.taps, [(5, 5), (20, 20), (35, 35)])

    def test_run_records_direct_ranking_without_intro_or_formation(self) -> None:
        """Handles a direct ranking entry and backs out without touching Challenge."""

        service = FakeObservationService(
            observations=[
                self._versus_observation(),
                self._ranking_observation(Path("ranking.png")),
                self._versus_observation(Path("returned.png")),
            ]
        )
        session = FakeSession()

        result = self._build_auditor(service=service, session=session).run(label_prefix="entry")

        self.assertFalse(result.elemental_intro_appeared)
        self.assertFalse(result.hero_formation_gate_appeared)
        self.assertEqual(result.destination_screen, ScreenType.PNC_HERO_SHOWDOWN_RANKING)
        self.assertEqual(session.taps, [(5, 5), (50, 50)])

    def test_run_stops_when_entry_destination_is_unknown(self) -> None:
        """Fails closed after one entry tap when the destination cannot be classified."""

        service = FakeObservationService(
            observations=[
                self._versus_observation(),
                make_observation(ScreenType.UNKNOWN),
                make_observation(ScreenType.UNKNOWN),
            ]
        )
        session = FakeSession()

        with self.assertRaises(SelectorResolutionError):
            self._build_auditor(service=service, session=session).run(label_prefix="entry")

        self.assertEqual(len(session.taps), 1)

    def test_run_rejects_ocr_localized_entry_before_tapping(self) -> None:
        """Refuses an OCR-derived action point even when the screen itself is typed."""

        service = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_VERSUS_CENTER,
                    visible_ids=(UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY,),
                    source_kinds={
                        UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY: VisibleElementSourceKind.OCR,
                    },
                )
            ]
        )
        session = FakeSession()

        with self.assertRaises(SelectorResolutionError):
            self._build_auditor(service=service, session=session).run(label_prefix="entry")

        self.assertEqual(session.taps, [])

    def test_summary_guard_matches_exact_date_account_and_castle(self) -> None:
        """Finds only the exact target's structured same-date summary across UTC artifact folders."""

        with tempfile.TemporaryDirectory() as temp_directory:
            artifact_root = Path(temp_directory)
            local_date = date(2026, 9, 1)
            target = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
            summary_path = artifact_root / "2026-09-02" / "mega_old_acc" / (
                f"20260902T020000Z_{hero_arena_audit_label(local_date)}.json"
            )
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "local_date": local_date.isoformat(),
                        "account_id": "mega_old_acc",
                        "castle": {
                            "kingdom": target.kingdom,
                            "castle_name": target.castle_name,
                            "castle_level": target.castle_level,
                        },
                    }
                ),
                encoding="utf-8",
            )

            found = find_existing_hero_arena_audit_summary(
                artifact_root,
                local_date=local_date,
                account_id="mega_old_acc",
                castle=target,
            )
            other_target = find_existing_hero_arena_audit_summary(
                artifact_root,
                local_date=local_date,
                account_id="mega_old_acc",
                castle=CastleIdentity(kingdom="K157", castle_name="NPC 3", castle_level=22),
            )

            self.assertEqual(found, summary_path)
            self.assertIsNone(other_target)

    def test_summary_guard_fails_closed_on_malformed_same_date_json(self) -> None:
        """Stops before live work when a candidate summary cannot be trusted."""

        with tempfile.TemporaryDirectory() as temp_directory:
            artifact_root = Path(temp_directory)
            local_date = date(2026, 9, 1)
            summary_path = artifact_root / f"broken_{hero_arena_audit_label(local_date)}.json"
            summary_path.write_text("not-json", encoding="utf-8")

            with self.assertRaises(SelectorResolutionError):
                find_existing_hero_arena_audit_summary(
                    artifact_root,
                    local_date=local_date,
                    account_id="mega_old_acc",
                    castle=CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22),
                )

    @staticmethod
    def _build_auditor(*, service: FakeObservationService, session: FakeSession) -> HeroArenaEntryAuditor:
        """Builds the audit over deterministic test doubles with no action delays."""

        logger = build_logger()
        registry = build_default_selector_registry()
        executor = ObservedActionExecutor(
            selector_registry=registry,
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=logger,
                sleep=lambda _: None,
            ),
            logger=logger,
            policy=ObservedActionExecutionPolicy(max_settle_observations=0),
            sleep=lambda _: None,
        )
        return HeroArenaEntryAuditor(observation_service=service, action_executor=executor)

    @staticmethod
    def _versus_observation(artifact_path: Path | None = None) -> Observation:
        """Builds a Versus Center observation with reviewed geometry for Hero Showdown."""

        return make_observation(
            ScreenType.PNC_VERSUS_CENTER,
            visible_ids=(UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY,),
            source_kinds={UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY: VisibleElementSourceKind.GEOMETRY},
            artifact_path=artifact_path,
        )

    @staticmethod
    def _intro_observation(artifact_path: Path) -> Observation:
        """Builds an Elemental Intro observation with a geometry-only Confirm action."""

        return make_observation(
            ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO,
            visible_ids=(
                UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_HEADER,
                UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_CONFIRM_BUTTON,
            ),
            source_kinds={
                UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_CONFIRM_BUTTON: VisibleElementSourceKind.GEOMETRY,
            },
            artifact_path=artifact_path,
        )

    @staticmethod
    def _formation_observation(artifact_path: Path) -> Observation:
        """Builds a Formation observation exposing only safe Back geometry to the audit."""

        return make_observation(
            ScreenType.PNC_HERO_FORMATION,
            visible_ids=(
                UiElementId.PNC_HERO_FORMATION_HEADER,
                UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            ),
            source_kinds={UiElementId.PNC_BACK_BUTTON_TOP_LEFT: VisibleElementSourceKind.GEOMETRY},
            artifact_path=artifact_path,
        )

    @staticmethod
    def _ranking_observation(artifact_path: Path) -> Observation:
        """Builds a ranking observation exposing safe Back plus the forbidden Challenge label."""

        return make_observation(
            ScreenType.PNC_HERO_SHOWDOWN_RANKING,
            visible_ids=(
                UiElementId.PNC_HERO_SHOWDOWN_RANKING_HEADER,
                UiElementId.PNC_HERO_SHOWDOWN_CURRENT_RANK_LABEL,
                UiElementId.PNC_HERO_SHOWDOWN_CHALLENGE_BUTTON,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            ),
            source_kinds={UiElementId.PNC_BACK_BUTTON_TOP_LEFT: VisibleElementSourceKind.GEOMETRY},
            artifact_path=artifact_path,
        )


if __name__ == "__main__":
    unittest.main()
