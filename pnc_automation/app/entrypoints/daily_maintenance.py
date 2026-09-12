"""Composition of isolated application graphs for Daily maintenance workers."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.connected_runner import ConnectedClaimOnlyCastleRunner
from pnc_automation.app.authoring.config.models import AppConfig
from pnc_automation.app.entrypoints.app import build_application_runner
from pnc_automation.app.pnc.domain.daily_maintenance import MutationAcknowledgement
from pnc_automation.bluestacks_management.instance_lease import (
    PROCESS_INSTANCE_LEASES,
    InstanceLeaseBundle,
)


@dataclass(slots=True)
class ConnectedClaimOnlyRunnerFactory:
    """Builds an isolated application object graph for each instance worker."""

    config_path: str
    app_config: AppConfig
    acknowledgements: tuple[MutationAcknowledgement, ...]
    verbose: bool = False

    def reserve_instances(self, instance_ids: tuple[str, ...]) -> InstanceLeaseBundle:
        """Reserves the configured display names for the complete daily worker pool."""

        display_names = tuple(
            self.app_config.require_instance(instance_id).display_name
            for instance_id in instance_ids
        )
        return PROCESS_INSTANCE_LEASES.acquire_bundle(display_names)

    def build(self, *, instance_id: str) -> ConnectedClaimOnlyCastleRunner:
        """Builds one worker with an independently owned OCR and connected-runtime graph."""

        application = build_application_runner(self.config_path, verbose=self.verbose)
        return ConnectedClaimOnlyCastleRunner(
            instance_id=instance_id,
            app_config=self.app_config,
            script_runner=application.script_runner,
            authorizer=DailyMutationAuthorizer(self.acknowledgements),
        )
