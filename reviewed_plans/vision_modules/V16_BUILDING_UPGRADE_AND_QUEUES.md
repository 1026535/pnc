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

## Implementation status — 2026-09-16 (accepted for stated coverage)

Implemented the scoped shared packet in this checkout (`codex/vision-v16-buildings`):

- `pnc_automation/app/pnc/domain/building_details.py` — typed `BuildingDetail`/`BuildingRequirementRow`/`BuildingDetailPhase` facts plus exact `current/max` level parsing; `Observation.building_detail` carries the fact through both publishers.
- `pnc_automation/app/pnc/domain/resource_cost.py` — canonical `ResourceCost` extracted from the Research schema and remapped; Research imports migrated.
- `pnc_automation/app/pnc/vision/building_details.py` — `BuildingContentProducer` (positive-proof phase — upgrade sections/upgrade-detail layout, the owned `Overall Hourly Output` stats label, or ≥2 measured Institute category controls — owner, level pair, costs, times, requirement row whose `go_bounds` comes only from the measured row Go, premium facts) and `filter_building_detail_controls` applied by both `ObservationBuilder._publish` and `NavigationPerception.build`.
- Selector semantics: `PNC_BUILDING_DETAILS_UPGRADE_BUTTON` is the primary-panel entry (reviewed non-monetized outcome → `PNC_BUILDING_DETAILS`); `PNC_BUILDING_UPGRADE_BUTTON` is the UPGRADE-phase mutation surface only; named `PNC_<X>_UPGRADE_BUTTON` selectors stay entry controls and are suppressed on proved UPGRADE frames. Measured controls: Farm dual-phase template, Institute primary entry, Institute blocked-detail row-owned Go, Home `PNC_HOME_BUILD_BUTTON` (literal Build-word anchor). The blocked Institute panel's red Upgrade is unqualified — the upgrade-detail mutation surface currently publishes only on the qualified Farm layout.
- `NavigationCore.open_building_upgrade_detail` + `WorkflowContext.open_building_upgrade_detail`: at most one phase-owned entry tap, completion requires fresh CLEAR same-building UPGRADE detail.
- feature02 `buildings.py` and `core_daily_mutation.py` consume the typed owner/level/phase facts; legacy `building_upgrade_task.py` resolves the phase-owned surface selector and parses the canonical N/M pair.

Evidence: `.local-data/devin-v16/` replay over 12 saved captures through both production paths (builder/perception agree); `tests/integration/vision/test_building_detail_facts.py` real-RapidOCR acceptance; contract tests migrated to typed fakes. The worker's full fallback passed 2,405 tests with seven skips. Lead correction checks covered phase/source proof, navigation, popup recovery, building workflow contracts, level publication, and real captured facts; final building-fact checks passed ten tests.

Lead live acceptance used the configured `mega_old_acc` active castle under one canonical reservation, runtime `20260916T143209Z_04a4d567`: Home → Institute PRIMARY → UPGRADE detail → PRIMARY → Home → Build Queue → Home. Detail frame0037 proved level22/45, CastleLv23 with its measured row Go, original4d08:36:48 and actual2d17:10:46, premium19,761 as a read-only fact, and four bounded material rows. Damaged numeric grouping leaves only the unreadable half unknown; resource types remain unqualified. Queue frame0047 proved first slot idle; final Home frame0049 was captured at14:34:47UTC and visually inspected. No resources were spent; the reservation was released and the pre-existing instance preserved. Artifacts/typed JSON/trace are in `.local-data/devin-v16/live_accepted_candidate/` in the V16 checkout.

Live findings corrected before acceptance: the internal Institute Back returns PRIMARY without changing ScreenType, so the canonical close operation requires that typed phase before workflow graph navigation; Build Queue is task-owned and its measured close belongs to the inspection workflow; Institute time/material regions must be explicitly planned; day durations and partly unreadable integer pairs must retain their observed meaning. Both publisher paths suppress generic Upgrade controls when content/phase proof is absent, and category/Go/entry control evidence must be TEMPLATE.

Precise unsupported separate layouts: named-primary upgrade-detail surfaces other than Institute (`institute_upgrade_detail`) and Farm generic (`building_detail_farm`) — e.g. Blacksmith, Hall of War — are not qualified; their phase stays unproved and the core operation stops before any entry tap. Confirmation/speedup states beyond the qualified shield warning, and premium Upgrade Now as an action, remain unsupported.
