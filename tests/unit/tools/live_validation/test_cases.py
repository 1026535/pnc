"""Frozen case registry integrity tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalCasePurpose,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect

from tools.live_validation.cases import (
    BODY_ENTRY_OPERATION_ID,
    CaseGate,
    CasePurpose,
    CASE_REGISTRY,
    CaseSpec,
    frozen_case_ids,
    require_case,
)


class CaseRegistryTests(unittest.TestCase):
    def test_registry_contains_the_four_released_cases(self):
        self.assertEqual(
            {
                "v44_bank_body_menu",
                "v44_bank_return_home",
                "v44_watchtower_body_menu",
                "v44_watchtower_return_home",
            },
            set(frozen_case_ids()),
        )

    def test_every_case_uses_the_body_entry_operation(self):
        for spec in CASE_REGISTRY.values():
            self.assertEqual(BODY_ENTRY_OPERATION_ID, spec.operation_id)
            self.assertIn(CaseGate.GUARDED_HOME_CITY, spec.required_preconditions)

    def test_discovery_cases_have_no_control(self):
        for spec in CASE_REGISTRY.values():
            if spec.purpose is CasePurpose.DISCOVERY:
                self.assertIsNone(spec.control_name)
                self.assertIsNone(spec.developmental_purpose)
                self.assertEqual(0, spec.max_control_attempts)

    def test_development_cases_map_to_control_validation(self):
        for spec in CASE_REGISTRY.values():
            if spec.purpose is CasePurpose.DEVELOPMENT_VALIDATION:
                self.assertIs(
                    DevelopmentalCasePurpose.CONTROL_VALIDATION,
                    spec.developmental_purpose,
                )
                self.assertEqual("return_home", spec.control_name)
                self.assertIs(
                    WorkflowEffect.NONSPENDING_STATE_CHANGE, spec.control_effect
                )
                self.assertTrue(spec.allowed_source_screens)

    def test_discovery_spec_rejects_a_control(self):
        with self.assertRaises(ValueError):
            CaseSpec(
                case_id="bad",
                purpose=CasePurpose.DISCOVERY,
                target=next(iter(CASE_REGISTRY.values())).target,
                home_city_slot=None,
                operation_id=BODY_ENTRY_OPERATION_ID,
                entry_effect=WorkflowEffect.READ_ONLY,
                released_action_id="x",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset(),
                max_control_attempts=0,
                required_preconditions=frozenset(),
                required_postconditions=frozenset(),
            )

    def test_control_spec_requires_screens_and_attempts(self):
        base = dict(
            case_id="bad",
            purpose=CasePurpose.DEVELOPMENT_VALIDATION,
            target=next(iter(CASE_REGISTRY.values())).target,
            home_city_slot=None,
            operation_id=BODY_ENTRY_OPERATION_ID,
            entry_effect=WorkflowEffect.READ_ONLY,
            released_action_id="x",
            control_name="return_home",
            control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
            required_preconditions=frozenset(),
            required_postconditions=frozenset(),
        )
        with self.assertRaises(ValueError):
            CaseSpec(**base, allowed_source_screens=frozenset(), max_control_attempts=1)
        with self.assertRaises(ValueError):
            CaseSpec(**base, allowed_source_screens=frozenset({"x"}), max_control_attempts=0)

    def test_require_case_rejects_unreleased_id(self):
        with self.assertRaises(KeyError):
            require_case("v44_not_released")


if __name__ == "__main__":
    unittest.main()
