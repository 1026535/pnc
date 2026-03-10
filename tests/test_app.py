"""Application runtime wiring tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app import build_application_runner


class ApplicationRunnerTests(unittest.TestCase):
    """Validates top-level runtime wiring."""

    def test_build_application_runner_uses_provided_catalog_for_selector_registry(self) -> None:
        """Threads the optional selector catalog path into the observation runtime registry."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    instances:
                      - id: bs-main
                        device_id: 127.0.0.1:5555
                        app_package: com.global.tmslg
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
                        selected_castle:
                          kingdom: K230
                          castle_name: Main
                    """
                ).strip(),
                encoding="utf-8",
            )
            catalog_path = root / "custom_selector_registry.yaml"
            catalog_path.write_text("selectors: []\n", encoding="utf-8", newline="\n")
            registry = object()
            ocr_service = object()
            task_registry = object()

            with (
                patch("pnc_automation.app.RapidOcrService", return_value=ocr_service),
                patch("pnc_automation.app.build_default_selector_registry", return_value=registry) as build_registry,
                patch("pnc_automation.app.build_default_task_registry", return_value=task_registry),
            ):
                application = build_application_runner(config_path, catalog_path=catalog_path)

        build_registry.assert_called_once_with(catalog_path=catalog_path)
        self.assertIs(application.script_runner.observation_builder.selector_registry, registry)


if __name__ == "__main__":
    unittest.main()
