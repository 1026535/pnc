# V16 — Building upgrade, prerequisites and queue menus

[Index and common contract](../PNC_VISION_MODULAR_PLAN.md). Depends on V01; V02 for automatic Home entry. Coordinate with [feature02](../PNC_CORE_REMAINING_02_BUILDINGS_PLAN.md). Deliverable: one shared upgrade/requirement/queue family, without redoing qualified building endpoints.

## Existing support and scope

Building capture tests already cover Farm, level publication, requirement Go, upgrade/detail variants, Build Queue and warning/confirmation surfaces. Inspect feature02's current commit before editing. The September15 task did not establish that all these are broken.

Owners: building helper functions in `pnc_observation_enricher.py`, profile/control data and OCR plans; `app/automation/tasks/building_workflow_support.py`, `building_upgrade_task.py`, `app/pnc/domain/building_operations.py` and core navigation. Building mutation/executor/journal ownership stays unchanged.

## Implementation

1. Inventory the consumer-required fields against current captured producers. Reuse complete pieces; fix only missing or inconsistent facts in the shared upgrade family.
2. Publish observed building identity/current and target level, ordinary costs/time, explicit unmet requirement rows, distinct Go controls, active queue/timer and relevant ordinary/premium/speedup controls.
3. Bind each prerequisite row to its own measured action geometry. A building's Home atlas location is not a prerequisite-menu selector.
4. Keep warning/confirmation surfaces owned and independently identified. Read their actual action and costs; no generic Confirm control can stand in for any mutation.
5. Wire both publishers and the existing typed consumer. Preserve queue busy/idle distinctions and unknown values. Restrict module extraction to the changed building family.

## Acceptance and proof

Target `test_building_captured_flows.py`, `test_building_level_publication.py`, `test_building_requirements_observation.py`, `test_building_confirmation_observation.py`, `test_upgrade_warning_guard.py` and affected building task contracts. Replay meaningful source frames through production OCR/planning; do not duplicate tests for every building sharing the same layout.

Start `py tools/run_tests.py group unit.app.pnc.vision`, then affected checks. One core-runtime route on a currently available building: Home → building → upgrade/prerequisite detail → building → Home. Inspect an existing queue only if present. Save typed facts and pre/post frames. Stop before upgrade, premium/speedup, hiring a builder or confirmation. Rare warning states can be qualified from saved captures; do not create them by spending. Name any separate building-specific layout needing its own future packet.
