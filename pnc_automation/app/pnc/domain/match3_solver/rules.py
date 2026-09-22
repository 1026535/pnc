"""Canonical match-3 pattern and effect detector.

One detector serves move legality, match/creation classification and
settled-board evaluation so no caller duplicates pattern knowledge. The
semantics mirror the packaged client's ``CheckHasBoom`` /
``CheckColorBoom`` / ``CheckNineGridBoom`` / ``CheckCrossBoom`` /
``CheckIfSwitchCell`` evidence: matches are horizontal or vertical
contiguous runs of at least three same-color cells, and the explicit
new-puzzle rule additionally accepts a same-color 2x2 square. The client
compares cell colorIds without excluding special functionTypes, so runs
and squares are detected by observed color across ordinary and special
tiles alike; ``group_has_special`` surfaces that involvement so callers
can mark it unsupported instead of truncating the pattern or simulating
the unqualified chained resolution. Creation precedence is color-clear >
nine-grid > cross within one overlapping match group; independent groups
each keep their own creation potential. Creation is only classified for
fully ordinary groups.

These functions never predict refills, cascades, spawn positions, chained
special outcomes or damage.
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3Board,
    Match3Position,
    Match3Rules,
    Match3SpecialKind,
    Match3TileColor,
)

_CREATION_PRECEDENCE = {
    Match3SpecialKind.COLOR_CLEAR: 3,
    Match3SpecialKind.NINE_GRID: 2,
    Match3SpecialKind.CROSS: 1,
}


def raw_color_at(board: Match3Board, position: Match3Position) -> Match3TileColor | None:
    """Return the cell's observed colorId whether it is ordinary or a special.

    Mirrors the client's colorId comparisons: a special tile keeps its
    observed color for pattern detection even though its participation in
    the resolution is unqualified.
    """

    return board.tile_at(position).color


def _run_through(
    board: Match3Board, position: Match3Position, row_step: int, column_step: int
) -> frozenset[Match3Position]:
    """Contiguous same-color cells through ``position`` on one axis."""

    color = raw_color_at(board, position)
    if color is None:
        return frozenset({position})
    cells = {position}
    for sign in (1, -1):
        row = position.row + row_step * sign
        column = position.column + column_step * sign
        while 0 <= row < board.rows and 0 <= column < board.columns:
            candidate = Match3Position(row=row, column=column)
            if raw_color_at(board, candidate) != color:
                break
            cells.add(candidate)
            row += row_step * sign
            column += column_step * sign
    return frozenset(cells)


def horizontal_run_through(board: Match3Board, position: Match3Position) -> frozenset[Match3Position]:
    """The maximal horizontal same-color run, including observed specials."""

    return _run_through(board, position, 0, 1)


def vertical_run_through(board: Match3Board, position: Match3Position) -> frozenset[Match3Position]:
    """The maximal vertical same-color run, including observed specials."""

    return _run_through(board, position, 1, 0)


def squares_through(board: Match3Board, position: Match3Position) -> tuple[frozenset[Match3Position], ...]:
    """Every same-color 2x2 square containing ``position``.

    Mirrors the client's four quadrant offsets: the position can be any of
    the four corners of a square, and cells compare by observed colorId
    including specials. Square membership alone does not imply a match
    unless the caller's rules enable square matching.
    """

    color = raw_color_at(board, position)
    if color is None:
        return ()
    squares: list[frozenset[Match3Position]] = []
    for row_offset, column_offset in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
        top = position.row + row_offset
        left = position.column + column_offset
        if top < 0 or left < 0 or top + 1 >= board.rows or left + 1 >= board.columns:
            continue
        cells = {
            Match3Position(row=top + dr, column=left + dc)
            for dr in (0, 1)
            for dc in (0, 1)
        }
        if all(raw_color_at(board, cell) == color for cell in cells):
            squares.append(frozenset(cells))
    return tuple(squares)


def match_at(board: Match3Board, position: Match3Position, rules: Match3Rules) -> bool:
    """Reports whether ``position`` participates in a color match.

    Equivalent to the client's ``CheckHasBoom``: a horizontal or vertical
    run of at least three through the position, or an enabled 2x2 square.
    Observed specials count toward the pattern by colorId; their
    involvement marks the containing group via ``group_has_special``.
    """

    if raw_color_at(board, position) is None:
        return False
    if len(horizontal_run_through(board, position)) >= 3:
        return True
    if len(vertical_run_through(board, position)) >= 3:
        return True
    return rules.square_matches_enabled and bool(squares_through(board, position))


def match_shapes(board: Match3Board, rules: Match3Rules) -> tuple[frozenset[Match3Position], ...]:
    """All maximal color-match shapes on the board.

    Shapes are maximal horizontal/vertical runs of at least three same-color
    cells plus, when enabled, every same-color 2x2 square. Observed specials
    participate by colorId exactly as the client's checks do.
    """

    shapes: list[frozenset[Match3Position]] = []
    for position in board.positions():
        color = raw_color_at(board, position)
        if color is None:
            continue
        for run in (
            horizontal_run_through(board, position),
            vertical_run_through(board, position),
        ):
            if len(run) >= 3 and run not in shapes:
                shapes.append(run)
        if rules.square_matches_enabled:
            for square in squares_through(board, position):
                if square not in shapes:
                    shapes.append(square)
    return tuple(shapes)


def match_groups(board: Match3Board, rules: Match3Rules) -> tuple[frozenset[Match3Position], ...]:
    """Maximal match groups: shapes sharing cells merge into one group.

    Overlapping run/square shapes form a single group so overlapping
    creation patterns resolve to one creation result, while independent
    groups remain distinct. Groups are returned in stable order sorted by
    their minimum row-major position.
    """

    groups: list[set[Match3Position]] = []
    for shape in match_shapes(board, rules):
        merged = set(shape)
        overlapping = [group for group in groups if group & shape]
        for group in overlapping:
            merged |= group
            groups.remove(group)
        groups.append(merged)
    groups.sort(key=min)
    return tuple(frozenset(group) for group in groups)


def group_has_special(board: Match3Board, group: frozenset[Match3Position]) -> bool:
    """Reports whether a match group contains an observed special cell.

    A special inside a matched pattern makes its resolution unqualified:
    the client forwards the pattern to the server rather than resolving it
    locally. Callers must check this predicate instead of assuming a
    matched group is purely ordinary.
    """

    return any(board.tile_at(position).special is not None for position in group)


def creation_at(board: Match3Board, position: Match3Position, rules: Match3Rules) -> Match3SpecialKind | None:
    """The special a settled ordinary match through ``position`` creates.

    Mirrors the client's ``CheckHasSpecialBoom`` precedence. A color-clear
    requires at least five unique same-color cells through the position and
    either a straight run of five or more, or intersecting horizontal and
    vertical runs of at least three each (the qualifying T/L). A straight
    run of four creates a nine-grid. An enabled 2x2 square creates a cross.

    Returns ``None`` when the matched structures through the position
    involve an observed special: that pattern's outcome is unqualified
    server-side resolution, not a predictable ordinary creation.
    """

    tile = board.tile_at(position)
    if not tile.ordinary or tile.color is None:
        return None
    horizontal = horizontal_run_through(board, position)
    vertical = vertical_run_through(board, position)
    squares = squares_through(board, position) if rules.square_matches_enabled else ()
    involved: set[Match3Position] = set()
    for run in (horizontal, vertical):
        if len(run) >= 3:
            involved |= run
    for square in squares:
        involved |= square
    if any(board.tile_at(cell).special is not None for cell in involved):
        return None
    unique = len(horizontal | vertical)
    if unique >= 5 and (
        len(horizontal) >= 5 or len(vertical) >= 5 or (len(horizontal) >= 3 and len(vertical) >= 3)
    ):
        return Match3SpecialKind.COLOR_CLEAR
    if len(horizontal) >= 4 or len(vertical) >= 4:
        return Match3SpecialKind.NINE_GRID
    if squares:
        return Match3SpecialKind.CROSS
    return None


def group_creation(
    board: Match3Board, group: frozenset[Match3Position], rules: Match3Rules
) -> Match3SpecialKind | None:
    """The single highest-precedence creation inside one match group.

    A six-plus run or larger overlap still resolves to one creation kind;
    callers must not credit lower-precedence duplicates within the group.
    A group containing an observed special has unqualified creation and
    returns ``None`` — callers surface it through ``group_has_special``.
    """

    if group_has_special(board, group):
        return None
    kinds = [
        kind
        for position in group
        if (kind := creation_at(board, position, rules)) is not None
    ]
    if not kinds:
        return None
    return max(kinds, key=lambda kind: _CREATION_PRECEDENCE[kind])


def swapped_match_groups(
    board: Match3Board,
    first: Match3Position,
    second: Match3Position,
    rules: Match3Rules,
) -> tuple[Match3Board, tuple[frozenset[Match3Position], ...]]:
    """Apply a swap and return the new board plus groups involving a swapped cell.

    Mirrors the client's ``CheckIfSwitchCell``: only matches containing at
    least one swapped position count, so a remote pre-existing match can
    never legalize a swap. The input board is unchanged.
    """

    post = board.swapped(first, second)
    groups = tuple(
        group
        for group in match_groups(post, rules)
        if first in group or second in group
    )
    return post, groups


def special_footprint(board: Match3Board, position: Match3Position) -> frozenset[Match3Position] | None:
    """The cells affected by clicking the observed special at ``position``.

    Returns ``None`` when the footprint cannot be honestly described: the
    tile is ordinary (not a special) or a color-clear whose observed color
    is unknown. Effects are clipped at board edges; spatial effects ignore
    tile color, while a color-clear affects every cell sharing its own
    observed color, including its own cell.
    """

    tile = board.tile_at(position)
    if tile.special is None:
        return None
    if tile.special is Match3SpecialKind.COLOR_CLEAR:
        if tile.color is None:
            return None
        return frozenset(
            candidate
            for candidate in board.positions()
            if board.tile_at(candidate).color == tile.color
        )
    if tile.special is Match3SpecialKind.NINE_GRID:
        return frozenset(
            candidate
            for candidate in board.positions()
            if abs(candidate.row - position.row) <= 1 and abs(candidate.column - position.column) <= 1
        )
    cells = {position}
    for row_step, column_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        row = position.row + row_step
        column = position.column + column_step
        if 0 <= row < board.rows and 0 <= column < board.columns:
            cells.add(Match3Position(row=row, column=column))
    return frozenset(cells)
