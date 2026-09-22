"""Authored match-3 board builder shared by pure rule/decision tests.

Each row is a whitespace-separated string of cell tokens. ``g`` ``b`` ``d``
``l`` ``r`` are ordinary colored tiles and ``.`` is an unreadable tile.
``<color>:cross``, ``<color>:nine`` and ``<color>:color`` author observed
specials carrying that color; ``.:<kind>`` authors a special whose color
was not readable. Board dimensions come from the authored rows only.
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3Board,
    Match3SpecialKind,
    Match3Tile,
    Match3TileColor,
)

_COLOR_TOKENS = {
    "g": Match3TileColor.GREEN,
    "b": Match3TileColor.BLUE,
    "d": Match3TileColor.DARK,
    "l": Match3TileColor.LIGHT,
    "r": Match3TileColor.RED,
}

_SPECIAL_TOKENS = {
    "cross": Match3SpecialKind.CROSS,
    "nine": Match3SpecialKind.NINE_GRID,
    "color": Match3SpecialKind.COLOR_CLEAR,
}


def match3_board(*rows: str) -> Match3Board:
    """Build a ``Match3Board`` from authored token rows.

    Raises ``ValueError`` naming the offending token when a row is empty or
    a token is unknown so authored-board typos fail loudly in tests.
    """

    if not rows:
        raise ValueError("At least one row is required.")
    parsed: list[list[Match3Tile]] = []
    for row_index, row in enumerate(rows):
        tokens = row.split()
        if not tokens:
            raise ValueError(f"Row {row_index} is empty.")
        parsed.append([_tile_token(token, row_index) for token in tokens])
    return Match3Board.from_rows(parsed)


def _tile_token(token: str, row_index: int) -> Match3Tile:
    """Parse one authored cell token into a ``Match3Tile``."""

    color_token, _, special_token = token.partition(":")
    if color_token == ".":
        color = None
    else:
        color = _COLOR_TOKENS.get(color_token)
        if color is None:
            raise ValueError(f"Unknown color token {color_token!r} in row {row_index}.")
    if not special_token:
        return Match3Tile(color=color)
    special = _SPECIAL_TOKENS.get(special_token)
    if special is None:
        raise ValueError(f"Unknown special token {special_token!r} in row {row_index}.")
    return Match3Tile(color=color, special=special)
