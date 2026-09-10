"""Canary acceptance contracts and evidence-based Daily release decisions.

This module never drives the game or manufactures live results. Feature adapters
must supply inspected transition evidence; authored cases are intentions only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
import json
import os
import tempfile
from pathlib import Path

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestDisposition, DailyQuestId
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog


class CanaryRole(StrEnum):
    """Identifies the two user-selected canary-only targets."""

    NPC_2 = "npc_2"
    FREE_COOKIES = "free_cookies"


class CanaryOutcome(StrEnum):
    """Separates completion, proven inapplicability, failure, and blocked proof."""

    PASSED = "passed"
    APPLICABILITY_SKIP = "applicability_skip"
    FAILED = "failed"
    BLOCKED = "blocked"


class CanaryReason(StrEnum):
    """Preserves business failure reasons without misreporting software defects."""

    NONE = "none"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    ITEM_UNAVAILABLE = "item_unavailable"
    FEATURE_LOCKED = "feature_locked"
    NO_INVENTORY = "no_inventory"
    NO_CAVALRY = "no_cavalry"
    UNEXPECTED_STATE = "unexpected_state"
    NOT_IMPLEMENTED = "not_implemented"
    IDENTITY_UNVERIFIED = "identity_unverified"
    POLICY_UNRESOLVED = "policy_unresolved"
    UNPROVEN_POSTCONDITION = "unproven_postcondition"
    ALREADY_COMMITTED = "already_committed"


@dataclass(frozen=True, slots=True)
class CanaryCase:
    """Declares one feature/target acceptance case, never a successful test record."""

    quest_id: DailyQuestId
    role: CanaryRole
    target_count: int | None = None
    game_day_count_limit: int | None = None
    paid_wishes_allowed: bool = False
    cooldown_seconds: int | None = None
    interleave_other_quests: bool = False
    approved_skip_reasons: frozenset[CanaryReason] = frozenset()

    @property
    def account_id(self) -> str:
        """Resolves the authored account alias without embedding login credentials."""

        return "mega_old_acc" if self.role == CanaryRole.NPC_2 else "serious_stuff"

    @property
    def castle_ref(self) -> str:
        """Returns the canonical canary castle alias."""

        return self.role.value


@dataclass(frozen=True, slots=True)
class CanaryResult:
    """Records one selected result for a feature's relevant implementation revision."""

    quest_id: DailyQuestId
    role: CanaryRole
    revision: str
    outcome: CanaryOutcome
    reason: CanaryReason
    artifact_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        """Rejects missing evidence and contradictory result classifications."""

        if not self.revision.strip():
            raise ValueError("Canary result requires a relevant implementation revision.")
        if self.outcome == CanaryOutcome.PASSED:
            if self.reason != CanaryReason.NONE:
                raise ValueError("Passed canary cannot carry a failure reason.")
            if len(set(self.artifact_paths)) < 2:
                raise ValueError("Passed canary requires distinct before and after evidence.")
        elif self.reason == CanaryReason.NONE:
            raise ValueError("Unsuccessful canary requires a typed reason.")
        if self.outcome == CanaryOutcome.APPLICABILITY_SKIP:
            if self.reason not in {
                CanaryReason.FEATURE_LOCKED, CanaryReason.NO_INVENTORY, CanaryReason.NO_CAVALRY,
            }:
                raise ValueError("This reason is not a proven applicability condition.")
            if not self.artifact_paths:
                raise ValueError("Applicability skip requires current observation evidence.")

    @property
    def is_software_error(self) -> bool:
        """Distinguishes unexpected runtime behavior from insufficient game resources."""

        return self.reason == CanaryReason.UNEXPECTED_STATE


@dataclass(frozen=True, slots=True)
class CanaryReleaseDecision:
    """Reports eligible features without enabling any configuration or scheduler."""

    evaluation_complete: bool
    validated_features: tuple[DailyQuestId, ...]
    missing_cases: tuple[CanaryCase, ...]


@dataclass(slots=True)
class CanaryEvidenceStore:
    """Persists one current evidence record per feature and canary castle."""

    root: Path

    def __post_init__(self) -> None:
        """Resolves the evidence root without creating directories during inspection."""

        self.root = self.root.resolve()

    def result_path(self, *, quest_id: DailyQuestId, role: CanaryRole) -> Path:
        """Returns the canonical path for one feature/role evidence record."""

        return self.root / "canary-evidence" / quest_id.value / role.value / "result.json"

    def save(self, result: CanaryResult) -> Path:
        """Atomically replaces one persisted result after validating its contract."""

        path = self.result_path(quest_id=result.quest_id, role=result.role)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "quest_id": result.quest_id.value,
                "role": result.role.value,
                "revision": result.revision,
                "outcome": result.outcome.value,
                "reason": result.reason.value,
                "artifact_paths": list(result.artifact_paths),
            },
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix="result-", suffix=".tmp", delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return path

    def load(self, *, quest_id: DailyQuestId, role: CanaryRole) -> CanaryResult | None:
        """Loads one result or returns None when that canary has not been evaluated."""

        path = self.result_path(quest_id=quest_id, role=role)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            result = CanaryResult(
                quest_id=DailyQuestId(payload["quest_id"]),
                role=CanaryRole(payload["role"]),
                revision=str(payload["revision"]),
                outcome=CanaryOutcome(payload["outcome"]),
                reason=CanaryReason(payload["reason"]),
                artifact_paths=tuple(str(item) for item in payload["artifact_paths"]),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(f"Canary evidence is malformed: {path}") from error
        if result.quest_id != quest_id or result.role != role:
            raise ValueError(f"Canary evidence identity does not match its path: {path}")
        return result

    def evaluate(self, *, revision: str | Mapping[DailyQuestId, str]) -> CanaryReleaseDecision:
        """Evaluates all persisted current evidence without enabling configuration."""

        results = tuple(
            result
            for case in planned_canaries()
            if (result := self.load(quest_id=case.quest_id, role=case.role)) is not None
        )
        return evaluate_canary_release(results, revision=revision)


def planned_canaries() -> tuple[CanaryCase, ...]:
    """Builds paired cases from the canonical catalog and locked interview decisions."""

    features = (DailyQuestId.CLAIM_COMPLETED,) + tuple(
        definition.quest_id
        for definition in DailyQuestCatalog().definitions
        if definition.disposition == DailyQuestDisposition.ENABLED
    )
    counts = {
        DailyQuestId.USE_RESOURCE_ITEM: 1,
        DailyQuestId.HERO_HALL: 5,
        DailyQuestId.UPGRADE_HERO: 3,
        DailyQuestId.SUMMON_SAURGIL: 1,
        DailyQuestId.WISHES: 5,
        DailyQuestId.TRIAL_SHOP: 1,
    }
    cookie_skips = {
        DailyQuestId.SUMMON_SAURGIL: frozenset({CanaryReason.FEATURE_LOCKED}),
        DailyQuestId.USE_RESOURCE_ITEM: frozenset({CanaryReason.NO_INVENTORY}),
        DailyQuestId.GATHER_FOOD: frozenset({CanaryReason.NO_CAVALRY}),
        DailyQuestId.GATHER_WOOD: frozenset({CanaryReason.NO_CAVALRY}),
        DailyQuestId.GATHER_IRON: frozenset({CanaryReason.NO_CAVALRY}),
        DailyQuestId.GATHER_GOLD: frozenset({CanaryReason.NO_CAVALRY}),
        DailyQuestId.GATHER_ALLIANCE_MINE: frozenset({CanaryReason.NO_CAVALRY}),
    }
    return tuple(
        CanaryCase(
            quest_id=feature,
            role=role,
            target_count=counts.get(feature),
            game_day_count_limit=50 if feature == DailyQuestId.WISHES else None,
            paid_wishes_allowed=feature == DailyQuestId.WISHES,
            cooldown_seconds=300 if feature == DailyQuestId.HERO_HALL else None,
            interleave_other_quests=feature == DailyQuestId.HERO_HALL,
            approved_skip_reasons=(
                cookie_skips.get(feature, frozenset())
                if role == CanaryRole.FREE_COOKIES else frozenset()
            ),
        )
        for feature in features
        for role in CanaryRole
    )


def evaluate_canary_release(
    results: tuple[CanaryResult, ...], *, revision: str | Mapping[DailyQuestId, str],
) -> CanaryReleaseDecision:
    """Finishes the entire evaluation before exposing only positively validated features."""

    cases = planned_canaries()
    revisions = (
        {case.quest_id: revision for case in cases}
        if isinstance(revision, str) else dict(revision)
    )
    if any(
        not isinstance(revisions.get(case.quest_id), str)
        or not revisions[case.quest_id].strip()
        for case in cases
    ):
        raise ValueError("Canary release requires a relevant revision for every feature.")
    expected = {(case.quest_id, case.role) for case in cases}
    selected: dict[tuple[DailyQuestId, CanaryRole], CanaryResult] = {}
    for result in results:
        key = (result.quest_id, result.role)
        if key not in expected:
            raise ValueError("Canary result is outside the planned target/feature matrix.")
        if result.revision != revisions[result.quest_id]:
            continue
        if key in selected:
            raise ValueError("Duplicate current canary result.")
        selected[key] = result
    missing = tuple(case for case in cases if (case.quest_id, case.role) not in selected)
    if missing:
        return CanaryReleaseDecision(False, (), missing)
    accepted = {
        (case.quest_id, case.role)
        for case in cases
        if (
            selected[(case.quest_id, case.role)].outcome == CanaryOutcome.PASSED
            or (
                selected[(case.quest_id, case.role)].outcome == CanaryOutcome.APPLICABILITY_SKIP
                and selected[(case.quest_id, case.role)].reason in case.approved_skip_reasons
            )
        )
    }
    features = tuple(dict.fromkeys(case.quest_id for case in cases))
    validated = tuple(
        feature for feature in features
        if all((feature, role) in accepted for role in CanaryRole)
    )
    return CanaryReleaseDecision(True, validated, ())
