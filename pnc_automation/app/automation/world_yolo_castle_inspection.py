"""Read-only inspection of one qualified World-map YOLO Castle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class WorldYoloCastleInspectionResult:
    """Records the selected box and confirmed detail/return observations."""

    bounds: Bounds
    confidence: float
    geometry_policy: str
    interaction_review: str
    detail_screen: ScreenType
    source_player_name: str
    profile_player_name: str
    source_captured_at: datetime
    detail_captured_at: datetime
    profile_captured_at: datetime
    returned_captured_at: datetime
    source_artifact_path: str | None
    detail_artifact_path: str | None
    profile_artifact_path: str | None
    returned_artifact_path: str | None
    raw_detection_count: int
    rejected_detection_count: int


@dataclass(frozen=True, slots=True)
class WorldYoloCastleInspectionWorkflow(CoreWorkflow[WorldYoloCastleInspectionResult]):
    """Runs Home → World → one Castle detail → World → Home without spending."""

    active_castle: CastleIdentity

    _spec = WorkflowSpec(
        name="world_yolo_castle_inspection",
        entry_screen=ScreenType.PNC_HOME_CITY,
        exit_screen=ScreenType.PNC_HOME_CITY,
        effect=WorkflowEffect.READ_ONLY,
    )

    @property
    def spec(self) -> WorkflowSpec:
        """Return the bounded Home-to-Home read-only lifecycle."""

        return self._spec

    def execute(self, context: WorkflowContext) -> WorldYoloCastleInspectionResult:
        """Acquire one fresh Castle, verify its detail, and return to World."""

        context.navigate(ScreenType.PNC_WORLD_MAP)
        target, source, detail, profile, returned = context.inspect_world_yolo_castle(
            active_castle=self.active_castle,
        )
        qualification = target.action_qualification
        if qualification is None:
            raise RuntimeError("Castle inspection lost its interaction qualification.")
        if target.name_text is None or profile.profile_player_name is None:
            raise RuntimeError("Castle inspection lost its matched player identity.")
        surface = source.spatial_surface
        diagnostics = () if surface is None else surface.detection_diagnostics
        raw_count = 0
        rejected_count = 0
        if diagnostics:
            raw_count = len(diagnostics[0].candidates)
            rejected_count = sum(not candidate.published for candidate in diagnostics[0].candidates)
        return WorldYoloCastleInspectionResult(
            bounds=target.bounds,
            confidence=float(target.require_metadata("confidence")),
            geometry_policy=qualification.geometry_policy,
            interaction_review=qualification.review_ref,
            detail_screen=detail.screen_type,
            source_player_name=target.name_text,
            profile_player_name=profile.profile_player_name,
            source_captured_at=source.captured_at,
            detail_captured_at=detail.captured_at,
            profile_captured_at=profile.captured_at,
            returned_captured_at=returned.captured_at,
            source_artifact_path=None if source.artifact_path is None else str(source.artifact_path),
            detail_artifact_path=None if detail.artifact_path is None else str(detail.artifact_path),
            profile_artifact_path=None if profile.artifact_path is None else str(profile.artifact_path),
            returned_artifact_path=None if returned.artifact_path is None else str(returned.artifact_path),
            raw_detection_count=raw_count,
            rejected_detection_count=rejected_count,
        )
