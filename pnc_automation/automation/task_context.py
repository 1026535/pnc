"""Per-step task context shared with concrete task implementations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pnc_automation.automation.scripts.models import ScriptStep
from pnc_automation.config.models import AccountConfig, DefaultsConfig
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner


@dataclass(frozen=True, slots=True)
class TaskContext:
    """Bundles stable runtime dependencies for one task execution."""

    account: AccountConfig
    defaults: DefaultsConfig
    step: ScriptStep
    params: Any
    flows: ScreenFlowPlanner
    logger: logging.LoggerAdapter
