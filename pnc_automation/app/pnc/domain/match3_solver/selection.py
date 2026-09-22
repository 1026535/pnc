"""Candidate enumeration and deterministic baseline one-step selection.

Every orthogonally adjacent ordinary-tile pair is examined once; a swap is
legal only when it creates a supported match involving a swapped position.
Observed specials are separate click actions. Swapping a special, or
activating one whose footprint clears another special, is unqualified
chaining: the candidate is reported unsupported rather than simulated.

Match patterns are detected by observed color through ordinary and
special cells alike, mirroring the client's colorId comparisons. A swap
candidate whose resulting match group contains an observed special is
reported unsupported — the client forwards that pattern to the server and
its chained resolution is unqualified — instead of being certified as a
truncated ordinary match.

Ranking is a documented lexicographic heuristic over supported immediate
features only: highest creation potential (color-clear > nine-grid > cross
> none), then immediate affected/matched cell count, then a stable
action/row/column tie-break. It is an uncalibrated baseline, not a win or
damage probability, and later combat-aware selection can re-rank the
exposed evaluations without duplicating the rule engine.
"""

from __future__ import annotations

from pnc_automation.app.pnc.domain.match3_solver.models import (
    Match3Action,
    Match3ActionKind,
    Match3Board,
    Match3CandidateEvaluation,
    Match3Decision,
    Match3DecisionStatus,
    Match3Position,
    Match3Rules,
    Match3SpecialKind,
)
from pnc_automation.app.pnc.domain.match3_solver.rules import (
    group_creation,
    group_has_special,
    horizontal_run_through,
    match_groups,
    special_footprint,
    swapped_match_groups,
    vertical_run_through,
)

_CREATION_RANK = {
    Match3SpecialKind.COLOR_CLEAR: 3,
    Match3SpecialKind.NINE_GRID: 2,
    Match3SpecialKind.CROSS: 1,
}

_ACTION_RANK = {
    Match3ActionKind.SWAP: 0,
    Match3ActionKind.SPECIAL_CLICK: 1,
}

BASELINE_LIMITATIONS: tuple[str, ...] = (
    "Baseline ranking is an uncalibrated lexicographic heuristic, not a win or damage estimate.",
    "Gravity, refills, cascades, special placement, chained effects and exact damage are unqualified and not simulated.",
    "Affected cell counts describe matched or footprint cells, not guaranteed clears or server outcomes.",
    "Match patterns involving an observed special are reported unsupported; their chained resolution is unqualified.",
)


def _adjacent_pairs(board: Match3Board) -> tuple[tuple[Match3Position, Match3Position], ...]:
    """Each orthogonally adjacent cell pair exactly once, in row-major order."""

    pairs: list[tuple[Match3Position, Match3Position]] = []
    for position in board.positions():
        for row, column in ((position.row, position.column + 1), (position.row + 1, position.column)):
            if row < board.rows and column < board.columns:
                pairs.append((position, Match3Position(row=row, column=column)))
    return tuple(pairs)


def _max_run_length(board: Match3Board, group: frozenset[Match3Position]) -> int:
    """Longest straight run inside one group, used only for explanations."""

    longest = 0
    for position in group:
        longest = max(
            longest,
            len(horizontal_run_through(board, position)),
            len(vertical_run_through(board, position)),
        )
    return longest


def _creation_label(board: Match3Board, group: frozenset[Match3Position], kind: Match3SpecialKind) -> str:
    """Short human-readable description of how a group creates a special."""

    longest = _max_run_length(board, group)
    if kind is Match3SpecialKind.COLOR_CLEAR:
        if longest >= 5:
            return f"straight run of {longest}"
        return "intersecting runs (T/L)"
    if kind is Match3SpecialKind.NINE_GRID:
        return f"straight run of {longest}"
    return "2x2 square"


def _evaluate_swap(
    board: Match3Board,
    first: Match3Position,
    second: Match3Position,
    rules: Match3Rules,
) -> Match3CandidateEvaluation | None:
    """Evaluate one adjacent pair; returns None when the swap cannot be a move."""

    action = Match3Action(kind=Match3ActionKind.SWAP, cells=(first, second))
    first_tile = board.tile_at(first)
    second_tile = board.tile_at(second)
    if not first_tile.ordinary or not second_tile.ordinary:
        return Match3CandidateEvaluation(
            action=action,
            supported=False,
            creation=None,
            affected_cells=frozenset(),
            reasons=("swapping an observed special triggers unqualified activation/chaining",),
        )
    if first_tile.color is None or second_tile.color is None:
        return Match3CandidateEvaluation(
            action=action,
            supported=False,
            creation=None,
            affected_cells=frozenset(),
            reasons=("a swapped tile's color is unreadable",),
        )
    if first_tile.color == second_tile.color:
        return None
    post, groups = swapped_match_groups(board, first, second, rules)
    if not groups:
        return None
    affected = frozenset().union(*groups)
    if any(group_has_special(post, group) for group in groups):
        return Match3CandidateEvaluation(
            action=action,
            supported=False,
            creation=None,
            affected_cells=affected,
            reasons=(
                "the match would involve an observed special; chained resolution is unqualified",
            ),
        )
    creations = [
        kind
        for group in groups
        if (kind := group_creation(post, group, rules)) is not None
    ]
    creation = max(creations, key=lambda kind: _CREATION_RANK[kind]) if creations else None
    reasons: list[str] = []
    if len(creations) > 1:
        reasons.append(
            "multiple independent match groups would create specials; exact spawn placement/count is unqualified"
        )
    return Match3CandidateEvaluation(
        action=action,
        supported=True,
        creation=creation,
        affected_cells=affected,
        reasons=tuple(reasons),
    )


def _evaluate_click(board: Match3Board, position: Match3Position) -> Match3CandidateEvaluation | None:
    """Evaluate clicking one observed special tile."""

    tile = board.tile_at(position)
    if tile.special is None:
        return None
    action = Match3Action(kind=Match3ActionKind.SPECIAL_CLICK, cells=(position,))
    footprint = special_footprint(board, position)
    if footprint is None:
        return Match3CandidateEvaluation(
            action=action,
            supported=False,
            creation=None,
            affected_cells=frozenset(),
            reasons=("the special's observed color is unreadable",),
        )
    if any(
        cell != position and board.tile_at(cell).special is not None
        for cell in footprint
    ):
        return Match3CandidateEvaluation(
            action=action,
            supported=False,
            creation=None,
            affected_cells=footprint,
            reasons=("activation would clear another special; chaining is unqualified",),
        )
    return Match3CandidateEvaluation(
        action=action,
        supported=True,
        creation=None,
        affected_cells=footprint,
        reasons=(),
    )


def evaluate_candidates(board: Match3Board, rules: Match3Rules) -> tuple[Match3CandidateEvaluation, ...]:
    """Evaluate every adjacent swap pair and every observed special click.

    Illegal swaps (same-color, non-matching) are not emitted; unqualified
    candidates are returned with ``supported=False`` and an actionable
    reason. Order is deterministic: swaps in row-major pair order, then
    special clicks in row-major order.
    """

    evaluations: list[Match3CandidateEvaluation] = []
    for first, second in _adjacent_pairs(board):
        evaluation = _evaluate_swap(board, first, second, rules)
        if evaluation is not None:
            evaluations.append(evaluation)
    for position in board.positions():
        evaluation = _evaluate_click(board, position)
        if evaluation is not None:
            evaluations.append(evaluation)
    return tuple(evaluations)


def rank_evaluations(evaluations: tuple[Match3CandidateEvaluation, ...]) -> tuple[Match3CandidateEvaluation, ...]:
    """Order supported candidates by the documented lexicographic heuristic.

    Highest creation potential first, then immediate affected/matched cell
    count, then a stable action-kind/row/column tie-break. Unsupported
    candidates retain their enumeration order after the ranked block.
    """

    def key(evaluation: Match3CandidateEvaluation) -> tuple[int, int, int, tuple[Match3Position, ...]]:
        return (
            -_CREATION_RANK.get(evaluation.creation, 0),
            -len(evaluation.affected_cells),
            _ACTION_RANK[evaluation.action.kind],
            evaluation.action.cells,
        )

    supported = sorted((e for e in evaluations if e.supported), key=key)
    unsupported = tuple(e for e in evaluations if not e.supported)
    return tuple(supported) + unsupported


def _explain(evaluation: Match3CandidateEvaluation, board: Match3Board, rules: Match3Rules) -> str:
    """Human-readable explanation of the selected action."""

    action = evaluation.action
    cells = ", ".join(f"({cell.row},{cell.column})" for cell in action.cells)
    if action.kind is Match3ActionKind.SPECIAL_CLICK:
        kind = board.tile_at(action.cells[0]).special
        return (
            f"click {kind.value} special at {cells}: affects {len(evaluation.affected_cells)} cells"
        )
    first, second = action.cells
    post, groups = swapped_match_groups(board, first, second, rules)
    if evaluation.creation is not None:
        creating = next(
            (group for group in groups if group_creation(post, group, rules) == evaluation.creation),
            frozenset(),
        )
        label = _creation_label(post, creating, evaluation.creation)
        return (
            f"swap {cells}: creates {evaluation.creation.value} via {label}; "
            f"{len(evaluation.affected_cells)} matched cells"
        )
    return f"swap {cells}: ordinary match; {len(evaluation.affected_cells)} matched cells"


def decide(board: Match3Board, rules: Match3Rules) -> Match3Decision:
    """Recommend one explained legal action for a settled observed board.

    Unreadable tiles yield ``unsupported_state``; a board with pre-existing
    ordinary matches yields ``unsettled_board`` because the server may still
    be resolving it. A pre-existing pattern involving an observed special
    yields ``unsupported_state``: its chained resolution is permanently
    unqualified, not merely still settling. When every candidate needs
    unqualified mechanics the result is ``unsupported_state``, distinct
    from ``no_legal_move``.
    """

    if not isinstance(board, Match3Board):
        raise TypeError("decide requires a Match3Board.")
    if not isinstance(rules, Match3Rules):
        raise TypeError("decide requires a Match3Rules.")
    unreadable = [
        position for position in board.positions() if board.tile_at(position).color is None
    ]
    if unreadable:
        return Match3Decision(
            status=Match3DecisionStatus.UNSUPPORTED_STATE,
            action=None,
            explanation=(
                f"board contains {len(unreadable)} unreadable tile(s); "
                "no color is fabricated"
            ),
            evaluations=(),
            limitations=BASELINE_LIMITATIONS,
        )
    existing_groups = match_groups(board, rules)
    if existing_groups:
        if any(group_has_special(board, group) for group in existing_groups):
            return Match3Decision(
                status=Match3DecisionStatus.UNSUPPORTED_STATE,
                action=None,
                explanation=(
                    "board has a pre-existing color match involving an observed special; "
                    "its chained resolution is unqualified"
                ),
                evaluations=(),
                limitations=BASELINE_LIMITATIONS,
            )
        return Match3Decision(
            status=Match3DecisionStatus.UNSETTLED_BOARD,
            action=None,
            explanation="board has pre-existing ordinary matches; it may still be resolving",
            evaluations=(),
            limitations=BASELINE_LIMITATIONS,
        )
    evaluations = evaluate_candidates(board, rules)
    if not any(evaluation.supported for evaluation in evaluations):
        if evaluations:
            return Match3Decision(
                status=Match3DecisionStatus.UNSUPPORTED_STATE,
                action=None,
                explanation="every candidate action requires unqualified special mechanics",
                evaluations=evaluations,
                limitations=BASELINE_LIMITATIONS,
            )
        return Match3Decision(
            status=Match3DecisionStatus.NO_LEGAL_MOVE,
            action=None,
            explanation="no legal swap creates a supported match and no special can be clicked",
            evaluations=(),
            limitations=BASELINE_LIMITATIONS,
        )
    ranked = rank_evaluations(evaluations)
    selected = ranked[0]
    return Match3Decision(
        status=Match3DecisionStatus.ACTION,
        action=selected.action,
        explanation=_explain(selected, board, rules),
        evaluations=ranked,
        limitations=BASELINE_LIMITATIONS,
    )
