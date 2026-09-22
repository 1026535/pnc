"""Pure match-3 board model and rule-detector tests."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3Action,
    Match3ActionKind,
    Match3Board,
    Match3Position,
    Match3Rules,
    Match3SpecialKind,
    Match3Tile,
    Match3TileColor,
)
from pnc_automation.app.pnc.domain.match3_solver.rules import (
    creation_at,
    group_creation,
    group_has_special,
    match_at,
    match_groups,
    special_footprint,
    squares_through,
    swapped_match_groups,
)
from tests.support.pnc.match3_boards import match3_board


P = Match3Position
RULES_PLAIN = Match3Rules(square_matches_enabled=False)
RULES_SQUARE = Match3Rules(square_matches_enabled=True)


class Match3ModelTests(unittest.TestCase):
    """The immutable validated logical models reject untyped input."""

    def test_position_requires_non_negative_integer_coordinates(self) -> None:
        """Rows and columns are typed ints, never raw strings or negatives."""

        with self.assertRaises(TypeError):
            P(row="0", column=0)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            P(row=0, column=1.5)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            P(row=-1, column=0)

    def test_tile_requires_typed_members_and_allows_unknown_color(self) -> None:
        """An unreadable color is representable; raw strings are not."""

        self.assertIsNone(Match3Tile().color)
        with self.assertRaises(TypeError):
            Match3Tile(color="green")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Tile(special="cross")  # type: ignore[arg-type]

    def test_rules_require_an_explicit_square_rule_choice(self) -> None:
        """Omitting the rule switch is rejected; it never defaults to off."""

        with self.assertRaises(TypeError):
            Match3Rules()  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            Match3Rules(square_matches_enabled="yes")  # type: ignore[arg-type]
        self.assertTrue(Match3Rules(square_matches_enabled=True).square_matches_enabled)
        self.assertFalse(Match3Rules(square_matches_enabled=False).square_matches_enabled)

    def test_board_requires_a_rectangular_grid_of_tiles(self) -> None:
        """Ragged or empty boards and untyped cells are rejected."""

        green = Match3Tile(color=Match3TileColor.GREEN)
        with self.assertRaises(TypeError):
            Match3Board(tiles=())  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Match3Board(tiles=((green,), [green]))  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            Match3Board(tiles=((green, green), (green,)))
        with self.assertRaises(TypeError):
            Match3Board(tiles=((green, "x"),))  # type: ignore[arg-type]

    def test_board_dimensions_come_from_the_input_not_a_context(self) -> None:
        """Authored 5x7 and 7x7 shapes report their own dimensions."""

        five_by_seven = match3_board(*["g b d l r g b"] * 5)
        seven_by_seven = match3_board(*["g b d l r g b"] * 7)
        self.assertEqual((five_by_seven.rows, five_by_seven.columns), (5, 7))
        self.assertEqual((seven_by_seven.rows, seven_by_seven.columns), (7, 7))

    def test_models_are_immutable(self) -> None:
        """Frozen inputs cannot be mutated by callers after construction."""

        tile = Match3Tile(color=Match3TileColor.GREEN)
        board = Match3Board(tiles=((tile,),))
        with self.assertRaises(FrozenInstanceError):
            tile.color = Match3TileColor.RED  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            board.tiles = ((tile,),)  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            RULES_PLAIN.square_matches_enabled = True  # type: ignore[misc]

    def test_action_requires_the_right_cells_for_its_kind(self) -> None:
        """A swap carries adjacent row-major cells; a click carries one."""

        with self.assertRaises(ValueError):
            Match3Action(kind=Match3ActionKind.SWAP, cells=(P(0, 0),))
        with self.assertRaises(ValueError):
            Match3Action(kind=Match3ActionKind.SWAP, cells=(P(0, 1), P(0, 0)))
        with self.assertRaisesRegex(ValueError, "orthogonally adjacent"):
            Match3Action(kind=Match3ActionKind.SWAP, cells=(P(0, 0), P(1, 1)))
        with self.assertRaises(ValueError):
            Match3Action(kind=Match3ActionKind.SPECIAL_CLICK, cells=(P(0, 0), P(0, 1)))
        with self.assertRaises(TypeError):
            Match3Action(kind="swap", cells=(P(0, 0), P(0, 1)))  # type: ignore[arg-type]

    def test_swapped_returns_a_new_board_and_keeps_the_input_unchanged(self) -> None:
        """Rule evaluation never mutates the caller's board."""

        board = match3_board("g b", "d l")
        before = board.tiles
        post = board.swapped(P(0, 0), P(0, 1))
        self.assertEqual(board.tiles, before)
        self.assertIsNot(post, board)
        self.assertEqual(post.tile_at(P(0, 0)).color, Match3TileColor.BLUE)
        self.assertEqual(post.tile_at(P(0, 1)).color, Match3TileColor.GREEN)


class MatchDetectionTests(unittest.TestCase):
    """One detector classifies runs, squares, groups and creation potential."""

    def test_horizontal_runs_of_three_four_and_five_match(self) -> None:
        """Contiguous horizontal same-color runs of at least three match."""

        board = match3_board(
            "g g g b d",
            "b b b b g",
            "r r r r r",
        )
        for row in range(3):
            self.assertTrue(match_at(board, P(row, 1), RULES_PLAIN))
        self.assertFalse(match_at(board, P(0, 3), RULES_PLAIN))
        self.assertFalse(match_at(board, P(0, 4), RULES_PLAIN))

    def test_vertical_runs_of_three_four_and_five_match(self) -> None:
        """Contiguous vertical same-color runs of at least three match."""

        board = match3_board(
            "g b r d l",
            "g b r l d",
            "g b r d l",
            "d b r l g",
            "l d r g b",
        )
        self.assertTrue(match_at(board, P(1, 0), RULES_PLAIN))
        self.assertTrue(match_at(board, P(2, 1), RULES_PLAIN))
        self.assertTrue(match_at(board, P(0, 2), RULES_PLAIN))
        self.assertFalse(match_at(board, P(4, 0), RULES_PLAIN))
        self.assertFalse(match_at(board, P(4, 1), RULES_PLAIN))

    def test_a_straight_five_creates_a_color_clear(self) -> None:
        """Five in a line has color-clear creation potential."""

        board = match3_board(
            "r r r r r",
            "g b d l g",
        )
        self.assertIs(creation_at(board, P(0, 2), RULES_PLAIN), Match3SpecialKind.COLOR_CLEAR)

    def test_a_straight_four_creates_a_nine_grid(self) -> None:
        """Four in a line has nine-grid creation potential, not color-clear."""

        board = match3_board(
            "r r r r g",
            "g b d l b",
        )
        self.assertIs(creation_at(board, P(0, 1), RULES_PLAIN), Match3SpecialKind.NINE_GRID)
        self.assertIs(creation_at(board, P(1, 0), RULES_PLAIN), None)

    def test_intersecting_runs_in_a_t_pattern_create_a_color_clear(self) -> None:
        """A T of two >=3 runs sharing the center creates a color-clear."""

        board = match3_board(
            "b r d",
            "r r r",
            "g r b",
        )
        self.assertIs(creation_at(board, P(1, 1), RULES_PLAIN), Match3SpecialKind.COLOR_CLEAR)

    def test_intersecting_runs_in_an_l_pattern_create_a_color_clear(self) -> None:
        """An L of two >=3 runs sharing an elbow creates a color-clear."""

        board = match3_board(
            "r d b",
            "r g l",
            "r r r",
        )
        self.assertIs(creation_at(board, P(2, 0), RULES_PLAIN), Match3SpecialKind.COLOR_CLEAR)

    def test_four_with_a_perpendicular_pair_is_not_a_color_clear(self) -> None:
        """A run of four plus a short perpendicular tail stays nine-grid."""

        board = match3_board(
            "b r d l",
            "r r r r",
            "g d b r",
        )
        self.assertIs(creation_at(board, P(1, 1), RULES_PLAIN), Match3SpecialKind.NINE_GRID)

    def test_a_square_matches_only_when_the_rule_is_enabled(self) -> None:
        """The evidenced new-puzzle 2x2 square is an explicit rule switch."""

        board = match3_board(
            "r r b",
            "r r g",
            "d l b",
        )
        self.assertTrue(match_at(board, P(0, 0), RULES_SQUARE))
        self.assertFalse(match_at(board, P(0, 0), RULES_PLAIN))
        self.assertIs(creation_at(board, P(0, 0), RULES_SQUARE), Match3SpecialKind.CROSS)
        self.assertIs(creation_at(board, P(0, 0), RULES_PLAIN), None)

    def test_overlap_precedence_resolves_color_then_nine_grid_then_cross(self) -> None:
        """One overlapping group resolves to its highest-precedence creation."""

        color_group_board = match3_board(
            "r r d",
            "r r g",
            "r r r",
        )
        groups = match_groups(color_group_board, RULES_SQUARE)
        self.assertEqual(len(groups), 1)
        self.assertIs(
            group_creation(color_group_board, groups[0], RULES_SQUARE),
            Match3SpecialKind.COLOR_CLEAR,
        )
        nine_group_board = match3_board(
            "r r d",
            "r r g",
            "r r l",
            "r r b",
        )
        groups = match_groups(nine_group_board, RULES_SQUARE)
        self.assertEqual(len(groups), 1)
        self.assertIs(
            group_creation(nine_group_board, groups[0], RULES_SQUARE),
            Match3SpecialKind.NINE_GRID,
        )

    def test_a_six_run_is_one_group_with_single_color_clear_credit(self) -> None:
        """Oversized runs never duplicate lower-precedence creation credit."""

        board = match3_board("r r r r r r")
        groups = match_groups(board, RULES_PLAIN)
        self.assertEqual(len(groups), 1)
        self.assertIs(
            group_creation(board, groups[0], RULES_PLAIN), Match3SpecialKind.COLOR_CLEAR
        )

    def test_independent_match_groups_remain_separate(self) -> None:
        """Matches that share no cells are distinct groups."""

        board = match3_board(
            "g g g d l",
            "b d l r g",
            "r r r b d",
        )
        groups = match_groups(board, RULES_PLAIN)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], frozenset({P(0, 0), P(0, 1), P(0, 2)}))
        self.assertEqual(groups[1], frozenset({P(2, 0), P(2, 1), P(2, 2)}))

    def test_a_color_run_through_a_special_is_detected_not_hidden(self) -> None:
        """CheckHasBoom compares colorIds: a same-color special joins the run.

        The detector surfaces the involvement so callers mark it
        unsupported instead of certifying a truncated ordinary match.
        """

        board = match3_board(
            "r r r:nine",
            "b d l",
        )
        groups = match_groups(board, RULES_PLAIN)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], frozenset({P(0, 0), P(0, 1), P(0, 2)}))
        self.assertTrue(group_has_special(board, groups[0]))
        self.assertTrue(match_at(board, P(0, 0), RULES_PLAIN))
        self.assertIsNone(creation_at(board, P(0, 0), RULES_PLAIN))
        self.assertIsNone(group_creation(board, groups[0], RULES_PLAIN))

    def test_an_enabled_square_through_a_special_is_detected(self) -> None:
        """A same-color 2x2 including a special is a special-involving match."""

        board = match3_board(
            "r r:nine",
            "r r",
        )
        self.assertEqual(len(squares_through(board, P(0, 0))), 1)
        groups = match_groups(board, RULES_SQUARE)
        self.assertEqual(len(groups), 1)
        self.assertTrue(group_has_special(board, groups[0]))
        self.assertIsNone(group_creation(board, groups[0], RULES_SQUARE))
        self.assertEqual(match_groups(board, RULES_PLAIN), ())

    def test_an_unrelated_special_does_not_hide_a_clean_match(self) -> None:
        """A special outside the matched cells keeps the group ordinary."""

        board = match3_board(
            "r:nine b d",
            "g g g",
            "l d b",
        )
        groups = match_groups(board, RULES_PLAIN)
        self.assertEqual(len(groups), 1)
        self.assertFalse(group_has_special(board, groups[0]))


class SpecialFootprintTests(unittest.TestCase):
    """Special activation footprints are pure, deterministic and clipped."""

    def test_color_clear_hits_every_cell_of_its_observed_color(self) -> None:
        """The color-clear footprint is color-driven across the whole board."""

        board = match3_board(
            "r b r:color",
            "g r b",
            "r d l",
        )
        footprint = special_footprint(board, P(0, 2))
        self.assertEqual(
            footprint,
            frozenset({P(0, 0), P(0, 2), P(1, 1), P(2, 0)}),
        )

    def test_nine_grid_is_centered_and_clipped_at_edges(self) -> None:
        """Nine-grid clears a 3x3 centered on the special, clipped at edges."""

        board = match3_board(
            "r b d l g",
            "b g r:nine l d",
            "d l g b r",
            "l d b g r",
        )
        self.assertEqual(len(special_footprint(board, P(1, 2)) or ()), 9)
        corner = match3_board("r:nine b", "g d")
        self.assertEqual(
            special_footprint(corner, P(0, 0)),
            frozenset({P(0, 0), P(0, 1), P(1, 0), P(1, 1)}),
        )

    def test_cross_footprint_interior_edge_and_corner_clip(self) -> None:
        """Cross clears self plus orthogonal neighbors: 5/4/3 by position."""

        board = match3_board(
            "r b d",
            "b r:cross g",
            "d l b",
        )
        self.assertEqual(
            special_footprint(board, P(1, 1)),
            frozenset({P(1, 1), P(0, 1), P(2, 1), P(1, 0), P(1, 2)}),
        )
        edge = match3_board("r b r:cross d", "g d l b", "b g d r")
        self.assertEqual(
            special_footprint(edge, P(0, 2)),
            frozenset({P(0, 2), P(0, 1), P(0, 3), P(1, 2)}),
        )
        corner = match3_board("r:cross b", "g d")
        self.assertEqual(
            special_footprint(corner, P(0, 0)),
            frozenset({P(0, 0), P(0, 1), P(1, 0)}),
        )

    def test_spatial_effects_ignore_tile_color(self) -> None:
        """Nine-grid and cross clear mixed colors; only position matters."""

        board = match3_board(
            "g b d",
            "l r:nine g",
            "r d b",
        )
        footprint = special_footprint(board, P(1, 1))
        self.assertEqual(len(footprint or ()), 9)
        colors = {board.tile_at(cell).color for cell in footprint or ()}
        self.assertGreater(len(colors), 1)

    def test_footprint_is_none_without_a_special_or_its_color(self) -> None:
        """An ordinary tile or colorless color-clear has no honest footprint."""

        board = match3_board("r b", "g d")
        self.assertIsNone(special_footprint(board, P(0, 0)))
        colorless = match3_board(".:color b", "g d")
        self.assertIsNone(special_footprint(colorless, P(0, 0)))


class SwapLegalityTests(unittest.TestCase):
    """Rule-level swap evaluation mirrors CheckIfSwitchCell semantics."""

    def test_a_swap_creating_a_match_involving_an_endpoint_is_legal(self) -> None:
        """The post-swap board reports the group containing a swapped cell."""

        board = match3_board(
            "g b g",
            "b g l",
            "d l d",
        )
        post, groups = swapped_match_groups(board, P(0, 1), P(1, 1), RULES_PLAIN)
        self.assertEqual(len(groups), 1)
        self.assertIn(P(0, 1), groups[0])
        self.assertEqual(groups[0], frozenset({P(0, 0), P(0, 1), P(0, 2)}))
        self.assertEqual(post.tile_at(P(1, 1)).color, Match3TileColor.BLUE)

    def test_a_swap_creating_no_match_is_illegal(self) -> None:
        """No group involving a swapped endpoint means no legal move."""

        board = match3_board(
            "g b g",
            "b g l",
            "d l d",
        )
        _, groups = swapped_match_groups(board, P(0, 0), P(0, 1), RULES_PLAIN)
        self.assertEqual(groups, ())

    def test_a_remote_existing_match_cannot_legalize_a_swap(self) -> None:
        """Groups not containing a swapped position are ignored."""

        board = match3_board(
            "g g g",
            "b d l",
            "d l b",
        )
        _, groups = swapped_match_groups(board, P(1, 0), P(2, 0), RULES_PLAIN)
        self.assertEqual(groups, ())

    def test_squares_through_reports_each_quadrant_membership(self) -> None:
        """A cell can anchor a same-color square from any of four corners."""

        board = match3_board(
            "r r b",
            "r r g",
            "d l b",
        )
        squares = squares_through(board, P(0, 0))
        self.assertEqual(len(squares), 1)
        self.assertIn(P(1, 1), squares[0])
