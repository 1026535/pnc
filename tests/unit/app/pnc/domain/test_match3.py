"""Match-3 domain contract tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.campaign import CampaignChapterIdentity, CampaignNodeFacts
from pnc_automation.app.pnc.domain.match3 import (
    Match3Availability,
    Match3AvailabilityStatus,
    Match3Context,
    Match3Mode,
    Match3Request,
    Match3Result,
    Match3Target,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.app.pnc.domain.observation import Bounds, DetectedListEntry, ListEntryKind
from pnc_automation.app.pnc.domain.screen_decision import ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class Match3ContractTests(unittest.TestCase):
    """Proves the typed shared match-3 request/target/result contract."""

    def test_match3_contexts_and_modes_cover_the_declared_surface(self) -> None:
        """Enumerates exactly the three contexts and three modes."""

        self.assertEqual(
            {member.value for member in Match3Context},
            {"campaign", "arena", "lost_land"},
        )
        self.assertEqual(
            {member.value for member in Match3Mode},
            {"solver", "daily_exit", "game_auto"},
        )

    def test_every_context_mode_pair_builds_a_typed_request(self) -> None:
        """All nine context/mode combinations are representable."""

        requests = [
            Match3Request(context=context, mode=mode)
            for context in Match3Context
            for mode in Match3Mode
        ]

        self.assertEqual(len(requests), 9)
        self.assertEqual(
            {(request.context, request.mode) for request in requests},
            {(context, mode) for context in Match3Context for mode in Match3Mode},
        )

    def test_request_rejects_untyped_context_and_mode(self) -> None:
        """Raw strings and unrelated enums cannot stand in for typed members."""

        with self.assertRaises(TypeError):
            Match3Request(context="campaign", mode=Match3Mode.SOLVER)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Request(context=Match3Context.CAMPAIGN, mode="solver")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Request(context=Match3Context.CAMPAIGN, mode=None)  # type: ignore[arg-type]

    def test_target_rejects_untyped_references(self) -> None:
        """Target fields accept only the declared observed-fact types."""

        with self.assertRaises(TypeError):
            Match3Target(context="campaign")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Target(context=Match3Context.CAMPAIGN, campaign_node={"stage": 1})  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Target(context=Match3Context.CAMPAIGN, frame_ref="frame-1")  # type: ignore[arg-type]

    def test_target_accepts_observed_campaign_facts_and_provenance(self) -> None:
        """Reuses the existing campaign facts and frame provenance unchanged."""

        target = Match3Target(
            context=Match3Context.CAMPAIGN,
            campaign_node=CampaignNodeFacts(chapter_number=3, stage_number=7),
            campaign_chapter=CampaignChapterIdentity(chapter_number=3),
            frame_ref=FrameRef(
                session_id="session",
                session_epoch=1,
                capture_sequence=2,
                input_sequence=0,
                captured_at=datetime.now(tz=UTC),
            ),
        )

        request = Match3Request(
            context=Match3Context.CAMPAIGN,
            mode=Match3Mode.DAILY_EXIT,
            target=target,
        )
        self.assertIs(request.target, target)

    def test_menu_reference_needs_no_invented_opponent_or_readiness(self) -> None:
        """An observed Arena menu is a valid reference before a target row is qualified."""

        decision = ScreenDecision(
            base_screen=ScreenType.PNC_VERSUS_CENTER,
            effective_screen=ScreenType.PNC_VERSUS_CENTER,
        )
        target = Match3Target(
            context=Match3Context.ARENA,
            source_decision=decision,
            frame_ref=_frame(),
        )

        self.assertIs(target.source_decision, decision)
        self.assertIsNone(target.selected_entry)
        with self.assertRaises(ValueError):
            replace(target, frame_ref=None)

    def test_selected_row_preserves_source_and_rejects_mixed_provenance(self) -> None:
        """A selected row cannot be relabeled with a later frame, screen, or layout."""

        frame = _frame()
        decision = ScreenDecision(
            base_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            effective_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            layout_id="campaign-chapter",
        )
        entry = DetectedListEntry(
            kind=ListEntryKind.CAMPAIGN_STAGE,
            bounds=Bounds(10, 10, 50, 50),
            title_text="3",
            campaign_node=CampaignNodeFacts(chapter_number=2, stage_number=3),
            frame_ref=frame,
            source_screen=decision.effective_screen,
            source_layout_id=decision.layout_id,
        )
        target = Match3Target(
            context=Match3Context.CAMPAIGN,
            frame_ref=frame,
            source_decision=decision,
            selected_entry=entry,
            campaign_node=entry.campaign_node,
        )
        self.assertIs(target.selected_entry, entry)
        for changed in (
            {"frame_ref": replace(frame, capture_sequence=2)},
            {"source_decision": replace(decision, layout_id="different")},
            {"source_decision": replace(decision, effective_screen=ScreenType.PNC_CAMPAIGN_STAGE)},
            {"campaign_node": CampaignNodeFacts(chapter_number=2, stage_number=4)},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                replace(target, **changed)

    def test_chapter_reference_preserves_its_source_frame(self) -> None:
        """Source chapter evidence cannot be rebound to a later preparation frame."""

        frame = _frame()
        chapter = CampaignChapterIdentity(
            chapter_number=2,
            frame_ref=frame,
            source_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            source_layout_id="campaign-chapter",
        )
        decision = ScreenDecision(
            base_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            effective_screen=ScreenType.PNC_CAMPAIGN_CHAPTER,
            layout_id="campaign-chapter",
        )
        target = Match3Target(
            context=Match3Context.CAMPAIGN,
            campaign_chapter=chapter,
            frame_ref=frame,
            source_decision=decision,
        )
        with self.assertRaises(ValueError):
            replace(target, frame_ref=replace(frame, capture_sequence=2))
        with self.assertRaises(ValueError):
            replace(target, source_decision=replace(decision, layout_id="different"))

    def test_non_campaign_target_rejects_campaign_facts(self) -> None:
        """Another feature cannot relabel Campaign target evidence as its own."""

        for context in (Match3Context.ARENA, Match3Context.LOST_LAND):
            with self.subTest(context=context), self.assertRaises(ValueError):
                Match3Target(
                    context=context,
                    campaign_node=CampaignNodeFacts(chapter_number=3, stage_number=7),
                )

    def test_request_rejects_a_target_for_a_different_context(self) -> None:
        """A request cannot carry another context's target reference."""

        with self.assertRaises(ValueError):
            Match3Request(
                context=Match3Context.ARENA,
                mode=Match3Mode.GAME_AUTO,
                target=Match3Target(context=Match3Context.CAMPAIGN),
            )

    def test_availability_requires_an_actionable_reason_when_unavailable(self) -> None:
        """Unavailable answers must explain themselves; available ones may not."""

        with self.assertRaises(ValueError):
            Match3Availability(
                context=Match3Context.CAMPAIGN,
                mode=Match3Mode.SOLVER,
                status=Match3AvailabilityStatus.NOT_IMPLEMENTED,
            )

        available = Match3Availability(
            context=Match3Context.CAMPAIGN,
            mode=Match3Mode.SOLVER,
            status=Match3AvailabilityStatus.AVAILABLE,
        )
        self.assertTrue(available.available)
        unavailable = Match3Availability(
            context=Match3Context.CAMPAIGN,
            mode=Match3Mode.SOLVER,
            status=Match3AvailabilityStatus.UNSUPPORTED,
            reason="pair not supported",
        )
        self.assertFalse(unavailable.available)

    def test_result_availability_must_describe_the_request(self) -> None:
        """A result cannot report availability for a different context/mode pair."""

        request = Match3Request(context=Match3Context.CAMPAIGN, mode=Match3Mode.SOLVER)
        availability = Match3Availability(
            context=Match3Context.ARENA,
            mode=Match3Mode.SOLVER,
            status=Match3AvailabilityStatus.NOT_IMPLEMENTED,
            reason="not implemented",
        )

        with self.assertRaises(ValueError):
            Match3Result(request=request, availability=availability)


def _frame() -> FrameRef:
    """One source frame shared by a target's canonical references."""

    return FrameRef(
        session_id="session",
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )


if __name__ == "__main__":
    unittest.main()
