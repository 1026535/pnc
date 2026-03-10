"""Discovery-tool runtime wiring tests."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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

    def _load_tool_module(self) -> object:
        """Loads the discovery tool module directly from disk for isolated unit testing."""

        tools_directory = Path(__file__).resolve().parents[1] / "tools"
        module_path = tools_directory / "discover_selector_registry.py"
        module_name = "codex_test_discover_selector_registry"
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


if __name__ == "__main__":
    unittest.main()
