"""Offline acceptance tests for the two-castle canary release contract."""

from __future__ import annotations

import unittest
from dataclasses import replace
import tempfile
from pathlib import Path

from pnc_automation.app.automation.daily_maintenance.canaries import (
    CanaryCase,
    CanaryEvidenceStore,
    CanaryOutcome,
    CanaryReason,
    CanaryResult,
    CanaryRole,
    evaluate_canary_release,
    planned_canaries,
)
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, validate_daily_diamond_limit


class DailyCanaryAcceptanceTests(unittest.TestCase):
    """Requires full evaluation, positive NPC evidence, and qualified cookie skips."""

    def setUp(self) -> None:
        """Creates a complete, explicitly synthetic fixture for one code revision."""

        self.cases = planned_canaries()
        self.results = tuple(self._passed(case) for case in self.cases)

    def test_every_planned_feature_has_exactly_two_canaries(self) -> None:
        """Covers each feature separately, including all four gather resources."""

        expected = {
            DailyQuestId.CLAIM_COMPLETED, DailyQuestId.HERO_ARENA,
            DailyQuestId.USE_RESOURCE_ITEM, DailyQuestId.HERO_HALL,
            DailyQuestId.UPGRADE_HERO, DailyQuestId.CAMPAIGN,
            DailyQuestId.GATHER_FOOD, DailyQuestId.GATHER_WOOD,
            DailyQuestId.GATHER_IRON, DailyQuestId.GATHER_GOLD,
            DailyQuestId.GATHER_ALLIANCE_MINE, DailyQuestId.RESOURCE_BUILDING_BOOST,
            DailyQuestId.TRIAL_SHOP, DailyQuestId.RARE_EARTH_SHOP,
            DailyQuestId.ALLIANCE_SHOP, DailyQuestId.PRAISE,
            DailyQuestId.SUMMON_SAURGIL, DailyQuestId.ENHANCE_GEM,
            DailyQuestId.ENHANCE_SAURGEM, DailyQuestId.ENHANCE_GEAR,
            DailyQuestId.WISHES, DailyQuestId.LAND_OF_TRIAL,
            DailyQuestId.LOST_LAND, DailyQuestId.ALLIANCE_DONATIONS,
            DailyQuestId.ALLIANCE_GIFT,
        }
        self.assertEqual(expected, {case.quest_id for case in self.cases})
        for feature in expected:
            with self.subTest(feature=feature):
                pair = [case for case in self.cases if case.quest_id == feature]
                self.assertEqual({CanaryRole.NPC_2, CanaryRole.FREE_COOKIES}, {case.role for case in pair})
                self.assertEqual(2, len(pair))

    def test_missing_canary_blocks_all_release(self) -> None:
        """Does not release early while one feature is still awaiting evaluation."""

        gate = evaluate_canary_release(self.results[:-1], revision="revision-1")
        self.assertFalse(gate.evaluation_complete)
        self.assertEqual((), gate.validated_features)

    def test_insufficient_funds_fails_only_affected_feature_after_full_evaluation(self) -> None:
        """Distinguishes an unsuccessful business precondition from a code defect."""

        results = self._replace_result(
            DailyQuestId.TRIAL_SHOP, CanaryRole.NPC_2,
            outcome=CanaryOutcome.FAILED, reason=CanaryReason.INSUFFICIENT_FUNDS,
        )
        gate = evaluate_canary_release(results, revision="revision-1")
        self.assertTrue(gate.evaluation_complete)
        self.assertNotIn(DailyQuestId.TRIAL_SHOP, gate.validated_features)
        self.assertIn(DailyQuestId.HERO_HALL, gate.validated_features)
        failed = next(result for result in results if result.reason == CanaryReason.INSUFFICIENT_FUNDS)
        self.assertFalse(failed.is_software_error)

    def test_npc_applicability_skip_is_not_positive_proof(self) -> None:
        """Requires NPC 2 to pass rather than satisfy its cell with a skip."""

        results = self._replace_result(
            DailyQuestId.SUMMON_SAURGIL, CanaryRole.NPC_2,
            outcome=CanaryOutcome.APPLICABILITY_SKIP, reason=CanaryReason.FEATURE_LOCKED,
        )
        self.assertNotIn(
            DailyQuestId.SUMMON_SAURGIL,
            evaluate_canary_release(results, revision="revision-1").validated_features,
        )

    def test_cookie_saurgil_lock_is_approved_but_ocr_failure_is_not(self) -> None:
        """Accepts the agreed Sauroi-below-30 skip, never an unknown screen."""

        results = self._replace_result(
            DailyQuestId.SUMMON_SAURGIL, CanaryRole.FREE_COOKIES,
            outcome=CanaryOutcome.APPLICABILITY_SKIP, reason=CanaryReason.FEATURE_LOCKED,
        )
        self.assertIn(
            DailyQuestId.SUMMON_SAURGIL,
            evaluate_canary_release(results, revision="revision-1").validated_features,
        )
        results = self._replace_result(
            DailyQuestId.SUMMON_SAURGIL, CanaryRole.FREE_COOKIES,
            outcome=CanaryOutcome.BLOCKED, reason=CanaryReason.UNEXPECTED_STATE,
        )
        self.assertNotIn(
            DailyQuestId.SUMMON_SAURGIL,
            evaluate_canary_release(results, revision="revision-1").validated_features,
        )

    def test_stale_revision_requires_relevant_retest_not_daily_repetition(self) -> None:
        """Reuses evidence without date expiry but never across an incompatible revision."""

        self.assertTrue(evaluate_canary_release(self.results, revision="revision-1").evaluation_complete)
        self.assertFalse(evaluate_canary_release(self.results, revision="revision-2").evaluation_complete)

    def test_duplicate_result_is_ambiguous_and_rejected(self) -> None:
        """Requires callers to select one current result, never average conflicting attempts."""

        with self.assertRaisesRegex(ValueError, "Duplicate"):
            evaluate_canary_release(self.results + (self.results[0],), revision="revision-1")

    def test_relevant_change_invalidates_only_its_feature_evidence(self) -> None:
        """Retains all other feature results while requiring the changed pair to rerun."""

        revisions = {case.quest_id: "revision-1" for case in self.cases}
        revisions[DailyQuestId.WISHES] = "revision-2"
        gate = evaluate_canary_release(self.results, revision=revisions)
        self.assertEqual(2, len(gate.missing_cases))
        self.assertEqual({DailyQuestId.WISHES}, {case.quest_id for case in gate.missing_cases})

    def test_success_requires_transition_evidence(self) -> None:
        """A success label or single static screenshot cannot promote a feature."""

        with self.assertRaisesRegex(ValueError, "before and after"):
            replace(self.results[0], artifact_paths=("one.png",))

    def test_stock_shortage_is_not_insufficient_funds(self) -> None:
        """Preserves the distinct expected Trial Shop stock failure reason."""

        result = replace(
            self.results[0], outcome=CanaryOutcome.FAILED,
            reason=CanaryReason.ITEM_UNAVAILABLE,
        )
        self.assertNotEqual(CanaryReason.INSUFFICIENT_FUNDS, result.reason)
        self.assertFalse(result.is_software_error)

    def test_trial_shop_quantities_and_target_roles(self) -> None:
        """Protects NPC resources and keeps both canaries out of automatic runs."""

        pair = [case for case in self.cases if case.quest_id == DailyQuestId.TRIAL_SHOP]
        self.assertTrue(all(case.target_count == 1 for case in pair))
        self.assertEqual(
            {("mega_old_acc", "npc_2"), ("serious_stuff", "free_cookies")},
            {(case.account_id, case.castle_ref) for case in pair},
        )

    def test_wishes_target_is_five_not_fifty(self) -> None:
        """Separates the Daily objective from the shared per-game-day safety limit."""

        for case in self.cases:
            if case.quest_id == DailyQuestId.WISHES:
                self.assertEqual(5, case.target_count)
                self.assertEqual(50, case.game_day_count_limit)
                self.assertTrue(case.paid_wishes_allowed)

    def test_uncapped_wish_price_does_not_authorize_other_uncapped_features(self) -> None:
        """Keeps the user's explicit Wishes exception scoped to that feature."""

        validate_daily_diamond_limit(None, quest_id=DailyQuestId.WISHES)
        for feature in {case.quest_id for case in self.cases} - {DailyQuestId.WISHES}:
            with self.subTest(feature=feature), self.assertRaisesRegex(ValueError, "Only wishes"):
                validate_daily_diamond_limit(None, quest_id=feature)

    def test_hero_hall_wait_contract_for_both_castles(self) -> None:
        """Allows useful work during five-minute free recruitment cooldowns."""

        for case in self.cases:
            if case.quest_id == DailyQuestId.HERO_HALL:
                self.assertEqual(5, case.target_count)
                self.assertEqual(300, case.cooldown_seconds)
                self.assertTrue(case.interleave_other_quests)

    def test_evidence_store_round_trips_and_evaluates_persisted_results(self) -> None:
        """Reuses current evidence by revision without treating storage as promotion."""

        with tempfile.TemporaryDirectory() as directory:
            store = CanaryEvidenceStore(Path(directory))
            for result in self.results:
                path = store.save(result)
                self.assertTrue(path.is_file())
            loaded = store.load(quest_id=self.cases[0].quest_id, role=self.cases[0].role)
            self.assertEqual(self.results[0], loaded)
            decision = store.evaluate(revision="revision-1")
            self.assertTrue(decision.evaluation_complete)
            self.assertEqual(
                {case.quest_id for case in self.cases}, set(decision.validated_features),
            )

    def test_evidence_store_rejects_path_identity_mismatch(self) -> None:
        """Prevents a copied result from being accepted for another canary cell."""

        with tempfile.TemporaryDirectory() as directory:
            store = CanaryEvidenceStore(Path(directory))
            path = store.save(self.results[0])
            payload = path.read_text(encoding="utf-8").replace(
                self.results[0].role.value, CanaryRole.FREE_COOKIES.value,
            )
            path.write_text(payload, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "does not match"):
                store.load(quest_id=self.results[0].quest_id, role=self.results[0].role)

    def _replace_result(self, quest_id, role, **changes) -> tuple[CanaryResult, ...]:
        """Changes one synthetic cell without changing the remaining evidence."""

        return tuple(
            replace(result, **changes)
            if result.quest_id == quest_id and result.role == role else result
            for result in self.results
        )

    @staticmethod
    def _passed(case: CanaryCase) -> CanaryResult:
        """Builds fake transition evidence for offline gate tests only."""

        return CanaryResult(
            quest_id=case.quest_id, role=case.role, revision="revision-1",
            outcome=CanaryOutcome.PASSED, reason=CanaryReason.NONE,
            artifact_paths=("fake-before.png", "fake-after.png"),
        )
