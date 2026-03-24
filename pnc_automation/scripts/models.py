"""Typed run-script models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pnc_automation.automation.task import CastleTargetPolicy, TaskId
from pnc_automation.config.models import CastleIdentity


@dataclass(frozen=True, slots=True)
class ScriptStep:
    """One ordered automation step from a run script."""

    task: TaskId
    castle: CastleIdentity | None = None
    castle_ref: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects ambiguous steps that try to use both concrete and referenced castle targets."""

        if self.castle is not None and self.castle_ref is not None:
            raise ValueError("ScriptStep cannot define both 'castle' and 'castle_ref'.")


@dataclass(frozen=True, slots=True)
class RunScript:
    """One loaded and validated automation run script."""

    name: str
    path: Path
    steps: tuple[ScriptStep, ...]


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


@dataclass(frozen=True, slots=True)
class PreparedRunScript:
    """One execution-ready run script with typed task parameters."""

    name: str
    path: Path
    steps: tuple[PreparedScriptStep, ...]
