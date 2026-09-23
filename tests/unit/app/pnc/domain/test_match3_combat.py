"""Source-backed tactical opportunity ranking without damage forecasts."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.match3_solver.combat import (
    Match3AttackRouting,
    Match3CombatState,
    Match3Enemy,
    Match3Hero,
    decide_combat,
)
from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3DecisionStatus,
    Match3Position,
    Match3Rules,
    Match3TileColor,
)
from pnc_automation.app.pnc.domain.match3_solver.selection import decide
from tests.support.pnc.match3_boards import match3_board


P = Match3Position
RULES = Match3Rules(square_matches_enabled=False)
ROUTING = Match3AttackRouting.COLUMN_FRONT
BOARD = match3_board(
    "g b g l r",
    "b g l g b",
    "d l d g d",
    "l d b r d",
    "r l d b b",
)


class CombatOpportunityTests(unittest.TestCase):
    """The selector uses observed front columns and countdowns only."""

    def test_imminent_front_enemy_changes_the_baseline_action(self) -> None:
        """A threatened front in column 3 wins over a neutral row match."""

        self.assertEqual(decide(BOARD, RULES).action.cells, (P(0, 1), P(1, 1)))
        state = Match3CombatState(
            attack_routing=ROUTING,
            enemies=(
                Match3Enemy("front", row=2, min_column=3, max_column=3, turns_until_attack=1),
            ),
            heroes=(Match3Hero(Match3TileColor.RED),),
        )
        decision = decide_combat(BOARD, RULES, state)
        self.assertEqual(decision.action.cells, (P(0, 2), P(0, 3)))
        self.assertIn("3 imminent-front", decision.explanation)
        self.assertTrue(any("not a win" in item for item in decision.limitations))

    def test_rear_enemy_does_not_supply_imminent_front_pressure(self) -> None:
        """The client's frontmost row shadows a rear countdown in its column."""

        state = Match3CombatState(
            attack_routing=ROUTING,
            enemies=(
                Match3Enemy("rear", row=1, min_column=3, max_column=3, turns_until_attack=1),
                Match3Enemy("front", row=2, min_column=3, max_column=3, turns_until_attack=4),
                Match3Enemy("left", row=1, min_column=0, max_column=0, turns_until_attack=1),
            ),
            heroes=(Match3Hero(Match3TileColor.RED),),
        )
        decision = decide_combat(BOARD, RULES, state)
        self.assertEqual(decision.action.cells, (P(0, 1), P(1, 1)))
        self.assertIn("1 imminent-front", decision.explanation)

    def test_hero_color_breaks_equal_front_exposure(self) -> None:
        """Color alignment is an MP opportunity, not an asserted MP gain."""

        state = Match3CombatState(
            attack_routing=ROUTING,
            enemies=(Match3Enemy("wide", row=1, min_column=0, max_column=4),),
            heroes=(Match3Hero(Match3TileColor.BLUE),),
        )
        decision = decide_combat(BOARD, RULES, state)
        self.assertEqual(decision.action.cells, (P(3, 2), P(4, 2)))
        self.assertIn("3 hero-color", decision.explanation)
        self.assertTrue(
            any("server controls actual targets" in item for item in decision.limitations)
        )

    def test_unknown_tile_still_stops_before_combat_ranking(self) -> None:
        """Tactical state does not override the canonical unreadable-board guard."""

        board = match3_board("g . b", "r g l", "l b d")
        state = Match3CombatState(
            attack_routing=ROUTING,
            enemies=(Match3Enemy("one", row=0, min_column=0, max_column=2),),
            heroes=(Match3Hero(Match3TileColor.RED),),
        )
        decision = decide_combat(board, RULES, state)
        self.assertIs(decision.status, Match3DecisionStatus.UNSUPPORTED_STATE)
        self.assertIsNone(decision.action)

    def test_out_of_board_enemy_span_is_rejected(self) -> None:
        """Combat geometry cannot be silently clipped to the observed board."""

        state = Match3CombatState(
            attack_routing=ROUTING,
            enemies=(Match3Enemy("one", row=0, min_column=0, max_column=5),),
            heroes=(Match3Hero(Match3TileColor.RED),),
        )
        with self.assertRaisesRegex(ValueError, "fit the board"):
            decide_combat(BOARD, RULES, state)

    def test_attack_routing_must_be_explicit(self) -> None:
        """A context name cannot silently imply the packaged column-front rule."""

        with self.assertRaisesRegex(TypeError, "qualified routing"):
            Match3CombatState(  # type: ignore[arg-type]
                attack_routing="column_front",
                enemies=(Match3Enemy("one", row=0, min_column=0, max_column=4),),
                heroes=(Match3Hero(Match3TileColor.RED),),
            )

    def test_absent_living_heroes_cannot_produce_a_battle_action(self) -> None:
        """A terminal or incomplete hero observation must stop tactical input."""

        with self.assertRaisesRegex(ValueError, "living heroes"):
            Match3CombatState(
                attack_routing=ROUTING,
                enemies=(Match3Enemy("one", row=0, min_column=0, max_column=4),),
                heroes=(),
            )
