# Puzzles & Conquest Multi-Castle Routine Targeting Sub-Plan

## 1. Purpose

This document defines the proposed extension for running one authored routine body against multiple account-scoped `castle_ref` aliases without duplicating the routine definition.

It is intentionally separate from:

- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan,
- [PNC_RUNTIME_CASTLE_TARGETING_SUBPLAN.md](/c:/Users/lebel/pnc/reviewed_plans/PNC_RUNTIME_CASTLE_TARGETING_SUBPLAN.md), which owns the current single-target runtime castle contract,
- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns feature-task planning,
- [scripts/README.md](/c:/Users/lebel/pnc/scripts/README.md), which owns the public authored-script guidance.

This file owns one future extension:

- allow one routine to apply the same nested workflow to multiple authored `castle_ref` aliases,
- keep the runtime task contract single-target and concrete,
- avoid duplicating castle-target lists across many task steps,
- preserve one canonical implementation of castle-target resolution and castle switching.

## 2. Current context

The current design already has a strong single-target model:

- each run is launched for one selected account,
- each script step may declare one optional `castle_ref`,
- `castle_ref` is resolved against the selected account's aliases in `config/castle_targets.yaml`,
- tasks continue to execute against one concrete castle target at a time,
- the runner already knows how to align one explicit target castle before running one optional-target task.

This is a good baseline and should remain the canonical execution contract.

However, the current authored-script shape becomes repetitive when the same routine body must run for more than one target castle in the same account.

## 3. Problem statement

Today, if one maintenance workflow should run for several castles, the author must choose between two bad options:

- duplicate the same routine body in multiple routine files, or
- duplicate the same sequence of task steps in one file while changing only `castle_ref`.

That is undesirable because:

- it duplicates the same operational logic,
- it makes later maintenance error-prone,
- it obscures the real intent, which is "repeat this workflow for these targets",
- it encourages script-local duplication instead of one canonical expression of repetition.

## 4. Goals

The future extension must achieve all of the following:

1. Keep one canonical execution model per task step: one prepared step targets one concrete castle or no castle.
2. Allow one authored routine block to run against multiple account-scoped `castle_ref` aliases.
3. Avoid repeating the same castle-target list on every task step.
4. Preserve the existing single-`castle_ref` step schema for simple routines.
5. Resolve aliases and validate them centrally.
6. Fail fast on malformed authored structures, empty target lists, and unknown aliases.
7. Keep the runtime runner and concrete tasks as unchanged as possible.
8. Make the authored semantics obvious and low-noise for routine authors.

## 5. Non-goals

This extension should not:

- add a second castle-targeting mechanism parallel to `castle_ref`,
- teach every individual task to accept a list of castles,
- create CLI list overrides for castles in the first slice,
- add an in-process scheduler or change routine scheduling boundaries,
- weaken fail-fast validation by silently skipping unknown aliases,
- broaden the runtime to execute multi-target tasks directly.

## 6. Core architectural decision

Multi-castle support should be modeled as script expansion, not as task behavior.

The canonical rule should be:

1. Authored scripts may contain one repeat-style block that declares multiple `castle_refs`.
2. That block contains nested ordinary task steps.
3. During script preparation, the block is expanded into ordinary prepared steps, one castle at a time.
4. After expansion, the runtime runner only sees the same concrete prepared task steps it already supports today.

This keeps one canonical runtime path:

- tasks still receive one explicit target castle or none,
- castle switching still happens through the existing single-target alignment flow,
- alias resolution still happens centrally during preparation,
- the runner does not need a second loop concept for multi-target authoring.

## 7. Recommended authored shape

The recommended future authored shape is a block-level repeat, not per-step `castle_refs`.

Target direction:

```yaml
name: daily_castle_maintenance

steps:
  - task: ensure_game_running
  - task: login
  - castle_refs: [main, farm, bank]
    steps:
      - task: building_upgrade
        params:
          priority: [castle, wall, institute, infantry_barracks]
          allow_speedups: false
      - task: research
        params:
          priority: [economy, development, military]
      - task: gathering
        params:
          preferred_resources: [food, wood, iron]
          max_parallel_marches: 2
```

Recommended semantics:

1. Resolve `main`, then run the nested block for `main`.
2. Resolve `farm`, then run the nested block for `farm`.
3. Resolve `bank`, then run the nested block for `bank`.

This order is preferred because it matches operational intent:

- finish all desired work for one castle,
- then move to the next castle,
- avoid interleaving castles step by step.

## 8. Why not per-step `castle_refs`

The tempting alternative is a shape like:

```yaml
- task: building_upgrade
  castle_refs: [main, farm]
```

This should be rejected as the primary design because it creates avoidable problems:

- the same target list would need to be repeated on every castle-bound step,
- scripts become noisy and harder to maintain,
- behavior ordering becomes less obvious once many steps use many lists,
- the concept being modeled is not "this step has many targets" but "this workflow repeats for many targets".

The repeat block is the more natural owner.

## 9. Proposed domain-model direction

The existing model has one `ScriptStep` and one `PreparedScriptStep`.

The likely clean extension is to represent authored script nodes as two distinct concepts:

- one task step node,
- one multi-castle repeat block node.

The preparation layer should then flatten authored nodes into one canonical `PreparedRunScript` containing only ordinary prepared task steps.

That avoids burdening the runtime with knowledge of authored nested structure.

## 10. YAML loading and validation requirements

The loader should eventually support both:

- the current ordinary step shape with optional `castle_ref`,
- the future repeat-block shape with `castle_refs` plus nested `steps`.

Required fail-fast validation:

- reject a node that mixes `task` with `castle_refs`,
- reject a node that mixes `params` with a repeat block,
- reject an empty `castle_refs` list,
- reject repeat blocks whose nested `steps` list is empty,
- reject nested inline `castle` definitions if the script contract still forbids them,
- reject unknown task ids inside nested blocks with accurate step context,
- reject malformed `castle_refs` entries that are not strings.

## 11. Script-preparation requirements

The preparation layer should own all multi-castle expansion behavior.

Required behavior:

1. Resolve each authored alias against the selected account's `castle_targets`.
2. Preserve authored order of aliases.
3. Preserve authored order of nested steps within each alias expansion.
4. Produce ordinary prepared steps that already contain one resolved concrete castle target.
5. Preserve existing validation rules for tasks that disallow, require, or optionally accept a castle target.

This is the most important DRY boundary in the design.

## 12. Runtime behavior requirements

The runtime should ideally not gain any awareness of multi-castle authored syntax.

After preparation:

- the runner should execute a flat prepared-step list,
- the runner should continue to auto-align one explicit target castle before optional-target tasks,
- concrete tasks should continue consuming one target castle through the existing context contract,
- logs and results should continue reporting one requested castle per executed step.

If the runner can remain unchanged, that is the preferred outcome.

## 13. Documentation requirements

When this extension is implemented, update:

- [scripts/README.md](/c:/Users/lebel/pnc/scripts/README.md),
- one example routine under [scripts/routines/](/c:/Users/lebel/pnc/scripts/routines),
- any relevant planning docs that still imply one routine must be authored separately per castle target.

Documentation should emphasize:

- `castle_ref` remains valid for simple one-target steps,
- repeat blocks are for shared workflows that should run across multiple castle aliases,
- aliases remain account-scoped through `config/castle_targets.yaml`.

## 14. Validation plan

Required automated coverage should include:

- loader accepts a valid multi-castle repeat block,
- loader rejects malformed repeat blocks,
- preparation expands one block into the correct ordered concrete steps,
- unknown alias resolution fails fast,
- task target-policy validation still works after expansion,
- existing single-`castle_ref` scripts still load and prepare unchanged.

Primary test targets:

- [tests/test_script_loader.py](/c:/Users/lebel/pnc/tests/test_script_loader.py)
- [tests/test_runtime_castle_targeting.py](/c:/Users/lebel/pnc/tests/test_runtime_castle_targeting.py)

Live validation should include one real routine run against an account that defines at least two castle aliases and verify:

- the first castle is selected and processed fully,
- the second castle is selected and processed fully,
- the steps do not interleave unexpectedly,
- failure artifacts still identify the concrete castle being processed when a step fails.

## 15. Incremental implementation sequence

Recommended future implementation order:

1. Finalize the authored repeat-block schema.
2. Extend the script-domain model to represent repeat blocks explicitly.
3. Extend YAML loading and fail-fast validation.
4. Implement repeat-block expansion during script preparation.
5. Add loader and preparation tests before any runtime changes.
6. Confirm whether the runner can remain unchanged; only modify it if a hard requirement appears.
7. Add docs and one example routine.
8. Validate the feature live with a bounded multi-castle routine.

## 16. Alternatives rejected

### 16.1 Duplicate one routine file per castle target

Rejected because it duplicates behavior and makes routine maintenance drift-prone.

### 16.2 Add `castle_refs` to every ordinary task step

Rejected because it duplicates target lists, creates noisy YAML, and models repetition at the wrong ownership boundary.

### 16.3 Add CLI support to pass a list of castle aliases

Rejected for the first slice because it creates another targeting surface before the authored routine contract is cleanly solved.

### 16.4 Teach the runtime runner to interpret nested loops directly

Rejected unless proven necessary, because script preparation is the cleaner place to flatten authored structure into the canonical step contract.

## 17. Near-term recommendation

Do not implement this extension until the current one-routine, one-account, one-target flow is proven reliable.

The recommended immediate priority remains:

- make one routine work well end to end,
- keep one `castle_ref` per relevant step,
- schedule one routine invocation per account,
- return to this plan once the single-target workflow is stable enough that the repetition pain is concrete rather than hypothetical.

## 18. Definition of done

This extension is done only when all of the following are true:

- one routine can author one maintenance block and apply it to multiple account-scoped castle aliases,
- alias resolution still has exactly one canonical implementation,
- concrete tasks still execute with one target castle at a time,
- the runner does not contain duplicated multi-target logic,
- malformed repeat blocks fail fast with clear validation errors,
- existing one-target scripts still work unchanged,
- documentation includes one canonical example of the new pattern,
- obsolete alternative authoring guidance has been removed.

