# D — Automate mechanical acceptance and current-state reconstruction

Priority: design minimal D1 alongside C2 in Q4, then render one cohort/current view in Q6, following the [coordinator review](../V44_QUALITY_REVIEW_AND_SEQUENCE.md). Owner: coordination/live-tooling owner; acceptance decisions remain with the coordinator. Review coverage: §4B/E and §6, with V44 coverage as one consumer.

## Cause and target design

Adding another handoff checklist leaves the same facts hand-maintained in the brief, helper, manifest, batch and ledger. Recorded case/count mismatches and stale status fields show that this is an operational data-model problem. Keep the existing evidence schema and ledger; implement one validated representation and render its repeated views. Do not create another dashboard, database or orchestration service.

The canonical split is: the released assignment defines selected cases and purpose; immutable executor results record actual observations/receipts; an independent acceptance record references those results and its disposition; a compact current view is derived from the latest accepted records plus explicitly current running assignments. Facts and acceptance judgments must not overwrite each other.

## D1 — Mechanical validation before coordinator reasoning

1. Define typed models/parsing for the existing `evidence.json` v2 contract in 15's tracked live support. Retain historical manifests as historical data; migrate the active producer and its consumers together without rewriting all old files.
2. Check selected-case completeness, candidate/import root/helper binding, cited artifact existence/hash, receipt-based actual counts, native-boundary references, incident publication and cleanup. Generate repeated summaries from these fields. A worker-written `passed` value is not independent proof; the validator detects mechanical inconsistency, while the coordinator still reviews source and critical native evidence.
3. Record acceptance with exact result IDs, source/assets tested, retained proof and reasons, rejected findings and next owner/trigger. Use existing runner fingerprint/results fields rather than building a second whole-tree hashing system. Unknown dependency scope triggers human review/conservative revalidation, not automatic promotion.
4. Render the batch summary and current ledger block from this accepted state. Where failure policy requires both `record.json` and a human README, render the human view from the record instead of entering the incident twice. Existing weekly collection remains canonical; do not add a competing incident index writer.
5. Make stale/incomplete state explicit on resumption. One view answers what is running, what was accepted/published, which evidence is missing and the next trigger. Older review `pushed: false` values remain truthful historical observations.

**Acceptance:** inject a missing selected case, wrong candidate, inherited unselected result, receipt-count mismatch and missing artifact into saved/fake records; each is caught before handback. The accepted record renders consistent batch/current views. A fresh coordinator can resume the pilot from that view and referenced artifacts without rereading the whole conversation. No live action is needed to test this parser/renderer.

## D2 — Pilot one accepted cohort and one current view

The existing coordinator ledger is `C:/Users/lebel/pnc/.local-data/devin-vision-pipeline/status.json`. It contains stale top-level snapshots and newer nested `v44_implementation_slices.slices.V44-4` records. Pilot a coordinator-owned `v44_implementation_slices.current_state` block rather than adding a separate status store.

1. Record the as-of time, source/worktree/import root, active assignment and purpose, latest accepted result, publication state, capacity owner and next blocker/trigger. Keep candidate, accepted source and verified remote tip separate. Import actual current records when implementation starts; do not reinstall the historical e11/1d/turn031 values as current.
2. Render one row per acceptance unit from its assignment, executor result and acceptance decision. Use canonical target/slot/effect identifiers, actual menu/endpoint/return contract, evidence references, disposition and unresolved owner/trigger. A geometrically eligible slot is not proof of its occupant or an accepted route.
3. Reuse existing owners: `scene_geometry.json` and `domain/home_city_slots.py` for geometry, `building_catalog.py` for semantic types, [BUILDING_MENU_COVERAGE](../../BUILDING_MENU_COVERAGE.md) for feature ownership and [V44-4](../V44_4_BUILDING_ROUTE_MIGRATION.md) for scope. The renderer must not create a competing catalog.
4. Derive counts using named denominators: selected cases, accepted route units, remaining required units and whole-epic status. Body recognition, discovery capture, production acceptance, local integration and verified publication remain separate facts. Preserve historical review dispositions and timestamps.
5. Keep unknown/held/external cases explicit with their next trigger. This pilot need not reobserve all 54 slots, revalidate every route or finish V44 to prove a state-rendering improvement. Existing whole-V44 completion obligations remain with the parent plan; partial acceptance stays independently useful.

## Migration, validation and stop condition

Migrate one active producer/consumer pair and one cohort. Preserve historical raw manifests and the previous independent reviews. Render current views from the new accepted record, then retire the equivalent hand-maintained fields in active templates so the change actually reduces duplicate work. Do not leave a new current block alongside an equally authoritative old block.

Use offline model/renderer tests for D1's recorded inconsistencies and one saved successful package. Run affected selection for tracked tooling changes; documentation-only portions use JSON/link checks and `git diff --check`. Consume an already-needed authorized batch's result for end-to-end integration. A report renderer needs no extra game tour.

**Done when:** mechanical omissions fail before review; one reviewed cohort renders consistent batch/current summaries; a fresh coordinator can identify accepted/published work, active ownership, the next action and its release trigger without reconstructing the conversation. Record review repair and resumption effort through 13. Stop expansion if the pilot leaves more independently maintained state than it removes.
