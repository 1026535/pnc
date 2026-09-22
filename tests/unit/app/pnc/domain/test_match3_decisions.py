"""Pure match-3 candidate enumeration and baseline decision tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3Action,
    Match3ActionKind,
    Match3DecisionStatus,
    Match3Position,
    Match3Rules,
    Match3SpecialKind,
)
from pnc_automation.app.pnc.domain.match3_solver.selection import (
    BASELINE_LIMITATIONS,
    decide,
    evaluate_candidates,
)
from tests.support.pnc.match3_boards import match3_board


P = Match3Position
RULES_PLAIN = Match3Rules(square_matches_enabled=False)
RULES_SQUARE = Match3Rules(square_matches_enabled=True)

# A settled 5x5 board with several ordinary legal swaps and no specials.
QUIET_5X5 = match3_board(
    "g b g l r",
    "b g l g b",
    "d l d g d",
    "l d b r d",
    "r l d b b",
)


class CandidateEnumerationTests(unittest.TestCase):
    """Adjacent pairs and observed specials are each evaluated once."""

    def test_each_adjacent_pair_produces_at_most_one_evaluation(self) -> None:
        """Swap candidate cells never repeat a pair in either direction."""

        evaluations = evaluate_candidates(QUIET_5X5, RULES_PLAIN)
        pairs = [
            evaluation.action.cells
            for evaluation in evaluations
            if evaluation.action.kind is Match3ActionKind.SWAP
        ]
        self.assertEqual(len(pairs), len(set(pairs)))
        for first, second in pairs:
            self.assertLess(first, second)
            distance = abs(first.row - second.row) + abs(first.column - second.column)
            self.assertEqual(distance, 1)

    def test_same_color_pairs_are_not_emitted(self) -> None:
        """A no-op swap between identical colors is not a candidate."""

        evaluations = evaluate_candidates(QUIET_5X5, RULES_PLAIN)
        pairs = {
            evaluation.action.cells
            for evaluation in evaluations
            if evaluation.action.kind is Match3ActionKind.SWAP
        }
        self.assertNotIn((P(1, 3), P(2, 3)), pairs)
        self.assertNotIn((P(4, 3), P(4, 4)), pairs)

    def test_swapping_an_observed_special_is_unsupported(self) -> None:
        """Pairs touching a special report chaining instead of a guess."""

        board = match3_board(
            "r:nine b g",
            "b g l",
            "l d g",
        )
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        touching = [
            evaluation
            for evaluation in evaluations
            if evaluation.action.kind is Match3ActionKind.SWAP
            and P(0, 0) in evaluation.action.cells
        ]
        self.assertEqual(len(touching), 2)
        for evaluation in touching:
            self.assertFalse(evaluation.supported)
            self.assertTrue(any("special" in reason for reason in evaluation.reasons))

    def test_an_unrelated_special_does_not_invalidate_supported_swaps(self) -> None:
        """A dormant special elsewhere leaves ordinary moves supported."""

        board = match3_board(
            "r:nine b g",
            "b g l",
            "l d g",
        )
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        supported_swaps = [
            evaluation
            for evaluation in evaluations
            if evaluation.supported and evaluation.action.kind is Match3ActionKind.SWAP
        ]
        self.assertTrue(supported_swaps)
        self.assertEqual(supported_swaps[0].action.cells, (P(1, 1), P(1, 2)))

    def test_a_swap_whose_match_reaches_a_special_is_unsupported(self) -> None:
        """M1-R1 reproduction: a run reaching a special is not certified.

        The swapped pair would form a raw colorId run ending in the
        observed special, so the candidate reports unsupported instead of a
        truncated ordinary nine-grid creation.
        """

        board = match3_board(
            "g g b g g:nine",
            "d l g r b",
        )
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        reproduced = [
            evaluation
            for evaluation in evaluations
            if evaluation.action.cells == (P(0, 2), P(1, 2))
        ]
        self.assertEqual(len(reproduced), 1)
        self.assertFalse(reproduced[0].supported)
        self.assertIsNone(reproduced[0].creation)
        self.assertTrue(any("special" in reason for reason in reproduced[0].reasons))
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        self.assertNotEqual(decision.action.cells, (P(0, 2), P(1, 2)))

    def test_a_swap_matching_through_a_special_in_the_middle_is_unsupported(self) -> None:
        """A special between matched cells is involvement, not a gap."""

        board = match3_board(
            "r r:nine b",
            "d l r",
        )
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        middle = [
            evaluation
            for evaluation in evaluations
            if evaluation.action.cells == (P(0, 2), P(1, 2))
        ]
        self.assertEqual(len(middle), 1)
        self.assertFalse(middle[0].supported)
        self.assertTrue(any("special" in reason for reason in middle[0].reasons))

    def test_a_swap_completing_a_square_through_a_special_is_unsupported(self) -> None:
        """An enabled square that includes a special is not a clean cross."""

        board = match3_board(
            "r r:nine b",
            "r b r",
        )
        action = Match3Action(kind=Match3ActionKind.SWAP, cells=(P(1, 1), P(1, 2)))
        enabled = [
            evaluation
            for evaluation in evaluate_candidates(board, RULES_SQUARE)
            if evaluation.action == action
        ]
        self.assertEqual(len(enabled), 1)
        self.assertFalse(enabled[0].supported)
        self.assertTrue(any("special" in reason for reason in enabled[0].reasons))
        plain = [
            evaluation
            for evaluation in evaluate_candidates(board, RULES_PLAIN)
            if evaluation.action == action
        ]
        self.assertEqual(plain, [])

    def test_a_supported_swap_exposes_creation_and_affected_cells(self) -> None:
        """Swap evaluations carry the best creation kind and matched cells."""

        board = match3_board(
            "g g b g d",
            "d l g r b",
            "b d l r r",
            "l g r d r",
        )
        evaluations = evaluate_candidates(board, RULES_SQUARE)
        creations = {
            evaluation.action.cells: evaluation.creation
            for evaluation in evaluations
            if evaluation.supported
        }
        self.assertIs(creations[(P(0, 2), P(1, 2))], Match3SpecialKind.NINE_GRID)
        self.assertIs(creations[(P(3, 2), P(3, 3))], Match3SpecialKind.CROSS)

    def test_click_footprint_clearing_another_special_is_unsupported(self) -> None:
        """Activation that would chain a second special is not simulated."""

        board = match3_board("r:nine b:nine")
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        self.assertTrue(evaluations)
        self.assertFalse(any(evaluation.supported for evaluation in evaluations))
        self.assertTrue(
            all(
                any("unqualified" in reason or "special" in reason for reason in e.reasons)
                for e in evaluations
            )
        )

    def test_click_on_a_colorless_color_clear_is_unsupported(self) -> None:
        """A color-clear without an observed color has no honest footprint."""

        board = match3_board(".:color b", "g d")
        evaluations = evaluate_candidates(board, RULES_PLAIN)
        clicks = [
            evaluation
            for evaluation in evaluations
            if evaluation.action.kind is Match3ActionKind.SPECIAL_CLICK
        ]
        self.assertEqual(len(clicks), 1)
        self.assertFalse(clicks[0].supported)


class DecideStatusTests(unittest.TestCase):
    """Decisions are explicit about unsupported and unsettled states."""

    def test_unreadable_tiles_yield_unsupported_state(self) -> None:
        """Unknown colors never get fabricated or guessed."""

        board = match3_board(
            "g . b",
            "d l r",
            "g b d",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.UNSUPPORTED_STATE)
        self.assertIsNone(decision.action)
        self.assertIn("unreadable", decision.explanation)

    def test_preexisting_matches_yield_unsettled_board(self) -> None:
        """A board already matching may still be resolving server-side."""

        board = match3_board(
            "g g g",
            "b d l",
            "r g b",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.UNSETTLED_BOARD)
        self.assertIsNone(decision.action)
        self.assertEqual(decision.evaluations, ())

    def test_a_preexisting_special_involving_match_is_unsupported_not_settled(self) -> None:
        """A raw match through a special is unqualified, never "settled"."""

        board = match3_board(
            "r r:nine r b",
            "d l b r",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.UNSUPPORTED_STATE)
        self.assertIsNone(decision.action)
        self.assertIn("special", decision.explanation)

    def test_a_square_only_board_is_settled_only_when_the_rule_applies(self) -> None:
        """The square rule decides whether a lone 2x2 is unsettled."""

        board = match3_board(
            "r r b",
            "r r g",
            "d l b",
        )
        self.assertIs(decide(board, RULES_SQUARE).status, Match3DecisionStatus.UNSETTLED_BOARD)
        self.assertIsNot(decide(board, RULES_PLAIN).status, Match3DecisionStatus.UNSETTLED_BOARD)

    def test_no_legal_move_is_an_honest_result(self) -> None:
        """A settled board with no legal action reports no_legal_move.

        The board colors cells by ``(row + column) % 3``, so every legal
        swap leaves runs of at most two and no move exists.
        """

        board = match3_board(
            "g b d",
            "b d g",
            "d g b",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.NO_LEGAL_MOVE)
        self.assertIsNone(decision.action)
        self.assertIn("no legal swap", decision.explanation)

    def test_only_unqualified_mechanics_yields_unsupported_state(self) -> None:
        """Candidates that only chain specials stay distinct from no_move."""

        board = match3_board("r:cross b:nine")
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.UNSUPPORTED_STATE)
        self.assertIsNone(decision.action)
        self.assertTrue(decision.evaluations)
        self.assertFalse(any(evaluation.supported for evaluation in decision.evaluations))

    def test_board_dimensions_never_depend_on_a_feature_context(self) -> None:
        """Decisions run on the input shape alone for 5x7 and 7x7 boards."""

        checker_5x7 = match3_board(
            "g b d g b d g",
            "b d g b d g b",
            "d g b d g b d",
            "g b d g b d g",
            "b d g b d g b",
        )
        self.assertEqual((checker_5x7.rows, checker_5x7.columns), (5, 7))
        checker_7x7 = match3_board(
            "g b d g b d g",
            "b d g b d g b",
            "d g b d g b d",
            "g b d g b d g",
            "b d g b d g b",
            "d g b d g b d",
            "g b d g b d g",
        )
        self.assertEqual((checker_7x7.rows, checker_7x7.columns), (7, 7))
        for board in (checker_5x7, checker_7x7):
            decision = decide(board, RULES_PLAIN)
            self.assertIs(decision.status, Match3DecisionStatus.NO_LEGAL_MOVE)

    def test_an_action_decision_carries_explanation_and_limitations(self) -> None:
        """The chosen action explains itself and labels its heuristic."""

        decision = decide(QUIET_5X5, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        self.assertIsNotNone(decision.action)
        self.assertTrue(decision.explanation.strip())
        self.assertTrue(any("uncalibrated" in item for item in decision.limitations))

    def test_decide_rejects_untyped_inputs(self) -> None:
        """The boundary requires the typed board and typed rules."""

        with self.assertRaises(TypeError):
            decide("board", RULES_PLAIN)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            decide(QUIET_5X5, "rules")  # type: ignore[arg-type]


class BaselineRankingTests(unittest.TestCase):
    """The documented lexicographic heuristic is deterministic."""

    def test_creation_potential_outranks_plain_matches(self) -> None:
        """A five-run color-clear beats every ordinary three-match swap."""

        board = match3_board(
            "g g b g g",
            "d l g r b",
            "b d l g r",
            "l r d b g",
            "r b g d l",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        self.assertEqual(
            decision.action, Match3Action(kind=Match3ActionKind.SWAP, cells=(P(0, 2), P(1, 2)))
        )
        self.assertIs(decision.evaluations[0].creation, Match3SpecialKind.COLOR_CLEAR)
        self.assertEqual(len(decision.evaluations[0].affected_cells), 5)
        self.assertIn("color_clear", decision.explanation)

    def test_nine_grid_creation_outranks_cross_creation(self) -> None:
        """Creation precedence orders supported candidates deterministically."""

        board = match3_board(
            "g g b g d",
            "d l g r b",
            "b d l r r",
            "l g r d r",
        )
        decision = decide(board, RULES_SQUARE)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        supported = [e for e in decision.evaluations if e.supported]
        self.assertIs(supported[0].creation, Match3SpecialKind.NINE_GRID)
        self.assertIs(supported[1].creation, Match3SpecialKind.CROSS)

    def test_affected_cell_count_breaks_creation_ties(self) -> None:
        """A larger immediate footprint beats a smaller plain match."""

        board = match3_board(
            "g b g l",
            "b r:cross g b",
            "d l b g",
        )
        decision = decide(board, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        self.assertIs(decision.action.kind, Match3ActionKind.SPECIAL_CLICK)
        self.assertEqual(len(decision.evaluations[0].affected_cells), 5)

    def test_stable_coordinate_tiebreak_picks_the_first_action(self) -> None:
        """Equal candidates resolve by action kind then row-major cells."""

        decision = decide(QUIET_5X5, RULES_PLAIN)
        self.assertIs(decision.status, Match3DecisionStatus.ACTION)
        self.assertEqual(
            decision.action,
            Match3Action(kind=Match3ActionKind.SWAP, cells=(P(0, 1), P(1, 1))),
        )
        cells = [e.action.cells for e in decision.evaluations if e.supported]
        self.assertEqual(cells, sorted(cells))

    def test_decide_is_deterministic(self) -> None:
        """The same board and rules always produce the identical decision."""

        first = decide(QUIET_5X5, RULES_PLAIN)
        second = decide(QUIET_5X5, RULES_PLAIN)
        self.assertEqual(first, second)

    def test_baseline_limitations_are_documented(self) -> None:
        """The heuristic never claims a win, damage or refill prediction."""

        self.assertTrue(any("uncalibrated" in item for item in BASELINE_LIMITATIONS))
        self.assertTrue(any("refill" in item or "cascade" in item for item in BASELINE_LIMITATIONS))
