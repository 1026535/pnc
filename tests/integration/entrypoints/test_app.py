"""Application runtime wiring tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app import build_application_runner
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import (
    BlueStacksInstanceResolver,
)


class ApplicationRunnerTests(unittest.TestCase):
    """Validates top-level runtime wiring."""

    @staticmethod
    def _write_yolo_config(root: Path, model_path: str | None) -> Path:
        config_path = root / "config" / "accounts.yaml"
        config_path.parent.mkdir()
        runtime = "" if model_path is None else f"runtime:\n  world_yolo_model_path: {model_path}\n"
        config_path.write_text(runtime + textwrap.dedent("""\
            instances:
              - id: bs-main
                display_name: example
                app_package: com.example.game
            accounts:
              - id: account_a
                instance_id: bs-main
                pnc_account_id: example
                username: example
                password: example
            """), encoding="utf-8")
        return config_path

    def test_configured_yolo_is_shared_by_both_observation_pipelines(self) -> None:
        """Resolve the model from the config workspace and load it only once."""
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = self._write_yolo_config(root, ".local-data/models/world.onnx")
            producer = object()
            with (
                patch("pnc_automation.app.entrypoints.app.load_world_yolo_producer", return_value=producer) as load,
                patch("pnc_automation.app.entrypoints.app.RapidOcrService"),
            ):
                application = build_application_runner(config_path)
                second_builder = application.script_runner.p2_observation_builder_factory()
            load.assert_called_once_with((root / ".local-data/models/world.onnx").resolve())
            self.assertIs(application.world_yolo_producer, producer)
            self.assertIs(application.script_runner.observation_builder.enricher.world_yolo_producer, producer)
            self.assertIs(second_builder.enricher.world_yolo_producer, producer)

    def test_yolo_is_optional_and_explicit_producer_takes_precedence(self) -> None:
        """Preserve callers that inject a reviewed producer or do not enable YOLO."""
        for model_path, explicit in ((None, None), ("missing.onnx", object())):
            with self.subTest(model_path=model_path), tempfile.TemporaryDirectory() as temp_directory:
                config_path = self._write_yolo_config(Path(temp_directory), model_path)
                with (
                    patch("pnc_automation.app.entrypoints.app.load_world_yolo_producer") as load,
                    patch("pnc_automation.app.entrypoints.app.RapidOcrService"),
                ):
                    application = build_application_runner(config_path, world_yolo_producer=explicit)
                load.assert_not_called()
                self.assertIs(application.world_yolo_producer, explicit)

    def test_configured_missing_yolo_fails_before_transport_initialization(self) -> None:
        """A broken selected model cannot silently disable the requested detector."""
        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = self._write_yolo_config(Path(temp_directory), "missing.onnx")
            with patch("pnc_automation.app.entrypoints.app.AdbClient") as adb:
                with self.assertRaisesRegex(FileNotFoundError, "YOLO ONNX model does not exist"):
                    build_application_runner(config_path)
            adb.assert_not_called()

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
