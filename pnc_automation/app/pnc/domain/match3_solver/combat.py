"""Source-backed, uncalibrated combat opportunities for match-3 decisions.

The packaged non-PVP client sends colored armies from cleared cells through
their board columns toward the frontmost living enemy row. Actual targets,
damage, HP changes and refills come from the server report. This selector
therefore ranks observable opportunities, never predicted kills or win odds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3ActionKind,
    Match3Board,
    Match3CandidateEvaluation,
    Match3Decision,
    Match3DecisionStatus,
    Match3Rules,
    Match3TileColor,
)
from pnc_automation.app.pnc.domain.match3_solver.selection import decide


@dataclass(frozen=True, slots=True)
class Match3Enemy:
    """One observed enemy and its horizontal coverage in board columns."""

    enemy_id: str
    row: int
    min_column: int
    max_column: int
    turns_until_attack: int | None = None

    def __post_init__(self) -> None:
        """Reject unusable geometry and invalid observed pressure values."""

        if not isinstance(self.enemy_id, str) or not self.enemy_id.strip():
            raise ValueError("Match3Enemy.enemy_id must be non-empty.")
        for name, value in (
            ("row", self.row),
            ("min_column", self.min_column),
            ("max_column", self.max_column),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"Match3Enemy.{name} must be a non-negative integer.")
        if self.min_column > self.max_column:
            raise ValueError("Match3Enemy column span must be ordered.")
        if self.turns_until_attack is not None and (
            type(self.turns_until_attack) is not int or self.turns_until_attack < 0
        ):
            raise ValueError("Match3Enemy.turns_until_attack must be non-negative or unknown.")


@dataclass(frozen=True, slots=True)
class Match3Hero:
    """A living observed hero whose color may receive army MP effects."""

    color: Match3TileColor

    def __post_init__(self) -> None:
        """Require a known hero color for a color-alignment opportunity."""

        if not isinstance(self.color, Match3TileColor):
            raise TypeError("Match3Hero.color must be a Match3TileColor.")


class Match3AttackRouting(StrEnum):
    """The explicitly qualified army-target routing for this combat state."""

    COLUMN_FRONT = "column_front"


@dataclass(frozen=True, slots=True)
class Match3CombatState:
    """Living units and explicit attack routing for one settled board."""

    attack_routing: Match3AttackRouting
    enemies: tuple[Match3Enemy, ...]
    heroes: tuple[Match3Hero, ...]

    def __post_init__(self) -> None:
        """Keep enemy identity unique and avoid pretending an empty fight is active."""

        if not isinstance(self.attack_routing, Match3AttackRouting):
            raise TypeError("Match3CombatState.attack_routing must be a qualified routing kind.")
        if not isinstance(self.enemies, tuple) or not self.enemies or not all(
            isinstance(enemy, Match3Enemy) for enemy in self.enemies
        ):
            raise ValueError("Match3CombatState requires observed living enemies.")
        if len({enemy.enemy_id for enemy in self.enemies}) != len(self.enemies):
            raise ValueError("Match3CombatState enemy IDs must be unique.")
        if not isinstance(self.heroes, tuple) or not self.heroes or not all(
            isinstance(hero, Match3Hero) for hero in self.heroes
        ):
            raise ValueError("Match3CombatState requires observed living heroes.")


@dataclass(frozen=True, slots=True)
class _Opportunity:
    """Ordinal evidence for one candidate; no estimated damage or probability."""

    imminent_front_cells: int
    front_cells: int
    hero_color_cells: int


def _front_enemies(state: Match3CombatState, column: int) -> tuple[Match3Enemy, ...]:
    """Mirror the client's maximum-row front list for one board column."""

    covering = tuple(
        enemy for enemy in state.enemies if enemy.min_column <= column <= enemy.max_column
    )
    if not covering:
        return ()
    front_row = max(enemy.row for enemy in covering)
    return tuple(enemy for enemy in covering if enemy.row == front_row)


def _opportunity(
    board: Match3Board,
    evaluation: Match3CandidateEvaluation,
    state: Match3CombatState,
) -> _Opportunity:
    """Count affected-cell exposure after the logical swap, without a refill."""

    action = evaluation.action
    post = board.swapped(*action.cells) if action.kind is Match3ActionKind.SWAP else board
    hero_colors = {hero.color for hero in state.heroes}
    imminent = front = aligned = 0
    for position in evaluation.affected_cells:
        targets = _front_enemies(state, position.column)
        if targets:
            front += 1
            if any(
                enemy.turns_until_attack is not None and enemy.turns_until_attack <= 1
                for enemy in targets
            ):
                imminent += 1
        if post.tile_at(position).color in hero_colors:
            aligned += 1
    return _Opportunity(imminent, front, aligned)


COMBAT_LIMITATIONS: tuple[str, ...] = (
    "Combat ranking is an uncalibrated opportunity heuristic, not a win, "
    "survival or damage estimate.",
    "The server controls actual targets, damage, HP changes, refills and "
    "cascades; none are predicted.",
    "An affected match cell may become a special instead of an immediate attack army.",
    "Threat priority uses an observed countdown only; unknown countdowns "
    "supply no imminent-threat evidence.",
    "Enemy skill readiness and retaliation damage are not modeled.",
)


def decide_combat(
    board: Match3Board,
    rules: Match3Rules,
    state: Match3CombatState,
) -> Match3Decision:
    """Prefer observed imminent-front exposure, front exposure and hero color.

    The existing rule engine still determines legal actions and unsupported
    mechanics. Its stable ranking breaks tactical ties. This is a transparent
    one-step baseline until current battle reports calibrate combat terms.
    """

    if not isinstance(board, Match3Board):
        raise TypeError("decide_combat requires a Match3Board.")
    if not isinstance(state, Match3CombatState):
        raise TypeError("decide_combat requires a Match3CombatState.")
    if any(enemy.max_column >= board.columns for enemy in state.enemies):
        raise ValueError("Observed enemy columns must fit the board.")
    baseline = decide(board, rules)
    if baseline.status is not Match3DecisionStatus.ACTION:
        return Match3Decision(
            status=baseline.status,
            action=None,
            explanation=baseline.explanation,
            evaluations=baseline.evaluations,
            limitations=baseline.limitations + COMBAT_LIMITATIONS,
        )
    supported = tuple(item for item in baseline.evaluations if item.supported)
    unsupported = tuple(item for item in baseline.evaluations if not item.supported)
    opportunities = {item.action: _opportunity(board, item, state) for item in supported}
    ranked = tuple(
        sorted(
            supported,
            key=lambda item: (
                -opportunities[item.action].imminent_front_cells,
                -opportunities[item.action].front_cells,
                -opportunities[item.action].hero_color_cells,
            ),
        )
    )
    selected = ranked[0]
    opportunity = opportunities[selected.action]
    cells = ", ".join(f"({cell.row},{cell.column})" for cell in selected.action.cells)
    return Match3Decision(
        status=Match3DecisionStatus.ACTION,
        action=selected.action,
        explanation=(
            f"{selected.action.kind.value} {cells}; "
            f"{opportunity.imminent_front_cells} imminent-front, "
            f"{opportunity.front_cells} front and "
            f"{opportunity.hero_color_cells} hero-color affected-cell opportunities"
        ),
        evaluations=ranked + unsupported,
        limitations=baseline.limitations + COMBAT_LIMITATIONS,
    )
