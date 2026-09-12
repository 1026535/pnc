"""Scheduled mail catalog: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import textwrap
import unittest

from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.authoring.mail.loader import load_mail_schedule_catalog
from pnc_automation.core.errors import ConfigurationError

from tests.support.entrypoints.scheduled_mail.write_accounts_config import _write_accounts_config
from tests.support.entrypoints.scheduled_mail.write_mail_definitions import _write_mail_definitions
from tests.support.entrypoints.scheduled_mail.write_mail_schedules import _write_mail_schedules


class ScheduledMailCatalogTests(unittest.TestCase):
    """Proves scheduled mail catalog."""

    def test_load_mail_schedule_catalog_parses_valid_files(self) -> None:
        """Loads reusable mail definitions and schedules through the canonical parser."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog = load_mail_schedule_catalog(
                definitions_path=_write_mail_definitions(root),
                schedules_path=_write_mail_schedules(root),
            )

        self.assertEqual(catalog.start_utc, datetime(2026, 3, 30, 0, 0, tzinfo=UTC))
        self.assertEqual([definition.id for definition in catalog.definitions], ["alliance_reset", "player_followup"])
        self.assertEqual([schedule.id for schedule in catalog.schedules], ["mailschedule_1", "mailschedule_2"])

    def test_load_mail_schedule_catalog_rejects_invalid_rotation_anchor(self) -> None:
        """Rejects rotation anchors that are not Monday midnight UTC."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-31T01:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

    def test_load_mail_schedule_catalog_rejects_non_utc_rotation_start_offset(self) -> None:
        """Rejects authored rotation anchors whose original offset is not already UTC."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00+02:00
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

    def test_load_mail_schedule_catalog_rejects_unknown_mail_reference(self) -> None:
        """Rejects schedules that reference a non-existent authored mail id."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            definitions_path = _write_mail_definitions(root)
            schedules_path = root / "mail_schedules.yaml"
            schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 5
                        mail_ids: [missing_mail]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_mail_schedule_catalog(definitions_path=definitions_path, schedules_path=schedules_path)

    def test_load_app_config_lazy_loads_optional_scheduled_mail_catalog(self) -> None:
        """Records the sibling scheduled-mail paths and loads the catalog only on first use."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            _write_mail_schedules(root)

            config = load_app_config(config_path)
            self.assertIsNone(config.mail_schedule_catalog)
            first_catalog = config.require_mail_schedule_catalog()
            second_catalog = config.require_mail_schedule_catalog()
            self.assertIs(first_catalog, second_catalog)
            self.assertIs(config.mail_schedule_catalog, first_catalog)
            self.assertEqual(config.mail_definitions_path, (root / "mail_definitions.yaml").resolve())
            self.assertEqual(config.mail_schedules_path, (root / "mail_schedules.yaml").resolve())

    def test_load_app_config_allows_partial_scheduled_mail_files_until_feature_use(self) -> None:
        """Allows unrelated startup work to proceed until scheduled-mail functionality is invoked."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)

            config = load_app_config(config_path)
            with self.assertRaises(ConfigurationError):
                config.require_mail_schedule_catalog()

    def test_load_app_config_allows_malformed_scheduled_mail_files_until_feature_use(self) -> None:
        """Allows unrelated startup work to proceed until lazy scheduled-mail validation is requested."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = _write_accounts_config(root)
            _write_mail_definitions(root)
            malformed_schedules_path = root / "mail_schedules.yaml"
            malformed_schedules_path.write_text(
                textwrap.dedent(
                    """
                    rotation:
                      cycle_days: 14
                      start_utc: 2026-03-30T00:00:00Z
                    mail_schedules:
                      - id: mailschedule_1
                        day_indices: [0]
                        hour_utc: 24
                        mail_ids: [alliance_reset]
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path)
            with self.assertRaises(ConfigurationError):
                config.require_mail_schedule_catalog()
