"""Offline tests for the host-owned subset of the accounts YAML contract."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.core.config.host import LiveAutomationRole, load_bluestacks_host_config
from pnc_automation.core.errors import ConfigurationError


class BlueStacksHostConfigTests(unittest.TestCase):
    """Keeps host validation independent from credentials and application files."""

    def test_host_loader_ignores_application_only_fields_and_missing_credentials(self) -> None:
        """Host management can start with only host bindings and memory policy."""

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    defaults:
                      bluestacks_config_path: fixtures/bluestacks.conf
                    runtime:
                      observation_mode: definitely-not-an-app-mode
                      artifacts: false
                      archives: [not, a, host, setting]
                      bluestacks_memory:
                        enabled: true
                        restart_roles: [live_testing]
                    instances:
                      - id: bs-main
                        display_name: serious_stuff
                        app_package: missing-or-ignored-by-host-loader
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        live_roles: [live_testing]
                        pnc_account_id: absent-from-host-schema
                        username_env: MISSING_USER
                        password_env: MISSING_PASS
                    credentials: super-secret-value
                    castle_file: missing-castles.yaml
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_bluestacks_host_config(config_path, env={})

        self.assertEqual(config.accounts[0].live_roles, frozenset({LiveAutomationRole.LIVE_TESTING}))
        self.assertTrue(config.memory_policy.enabled)
        self.assertEqual(config.instances[0].display_name, "serious_stuff")

    def test_host_loader_rejects_falsy_relevant_shapes(self) -> None:
        """False and list values are not silently treated as omitted mappings."""

        invalid_values = (
            ("accounts", "false"),
            ("instances", "{}"),
            ("runtime", "[]"),
            ("runtime:\n  bluestacks_memory", "[]"),
            (
                "accounts",
                "- id: account_a\n  instance_id: bs-main\n  live_roles: false",
            ),
        )
        for field_name, value in invalid_values:
            with self.subTest(field_name=field_name):
                with tempfile.TemporaryDirectory() as directory:
                    config_path = Path(directory) / "accounts.yaml"
                    if field_name.startswith("runtime:\n"):
                        content = f"runtime:\n  bluestacks_memory: {value}\n"
                    elif field_name == "accounts" and value.startswith("-"):
                        content = (
                            "instances:\n"
                            "  - id: bs-main\n"
                            "    display_name: testing\n"
                            f"accounts:\n  {value.replace(chr(10), chr(10) + '  ')}\n"
                        )
                    else:
                        content = f"{field_name}: {value}\n"
                    config_path.write_text(content, encoding="utf-8")

                    with self.assertRaises(ConfigurationError):
                        load_bluestacks_host_config(config_path)

    def test_host_loader_rejects_duplicate_display_names_and_mixed_instance_roles(self) -> None:
        """Host eligibility fails closed for ambiguous or contradictory physical bindings."""

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    instances:
                      - id: bs-main
                        display_name: Testing
                      - id: bs-other
                        display_name: testing
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        live_roles: [read_only]
                      - id: account_b
                        instance_id: bs-main
                        live_roles: [live_testing]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "display_name"):
                load_bluestacks_host_config(config_path)

            config_path.write_text(
                textwrap.dedent(
                    """
                    instances:
                      - id: bs-main
                        display_name: testing
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        live_roles: [read_only]
                      - id: account_b
                        instance_id: bs-main
                        live_roles: [live_testing]
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigurationError, "cannot combine read_only"):
                load_bluestacks_host_config(config_path)

    def test_host_errors_do_not_echo_unrelated_secret_values(self) -> None:
        """Malformed host YAML reports a field context without dumping arbitrary input."""

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "accounts.yaml"
            config_path.write_text(
                "accounts: false\ncredentials: top-secret-value\n",
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError) as raised:
                load_bluestacks_host_config(config_path)

        self.assertNotIn("top-secret-value", str(raised.exception))

    def test_application_loader_still_rejects_app_owned_invalid_settings(self) -> None:
        """Separating host parsing does not weaken application configuration validation."""

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    runtime:
                      observation_mode: invalid-mode
                    instances:
                      - id: bs-main
                        display_name: testing
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: user
                        username: username
                        password: password
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)


if __name__ == "__main__":
    unittest.main()
