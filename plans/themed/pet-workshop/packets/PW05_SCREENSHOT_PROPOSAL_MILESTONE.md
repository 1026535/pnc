# PW05 — Saved screenshots and proposed-action milestone

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW02](PW02_RECOGNITION_CONTROLS.md), [PW04](PW04_ONE_STEP_SOLVER.md)

## Read before implementation

- [Plan 01: saved evidence and native input modes](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#3-evidence-and-existing-owners)
- [Plan 01: recognition verification and gaps](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#6-verification-and-evidence-gaps)
- [Plan 02: saved screenshot scenarios](../PNC_PET_WORKSHOP_02_SOLVER_POLICY_PLAN.md#5-required-scenarios-and-acceptance-limits)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** recognition worker, with Plan 02's accepted public planner. **Prerequisite detail:** PW02 for labels; PW04 for proposed actions.

Provide a small offline analysis entry point using the production parser and planner. It accepts saved images/fixture sets and emits machine-readable facts, an annotated review image and the proposed action/reason under `.local-data/`. Reuse existing rendering/serialization utilities where suitable. Do not create a second recognizer in the tool. Phone reference frames may be labeled by their evidenced layout, but must never qualify BlueStacks gesture geometry.

Select and track the smallest sanitized crops/full Workshop fixtures required for portable regression tests, with an authored manifest. Retain native input modes. Originals, generated annotations and bulk extraction stay ignored. Do not change `tests/data/local_fixture_artifacts.json` or require another worker to have the originating user's Pictures directory.

## Acceptance

The ready three-coconut order is labeled as three and rejected; the Wood 10 + coconut lasso order is eligible but incomplete; the selected Tree 4/production/merge sequence is distinguishable; unknown and black frames never produce a gameplay gesture.

## Focused validation

Compare both the recognized facts and the proposed action with reviewed labels for the cited native sequence and order frames. Explicitly reject the ready three-coconut order and block gameplay proposals from unreadable/black frames. Show observed Workshop level and relevant producer state with their evidence; do not infer hidden server order IDs or label an observed order invalid from an unproven level rule. The [reviewed progression findings](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection) set that boundary. Keep generated annotated images and machine-readable reports ignored; portable authored fixtures remain tracked.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Portable labeled fixtures, offline analysis command, generated report locations and exact reviewed proposed actions. Lead acceptance is the first screenshot/proposal milestone and is mandatory before the lead invokes a production gameplay caller in PW10. PW06 and PW07 may finish their scoped offline work independently of this analysis-tool/report handoff.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.

### Delegation — 2026-09-21 UTC

**Delegated, offline only.** Recognition session `cedar-stealer`, turn 014, starts from accepted `1f14e06` in `pet-workshop-pw01`. Brief: `.local-data/devin-briefs/pw05-implementation.md`; run: `.local-data/devin-implement/pw01-platform-check`. Scope is this packet's real-parser/planner analysis tool, portable labels/fixtures, review images and behavioral checks. The lead reviews exact reports and three-coconut rejection. Shared policy/authority/workflow owners remain unchanged; any material shared-contract issue returns to the lead. No Main/ADB/lease access. Lead owns status records and acceptance.

### Freeze recovery — 2026-09-21

Turn 014 was interrupted with no tracked source edits or completed acceptance evidence. The lead verified absent supervisor/children and native `cedar-stealer` identity in the exact checkout, preserving `turn-014/recovery-original-state.json` and `recovery-evidence.json`. Same session resumed as **turn 015**, base `1f14e06`, with `.local-data/devin-briefs/pw05-recover-20260921.md`; startup and the replacement completion route were verified. Unrelated `nul` and `pnc_automation.egg-info/` remain untouched.

User-approved simulator use is available for logical development, while PW07 owns any necessary simulator changes. PW05 keeps actual native recognition/geometry evidence separate from simulated or downscaled images and routes concrete simulator gaps to the lead. Status remains **Delegated**; final candidate/report review, offline evidence and any applicable live proof remain required before acceptance. The new lead and Main's 01:00–05:00 Toronto limit are recorded in the roadmap; this assignment has no live authority.
