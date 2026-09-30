# B — Reduce validation cost through real ownership and test boundaries

Priority: first bounded velocity improvement, with lightweight preparation now and heavy validation scheduled through the shared owner. Do not change a frozen V acceptance candidate mid-run. Owner: existing test-selection/runtime owner, with vision owners validating consumers. Review coverage: §4C, §5 fixture ownership, §6 measures, expanded to the deeper testing architecture identified in 00.

## Broader objective and evidence

The earlier plan fixed one selection rule; that is only one cause. [Static analysis](00_ROOT_CAUSES.md#static-selection-evidence) at a3 shows 410 selected modules for a Home fixture, 225 for a packaged camera image, and 292 for a camera implementation path. The latter two would survive removal of the fixture full rule. The saved e11 gate spent 1,949.409 s in execution and 2.094 s in selection. Prioritize reducing unnecessary selected/executed work, not accelerating selection calculation or renaming a full run “affected.”

There are three deliverables: (B1) explicit fixture and packaged-asset ownership; (B2) move pure assertions to their actual producer and retain meaningful composition checks; (B3) narrow proof invalidation across iterations. Architecture changes that remove real import coupling belong to 14; the selector must continue to expose genuine consumers.

## Source-proven diagnosis

The e11 record [E2](README.md#evidence-index) selected all 409 modules for 11 fixture/manifest paths. `tests/selection_rules.yaml` lists `tests/data/*` under `full`. `tools/test_selection/planner.py:affected_plan` checks full patterns first and returns before resource selection when any fallback exists. `fnmatchcase` makes this pattern cover nested paths. A new `resources` rule alone cannot override it.

`tools/test_selection/ownership.py` already supplies validated additive resource groups; no new selector engine or coverage-measurement service is required. Existing source ownership, static declaration/import consumers, architecture checks and four CI shards must be preserved. This is a follow-up to [the existing test-runtime slices](../../../../testing/PNC_CI_RUNTIME_INDEPENDENT_SLICES.md), not a restart of that work.

## Smallest target design

Start with `tests/data/home_city_slot_bodies/`, whose direct consumers can be inspected. Map that owned subtree to its verified enclosing test groups using the existing rule schema. Remove the blanket `tests/data/*` full entry only when the unchanged **unknown non-Python dependency** fallback demonstrably preserves full selection for every unowned fixture. Keep explicit full entries for shared schemas/manifests and other cross-cutting resources. Do not reverse full/resource precedence globally.

Keep `tests/data/screen_recognition/manifest.json` and `replacement_core_provenance.json` conservative until their cross-feature readers are mapped. Narrowing Home fixtures alone will not shrink an e11-shaped combined diff that still touches shared files; report that limit. Include packaged `pnc_automation/app/pnc/vision/data/home_city_camera/*` in the same explicit consumer audit. Current resource rules are additive: adding a narrow pattern while retaining a matching broad `vision/data/*` rule will still select its broad groups. Replace only the audited ownership portion, explicitly retain unknown/shared fallback and preserve all remaining data owners. No global “narrowest pattern wins” rule.

## B1 — Resource ownership deliverables

The [coordinator review](../V44_QUALITY_REVIEW_AND_SEQUENCE.md) splits this into screenshot ownership first and a separate packaged-asset closure. The latter has verified consumers in `unit.app.pnc.navigation` and `integration.workflows`, in addition to camera groups: catalog loading opens every crop, including for callers requesting another target. Preserve these consumers and complete the closure audit before replacing the broad resource rule. Update synthetic group inventories in selector tests when adding real groups.

1. **Baseline from saved results.** Read e11 selection/results/log artifacts via its `source_records`, verify bindings, record changed paths, all fallback reasons, complete inventory and available module runtimes. Keep measured wall time separate from summed test durations. Do not run `measure` to rediscover why selection was broad.
2. **Create the consumer map.** Enumerate literal paths, manifest enumeration, shared fixture helpers and indirect users. Initial observed consumers include camera unit `test_home_city_slot_bodies`, `test_home_city_military_bodies`, `test_home_city_configurable_bodies`, `test_market_body`, `test_endpoint_first`, and integration `test_targets` / `test_home_city_slot_body_publishers`. Trace `tests/support/pnc/home_city_camera/fixtures.py` imports too. Record rationale for the full enclosing groups; never rely solely on filename search or coverage contexts for non-Python resources.
3. **Change rules through existing interfaces.** Prefer existing groups `unit.app.pnc.vision.home_city_camera` and `integration.vision.home_city_camera`, adding every verified outside consumer's enclosing group. Preserve fixture-integrity tests that enumerate the whole subtree even for a one-file change. Use additive owners where two features consume a resource. If mapping remains uncertain, keep that resource full. Avoid a new schema solely to select one test method.
4. **Prove selection on representative deltas.** Extend `tests/unit/test_selection/test_planner.py`, `test_ownership.py`, `test_scoped_ownership.py` and `test_fault_recall.py` as appropriate. Cover an owned PNG change, owned manifest addition/removal, unknown PNG, shared manifest, mixed owned-plus-unknown diff and directly changed tests. Preserve architecture and declaration/import consumers in mixed source/fixture changes. Test outcomes/selected consumers rather than exact explanation wording.
5. **Demonstrate benefit and retained failure detection.** Compare old/new plans for the same fixture-only change set using the existing planner test harness. Introduce a controlled bad fixture or manifest reference in an isolated test sandbox and show an independently identified owning test is still selected and fails. Preserve native assertions; do not remove tests to manufacture the speedup. Report selected-module count reduction and estimated historical runtime as an estimate only.
6. **Integrate as a separate infrastructure candidate.** Update `tests/README.md` with the specific ownership rule and limits. Run focused selector/harness groups, then one final affected gate. Rule/planner changes legitimately select full; retain that integration gate. Reuse compatible passing full-fallback proof instead of a second local full run.

```powershell
py -3.13 tools/run_tests.py group unit.test_selection
py -3.13 tools/run_tests.py group test_harness
py -3.13 tools/run_tests.py affected --base origin/main --explain --json .test-impact/fixture-owners-selection.json --results .test-impact/fixture-owners-results.json
```

The historical e11 full fallback has `mode: affected`; `tools/audit_test_selection.py` requires independent same-source results with `mode: full` or `measure`. Do not relabel e11 artifacts to satisfy that tool. Use them for baseline/timing analysis; use controlled recall checks for this change. An additional independent full audit is warranted only if a material ownership uncertainty remains, with its own explicit scope and capacity allocation.

## B2 — Test the smallest meaningful boundary

Use the saved module timings, not a new full measurement. Start with the actual high-cost Home cohort (`test_targets`, `test_home_city_slot_bodies`, `test_home_city_slot_body_publishers`, `test_zoom_view`) and compare each test's contract, native fixture, setup, publisher and unique assertion. The existence of two expensive tests using one frame is not enough to call them duplicates.

1. Keep image identity/score, projection geometry, ambiguity and erasure negatives on the canonical localizer/producer with the necessary native source and holdout. Use deterministic focused inputs for pure slot/math/policy tests. Do not replace a native rendering regression with a self-generated crop that merely restates implementation.
2. Keep real both-publisher cases for shared wiring, fresh provenance, guards and representative changed fields. Do not force every geometry parameter/negative through both full publishers. Reuse `make_publication_pair`; 14 may remove duplicate common publication wiring while preserving different publisher policies.
3. Replace the separately maintained exact fixture-name list with a manifest-to-files inventory invariant plus explicit required contract/case references. The existing tests validate hashes/masks/provenance; retain those. A manifest cannot validate its own semantic truth: expected identity/slot/action assertions remain independently authored. A new valid fixture should not require a second unrelated filename-list edit merely to pass inventory.
4. Consolidate a test only with a short old→new assertion ledger proving the same meaningful boundary. Cache only immutable template/setup already allowed by the runtime; never cache observations, mutable OCR results or frame identity. Existing feature-package splits and immutable template caching are already implemented and are not new deliverables.

**Acceptance:** every removed expensive replay has a named surviving contract; the saved target cohort has fewer redundant full-composition executions; identical native/negative outcomes are preserved. Compare normal uninstrumented cohort runtime under compatible conditions only when running its necessary checks. Report noise/sample limitations; test-count reduction alone is not the goal.

## B3 — Separate development proof from final integration proof

During a coherent edit batch run focused owning checks that can disprove the change, then one final affected gate. Do not run a full gate after every helper/fixture annotation or before every missing-menu discovery. A passing full fallback is already the broad gate; do not follow it with local `full` or routine `measure`. Preserve CI's existing four shards and static selection.

Use 11's result model to retain passing proof by candidate, actual changed production/assets/contracts and case ownership. A test-only expectation fix may require its test/consumer delta while unchanged production proof is retained with a documented rationale; a shared action/provenance change may invalidate several cases. No permission to assert that arbitrary code changes are safe merely because tests previously passed. Unknown ownership stays conservative.

**Acceptance:** the next correction package names only truly invalidated proof and runs it, while the final coherent candidate still satisfies its complete gate. Measure avoided duplicate runs from existing timestamps; do not add a new global incremental-test cache.

## Acceptance and limits

- [ ] Owned fixture-only deltas select all demonstrated readers and fewer modules than the old full rule.
- [ ] Unknown/shared resources and mixed unknown changes still trigger full fallback; production static consumer safeguards remain.
- [ ] Deliberate fixture failure is caught by a selected reader; relevant native/publisher tests remain intact.
- [ ] Final infrastructure gate passes and the report distinguishes selection savings from observed runtime savings.

No live test is needed for test selection or test-only boundary refactoring with equivalent assertions. If production behavior changes, 14/15 define the affected live proof. Do not alter the already running V gate or remove local files to manipulate selection. Split a remaining global manifest only after consumer evidence shows a real feature boundary and selection benefit; this can be a later B1 slice, not a prerequisite for the first owned-fixture improvement.
