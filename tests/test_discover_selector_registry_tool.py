"""Discovery-tool runtime wiring tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.test_support import make_observation


class DiscoverSelectorRegistryToolTests(unittest.TestCase):
    """Validates selector-discovery tool wiring without invoking live dependencies."""

    def test_build_runtime_uses_one_catalog_path_for_runtime_and_analyzer(self) -> None:
        """Builds the observation runtime and analyzer from the same catalog source."""

        module = self._load_tool_module()
        config_path = Path("config/accounts.yaml")
        catalog_path = Path("custom_selector_registry.yaml")
        analyzer_catalog = object()
        ocr_service = object()
        fake_application = SimpleNamespace(
            script_runner=SimpleNamespace(
                observation_builder=SimpleNamespace(
                    selector_engine=SimpleNamespace(ocr_service=ocr_service),
                    enricher=SimpleNamespace(ocr_service=ocr_service),
                )
            )
        )

        with (
            patch.object(module, "build_application_runner", return_value=fake_application) as build_runner,
            patch.object(module, "load_selector_catalog_document", return_value=analyzer_catalog) as load_catalog,
        ):
            runtime = module._build_runtime(config_path=config_path, catalog_path=catalog_path, verbose=True)

        build_runner.assert_called_once_with(config_path, verbose=True, catalog_path=catalog_path)
        load_catalog.assert_called_once_with(catalog_path)
        self.assertIs(runtime.application, fake_application)
        self.assertIs(runtime.analyzer.observation_builder, fake_application.script_runner.observation_builder)
        self.assertIs(runtime.analyzer.catalog, analyzer_catalog)
        self.assertIs(runtime.analyzer.ocr_service, ocr_service)

    def test_live_discovery_uses_connected_runtime_executor_and_flow_planner(self) -> None:
        """Runs live discovery setup through the connected runtime identities exposed by ScriptRunner."""

        module = self._load_tool_module("discover_selector_registry.py", "codex_test_discover_selector_registry")
        account = object()
        observed_action_executor = object()
        flow_planner = object()
        session = object()
        observation_service = _FakeCapturedObservationService()
        connected_runtime = _FakeConnectedRuntime(
            session=session,
            observation_service=observation_service,
            flow_planner=flow_planner,
            observed_action_executor=observed_action_executor,
        )
        script_runner = _FakeToolScriptRunner(
            config=_FakeToolConfig(account=account),
            connected_runtime=connected_runtime,
        )
        runtime = module.SelectorDiscoveryRuntime(
            application=SimpleNamespace(script_runner=script_runner),
            analyzer=_FakeDiscoveryAnalyzer(),
        )
        settle_calls: list[dict[str, object]] = []

        def fake_settle_to_home_city(**kwargs: object) -> object:
            """Records the connected services used to settle before returning the current capture."""

            settle_calls.append(kwargs)
            return kwargs["current_capture"]

        with patch.object(module, "_settle_to_home_city", side_effect=fake_settle_to_home_city):
            live_session = module._run_live_discovery(
                runtime=runtime,
                account_id="testing",
                settle_home_city=True,
                probe_selectors=(),
                stage_visible_selectors=(),
            )

        self.assertEqual(script_runner.config.requested_account_ids, ["testing"])
        self.assertEqual(script_runner.connected_runtime_accounts, [account])
        self.assertEqual(
            connected_runtime.require_reasons,
            ["Live selector discovery requires a connected observed-action executor."],
        )
        self.assertIs(settle_calls[0]["action_executor"], observed_action_executor)
        self.assertIs(settle_calls[0]["flows"], flow_planner)
        self.assertIs(settle_calls[0]["session"], session)
        self.assertEqual(observation_service.labels, ["discovery_start"])
        self.assertEqual(live_session.snapshots, ("snapshot:PNC_HOME_CITY",))

    def test_live_discovery_fails_fast_without_connected_observed_executor(self) -> None:
        """Rejects live discovery before captures when the connected runtime lacks selector-backed actions."""

        module = self._load_tool_module("discover_selector_registry.py", "codex_test_discover_selector_registry")
        observation_service = _FakeCapturedObservationService()
        script_runner = _FakeToolScriptRunner(
            config=_FakeToolConfig(account=object()),
            connected_runtime=_FakeConnectedRuntime(
                session=object(),
                observation_service=observation_service,
                flow_planner=object(),
                observed_action_executor=None,
            ),
        )
        runtime = module.SelectorDiscoveryRuntime(
            application=SimpleNamespace(script_runner=script_runner),
            analyzer=_FakeDiscoveryAnalyzer(),
        )

        with self.assertRaises(SelectorResolutionError):
            module._run_live_discovery(
                runtime=runtime,
                account_id="testing",
                settle_home_city=False,
                probe_selectors=(),
                stage_visible_selectors=(),
            )

        self.assertEqual(observation_service.labels, [])

    def test_navigation_validation_tool_uses_connected_runtime_executor_and_flow_planner(self) -> None:
        """Builds the validator from the connected runtime executor and planner identities."""

        module = self._load_tool_module("validate_navigation_selectors.py", "codex_test_validate_navigation_selectors")
        selector_registry = object()
        observation_service = object()
        observed_action_executor = object()
        flow_planner = object()
        logger = object()
        validator = object()
        runtime = _FakeConnectedRuntime(
            session=object(),
            observation_service=observation_service,
            flow_planner=flow_planner,
            observed_action_executor=observed_action_executor,
        )
        script_runner = SimpleNamespace(
            observation_builder=SimpleNamespace(selector_registry=selector_registry),
            logger=logger,
        )

        with patch.object(module, "NavigationSelectorValidator", return_value=validator) as validator_class:
            result = module._build_navigation_selector_validator(script_runner=script_runner, runtime=runtime)

        self.assertIs(result, validator)
        validator_class.assert_called_once_with(
            selector_registry=selector_registry,
            observation_service=observation_service,
            action_executor=observed_action_executor,
            screen_flows=flow_planner,
            logger=logger,
        )
        self.assertEqual(
            runtime.require_reasons,
            ["Navigation-selector validation requires a connected observed-action executor."],
        )

    def test_navigation_validation_tool_fails_fast_without_connected_observed_executor(self) -> None:
        """Rejects validator construction when connected runtime cannot provide observed actions."""

        module = self._load_tool_module("validate_navigation_selectors.py", "codex_test_validate_navigation_selectors")
        runtime = _FakeConnectedRuntime(
            session=object(),
            observation_service=object(),
            flow_planner=object(),
            observed_action_executor=None,
        )

        with self.assertRaises(SelectorResolutionError):
            module._build_navigation_selector_validator(
                script_runner=SimpleNamespace(observation_builder=object(), logger=object()),
                runtime=runtime,
            )

    def _load_tool_module(self, filename: str = "discover_selector_registry.py", module_name: str = "codex_test_tool") -> object:
        """Loads one tool module directly from disk for isolated unit testing."""

        tools_directory = Path(__file__).resolve().parents[1] / "tools"
        module_path = tools_directory / filename
        added_path = False
        if str(tools_directory) not in sys.path:
            sys.path.insert(0, str(tools_directory))
            added_path = True

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise AssertionError(f"Could not load tool module from '{module_path}'.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            return module
        finally:
            sys.modules.pop(module_name, None)
            if added_path:
                sys.path.remove(str(tools_directory))


@dataclass(slots=True)
class _FakeToolConfig:
    """Provides account lookup for live-tool wiring tests."""

    account: object
    requested_account_ids: list[str] = field(default_factory=list)

    def require_account(self, account_id: str) -> object:
        """Records one requested account id and returns the seeded account object."""

        self.requested_account_ids.append(account_id)
        return self.account


@dataclass(slots=True)
class _FakeToolScriptRunner:
    """Provides the connected runtime returned by tool-facing ScriptRunner calls."""

    config: _FakeToolConfig
    connected_runtime: object
    connected_runtime_accounts: list[object] = field(default_factory=list)

    def build_connected_runtime(self, *, account: object) -> object:
        """Records the account used for connected-runtime construction and returns the seeded runtime."""

        self.connected_runtime_accounts.append(account)
        return self.connected_runtime


@dataclass(slots=True)
class _FakeConnectedRuntime:
    """Mimics the connected runtime contract consumed by live tools."""

    session: object
    observation_service: object
    flow_planner: object
    observed_action_executor: object | None
    require_reasons: list[str] = field(default_factory=list)

    def require_observed_action_executor(self, reason: str) -> object:
        """Returns the seeded observed executor or raises the same fail-fast error as the real runtime."""

        self.require_reasons.append(reason)
        if self.observed_action_executor is None:
            raise SelectorResolutionError(reason)
        return self.observed_action_executor


@dataclass(slots=True)
class _FakeCapturedObservationService:
    """Captures deterministic observations for discovery live-tool tests."""

    labels: list[str] = field(default_factory=list)

    def capture_observation(self, label: str, request: object | None = None) -> object:
        """Returns one minimal captured observation and records the requested label."""

        del request
        self.labels.append(label)
        return SimpleNamespace(
            observation=make_observation(ScreenType.PNC_HOME_CITY),
            screenshot=SimpleNamespace(
                artifact=SimpleNamespace(path=Path(f"{label}.png")),
                image=object(),
            ),
        )


@dataclass(slots=True)
class _FakeDiscoveryAnalyzer:
    """Builds deterministic snapshot labels from captured observations."""

    def analyze_captured_observation(self, capture: object) -> str:
        """Returns a compact snapshot label for one captured observation."""

        return f"snapshot:{capture.observation.screen_type.name}"


if __name__ == "__main__":
    unittest.main()
