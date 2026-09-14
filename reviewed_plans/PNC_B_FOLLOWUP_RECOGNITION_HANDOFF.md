# B follow-up: Resource cards, Hero results and broader Research

Date: September 13, 2026. Owner: B, the recognition task.

## Activation and purpose

The user requested this handoff so B takes complete recognition ownership of these
three gaps **after finishing its current work**. Finish and preserve the current
screen-first/OCR migration before activating this follow-up. This document does not
interrupt or resume B, merge branches, or import unfinished work.

When B reaches that checkpoint, adopt the three deliverables below into its active
plan and checklist. B owns diagnosis, necessary evidence collection, implementation,
perception models/IDs, assets, guards, OCR regions, canonical parsing/publication,
regressions and producer qualification. These are implementation deliverables, not
just entries to classify as pre-existing unsupported behavior. A concrete missing
capture or external prerequisite must be recorded with the exact fact needed and
next evidence step; it does not silently transfer implementation back to A.

B's existing worktree is
`C:/Users/lebel/pnc/.local-data/worktrees/non-yolo-recognition-continuation`, branch
`codex/non-yolo-recognition-continuation`. Its active files were inspected at HEAD
`93798a6` with ongoing local work. Verify the current checkpoint on activation;
preserve subsequent changes and do not reset to this historical HEAD.

The current B plan qualifies captured Research detail variants and preserves
existing Quest/Bag parsing. It does not explicitly commit to the Resource fragment
correction or Hero result sequence, and leaves non-Development tree-node selection
outside its existing producer. This follow-up closes those scope gaps.

Read the repository `AGENTS.md`, applicable implementation/live skills, B's current
`PNC_NON_YOLO_RECOGNITION_PLAN.md` and remaining checklist, and the scoped references
below. Full task transcripts and the full extracted game source are unnecessary.

## Ownership and delivery boundary

| B owns completely | A retains |
|---|---|
| Resource fragment/card facts and action evidence in both production observation paths | Bounded scrolling/reframing, full-inventory completion, single Use, stock/Daily receipts and execution callers |
| Hero stable result identities, transition evidence, distinct Confirm/Close controls, attempts/cooldown facts | Bounded result traversal/settling, recruitment policy, cooldown orchestration, durable reconciliation and execution callers |
| Research category/node/detail/requirements/queue facts, including the missing Institute entry evidence | Category/node selection policy, navigation edges, Start eligibility enforcement, mutation journal and caller integration |

Use the existing vision owners and whole-file ownership in
[A/B coordination](PNC_AB_COORDINATED_CONTINUATION.md). A's runtime, navigation,
workflows, action policy, authorizer, journal and mutation consumers remain A-owned.
If a producer contract needs an addition, B owns its perception model/identifier
change and documents the exact consumer adaptation for A. Do not move parsing or
recognition into A's workflows, add a parallel observer, or weaken an action guard.

Preserve B's zero-full-screen-OCR contract, independent screen/layout identity,
current-frame provenance, measured controls and bounded semantic OCR regions.
New YOLO/map-object discovery remains outside this handoff. A's latest independent
code passed 2,027 tests with six skips; that is historical consumer evidence and
does not validate B's new changes or the future combined candidate.

## 1. Resource inventory: retain and classify partial cards

**Value:** A can distinguish a card that needs reframing from unreadable interior
content, and can prove a complete inventory before using one owned pack.

**Observed failure:** on the selected Resource tab at 900×1600, the detector's
120-pixel minimum omitted visible 60-pixel and 66-pixel edge fragments. Taller
partial cards were UNREADABLE instead of CLIPPED. Three settled scroll frames
produced zero CLIPPED rows through the production paths. One omitted top fragment
visibly contained `Owned: 727`. No Use occurred.

**B deliverable:**

- Retain visibly evidenced top/bottom card fragments in canonical publication,
  with their viewport/row geometry and explicit incomplete/clipped state. Preserve
  only readable, correctly associated fields; do not invent a title, count or
  item identity for a fragment.
- Distinguish viewport clipping from unreadable content inside a fully visible
  card. Use observed viewport/card geometry at supported scales; do not hard-code
  the old 120-pixel threshold or fix only one screenshot's edge coordinate.
- Preserve complete-row title/item/count and measured action association, selected
  Resource-tab ownership, uncertainty and the distinction between single Use,
  bulk Use and purchase. A partial/ambiguous row cannot acquire an actionable Use.
- If entry from an unselected Resource tab is required, qualify the actual tab
  control and selected-state transition evidence. If the saved evidence lacks
  that state, name the required capture explicitly; a selected anchor alone is
  not an unselected-tab control.

**Acceptance:** actual OCR replay of the saved three frames through both
production builders retains the evidenced fragments with correct status/geometry,
preserves complete rows and does not synthesize missing fields/actions. Add focused
regressions for those defects and representative complete/interior-unreadable,
foreign-tab and overlay negatives. Publish the exact facts A should use to decide
whether to reframe; B does not implement scrolling or claim whole-inventory success.

**Evidence:** A's `core_resume/resource_edge_geometry.json` identifies the exact
three frames and the earlier real-OCR report in
`manual_update_20260913T214455Z/`. The scoped
[Resource source note](../docs/game-reference/workflows/resource-inventory.md)
explains recycled cells and partial viewport intersection, with Lua paths/symbols.
It also separates quantity-1 intent from stock/Daily proof.

## 2. Hero Hall: summon and result recognition

**Value:** the core can finish a free recruitment through its result sequence and
observe the receipt without operator clicks or accidental paid recruitment.

**Observed failure:** one authorized free single on K157 / NPC 2 led through a
summon animation, an Albertus presentation with Confirm, then a fragments result
with blue Close and a separate paid Recruit 1x. Recognition returned UNKNOWN for
the transition/result frames. After operator Confirm/Close, attempts changed from
five to four. The existing `hero-hall-recruit-001` journal entry is COMMITTED; it
must not be replayed to recreate evidence.

**B deliverable:**

- Qualify the evidenced stable hero-presentation and reward/fragments result
  identities independently of arbitrary hero name text or a generic Confirm word.
  Record the observed summon transition, including any interval with insufficient
  identity evidence, so A can own a bounded wait. Publish a summon/loading identity
  only when its own visual evidence supports it.
- Publish distinct, currently measured Confirm and Close controls for the correct
  result state. Result-screen Recruit/Draw remains separate from the Hero Hall
  free-single control; a visible paid action cannot inherit free authority.
- Preserve attempts and cooldown content after returning to the Recruit panel.
  A cooldown frame need not display an attempts count at the same time. Missing
  fields stay missing, and button disappearance alone is not a receipt.
- Retain foreground ownership: missing identity/control and unrelated overlays
  cannot expose background actions. Do not relabel arbitrary UNKNOWN frames as
  loading or add workflow retries to make recognition appear complete.

**Acceptance:** both production paths recognize the saved stable result states and
publish only their independently supported controls. Erasing result identity or
the relevant control, substituting a paid Recruit control, and applying a blocking
overlay must preserve the intended abstention. Document the observed sequence and
control destinations with evidence. A then qualifies automatic traversal and the
existing reconciliation path; one free-single receipt is not five-single Daily
acceptance. No new recruit is required merely to rerun the saved-frame tests.

**Evidence:** `core_resume/manual_update_20260913T214455Z/` contains frames ending
`0078_hero_hall_dispatch`, `0079_hero_hall_recruit_post`,
`0080_hero_result_diagnostic` and `0081_hero_after_manual_confirm`.
`manual_update_20260913T220305Z/` contains the later after-close and reconciliation
evidence. The [Hero source note](../docs/game-reference/workflows/hero-hall-recruitment.md)
identifies `PubGetNewHeroView` Confirm and `PubDrawRewardView` Close versus Draw,
with source version and live-build limitations.

## 3. Research: complete the producer facts beyond Development

**Value:** A can extend the original category priorities beyond Development and
decide whether a normal Start is eligible from actual current UI facts.

**Current state:** B's checklist qualifies captured Economy/Military/Fortification
detail variants while explicitly leaving their tree-node selection outside the
Development row producer. A's new direct/authored callers intentionally accept only
Development. Broader category support is not delivered by recognizing detail
screens alone, and visible blue Research does not establish an idle queue.

**B deliverable:**

- Cover the original Research categories: retain Development and implement the
  missing Economy, Military and Fortification producer contracts. Reuse the
  existing category model and canonical row/detail parser rather than introducing
  a second category naming scheme.
- Publish current category identity, observed node identity/title, row bounds and
  valid selection geometry. Preserve association between the selected node and
  its detail. Duplicate, clipped, unreadable or ambiguous nodes stay explicit;
  do not assume the Development node's coordinates apply to another category.
- Publish the evidenced normal versus premium controls, current level/requirements
  where displayed, and independent idle/busy/active/completed queue/detail facts.
  An unmet requirement must be distinguished from a satisfied Requirement heading;
  an empty field or merely visible Start cannot imply eligibility or completion.
- Close the reproduced Institute entry dependency within this Research slice:
  after Research Queue Go, A's saved Home frame visibly shows Institute but both
  builders publish zero Institute objects and OCR returns no Institute line.
  Correct the existing Home building identity/observed-action publication using
  supported visual evidence. The focus arrow or expected camera position alone
  cannot authorize a guessed building tap; no new YOLO discovery is requested.

**Acceptance:** replay the existing category variants and add the missing
tree-node/queue cases through both real production builders, with sufficient
saved evidence for each category's newly supported facts. Cover normal/premium,
idle/busy, active/Start suppression, satisfied/unmet and ambiguous/missing-node
distinctions where they affect this contract. The Institute failure frame must
produce one correct Institute identity with valid evidence/geometry, or B must
report the exact remaining producer limitation. Document which facts allow A to
add an idle-queue predicate; implementing that workflow predicate remains A's job.
Do not claim a new research has started from a screenshot-only qualification.

**Evidence:** B's `tests/integration/vision/test_research_captured_variants.py`,
`test_research_tree_visual_controls.py` and `test_research_queue_navigation.py`
are the existing qualification starting points. Its current capture findings and
manifest identify the original detail frames. A's
`core_resume/research_caller_20260913T232029Z/` contains the Institute source frame
ending `0026_core_7_building_source.png`,
`research_replay_20260913T232029Z_observation_diagnostic.json`, `summary.json` and
`stop.json`. Exact active NPC 2 identity passed; the journal remained unchanged,
with zero Research Starts/diamonds. This isolates the entry failure from authority
or mutation execution.

## Existing implementation entry points

Paths here are relative to B's worktree and were verified when drafting:

| Slice | Canonical producer/test starting points |
|---|---|
| Shared publication | `pnc_automation/app/pnc/vision/observation_builder.py`, `navigation_perception.py`, `pnc_observation_enricher.py`; existing visual profiles/controls and `vision/data/screen_anchors.json` |
| Resource | `pnc_automation/app/pnc/vision/resource_inventory.py` (`parse_resource_inventory`, card geometry and clipping), the enricher's Resource additions; `tests/unit/app/pnc/vision/test_resource_inventory_vision.py` |
| Hero | Existing Hero Hall enrichment and visual controls; `tests/integration/vision/test_hero_observation.py`. There is no qualified summon/result-specific producer to preserve. Existing Hero Showdown intro Confirm is a different screen contract. |
| Research | The enricher's Research tree/queue additions, existing Research anchors and the three integration tests named above; `pnc_automation/app/pnc/vision/spatial_surfaces.py` for the missing Home Institute publication |

Consumer references such as `automation/daily_maintenance/hero_hall.py`,
`automation/research.py` and `automation/engine/core_daily_mutation.py` explain
required facts and receipts; reading them does not transfer their ownership to B.
Inspect actual current owners before editing, since B's preceding migration may
legitimately move these internal entry points.

## Evidence locations and collection limits

All `core_resume/` paths above are relative to this verified A evidence root:

`C:/Users/lebel/pnc/.local-data/worktrees/workflow-recognition-integration/.local-data/artifacts/`

These artifacts are ignored/local, not packaged assets or automatically available
in B's checkout. Read them in place; add only deliberately authored, appropriately
sanitized fixtures to B's tracked test data with source/build provenance. Do not
import A's dirty production code or edit A's worktree. If evidence is unavailable,
request the exact missing file/state rather than rebuilding the project history.

Use saved evidence and recovered package source first. APK 5.0.203/233 source and
the later live footer `5.2.77 / 5.0.204.235` are different versions; source handlers
explain behavior but do not prove a current visual control or server result.

Needed live inspection uses the configured BlueStacks API and canonical lease.
The user prefers API inspection, including observed input for evidence collection;
request a manual click only when BlueStacks is unresponsive. An inspection
workaround does not count as production selector/workflow acceptance. Preserve
pre-existing instances and stop when current identity/screen/input evidence is
unproved. No direct game-service calls or automatic Daily activation are included.

This document supplies no new spending, account/castle-switch or configuration
authority. Reuse applicable explicit user authorization without asking twice; if
a necessary new irreversible action lacks an exact target/action/budget, obtain
the missing authority after preparing its evidence and limits. Do not replay the
committed Hero single. A's last `serious_stuff` inspection returned all-black frames
and that account lacked `DAILY_CANARY`; neither condition is assumed resolved.

## Completion and return to A

1. Finish B's current work, then record these three items in B's active plan with
   explicit implementation ownership. Retain completed producer fixes instead of
   recreating them when applying this later handoff.
2. Implement each coherent slice through the existing owners. Run the relevant
   focused groups and `tools/run_tests.py affected --base origin/main --explain`;
   use the runner's full fallback when required by changed shared contracts.
   Do not substitute synthetic OCR text for actual OCR replay of the motivating
   captures, or repeat already sufficient live mutations as a validation ritual.
3. Report each item as qualified or explicitly blocked, with exact fact/ID/model
   changes, source fixtures/builds, actual commands/results, and remaining evidence
   needs. Same-session captures/resizes are reference evidence, not independent
   holdout accuracy or end-to-end workflow success.
4. Supply a reviewable completed B checkpoint and a concise consumer handback:
   facts A may rely on, route/control evidence, compatibility changes and negative
   cases. A/B integration occurs after B finishes, according to the user's sequence;
   this handoff itself does not authorize merge/push or automatic scheduling.

A then completes Resource traversal/callers, Hero result navigation, and broader
Research consumers through its existing mutation boundary and journals. Any
remaining A-owned enforcement gap is named precisely rather than treated as B
producer completion or silently implemented in the vision subsystem.
