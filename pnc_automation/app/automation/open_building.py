"""Read-only opening of one modeled home-city building on the replacement core."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections.abc import Mapping

from pnc_automation.app.automation.engine.core_workflow import (
    CoreWorkflow,
    WorkflowContext,
    WorkflowEffect,
    WorkflowSpec,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    primary_screen_type_for_home_city_object,
)
from pnc_automation.app.pnc.domain.policy_models import OpenBuildingPolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ScriptValidationError


@dataclass(frozen=True, slots=True)
class OpenBuildingResult:
    """Carries the exact building endpoint observed by the workflow."""

    building: HomeCityObjectId
    screen_type: ScreenType
    captured_at: datetime
    artifact_path: str | None = None

    @property
    def target(self) -> HomeCityObjectId:
        """Returns the requested building for callers that use target terminology."""

        return self.building


@dataclass(frozen=True, slots=True)
class OpenBuildingWorkflow(CoreWorkflow[OpenBuildingResult]):
    """Opens one modeled building and reports its exact primary screen."""

    policy: OpenBuildingPolicy
    _spec: WorkflowSpec = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Validates the target before the workflow can enter a connected runtime."""

        if not isinstance(self.policy, OpenBuildingPolicy):
            raise TypeError("OpenBuildingWorkflow requires an OpenBuildingPolicy.")
        destination = primary_screen_type_for_home_city_object(self.policy.building)
        if destination is None:
            raise ScriptValidationError(
                f"Building '{self.policy.building.value}' has no modeled primary screen.",
                field="building",
                value=self.policy.building.value,
            )
        object.__setattr__(
            self,
            "_spec",
            WorkflowSpec(
                name="open_building",
                entry_screen=ScreenType.PNC_HOME_CITY,
                exit_screen=destination,
                effect=WorkflowEffect.READ_ONLY,
            ),
        )

    @property
    def spec(self) -> WorkflowSpec:
        """Returns the Home-to-exact-building read-only contract."""

        return self._spec

    def execute(self, context: WorkflowContext) -> OpenBuildingResult:
        """Delegates building targeting and observed completion to NavigationCore."""

        observation = context.open_building(self.policy.building)
        expected_screen = self.spec.exit_screen
        if observation.screen_type != expected_screen:
            raise RuntimeError(
                f"Building open reached unexpected screen '{observation.screen_type.name}'."
            )
        return OpenBuildingResult(
            building=self.policy.building,
            screen_type=observation.screen_type,
            captured_at=observation.captured_at,
            artifact_path=None if observation.artifact_path is None else str(observation.artifact_path),
        )


def build_open_building_workflow(params: Mapping[str, object]) -> OpenBuildingWorkflow:
    """Parses and validates direct open-building parameters before runtime construction."""

    return OpenBuildingWorkflow(policy=OpenBuildingPolicy.from_params(params))
