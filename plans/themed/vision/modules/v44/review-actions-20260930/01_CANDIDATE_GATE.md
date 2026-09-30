# 01 — Close the current candidate gate without duplicating qualification

> Supporting V44 case study from the first planning pass. The [velocity roadmap](README.md) and [cause assessment](00_ROOT_CAUSES.md) supersede its priority and current-status assumptions. Reconcile historical candidate, ownership and policy notes before execution; this document is not a live assignment.

Priority: immediate V44 prerequisite. Owner: existing V acceptance lead; Sol owns the saved-evidence correction diagnosis after Sepia031's terminal handback. Heavy qualification waits for M's explicit return. Review coverage: §1, §2 combined candidate, §7.1, amended by the later checkpoint.

## Current state and target

At the inspected baseline, `1d683cf8` already contains the military read-only admission correction, Bank loading-frame settling and Watchtower native/publisher work. The inventory/publisher omissions are already corrected. [E8](README.md#evidence-index) supersedes the report's pending-test status: source0047 passes, holdout0050 has four failures across unit/publisher checks, and the affected gate was not run. The raw full crop scores .8064 against a .90 gate; a masked diagnostic scores .9887 with projection error 11.23, already inside the 12-pixel gate. The worker's claim that no common reference can qualify both views is disputed by the saved geometry review. Neither diagnostic masking nor a projected midpoint is production acceptance.

Deliver a single accepted offline record for the actual finished candidate, then a bounded release of only the next required live cases. This package does not itself complete V44 or qualify Watchtower/Bank routes.

## Relevant owners

- `pnc_automation/app/pnc/vision/home_city_camera/catalog.py`, `localization.py`, `targets.py`: native body evidence and shared matcher ownership.
- `pnc_automation/app/pnc/navigation/home_city_scan.py` and `app/automation/engine/navigation_core.py`: normalization, bounded acquisition and route admission.
- `tests/unit/app/pnc/vision/home_city_camera/test_home_city_slot_bodies.py`: fixture inventory and body qualification.
- `tests/integration/vision/home_city_camera/test_home_city_slot_body_publishers.py`: both real observation publishers.
- Existing ignored gate result/selection artifacts and coordinator independent-review records are the evidence owners; do not create a second runner.

## Deliverables

1. **Reconcile terminal evidence and active ownership.** Read Sepia031 probe/logs and the current Sol handback before launching anything. Record candidate/import root, tree state, result hashes and the four named holdout failures. Source inventory checks passed; avoid redoing their repair. Confirm the current owner has returned its writers before editing and reacquire heavy capacity only when needed.
2. **Qualify the smallest saved-evidence hypothesis.** The existing proposal crops uncontaminated stone shaft from original template rows80:200/columns15:100, with a candidate shared reference near `(1047,577,85,120)` and re-expressed action geometry. Independently check this derivation, then change only Watchtower template/catalog/fixture expectations and owning tests. Measure both native views through the actual unchanged matcher, including erasure/rival negatives, both publishers and safe action bounds. Keep score .90 and projection12 unchanged. If either view fails or a rival is admitted, inspect that result and seek the missing independent view; do not present the proposal as proof of arbitrary zoom/session robustness. Shared matcher changes return to the perception owner.
3. **Bind qualification to the finished tree.** Reuse the worker's passing focused/both-publisher evidence when it covers that tree. If missing, run the owning camera groups and affected consumers once. For unchanged production plus a genuine test-only fix, record precisely which original proof remains applicable and which delta was rerun; do not silently substitute an old SHA.
4. **Complete one final affected gate.** Reuse an already passing exact-candidate gate. Otherwise, under the heavy allocation, run the command below and retain selection/results. Any full fallback is the required gate under current rules; [09](09_FIXTURE_DEPENDENCY_OWNERSHIP.md) must not be inserted to shrink it mid-acceptance.
5. **Release or hold the next cases.** Independent review either names the actual defect/next owner, or freezes the candidate and releases a reviewed discovery batch. Include Bank safe acquisition and Watchtower passive body readiness; menu capture requires 02's additional prepared boundary. Preserve Market027, Alliance Hall028 and Campaign030 proof where changes do not affect those paths.

```powershell
py -3.13 tools/run_tests.py group unit.app.pnc.vision.home_city_camera
py -3.13 tools/run_tests.py group integration.vision.home_city_camera
py -3.13 tools/run_tests.py affected --base origin/main --explain --json .test-impact/v44-gate-selection.json --results .test-impact/v44-gate-results.json
```

The focused commands are alternatives for missing development evidence, not mandatory repeats of the worker's passing work. Record resolved base SHA alongside the command.

## Acceptance and remaining live boundary

- [ ] Watchtower source/holdout results contain measured ID, slot4, frame provenance and action geometry, including both production publishers where wiring changed.
- [ ] Finished-candidate gate has no unresolved failures; skips are explained; source and evidence bindings are independently checked.
- [ ] Batch references the exact released candidate/helper and includes only selected cases, config root, input limits and cleanup owner.
- [ ] Bank normalization is exercised by one real `locate_building(BANK)` on that candidate. The recorded black-frame sequence is proved deterministically; do not deliberately reproduce it live.

If the live case cannot acquire a safe fresh body, its route stays pending with the actual stopping boundary. Source review, passive body matching and a passing offline gate do not count as menu/panel/return proof. Publication is the owning coordinator's later action under its existing authority, not authorized by this document.
