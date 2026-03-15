"""Configuration-loader tests."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from pnc_automation.config.loader import load_app_config
from pnc_automation.config.models import CastleRosterOrdering, CredentialSource
from pnc_automation.errors import ConfigurationError


class ConfigLoaderTests(unittest.TestCase):
    """Validates typed config loading and fail-fast startup rules."""

    def test_load_app_config_resolves_credentials_and_paths(self) -> None:
        """Loads a valid config and resolves the artifact root under the workspace root."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    artifacts:
                      root: artifacts
                    defaults:
                      adb_path: adb
                      screenshot_format: png
                      stable_click_delay_ms: 111
                      post_action_observe_delay_ms: 222
                      chat_stable_click_delay_ms: 33
                      chat_post_action_observe_delay_ms: 44
                    instances:
                      - id: bs-main
                        device_id: 127.0.0.1:5555
                        app_package: com.global.tmslg
                    accounts:
                      - id: account_a
                        instance_id: bs-main
                        pnc_account_id: user
                        username_env: TEST_USER
                        password_env: TEST_PASS
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path, env={"TEST_USER": "user", "TEST_PASS": "pass"})

            self.assertEqual(config.defaults.stable_click_delay_ms, 111)
            self.assertEqual(config.defaults.chat_stable_click_delay_ms, 33)
            self.assertEqual(config.defaults.chat_post_action_observe_delay_ms, 44)
            self.assertTrue(config.artifact_root.is_dir())
            self.assertEqual(config.artifact_root, (root / "artifacts").resolve())
            self.assertEqual(config.require_account("account_a").credentials.username, "user")
            self.assertEqual(config.require_instance("bs-main").device_id, "127.0.0.1:5555")

    def test_load_app_config_resolves_repo_style_config_artifacts_outside_config_directory(self) -> None:
        """Resolves ``config/accounts.yaml`` artifact roots at the workspace root, not inside ``config``."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_dir = root / "config"
            config_dir.mkdir()
            config_path = config_dir / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    artifacts:
                      root: artifacts
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
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path)

            self.assertEqual(config.artifact_root, (root / "artifacts").resolve())
            self.assertNotEqual(config.artifact_root, (config_dir / "artifacts").resolve())

    def test_load_app_config_fails_when_secret_is_missing(self) -> None:
        """Rejects login-enabled accounts that reference missing environment variables."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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
                        pnc_account_id: user
                        username_env: TEST_USER
                        password_env: TEST_PASS
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path, env={"TEST_USER": "user"})

    def test_load_app_config_accepts_inline_credentials(self) -> None:
        """Loads credentials directly from the repository config file."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path)

            credentials = config.require_account("account_a").credentials
            self.assertIsNotNone(credentials)
            self.assertEqual(credentials.username, "inline_user")
            self.assertEqual(credentials.password, "inline_pass")
            self.assertEqual(credentials.source, CredentialSource.INLINE)
            self.assertEqual(config.require_account("account_a").artifact_directory_name, "account_a")

    def test_load_app_config_formats_account_artifact_directory_from_account_id(self) -> None:
        """Formats per-account artifact directories from the canonical account identifier."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    instances:
                      - id: bs-main
                        device_id: 127.0.0.1:5555
                        app_package: com.global.tmslg
                    accounts:
                      - id: ColdDukeOfTheNorth
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path)

            self.assertEqual(config.require_account("ColdDukeOfTheNorth").artifact_directory_name, "cold_duke_of_the_north")

    def test_load_app_config_rejects_colliding_account_artifact_directories(self) -> None:
        """Rejects distinct account ids that normalize into the same artifact directory name."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    instances:
                      - id: bs-main
                        device_id: 127.0.0.1:5555
                        app_package: com.global.tmslg
                    accounts:
                      - id: ColdDuke
                        instance_id: bs-main
                        pnc_account_id: cold_1
                        username: cold_1
                        password: inline_pass
                      - id: cold_duke
                        instance_id: bs-main
                        pnc_account_id: cold_2
                        username: cold_2
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError) as context:
                load_app_config(config_path)

            self.assertIn("artifact-directory normalization", str(context.exception))

    def test_load_app_config_loads_castle_rosters_from_sibling_file(self) -> None:
        """Loads the sibling castles.yaml file as an optional discovered roster cache."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            castles_path = root / "castles.yaml"
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
                    """
                ).strip(),
                encoding="utf-8",
            )
            castles_path.write_text(
                textwrap.dedent(
                    """
                    pnc_accounts:
                      - pnc_account_id: inline_user
                        ordering: full_scan
                        castles:
                          - kingdom: K230
                            castle_name: Main
                          - kingdom: K230
                            castle_name: Farm
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = load_app_config(config_path)

            self.assertEqual(len(config.castle_rosters), 1)
            self.assertEqual(config.castle_rosters[0].pnc_account_id, "inline_user")
            self.assertEqual(len(config.castle_rosters[0].castles), 2)
            self.assertEqual(config.castle_rosters[0].ordering, CastleRosterOrdering.FULL_SCAN)
            self.assertEqual(config.castle_roster_path, castles_path.resolve())

    def test_load_app_config_rejects_legacy_selected_castle(self) -> None:
        """Rejects the removed account-level selected-castle schema instead of silently accepting it."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)

    def test_load_app_config_rejects_mixed_inline_and_environment_credentials(self) -> None:
        """Rejects accounts that try to use both credential modes at once."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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
                        password_env: TEST_PASS
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path, env={"TEST_PASS": "pass"})

    def test_load_app_config_rejects_multiple_accounts_for_one_instance_and_pnc_account(self) -> None:
        """Rejects duplicate runtime targets for the same BlueStacks/P&C identity pair."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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
                      - id: account_b
                        instance_id: bs-main
                        pnc_account_id: inline_user
                        username: inline_user
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)

    def test_load_app_config_rejects_duplicate_castles_within_roster(self) -> None:
        """Rejects castle-roster cache files that define the same castle twice."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            castles_path = root / "castles.yaml"
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
                    """
                ).strip(),
                encoding="utf-8",
            )
            castles_path.write_text(
                textwrap.dedent(
                    """
                    pnc_accounts:
                      - pnc_account_id: inline_user
                        castles:
                          - kingdom: K230
                            castle_name: Main
                          - kingdom: K230
                            castle_name: Main
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)

    def test_load_app_config_rejects_unknown_castle_roster_ordering(self) -> None:
        """Rejects roster cache files that claim an unsupported ordering mode."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            castles_path = root / "castles.yaml"
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
                    """
                ).strip(),
                encoding="utf-8",
            )
            castles_path.write_text(
                textwrap.dedent(
                    """
                    pnc_accounts:
                      - pnc_account_id: inline_user
                        ordering: guessed
                        castles:
                          - kingdom: K230
                            castle_name: Main
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)

    def test_load_app_config_rejects_pnc_account_id_that_differs_from_username(self) -> None:
        """Rejects targets whose explicit P&C identity does not match the configured username."""

        with tempfile.TemporaryDirectory() as temp_directory:
            config_path = Path(temp_directory) / "accounts.yaml"
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
                        pnc_account_id: different_identity
                        username: inline_user
                        password: inline_pass
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)

    def test_load_app_config_rejects_non_canonical_roster_kingdom_identifier(self) -> None:
        """Rejects castle-roster kingdoms that are not authored in canonical `K###` form."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            config_path = root / "accounts.yaml"
            castles_path = root / "castles.yaml"
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
                    """
                ).strip(),
                encoding="utf-8",
            )
            castles_path.write_text(
                textwrap.dedent(
                    """
                    pnc_accounts:
                      - pnc_account_id: inline_user
                        castles:
                          - kingdom: k230
                            castle_name: Main
                    """
                ).strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ConfigurationError):
                load_app_config(config_path)


if __name__ == "__main__":
    unittest.main()
