"""Goal evaluation and ranking (Plan 02 PW03).

One pass classifies the survey into assessments, evaluates every policy
goal against the observed board (allocation + advisory effort), and ranks
them inside their reward category. Zero-cost goals — ready, satisfied by
usable stock, or achievable through free merges/feeds alone — rank ahead of
every positive-cost goal. Goals with a known usable estimate rank ahead of
every goal whose estimate is absent or uncertain; inside each estimate
class the documented key order applies. Inspection resolves unresolved
contenders — clipped cards, UNKNOWN reward categories, and unread
quantities — before a guess is allowed to rank them.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import cmp_to_key

from pnc_automation.app.automation.pet_workshop.board import BoardFacts, MergeChains
from pnc_automation.app.automation.pet_workshop.effort import (
    GoalAllocation,
    GoalEffort,
    allocate_goal,
    estimate_goal,
)
from pnc_automation.app.automation.pet_workshop.policy import (
    OrderAssessment,
    assess_order,
)
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopOrderRewardCategory,
    WorkshopPolicy,
    WorkshopState,
    WorkshopSurveyCoverage,
    WorkshopSurveyFreshness,
)
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog


@dataclass(frozen=True, slots=True)
class GoalEvaluation:
    """One policy goal evaluated against the current board."""

    assessment: OrderAssessment
    allocation: GoalAllocation
    effort: GoalEffort

    @property
    def order_ref(self) -> int:
        """Returns the survey-local order ref."""

        return self.assessment.order.order_ref

    @property
    def ready(self) -> bool | None:
        """Returns the observed ready control state."""

        return self.assessment.order.ready

    @property
    def satisfied(self) -> bool:
        """Returns whether usable Normal stock already meets the order."""

        return self.allocation.satisfied

    @property
    def zero_cost(self) -> bool:
        """Returns whether the goal needs no production energy to finish."""

        return self.allocation.covered_by_stock


@dataclass(frozen=True, slots=True)
class GoalSelection:
    """The ranked goals plus the survey context the planner needs."""

    primary: GoalEvaluation | None
    ranked: tuple[GoalEvaluation, ...]
    assessments: tuple[OrderAssessment, ...]
    survey_ok: bool
    inspect_order_ref: int | None
    reason: str

    def evaluation_for(self, order_ref: int) -> GoalEvaluation | None:
        """Returns the evaluation for one surveyed order, or ``None``."""

        for evaluation in self.ranked:
            if evaluation.order_ref == order_ref:
                return evaluation
        return None

    @property
    def eligible_refs(self) -> frozenset[int]:
        """Returns order refs admitted as policy goals."""

        return frozenset(evaluation.order_ref for evaluation in self.ranked)


def _ratio(evaluation: GoalEvaluation) -> Fraction:
    """Primary reward quantity per unit of advisory energy (0 if infeasible)."""

    energy = evaluation.effort.energy
    if energy is None or energy <= 0:
        return Fraction(0)
    return Fraction(evaluation.assessment.primary_quantity or 0) / energy


def _estimate_known(evaluation: GoalEvaluation) -> bool:
    """Returns whether the goal carries a known usable numerical estimate.

    ``energy=None`` (no supported path) and ``uncertain=True`` (a finite
    producer's unobserved remaining uses) both count as unknown — only a
    real, certain estimate ranks in the known class.
    """

    return evaluation.effort.energy is not None and not evaluation.effort.uncertain


def _secondary_key(assessment: OrderAssessment) -> tuple[int, ...]:
    """Provisional sort key for the policy-ordered secondary rewards.

    Unread counts sort as 0 here; the selection pass inspects any contender
    whose unread entries could still change the applicable ranking.
    """

    return tuple(q if q is not None else 0 for q in assessment.secondary_quantities)


def _compare_positive(a: GoalEvaluation, b: GoalEvaluation) -> int:
    """Orders two goals inside one reward category (Plan 02 ordering).

    Known usable estimates always rank above absent or uncertain ones.
    Inside the known class the comparison is reward-per-unit-energy ratio,
    then less remaining estimated effort. Inside the unknown class no
    made-up ratio or sentinel applies: the primary reward quantity decides.
    Both classes then take the policy-ordered secondary rewards and the
    stable survey index.
    """

    known_a, known_b = _estimate_known(a), _estimate_known(b)
    if known_a != known_b:
        return -1 if known_a else 1
    if known_a:
        ratio_a, ratio_b = _ratio(a), _ratio(b)
        if ratio_a != ratio_b:
            return -1 if ratio_a > ratio_b else 1
        energy_a, energy_b = a.effort.energy, b.effort.energy
        if energy_a != energy_b:
            return -1 if energy_a < energy_b else 1
    else:
        primary_a = a.assessment.primary_quantity or 0
        primary_b = b.assessment.primary_quantity or 0
        if primary_a != primary_b:
            return -1 if primary_a > primary_b else 1
    secondary_a = _secondary_key(a.assessment)
    secondary_b = _secondary_key(b.assessment)
    if secondary_a != secondary_b:
        return -1 if secondary_a > secondary_b else 1
    return a.assessment.survey_index - b.assessment.survey_index


def _zero_key(evaluation: GoalEvaluation) -> tuple:
    """Orders zero-cost goals: primary reward, fewer free actions, secondary.

    The secondary comparison follows the policy category order, not a sum
    of unrelated reward counts. An observed ready control breaks the
    remaining tie; the survey index keeps the ordering total.
    """

    ready_penalty = 0 if evaluation.ready is True else 1
    return (
        -(evaluation.assessment.primary_quantity or 0),
        evaluation.allocation.free_actions,
        tuple(-q for q in _secondary_key(evaluation.assessment)),
        ready_penalty,
        evaluation.assessment.survey_index,
    )


def _ties_before_secondary(a: GoalEvaluation, b: GoalEvaluation) -> bool:
    """Returns whether two ranked goals tie on every key before secondary.

    Only then can an unread secondary count still reorder them — a decided
    earlier key makes the unread fact irrelevant to the applicable ranking.
    """

    if a.zero_cost != b.zero_cost:
        return False
    primary_a = a.assessment.primary_quantity or 0
    primary_b = b.assessment.primary_quantity or 0
    if a.zero_cost:
        return (
            primary_a == primary_b
            and a.allocation.free_actions == b.allocation.free_actions
        )
    known_a, known_b = _estimate_known(a), _estimate_known(b)
    if known_a != known_b:
        return False
    if known_a:
        return _ratio(a) == _ratio(b) and a.effort.energy == b.effort.energy
    return primary_a == primary_b


def _secondary_inspect_ref(
    contender: GoalEvaluation, rival: GoalEvaluation
) -> int | None:
    """Returns the order to inspect when an unread secondary could reorder.

    Walks the policy-ordered secondary positions; the first position that is
    unread on either side — before any decisive known difference — names the
    card whose contents must be read.
    """

    for own, other in zip(
        contender.assessment.secondary_quantities,
        rival.assessment.secondary_quantities,
    ):
        if own is None or other is None:
            return contender.order_ref if own is None else rival.order_ref
        if own != other:
            return None
    return None


def rank_goals(evaluations: list[GoalEvaluation]) -> list[GoalEvaluation]:
    """Ranks evaluated goals of one reward category.

    Zero-cost goals form an earlier class than every positive-cost goal;
    within a class the order is the documented zero-cost key and the
    ratio/effort comparator respectively.
    """

    zero = sorted(
        (evaluation for evaluation in evaluations if evaluation.zero_cost),
        key=_zero_key,
    )
    positive = sorted(
        (evaluation for evaluation in evaluations if not evaluation.zero_cost),
        key=cmp_to_key(_compare_positive),
    )
    return [*zero, *positive]


def _ranking_inspect_ref(ranked: list[GoalEvaluation]) -> int | None:
    """Finds unread rewards that can change a same-category selection."""

    for goal in ranked:
        if goal.assessment.primary_quantity is None:
            return goal.order_ref
    if ranked:
        leader = ranked[0]
        for contender in ranked[1:]:
            if _ties_before_secondary(contender, leader):
                pending = _secondary_inspect_ref(contender, leader)
                if pending is not None:
                    return pending
    return None


def select_goals(
    state: WorkshopState,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> GoalSelection:
    """Evaluates and ranks the survey's policy goals for one state.

    The primary goal is the top-ranked goal of the best occupied reward
    category; categories are never mixed and a lower-category goal is never
    produced toward while a higher-category goal exists. When a candidate's
    reward facts were never read, ``inspect_order_ref`` names the order whose
    inspection is required before ranking can be trusted.
    """

    survey = state.order_survey
    assessments = tuple(
        assess_order(order, index, catalog, policy)
        for index, order in enumerate(survey.orders)
    )
    survey_ok = (
        survey.coverage == WorkshopSurveyCoverage.COMPLETE
        and survey.freshness == WorkshopSurveyFreshness.CURRENT
    )
    goals = [assessment for assessment in assessments if assessment.is_goal]
    if not survey_ok:
        return GoalSelection(
            primary=None,
            ranked=(),
            assessments=assessments,
            survey_ok=False,
            inspect_order_ref=None,
            reason="order survey is not complete and current",
        )
    # Unresolved contenders — clipped or otherwise unread cards, and
    # eligible cards carrying an UNKNOWN reward category — could change the
    # applicable ranking, so their contents are read before it is trusted.
    # Known ineligible cards (proven totals, unknown item ids, resolved
    # non-order rows) never reach this list.
    inspect_order_ref = next(
        (
            assessment.order.order_ref
            for assessment in assessments
            if assessment.unresolved or assessment.unknown_reward
        ),
        None,
    )
    if not goals:
        return GoalSelection(
            primary=None,
            ranked=(),
            assessments=assessments,
            survey_ok=True,
            inspect_order_ref=inspect_order_ref,
            reason="no eligible two-piece order in the complete survey",
        )
    best_rank = min(assessment.category_rank for assessment in goals if assessment.category_rank is not None)
    candidates = [
        assessment for assessment in goals if assessment.category_rank == best_rank
    ]
    board = BoardFacts(state)
    chains = MergeChains(catalog)
    evaluated: dict[int, GoalEvaluation] = {}
    for assessment in goals:
        allocation = allocate_goal(
            assessment.order.requirements, board, chains, catalog
        )
        effort = estimate_goal(allocation, board, chains, catalog)
        evaluated[assessment.order.order_ref] = GoalEvaluation(
            assessment=assessment, allocation=allocation, effort=effort
        )
    best_category = [evaluated[assessment.order.order_ref] for assessment in candidates]
    ranked_best = rank_goals(best_category)
    by_rank: dict[int, list[GoalEvaluation]] = {}
    for assessment in goals:
        if assessment.category_rank is None or assessment.category_rank == best_rank:
            continue
        by_rank.setdefault(assessment.category_rank, []).append(
            evaluated[assessment.order.order_ref]
        )
    ranked = [*ranked_best]
    for rank in sorted(by_rank):
        ranked.extend(rank_goals(by_rank[rank]))
    primary = ranked[0] if ranked else None
    if inspect_order_ref is None:
        inspect_order_ref = _ranking_inspect_ref(ranked_best)
    if inspect_order_ref is None and primary is not None:
        if primary.satisfied and primary.ready is None:
            inspect_order_ref = primary.order_ref
        elif not (primary.satisfied and primary.ready is True):
            # The primary remains the goal, but a safe ready secondary is
            # the next action. Its own competing rewards must also be known.
            ready = [
                goal for goal in ranked
                if goal is not primary and goal.ready is not False and goal.satisfied
                and primary.allocation.surplus_shortfall(
                    goal.assessment.order.requirements, board
                ) is None
            ]
            if ready:
                category = ready[0].assessment.category_rank
                contenders = [goal for goal in ready if goal.assessment.category_rank == category]
                inspect_order_ref = _ranking_inspect_ref(contenders)
                if inspect_order_ref is None and contenders[0].ready is None:
                    inspect_order_ref = contenders[0].order_ref
    return GoalSelection(
        primary=primary,
        ranked=tuple(ranked),
        assessments=assessments,
        survey_ok=True,
        inspect_order_ref=inspect_order_ref,
        reason="",
    )
