"""Application runtime wiring tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app import build_application_runner
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import BlueStacksInstanceResolver


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
                        display_name: serious_stuff
                        app_package: com.global.tmslg
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
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
                patch("pnc_automation.app.entrypoints.app.RapidOcrService", return_value=ocr_service),
                patch("pnc_automation.app.entrypoints.app.build_default_selector_registry", return_value=registry) as build_registry,
                patch("pnc_automation.app.entrypoints.app.build_default_task_registry", return_value=task_registry),
            ):
                application = build_application_runner(config_path, catalog_path=catalog_path)

        build_registry.assert_called_once_with(catalog_path=catalog_path)
        self.assertIs(application.script_runner.observation_builder.selector_registry, registry)

    def test_build_application_runner_wires_durable_archive_stores_under_archive_root(self) -> None:
        """Builds the durable mail and chat archive stores under the configured archive root instead of artifacts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    artifacts:
                      root: artifacts
                    archives:
                      root: archives
                    instances:
                      - id: bs-main
                        display_name: serious_stuff
                        app_package: com.global.tmslg
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            application = build_application_runner(config_path)

        self.assertEqual(application.script_runner.mail_archive_store.root, (root / "archives" / "mail").resolve())
        self.assertEqual(application.script_runner.chat_archive_store.root, (root / "archives" / "chat").resolve())

    def test_build_application_runner_wires_bluestacks_resolver_with_resolved_config_path(self) -> None:
        """Builds the resolver from the loaded config defaults instead of hardcoding the host metadata path."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_directory = root / "config"
            config_directory.mkdir()
            config_path = config_directory / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    defaults:
                      bluestacks_config_path: runtime/bluestacks.conf
                    instances:
                      - id: bs-main
                        display_name: serious_stuff
                        app_package: com.global.tmslg
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            application = build_application_runner(config_path)

        self.assertIsInstance(application.script_runner.instance_resolver, BlueStacksInstanceResolver)
        self.assertEqual(
            application.script_runner.instance_resolver.config_path,
            (root / "runtime" / "bluestacks.conf").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
