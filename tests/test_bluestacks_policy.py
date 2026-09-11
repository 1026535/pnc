"""BlueStacks role and capability policy tests."""

from __future__ import annotations

import unittest

from pnc_automation.bluestacks_management.policy import (
    BlueStacksMemoryPolicy,
    LiveAutomationRole,
    capabilities_for_roles,
    is_memory_restart_eligible,
    validate_live_roles,
)
from pnc_automation.core.errors import ConfigurationError


class BlueStacksPolicyTests(unittest.TestCase):
    """Keeps role-to-capability and memory-restart decisions centralized and dynamic."""

    def test_read_only_capabilities_allow_observation_but_no_control(self) -> None:
        """Maps the read-only role to no launch, app, or input capability."""

        capabilities = capabilities_for_roles((LiveAutomationRole.READ_ONLY,))

        self.assertFalse(capabilities.allow_instance_launch)
        self.assertFalse(capabilities.allow_app_launch)
        self.assertFalse(capabilities.allow_input)

    def test_contradictory_roles_are_rejected(self) -> None:
        """Prevents one account from being both read-only and automation-enabled."""

        with self.assertRaisesRegex(ConfigurationError, "cannot combine read_only"):
            validate_live_roles(
                (LiveAutomationRole.READ_ONLY, LiveAutomationRole.SMOKE_TEST),
                account_id="account_a",
            )

    def test_memory_restart_roles_are_configurable_and_exclude_read_only(self) -> None:
        """Uses the configured role set while preserving the read-only safety exclusion."""

        policy = BlueStacksMemoryPolicy(restart_roles=frozenset({LiveAutomationRole.LIVE_TESTING}))

        self.assertTrue(
            is_memory_restart_eligible((LiveAutomationRole.LIVE_TESTING,), policy.restart_roles)
        )
        self.assertFalse(
            is_memory_restart_eligible((LiveAutomationRole.SMOKE_TEST,), policy.restart_roles)
        )
        self.assertFalse(
            is_memory_restart_eligible((LiveAutomationRole.READ_ONLY,), policy.restart_roles)
        )


if __name__ == "__main__":
    unittest.main()
