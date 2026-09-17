"""Goal evaluation and ranking (Plan 02 PW03).

One pass classifies the survey into assessments, evaluates every policy
goal against the observed board (allocation + advisory effort), and ranks
them inside their reward category. Zero-cost goals — ready, satisfied by
usable stock, or achievable through free merges/feeds alone — rank ahead of
every positive-cost goal. Uncertain goals (finite producers with unobserved
remaining uses) rank below certain ones, never above; inspection resolves
unread reward facts before a guess is allowed to rank them.
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


def _compare_positive(a: GoalEvaluation, b: GoalEvaluation) -> int:
    """Orders two goals inside one reward category (Plan 02 ordering).

    Certain estimates always rank above uncertain ones. Inside each
    certainty class the comparison is reward-per-unit-energy ratio, then
    less remaining estimated effort, then more secondary reward, then a
    stable survey index.
    """

    if a.effort.uncertain != b.effort.uncertain:
        return 1 if a.effort.uncertain else -1
    ratio_a, ratio_b = _ratio(a), _ratio(b)
    if ratio_a != ratio_b:
        return -1 if ratio_a > ratio_b else 1
    effort_a = a.effort.energy if a.effort.energy is not None else Fraction(10**9)
    effort_b = b.effort.energy if b.effort.energy is not None else Fraction(10**9)
    if effort_a != effort_b:
        return -1 if effort_a < effort_b else 1
    secondary_a = a.assessment.secondary_quantity or 0
    secondary_b = b.assessment.secondary_quantity or 0
    if secondary_a != secondary_b:
        return -1 if secondary_a > secondary_b else 1
    return a.assessment.survey_index - b.assessment.survey_index


def _zero_key(evaluation: GoalEvaluation) -> tuple[int, int, int, int, int]:
    """Orders zero-cost goals: primary reward, fewer free actions, secondary.

    An observed ready control breaks the remaining tie; the survey index
    keeps the ordering total.
    """

    ready_penalty = 0 if evaluation.ready is True else 1
    return (
        -(evaluation.assessment.primary_quantity or 0),
        evaluation.allocation.free_actions,
        -(evaluation.assessment.secondary_quantity or 0),
        ready_penalty,
        evaluation.assessment.survey_index,
    )


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
    if not goals:
        return GoalSelection(
            primary=None,
            ranked=(),
            assessments=assessments,
            survey_ok=True,
            inspect_order_ref=None,
            reason="no eligible two-piece order in the complete survey",
        )
    best_rank = min(assessment.category_rank for assessment in goals if assessment.category_rank is not None)
    candidates = [
        assessment for assessment in goals if assessment.category_rank == best_rank
    ]
    inspect_order_ref = next(
        (
            assessment.order.order_ref
            for assessment in candidates
            if assessment.primary_quantity is None
        ),
        None,
    )
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
    if inspect_order_ref is None and len(ranked_best) >= 2:
        # An unread secondary count blocks ranking when the top two are
        # otherwise indistinguishable by every earlier key.
        first, second = ranked_best[0], ranked_best[1]
        tied_zero = (
            first.zero_cost
            and second.zero_cost
            and (first.assessment.primary_quantity or 0)
            == (second.assessment.primary_quantity or 0)
            and first.allocation.free_actions == second.allocation.free_actions
        )
        tied_positive = (
            not first.zero_cost
            and not second.zero_cost
            and first.effort.uncertain == second.effort.uncertain
            and _ratio(first) == _ratio(second)
            and (first.effort.energy or Fraction(10**9))
            == (second.effort.energy or Fraction(10**9))
        )
        if (tied_zero or tied_positive) and (
            first.assessment.secondary_quantity is None
            or second.assessment.secondary_quantity is None
        ):
            inspect_order_ref = (
                first.order_ref
                if first.assessment.secondary_quantity is None
                else second.order_ref
            )
    return GoalSelection(
        primary=primary,
        ranked=tuple(ranked),
        assessments=assessments,
        survey_ok=True,
        inspect_order_ref=inspect_order_ref,
        reason="",
    )
