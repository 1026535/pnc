# Multi-Castle Ref Implementation Review

Reviewed commit: `b15d9b8a4e421100d4eee38b7d154411b0be63a6` (`implemented PNC_MULTI_CASTLE_REF_SUBPLAN.md`)

## Findings

### 1. High: malformed in-memory repeat blocks can crash with raw `AttributeError`

Files:
- `pnc_automation/app/authoring/scripts/models.py`
- `pnc_automation/app/authoring/scripts/registry.py`

Relevant lines:
- `pnc_automation/app/authoring/scripts/models.py:51-64`
- `pnc_automation/app/authoring/scripts/registry.py:138-149`

Problem:
- `CastleRefRepeatBlock` is now a public authored node type, but its model validation only checks for non-empty `castle_refs` and non-empty `steps`.
- If code constructs a repeat block programmatically with an invalid nested item, `prepare_script()` can crash with a raw `AttributeError` instead of a typed `ScriptValidationError`.
- Repro used during review:

```python
RunScript(
    name="x",
    path=Path("x.yaml"),
    steps=(CastleRefRepeatBlock(castle_refs=("main",), steps=(object(),)),),
)
```

With valid `castle_targets`, this currently fails inside `_prepare_repeat_block()` when it reads `nested_step.castle`.

Why this matters:
- The codebase already supports in-memory script construction for generated scripts.
- This violates the fail-fast typed-error contract and makes debugging much harder.
- It also means the public model is only safe when it comes from YAML, not when it comes from Python.

Clean fix:
- Strengthen `CastleRefRepeatBlock.__post_init__()` to validate:
  - every `castle_ref` is a non-empty `str`,
  - every nested item is a `ScriptStep`,
  - every nested step has no `castle` and no `castle_ref`.
- Keep the registry-side guard as a defensive backstop if desired, but the model should reject malformed construction first.
- Add a unit test that constructs an invalid repeat block in memory and asserts a typed validation failure instead of a raw attribute crash.

### 2. Medium: the script loader still accepts unsupported keys silently

Files:
- `pnc_automation/app/authoring/scripts/loader.py`

Relevant lines:
- `pnc_automation/app/authoring/scripts/loader.py:24-33`
- `pnc_automation/app/authoring/scripts/loader.py:49-73`
- `pnc_automation/app/authoring/scripts/loader.py:85-142`
- `pnc_automation/app/authoring/scripts/loader.py:168-202`

Problem:
- The new loader validates `task` vs `castle_refs`, but it still does not reject extra keys at the root, on ordinary task steps, or on repeat blocks.
- Example accepted today:

```yaml
name: bad
unexpected_root: true
steps:
  - task: login
    unexpected: true
```

- This loads successfully instead of failing.

Why this matters:
- The repo guidelines explicitly prefer fail-fast validation and avoiding stale/legacy parallel schema.
- The scheduled-mail loader already rejects unsupported keys, so script loading is now inconsistent with the stricter authoring surfaces elsewhere in the codebase.
- This is especially risky now that the step schema became richer. Typos like `castle_refs`, `param`, or stale block keys can silently be ignored.

Clean fix:
- Add one shared `_require_no_extra_keys(...)` helper for run scripts, matching the scheduled-mail loader pattern.
- Enforce allowed keys:
  - root: `name`, `steps`
  - ordinary step: `task`, `params`, `castle_ref`
  - repeat block: `castle_refs`, `steps`
- Keep the explicit legacy `castle` rejection, but treat every other unexpected key as invalid too.
- Add loader tests for:
  - unexpected root key,
  - unexpected ordinary-step key,
  - unexpected repeat-block key.

### 3. Medium: repeat-block preparation resolves the same castle alias multiple times and introduces a throwaway helper type

Files:
- `pnc_automation/app/authoring/scripts/registry.py`

Relevant lines:
- `pnc_automation/app/authoring/scripts/registry.py:130-164`
- `pnc_automation/app/authoring/scripts/registry.py:214-220`
- `pnc_automation/app/authoring/scripts/registry.py:223-256`

Problem:
- `_prepare_repeat_block()` first resolves each alias through `_resolve_step_castle(_RepeatBlockCastleRef(...))`.
- It then generates nested `ScriptStep`s with that same `castle_ref`.
- `_prepare_task_step()` immediately resolves the same alias again for every nested step.
- This duplicates the castle-resolution work and requires the synthetic `_RepeatBlockCastleRef` class only to pass through the existing helper.

Why this matters:
- It is not a correctness failure today, but it creates avoidable duplication in the exact area the plan wanted to keep canonical and simple.
- The current flow spreads one concept across:
  - `_prepare_repeat_block()`,
  - `_RepeatBlockCastleRef`,
  - `_resolve_step_castle()`,
  - `_prepare_task_step()`.

Clean fix:
- Resolve each `castle_ref` exactly once per repeat-block castle iteration.
- Reuse that resolved `CastleIdentity` for every nested prepared step in that iteration.
- Two clean options:
  - extend `_prepare_task_step()` with an optional pre-resolved castle argument, or
  - add a small helper that validates task policy and parses params using a provided `resolved_castle`.
- After that, delete `_RepeatBlockCastleRef`.
- Add one targeted test that verifies the refactor still preserves:
  - alias order,
  - nested step order,
  - `step_path` provenance,
  - concrete `resolved_castle` reporting.

## Recommended Fix Order

1. Fix finding 1 first because it is a real typed-error contract break.
2. Fix finding 2 next to restore fail-fast schema behavior before more scripts are authored.
3. Refactor finding 3 last once the validation contract is locked in.

## Validation Notes

Review validation performed:
- `py -m unittest tests.test_script_loader tests.test_runtime_castle_targeting`

Additional manual probes performed during review:
- confirmed malformed in-memory repeat blocks can raise raw `AttributeError`,
- confirmed unsupported root/step keys are currently accepted by `load_run_script()`.
