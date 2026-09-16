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

### Execution record — 2026-09-16

**Current status: Delegated.** The catalog slice is independently reviewed and saved at `0fb4af03acff0c5e9f32abe2b42722b55e016849`; shared-state/observation work is running. PW01 is not yet accepted, merged or pushed. PW02/PW03/PW06 remain gated on complete PW01 acceptance.

- Worker checkout/branch: `C:/Users/lebel/pnc/.local-data/worktrees/pet-workshop-pw01`, `codex/pet-workshop-pw01`.
- Base: `b8c96b8e36b943a47006fde320629e1ae313ad29`, incorporating accepted `origin/main` `a73843cebfcee2105d8efd07706dd7fcb94fda10`. First dispatch used `f346d91` before that synchronization.
- Active worker: session `cedar-stealer`, `.local-data/devin-implement/pw01-platform-check`, turn `003`; brief `.local-data/devin-briefs/pw01-shared-state.md`. Startup confirmed. The existing native completion callback and lead monitor cover this run; monitor evidence is in the coordinating checkout's `.local-data/devin-monitor`.
- The catalog and shared-state portions are internal handoffs of PW01, not new packets/dependencies. Lead reviews actual implementation and combined checks before releasing consumers. No live effect/access is needed for this foundation; live validation for later packets remains on hold for the user's replacement account.

#### Independent catalog review

- Catalog contains 114 items, 20 producers and 123 drop entries. All seven decoded source hashes matched the original evidence.
- `PW01-C1` fixed: the JSON loader now rejects duplicate object keys before Python can silently discard earlier values; a focused regression reproduces the original acceptance defect.
- `PW01-C2` fixed: authored `randomItems` candidates are explicitly distinct from current occupancy. The recovered client's `MergeAdventureData:InitChessboard` uses server `gridMap`; the runtime must observe actual pieces.
- Lead command `py -m unittest tests.unit.app.pnc.test_pet_workshop_catalog`: **17 passed** after corrections. `git diff --check`: **passed**. Prior worker `unit.app.pnc` evidence contains **573 passed**, including the original 16 catalog tests; it is not a full-suite acceptance run.
- Reviewed revision and file hashes: worker `.local-data/reports/pet-workshop/pw01-catalog-lead-review.json`. Worker group evidence: `.test-impact/results.json`, run `95b2c16a751a4a628e194825c2f1f466`. Full combined PW01 checks and installed-package loading remain assigned to the shared-state handoff.

#### Handled attempts and recovery evidence

Paths below are relative to the worker's `.local-data/devin-implement/`. Each turn retains `result.json`, error logs and any actual handoff. Do not re-handle completed turns or read the full conversation/export. All stopped attempts reported `writers_stopped: true`; no competing writer was started.

| Run / turn | Outcome | Lead disposition |
| --- | --- | --- |
| `pw01/turn-001` (`spectacled-jaborosa`) | Internal service error after 659.63 seconds; trace `5f6eb6de10cb0404c172ade961f1acba`; no edits/tests. | Verified exact saved session with `devin list --format json`, synchronized the clean checkout, resumed once. |
| `pw01/turn-002` | Same error after 2.79 seconds; trace `5c7ebafa441f353f7a6f95688aec6519`; no edits/tests. | Preserved failed session and used a clean implementation session. |
| `pw01-recovery/turn-001` (`tricolor-bearskin`) | Same error after 484.20 seconds; trace `a71b01b33e6b0bc2ce5767635e56e736`; no edits/tests. | Ran a materially smaller read-only platform diagnostic rather than another unchanged package attempt. |
| `pw01-platform-check/turn-001` (`cedar-stealer`) | Passed in 12.15 seconds; verified `swe-2-max` final response, Python 3.13 and expected HEAD; clean checkout. | Basic command/final-response path works. Resumed with the bounded catalog slice. |
| `pw01-platform-check/turn-002` | Same service error after 1235.56 seconds; trace `d96576f355ffb2f172187a0a18bb5c56`; catalog/docs/tests preserved, 573-test group passed. | Reviewed saved implementation, applied the two findings above, independently checked and committed the catalog slice, resumed shared-state work. |

The reported service error is `-32013`, internal `Protocol error (invalid_argument)`, marked retryable by Devin. Root cause remains unknown; diagnostic success does not prove it fixed. Installed CLI recorded `3000.10.27 (bcbe88c7)` and `swe-2-max`. No permission or model substitution occurred. The user confirmed these should be treated as recoverable: preserve useful work, continue automatically, and notify again only when recovery stops making progress or requires input.
