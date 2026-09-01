"""Safe Hero Arena entry audit used to measure recurring informational gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError

_HERO_ARENA_AUDIT_LABEL_PREFIX = "hero_arena_audit_entry"


def hero_arena_audit_label(local_date: date) -> str:
    """Returns the canonical artifact label for one local-calendar audit entry."""

    return f"{_HERO_ARENA_AUDIT_LABEL_PREFIX}_{local_date.isoformat()}"


def find_existing_hero_arena_audit_summary(
    artifact_root: Path,
    *,
    local_date: date,
    account_id: str,
    castle: CastleIdentity,
) -> Path | None:
    """Returns an exact-target summary for the date or fails closed on malformed matching evidence."""

    if not artifact_root.exists():
        return None
    label = hero_arena_audit_label(local_date)
    for path in sorted(artifact_root.rglob(f"*_{label}.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SelectorResolutionError(
                "Hero Arena audit found an unreadable same-date summary and stopped before live navigation.",
                summary_path=str(path),
            ) from error
        if not isinstance(document, dict):
            raise SelectorResolutionError(
                "Hero Arena audit summary must contain a JSON object.",
                summary_path=str(path),
            )
        if _summary_matches_target(
            document,
            local_date=local_date,
            account_id=account_id,
            castle=castle,
        ):
            return path
    return None


def _summary_matches_target(
    document: dict[object, object],
    *,
    local_date: date,
    account_id: str,
    castle: CastleIdentity,
) -> bool:
    """Returns whether one parsed summary belongs to the exact requested date, account, and castle."""

    castle_document = document.get("castle")
    if not isinstance(castle_document, dict):
        return False
    return (
        document.get("local_date") == local_date.isoformat()
        and document.get("account_id") == account_id
        and castle_document.get("kingdom") == castle.kingdom
        and castle_document.get("castle_name") == castle.castle_name
        and castle_document.get("castle_level") == castle.castle_level
    )


class HeroArenaAuditObservationService(Protocol):
    """Defines the observation seam required by the Hero Arena audit."""

    def observe(
        self,
        label: str,
        request: ObservationRequest | None = None,
    ) -> Observation:
        """Returns one fresh typed observation."""


@dataclass(frozen=True, slots=True)
class HeroArenaEntryAuditResult:
    """Records the two recurring gates and evidence from one safe Arena entry."""

    elemental_intro_appeared: bool
    hero_formation_gate_appeared: bool
    destination_screen: ScreenType
    final_screen: ScreenType
    evidence_artifact_paths: tuple[Path, ...]


@dataclass(slots=True)
class HeroArenaEntryAuditor:
    """Enters Hero Showdown and backs out before formation or attempt mutations."""

    observation_service: HeroArenaAuditObservationService
    action_executor: ObservedActionExecutor

    def run(self, *, label_prefix: str) -> HeroArenaEntryAuditResult:
        """Runs one guarded audit from Versus Center and returns there safely."""

        evidence_paths: list[Path] = []
        current = self._observe(f"{label_prefix}_versus_before")
        self._require_screen(current, ScreenType.PNC_VERSUS_CENTER, "Audit must start in Versus Center.")
        self._require_geometry_selector(current, UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY)

        current = self._tap_and_observe(
            current,
            selector_id=UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY,
            label_prefix=f"{label_prefix}_enter",
            reason="open_hero_showdown_for_non_mutating_gate_audit",
        )
        self._append_artifact(evidence_paths, current)
        elemental_intro_appeared = current.screen_type == ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO
        if elemental_intro_appeared:
            self._require_geometry_selector(
                current,
                UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_CONFIRM_BUTTON,
            )
            current = self._tap_and_observe(
                current,
                selector_id=UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_CONFIRM_BUTTON,
                label_prefix=f"{label_prefix}_dismiss_intro",
                reason="dismiss_informational_elemental_intro_without_starting_an_attempt",
            )
            self._append_artifact(evidence_paths, current)

        destination_screen = current.screen_type
        if destination_screen not in {
            ScreenType.PNC_HERO_FORMATION,
            ScreenType.PNC_HERO_SHOWDOWN_RANKING,
        }:
            raise SelectorResolutionError(
                "Hero Arena audit reached an unreviewed destination and stopped before further input.",
                screen_type=destination_screen,
            )
        hero_formation_gate_appeared = destination_screen == ScreenType.PNC_HERO_FORMATION
        self._require_geometry_selector(current, UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        current = self._tap_and_observe(
            current,
            selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            label_prefix=f"{label_prefix}_return",
            reason="leave_hero_showdown_without_saving_formation_or_starting_an_attempt",
        )
        self._append_artifact(evidence_paths, current)
        self._require_screen(
            current,
            ScreenType.PNC_VERSUS_CENTER,
            "Hero Arena audit could not prove a safe return to Versus Center.",
        )
        return HeroArenaEntryAuditResult(
            elemental_intro_appeared=elemental_intro_appeared,
            hero_formation_gate_appeared=hero_formation_gate_appeared,
            destination_screen=destination_screen,
            final_screen=current.screen_type,
            evidence_artifact_paths=tuple(evidence_paths),
        )

    def _tap_and_observe(
        self,
        observation: Observation,
        *,
        selector_id: UiElementId,
        label_prefix: str,
        reason: str,
    ) -> Observation:
        """Executes one selector-backed tap and namespaces all follow-up evidence."""

        result = self.action_executor.execute_actions(
            [
                TapAction(
                    selector_id=selector_id,
                    reason=reason,
                    observe_after=True,
                    follow_up_request=ObservationRequest.full_runtime_default(),
                )
            ],
            observation,
            observe=lambda label, request=None: self._observe(f"{label_prefix}_{label}", request),
        )
        return result.observation

    def _observe(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Captures one observation through the injected runtime service."""

        return self.observation_service.observe(label, request=request)

    @staticmethod
    def _require_screen(observation: Observation, expected: ScreenType, message: str) -> None:
        """Fails closed when the audit is not on its expected reviewed screen."""

        if observation.screen_type != expected:
            raise SelectorResolutionError(message, screen_type=observation.screen_type)

    @staticmethod
    def _require_geometry_selector(observation: Observation, selector_id: UiElementId) -> None:
        """Rejects missing or OCR-localized action selectors before any tap occurs."""

        element = observation.require(selector_id)
        if element.source_kind != VisibleElementSourceKind.GEOMETRY:
            raise SelectorResolutionError(
                "Hero Arena audit action selectors must use reviewed normalized geometry.",
                selector_id=selector_id,
                screen_type=observation.screen_type,
                source_kind=element.source_kind.value,
            )

    @staticmethod
    def _append_artifact(paths: list[Path], observation: Observation) -> None:
        """Adds one persisted screenshot path when the observation owns one."""

        if observation.artifact_path is not None:
            paths.append(observation.artifact_path)
