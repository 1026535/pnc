"""Offline contract checks across moved production owners and their consumers."""

from __future__ import annotations

import unittest
from dataclasses import asdict
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from pnc_automation.app import runtime
from pnc_automation.app.authoring.config.models import AppConfig
from pnc_automation.app.authoring.config.yaml_helpers import load_castle_identity
from pnc_automation.app.entrypoints.daily_maintenance import ConnectedClaimOnlyRunnerFactory
from pnc_automation.app.pnc.domain.castles import (
    CastleIdentity,
    CastleRosterOrdering,
    PncAccountCastleRosterConfig,
)
from pnc_automation.app.pnc.domain.observation_policy import (
    ObservationArtifactKind,
    observation_artifact_selection,
    resolve_observation_artifact_policy,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.observation_policy import ObservationMode


class CompositionContractTests(unittest.TestCase):
    """Proves canonical identity and injection without constructing a runtime."""

    def test_daily_factory_injects_the_mocked_application_dependencies(self) -> None:
        config = cast(AppConfig, object())
        script_runner = object()
        factory = ConnectedClaimOnlyRunnerFactory(
            config_path="unused-offline-config.yaml",
            app_config=config,
            acknowledgements=(),
            verbose=True,
        )
        with patch(
            "pnc_automation.app.entrypoints.daily_maintenance.build_application_runner",
            return_value=SimpleNamespace(script_runner=script_runner),
        ) as build:
            worker = factory.build(instance_id="offline-worker")
        build.assert_called_once_with("unused-offline-config.yaml", verbose=True)
        self.assertEqual(worker.instance_id, "offline-worker")
        self.assertIs(worker.app_config, config)
        self.assertIs(worker.script_runner, script_runner)
        self.assertEqual(worker.authorizer.acknowledgements, ())

    def test_authored_castle_parser_returns_the_domain_value(self) -> None:
        payload = {"kingdom": "K230", "castle_name": "Offline castle", "castle_level": 12}
        castle = load_castle_identity(payload, context="offline.castle")
        self.assertIs(type(castle), CastleIdentity)
        self.assertEqual(asdict(castle), payload)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id="offline-account",
            castles=(castle,),
            ordering=CastleRosterOrdering.FULL_SCAN,
        )
        self.assertIs(roster.castles[0], castle)
        self.assertTrue(roster.has_trusted_ordering)

    def test_observation_request_and_runtime_exports_share_domain_policy(self) -> None:
        selection = observation_artifact_selection(ObservationArtifactKind.SCREENSHOT)
        request = ObservationRequest(artifact_selection=selection)
        resolved = resolve_observation_artifact_policy(
            mode=ObservationMode.LIGHT,
            request_selection=request.artifact_selection,
        )
        self.assertEqual(resolved.selection, selection)
        self.assertIs(runtime.ObservationMode, ObservationMode)
        self.assertIs(runtime.ObservationArtifactKind, ObservationArtifactKind)
        self.assertIs(runtime.resolve_observation_artifact_policy, resolve_observation_artifact_policy)
