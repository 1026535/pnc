"""Typed run-script models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from pnc_automation.app.automation.engine.task import CastleTargetPolicy, TaskId
from pnc_automation.app.authoring.config.models import CastleIdentity


@dataclass(frozen=True, slots=True)
class ScriptStep:
    """One ordered automation step from a run script."""

    task: TaskId
    castle: CastleIdentity | None = None
    castle_ref: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects ambiguous steps that try to use both concrete and referenced castle targets."""

        if self.castle is not None and self.castle_ref is not None:
            raise ValueError("ScriptStep cannot define both 'castle' and 'castle_ref'.")

    def with_castle_ref(
        self,
        castle_ref: str,
        *,
        provenance: Mapping[str, Any] | None = None,
    ) -> ScriptStep:
        """Returns one generated step copy bound to the provided authored castle alias."""

        merged_provenance = dict(self.provenance)
        if provenance is not None:
            merged_provenance.update(provenance)
        return ScriptStep(
            task=self.task,
            castle=self.castle,
            castle_ref=castle_ref,
            params=self.params,
            provenance=merged_provenance,
        )


@dataclass(frozen=True, slots=True)
class CastleRefRepeatBlock:
    """Repeats one nested ordinary workflow for each authored castle alias in order."""

    castle_refs: tuple[str, ...]
    steps: tuple[ScriptStep, ...]
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects malformed repeat blocks that omit targets or nested steps."""

        if not self.castle_refs:
            raise ValueError("CastleRefRepeatBlock requires at least one castle_ref.")
        if not self.steps:
            raise ValueError("CastleRefRepeatBlock requires at least one nested step.")


ScriptNode: TypeAlias = ScriptStep | CastleRefRepeatBlock


@dataclass(frozen=True, slots=True)
class RunScript:
    """One loaded and validated automation run script."""

    name: str
    path: Path
    steps: tuple[ScriptNode, ...]


@dataclass(frozen=True, slots=True)
class PreparedScriptStep:
    """One task step after task and castle-target validation has succeeded."""

    script_step: ScriptStep
    parsed_params: Any
    castle_target_policy: CastleTargetPolicy
    resolved_castle: CastleIdentity | None = None

    @property
    def task(self) -> TaskId:
        """Returns the canonical task identifier for the prepared step."""

        return self.script_step.task

    @property
    def castle(self) -> CastleIdentity | None:
        """Returns the optional explicit castle target requested by the step."""

        return self.resolved_castle

    @property
    def castle_ref(self) -> str | None:
        """Returns the optional authored castle-target alias requested by the step."""

        return self.script_step.castle_ref

    @property
    def provenance(self) -> Mapping[str, Any]:
        """Returns the optional diagnostic provenance attached to the authored or generated step."""

        return self.script_step.provenance


@dataclass(frozen=True, slots=True)
class PreparedRunScript:
    """One execution-ready run script with typed task parameters."""

    name: str
    path: Path
    steps: tuple[PreparedScriptStep, ...]
