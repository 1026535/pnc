# 08 — Make each route assignment and handback complete for acceptance

> Supporting handoff requirements. [Plan C](15_LIVE_DISCOVERY_AND_VALIDATION.md) and [Plan D](11_COVERAGE_AND_CURRENT_STATE.md) turn repeated manual checks into shared case/result tooling; do not create another independently maintained checklist.

Priority: apply to the next batch. Owners: coordinator owns brief/review; assigned worker owns its curated evidence. Review coverage: §4B; §5 complete route packages and executable handoffs; §7 review/release.

## Concrete failures to prevent

[E2/E4](README.md#evidence-index) identify three observed defects: Watchtower was omitted from an exact fixture-inventory assertion and lacked both real publisher coverage; live030 inherited unselected case metadata and wrong counts; an isolated-worktree preflight omitted the primary config path. Fix those boundaries without adding another workflow framework or a broad metadata test matrix.

## Assignment contract

Extend the existing [QA batch format](../../../../../../.agents/skills/test-bluestacks-live/references/live-test-batch.md) and [Devin handoff guidance](../../../../../../.agents/skills/devin-implement/references/handoff.md) only where fields are missing. Reconcile the separately owned [E8 policy update](README.md#evidence-index) before editing those shared instructions; do not revive an old no-collection/zero-spend default. Keep existing `evidence.json` and native receipt/artifact formats canonical.

Each route package must name exact target keys and caller symbols, body/holdout, any menu, destination, return, source/fixture paths, relevant test owners, candidate/import root, required live cases, held cases with reasons, and acceptance owner. V44 owns acquisition; the named feature owner owns its content/actions/returns. One integration writer serializes shared catalog entries. Prefer one coherent body→menu→endpoint→return package over a sequence of tiny assignments when its evidence is ready.

## Preparation and implementation steps

1. **Use one selected-case list.** Build dispatch order, per-case manifest rows and result summaries from that list in the current helper. Retained historical proof belongs in a separate provenance section, never in current execution counts. Planned-but-held cases remain explicitly held outside the selected execution set. Selected cases that do not run must still return `not_run` with the stopping dependency; the QA ledger maps required proof to pending.
2. **Make config/import binding explicit before live use.** The brief carries exact candidate, source/import root, primary `C:/Users/lebel/pnc/config/accounts.yaml` location, report repository root, accepted offline record and frozen helper hashes. Resolve existence/configuration before ADB. Do not copy sensitive local config into a worktree or print its contents. Include the exact reviewed entry command only once the helper exists and its routing is verified offline.
3. **Catch fixture completeness before the final gate.** The fixture author updates native file, manifest, required exact inventory, template crop provenance and real publisher assertions in the same source package. For Watchtower, these edits already exist; verify the handback rather than adding them again. Use the owning fixture and publisher groups, not a separate global fixture linter unless existing validation genuinely cannot cover an observed defect.
4. **Derive actual action counts from canonical receipts.** Report attempted, confirmed and uncertain inputs separately, by tap/swipe/wheel detent and case. Count actual post-jitter primitives; keep logical `locate/open` operations separate from physical receipts and helper pre-locate counters. Include setup/recovery inputs. Case totals must reconcile with batch totals and cumulative caps. Historical live030's 23 confirmed inputs including six outward detents are a useful regression fixture for accounting only.
5. **Return the curated evidence package.** Each selected case includes precondition, actual invoked boundary, outcome, source/menu/endpoint/return native frames as applicable, confirmed receipts, candidate binding, unresolved findings and next trigger. Include incidents, final screen, warm-instance preservation, task/reservation release and writer/process termination. No reservation contents or secrets. Return compact command/results references instead of the full transcript.
6. **Review at the package boundary.** Coordinator checks candidate/artifact hashes, result/count consistency and representative native evidence; inspect deeper trace only for a discrepancy or acceptance-critical uncertainty. Return concrete findings to the same owner, then resume the next ready package after cleanup. Worker completion is not coordinator acceptance.

## Verification proportional to the change

If only brief/skill prose changes, validate links and `git diff --check`. If helper selection/accounting changes, use its existing offline fake harness to prove: no unselected case enters dispatch/results; selected-but-not-run remains explicit; actual counts include detents/setup/recovery; missing config/candidate/hash fails before connection; uncertain input stops dependent dispatch. Do not rerun frozen passing helper checks on unchanged code.

Use the existing fixture inventory and both-publisher regression for the changed native asset; do not add a wording test for handoff instructions. A production change still needs its ordinary affected gate and applicable live proof. Preparation fakes do not accept the live route.

## Done and handoff example

The next assignment can be reviewed without reconstructing inherited metadata: the selected set matches the returned set, candidate/import binding is explicit, counts reconcile, native proof is curated, every interruption is linked and cleanup is terminal. A concise handoff begins:

```text
Candidate / import root / helper manifest: exact values and links
Selected: B-ACQ, W-DISCOVERY, HOW-BODY
Passed / failed / not_run: one disposition per selected case
Physical receipts: attempted / confirmed / uncertain, by primitive and case
Proof: native boundaries + offline commands/results
Remaining: named gap, owner, next trigger
Cleanup: actual final screen; leases/reservation/writers; warm-instance state
```

These are illustrative case names, not a released assignment. Keep the actual next selected set and input ceilings in the QA batch.
