# PW02 — Workshop recognition, orders and measured controls

[Roadmap, status and dispatch workflow](../PNC_PET_WORKSHOP_ROADMAP.md) · [Common architecture](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#common-baseline-and-architecture-requirements)

**Kind:** Implementation packet. **Dependencies:** [PW01](PW01_SHARED_CONTRACT_CATALOG.md)

## Read before implementation

- [Plan 01: evidence and canonical vision owners](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#3-evidence-and-existing-owners)
- [Plan 01: shared contract](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#4-shared-interface-contract)
- [Plan 01: recognition verification and gaps](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#6-verification-and-evidence-gaps)

The linked design sections own the requirements; this packet owns the assigned implementation and proof. Use the accepted dependency commit, reconcile newer changes by symbol, and return shared-contract corrections to their owner.

## Assignment

**Owner:** recognition worker. **Prerequisite detail:** accepted PW01. Can run alongside PW03/PW04 after PW01 is accepted.

1. Add evidence-backed profiles for Beast Manor/Workshop board and observed detail surfaces; expand to recycling confirmation, feeding/activation/depletion and level-result surfaces as their targeted evidence is acquired. Register the corresponding selector semantics/content request family through existing owners. Do not treat a requested screen as proof of its identity.
2. Detect the grid from the proved layout/anchors and measure cell geometry. Recognize item sprite/tier and overlays separately; use cached templates and bounded OCR for energy, header, selected-item names, rewards and details. Start with the existing OpenCV/OCR tools. Unknown icons request bounded information acquisition or stop; no external vision-service dependency is introduced.
3. Parse full/partial orders and duplicated ingredient icons correctly. Preserve portrait/inspection and immediate-submit controls separately. A clipped card cannot establish a total of two. Recipe/reward lookup may explain an observation but must not replace visible evidence with a guessed server order. Apply the [progression evidence limits](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#workshop-progression-and-order-selection): report visible level, requirements and producer state without inventing hidden order type/prerequisite completion or rejecting a card because inferred level eligibility disagrees.
4. Publish the same content through both observers, including native RGBA input and provenance. Do not normalize only the test fixture to hide the existing capture/OCR boundary issue. Reuse canonical image normalization where appropriate; do not implement a Workshop-only global OCR fix.
5. Keep order positions frame-owned. A bounded strip survey belongs to Plan 03; the parser identifies visible cards, partial edges and measured scroll surface. Distinguish currently reachable order coverage from unexposed server orders.
6. Extend recognition of the four ordinary mechanics and the restricted recycling controls. Unavailable action-state evidence is an explicit qualification gap, not permission to guess its result.
7. Hand back a route-evidence table for the four entry/return pairs in [Plan 01 evidence](../PNC_PET_WORKSHOP_01_RECOGNITION_STATE_PLAN.md#evidence-that-can-be-used-without-live-access): source profile, measured control, destination profile, artifact pair and confidence. Lead acceptance of that table is required before Plan 03 PW07 registers the corresponding production edge. Missing control evidence remains a targeted gap; no edge is inferred from a remembered coordinate.

## Acceptance

Real saved board/details are labeled correctly where evidence is readable; unknown/transition states abstain; both observers agree; no parser performs navigation, planning or input.

## Focused validation

Replay the smallest representative native board/detail/transition captures through both production publishers. Check content, measured controls and frame provenance together, including repeated ingredients and clipped cards. Record exact readable coverage and missing action-state captures; keep those qualifications open for PW10.

Follow the [common validation and acceptance gates](../PNC_PET_WORKSHOP_ROADMAP.md#validation-and-acceptance). Record passed, failed and skipped commands; do not repeat adequate checks without a relevant change.

## Handoff

Recognized fixture manifest, measured-control/profile ownership, both-publisher checks and the four-pair route-evidence table. PW05 consumes the labels; PW07 consumes the accepted route facts. Missing current action-state evidence stays explicit for PW10.

Use the [common handoff record](../PNC_PET_WORKSHOP_ROADMAP.md#worker-handoff-and-lead-review). Keep detailed acceptance evidence with this packet and its summary status in the roadmap.
