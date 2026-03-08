"""Typed run-script models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pnc_automation.automation.task import TaskId


@dataclass(frozen=True, slots=True)
class ScriptStep:
    """One ordered automation step from a run script."""

    task: TaskId
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunScript:
    """One loaded and validated automation run script."""

    name: str
    path: Path
    steps: tuple[ScriptStep, ...]


@dataclass(frozen=True, slots=True)
class PreparedScriptStep:
    """One task step after task-specific parameter validation has succeeded."""

    script_step: ScriptStep
    parsed_params: Any

    @property
    def task(self) -> TaskId:
        """Returns the canonical task identifier for the prepared step."""

        return self.script_step.task


@dataclass(frozen=True, slots=True)
class PreparedRunScript:
    """One execution-ready run script with typed task parameters."""

    name: str
    path: Path
    steps: tuple[PreparedScriptStep, ...]
