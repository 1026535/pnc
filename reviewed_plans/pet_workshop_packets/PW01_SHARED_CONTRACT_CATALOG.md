# PW01 — Shared types, catalog and portable seed fixtures

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** Current accepted repository base; no Workshop predecessor.

## Read before implementation

- [Plan 01: baseline and common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)
- [Plan 01: agreed policy](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#2-agreed-behavior-shared-by-the-three-plans)
- [Plan 01: evidence and existing owners](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#3-evidence-and-existing-owners)
- [Plan 01: shared state and interface contract](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#4-shared-interface-contract)
- [Plan 02: estimator and policy requirements that the types must support](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#2-policy-and-planning-semantics)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** Plan 01 foundation worker. **Prerequisite detail:** current accepted repository base only. **No live access.**

1. Inventory the decoded artifacts and manifest. Build one deterministic authored catalog from required item/producer/drop/energy/unlock/recycling fields, with source hashes and packaged build. Resolve defaults/shared references as data without executing Lua. A small importer is justified only for this known table format; do not build a general Lua interpreter. Do not require raw extracted files at runtime or copy all 1,263 order forms merely to invent server identities.
2. Retain all 114 seed item definitions and the producer/drop relationships needed for the supported chains. Preserve other valid items as recognized-but-unusable where policy excludes them. Known model coverage and visual-template coverage are separate; the seed count is not a fixed-length validation rule. Follow the [reviewed progression evidence](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection), preserve inherited table defaults and keep item tier distinct from Workshop-level progression. Do not add hidden active-order IDs or a fabricated generator minimum-level invariant.
3. Add shared types and agreed action interfaces. Add authored minimal typed fixtures for quantities, partial recognition, zero energy, feed/depletion/activation and recycling. Synthetic transitions must be labeled synthetic.
4. Write the canonical implementation design to `docs/PET_WORKSHOP_DESIGN.md`: owner map, data flow, interfaces and extension method. Add `docs/game-reference/workflows/pet-workshop.md` for sourced game facts and update its existing index. Keep game facts distinct from user policy, including the reviewed level-linked progression and the unknown server random-order selector. Include observation date/build, provenance, confidence and limits. Later packages update their owned sections in those same documents.
5. Hand back exact definitions, catalog provenance, changed symbols and focused test results. Lead reviews and records the accepted foundation commit before workers consume it.

## Acceptance

Catalog loads without local APK paths; quantities/statuses preserve excluded and unknown states; independent typed fixtures can instantiate the shared contract; no runtime I/O in logical types; the documented interface is sufficient for Plan 02 tests.

## Focused validation

Use small catalog/schema and shared-model tests: inherited table defaults, real references, duplicate/dangling invalid data, quantities and explicit unknown states. Load the packaged catalog in a portable checkout without ignored APK material. Do not require a screenshot parser or runtime stub to prove the foundation.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Shared model/interface and catalog commit, provenance hashes, portable seed fixtures, canonical design/behavior documents and catalog/model check results. Lead acceptance of this commit releases PW02, PW03 and PW06.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
