"""Immutable logical models for the pure match-3 board engine.

These types describe only what the shared observation layer can report and
what a caller can do next: row/column coordinates, a rectangular board of
typed tiles, the explicit rule switches, and logical swap/special-click
actions. Board dimensions come from the observed input, never from a
Campaign/Arena/Lost Land context name. An unknown tile color is
representable and yields an explicit unsupported decision rather than a
fabricated color or best guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Match3TileColor(StrEnum):
    """The five tile colors evidenced in the packaged battle client."""

    GREEN = "green"
    BLUE = "blue"
    DARK = "dark"
    LIGHT = "light"
    RED = "red"


class Match3SpecialKind(StrEnum):
    """Observed special tiles, named by their activation effect.

    The packaged client calls these ``COLOR_BOOM``, ``SMALL_BOOM`` and
    ``CROSS_BOOM``; the logical names describe the evidenced effect instead.
    """

    COLOR_CLEAR = "color_clear"
    NINE_GRID = "nine_grid"
    CROSS = "cross"


class Match3ActionKind(StrEnum):
    """The two distinct player actions evidenced by the client."""

    SWAP = "swap"
    SPECIAL_CLICK = "special_click"


class Match3DecisionStatus(StrEnum):
    """The honest outcome of one pure board decision."""

    ACTION = "action"
    NO_LEGAL_MOVE = "no_legal_move"
    UNSETTLED_BOARD = "unsettled_board"
    UNSUPPORTED_STATE = "unsupported_state"


@dataclass(frozen=True, order=True, slots=True)
class Match3Position:
    """One board cell in row/column coordinates, ordered row-major."""

    row: int
    column: int

    def __post_init__(self) -> None:
        """Require non-negative integer coordinates."""

        if not isinstance(self.row, int) or isinstance(self.row, bool):
            raise TypeError("Match3Position.row must be an int.")
        if not isinstance(self.column, int) or isinstance(self.column, bool):
            raise TypeError("Match3Position.column must be an int.")
        if self.row < 0 or self.column < 0:
            raise ValueError("Match3Position coordinates must be non-negative.")


@dataclass(frozen=True, slots=True)
class Match3Tile:
    """One observed board cell.

    ``color`` is ``None`` when the cell was not readable. A tile with a
    ``special`` kind is an observed special, clicked rather than swapped;
    ordinary tiles have ``special=None``.
    """

    color: Match3TileColor | None = None
    special: Match3SpecialKind | None = None

    def __post_init__(self) -> None:
        """Require typed members; an unknown color stays ``None``."""

        if self.color is not None and not isinstance(self.color, Match3TileColor):
            raise TypeError("Match3Tile.color must be a Match3TileColor or None.")
        if self.special is not None and not isinstance(self.special, Match3SpecialKind):
            raise TypeError("Match3Tile.special must be a Match3SpecialKind or None.")

    @property
    def ordinary(self) -> bool:
        """Reports whether this tile can participate in an ordinary swap."""

        return self.special is None


@dataclass(frozen=True, slots=True)
class Match3Rules:
    """The explicit rule switches a qualified observation supplies.

    ``square_matches_enabled`` is the evidenced new-puzzle rule that accepts
    a same-color 2x2 square as a match and creates a cross special. It is
    required and has no default: an unknown rule version must be surfaced by
    the caller, never silently coerced into either ruleset.
    """

    square_matches_enabled: bool

    def __post_init__(self) -> None:
        """Require a typed boolean rule switch."""

        if not isinstance(self.square_matches_enabled, bool):
            raise TypeError("Match3Rules.square_matches_enabled must be a bool.")


@dataclass(frozen=True, slots=True)
class Match3Board:
    """A rectangular board of observed tiles.

    ``tiles`` is indexed ``tiles[row][column]`` and must be non-empty and
    rectangular. Instances are immutable; ``swapped`` returns a new board.
    """

    tiles: tuple[tuple[Match3Tile, ...], ...]

    def __post_init__(self) -> None:
        """Require a non-empty rectangular grid of typed tiles."""

        if not isinstance(self.tiles, tuple) or not self.tiles:
            raise TypeError("Match3Board.tiles must be a non-empty tuple of row tuples.")
        width: int | None = None
        for row in self.tiles:
            if not isinstance(row, tuple) or not row:
                raise TypeError("Match3Board rows must be non-empty tuples.")
            if width is None:
                width = len(row)
            elif len(row) != width:
                raise ValueError("Match3Board must be rectangular.")
            for tile in row:
                if not isinstance(tile, Match3Tile):
                    raise TypeError("Match3Board cells must be Match3Tile values.")

    @classmethod
    def from_rows(cls, rows: tuple[tuple[Match3Tile, ...], ...] | list[list[Match3Tile]]) -> Match3Board:
        """Build a board from row sequences, validating rectangular shape."""

        return cls(tiles=tuple(tuple(row) for row in rows))

    @property
    def rows(self) -> int:
        """Board height in rows."""

        return len(self.tiles)

    @property
    def columns(self) -> int:
        """Board width in columns."""

        return len(self.tiles[0])

    def contains(self, position: Match3Position) -> bool:
        """Reports whether a position lies inside the board."""

        return 0 <= position.row < self.rows and 0 <= position.column < self.columns

    def tile_at(self, position: Match3Position) -> Match3Tile:
        """Return the tile at a position, rejecting out-of-board access."""

        if not isinstance(position, Match3Position):
            raise TypeError("Match3Board.tile_at requires a Match3Position.")
        if not self.contains(position):
            raise ValueError(f"Position {position} is outside the board.")
        return self.tiles[position.row][position.column]

    def positions(self) -> tuple[Match3Position, ...]:
        """All board positions in stable row-major order."""

        return tuple(
            Match3Position(row=row, column=column)
            for row in range(self.rows)
            for column in range(self.columns)
        )

    def swapped(self, first: Match3Position, second: Match3Position) -> Match3Board:
        """Return a new board with two positions exchanged; inputs unchanged."""

        self.tile_at(first)
        self.tile_at(second)
        rows = [list(row) for row in self.tiles]
        rows[first.row][first.column], rows[second.row][second.column] = (
            rows[second.row][second.column],
            rows[first.row][first.column],
        )
        return Match3Board(tiles=tuple(tuple(row) for row in rows))


@dataclass(frozen=True, slots=True)
class Match3Action:
    """One logical player action on the board.

    A swap carries exactly two orthogonally adjacent cells in row-major
    order; a special click carries the one observed special cell.
    """

    kind: Match3ActionKind
    cells: tuple[Match3Position, ...]

    def __post_init__(self) -> None:
        """Require a typed kind and the right number of typed cells."""

        if not isinstance(self.kind, Match3ActionKind):
            raise TypeError("Match3Action.kind must be a Match3ActionKind.")
        if not isinstance(self.cells, tuple) or not all(
            isinstance(cell, Match3Position) for cell in self.cells
        ):
            raise TypeError("Match3Action.cells must be a tuple of Match3Position values.")
        expected = 2 if self.kind is Match3ActionKind.SWAP else 1
        if len(self.cells) != expected:
            raise ValueError(f"A {self.kind.value} action requires exactly {expected} cell(s).")
        if self.kind is Match3ActionKind.SWAP and self.cells[0] >= self.cells[1]:
            raise ValueError("Swap cells must be distinct and in row-major order.")
        if self.kind is Match3ActionKind.SWAP:
            first, second = self.cells
            if abs(first.row - second.row) + abs(first.column - second.column) != 1:
                raise ValueError("Swap cells must be orthogonally adjacent.")


@dataclass(frozen=True, slots=True)
class Match3CandidateEvaluation:
    """The supported or rejected evaluation of one candidate action.

    ``creation`` is the best special the action could create, if any; the
    exact server-chosen spawn position/count is never predicted.
    ``affected_cells`` are the immediate matched cells for a swap or the
    activation footprint for a special click. For a creation candidate the
    count is the matched cells, not a claim every matched cell disappears.
    ``reasons`` carries the unsupported reason or the limitations of a
    supported evaluation.
    """

    action: Match3Action
    supported: bool
    creation: Match3SpecialKind | None
    affected_cells: frozenset[Match3Position]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require typed fields and a reason for unsupported candidates."""

        if not isinstance(self.action, Match3Action):
            raise TypeError("Match3CandidateEvaluation.action must be a Match3Action.")
        if not isinstance(self.supported, bool):
            raise TypeError("Match3CandidateEvaluation.supported must be a bool.")
        if self.creation is not None and not isinstance(self.creation, Match3SpecialKind):
            raise TypeError("Match3CandidateEvaluation.creation must be a Match3SpecialKind or None.")
        if not isinstance(self.affected_cells, frozenset) or not all(
            isinstance(cell, Match3Position) for cell in self.affected_cells
        ):
            raise TypeError(
                "Match3CandidateEvaluation.affected_cells must be a frozenset of Match3Position."
            )
        if not isinstance(self.reasons, tuple) or not all(
            isinstance(reason, str) and reason.strip() for reason in self.reasons
        ):
            raise TypeError("Match3CandidateEvaluation.reasons must be a tuple of non-empty strings.")
        if not self.supported and not self.reasons:
            raise ValueError("An unsupported candidate requires an actionable reason.")


@dataclass(frozen=True, slots=True)
class Match3Decision:
    """The explained one-step result for one settled observed board.

    ``evaluations`` lists every enumerated candidate in ranking order so
    later combat-aware selection can re-rank supported actions without
    duplicating the rule engine. ``limitations`` states what this baseline
    deliberately does not model.
    """

    status: Match3DecisionStatus
    action: Match3Action | None
    explanation: str
    evaluations: tuple[Match3CandidateEvaluation, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        """Require a typed status, honest explanation and consistent action."""

        if not isinstance(self.status, Match3DecisionStatus):
            raise TypeError("Match3Decision.status must be a Match3DecisionStatus.")
        if self.action is not None and not isinstance(self.action, Match3Action):
            raise TypeError("Match3Decision.action must be a Match3Action or None.")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("Match3Decision requires a non-empty explanation.")
        if not isinstance(self.evaluations, tuple) or not all(
            isinstance(evaluation, Match3CandidateEvaluation) for evaluation in self.evaluations
        ):
            raise TypeError("Match3Decision.evaluations must be a tuple of Match3CandidateEvaluation.")
        if not isinstance(self.limitations, tuple) or not all(
            isinstance(limitation, str) for limitation in self.limitations
        ):
            raise TypeError("Match3Decision.limitations must be a tuple of strings.")
        if self.status is Match3DecisionStatus.ACTION:
            if self.action is None:
                raise ValueError("An action decision must carry the selected action.")
        elif self.action is not None:
            raise ValueError("A non-action decision must not carry a selected action.")
