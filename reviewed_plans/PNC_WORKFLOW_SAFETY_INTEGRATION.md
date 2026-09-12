# Workflow safety integration

## Provenance

This bounded transfer follows `reviewed_plans/audit_followups_2026_09_12/01_workflow_safety.md` from the audit handoff in `C:/Users/lebel/.codex/worktrees/a032/pnc`. The source implementation diff was inspected read-only and its changes were applied selectively against the current owners in this worktree.

## Integrated invariants

- `AutomationSession` rejects reentry before replacing its reservation or context token, and an implicit call through another `AutomationApi` is rejected before dispatch.
- Daily claim reconciliation commits only when the post-action row states are nonempty and recognized (`Go`, `Completed`, or `Requirement`).
- Daily mutation scans process each stable viewport once and retain unknown-title evidence from the final viewport.
- World-map corner snapping uses one helper that filters snapped coordinates after parity correction, keeping row-major, row, and column samples inside requested bounds.

Luna completed the selective transfer and consolidated self-review, then root formally reviewed the complete result with no actionable findings. The private feature `codex/workflow-port-safety-integration` was rebased from `39ce6fc` onto the independent Castle endpoint port at `87e6151295c77c9091dd43fc6164c902a197b794`. The source audit worktree was preserved; its files were not copied wholesale.

## Verification

Commands used `C:/Users/lebel/AppData/Local/Programs/Python/Python313/python.exe`.

- The four focused unittest modules passed: `tests.integration.entrypoints.test_automation_api_runner` (10), `tests.unit.app.automation.daily_maintenance.test_daily_claim_executor` (4), `tests.unit.app.automation.daily_maintenance.test_daily_maintenance_coordinator` (10), and `tests.unit.app.pnc.navigation.test_world_coordinate_domain` (5): 29 passed, no skips.
- `tools/run_tests.py full --json .test-impact/safety-integration-selection.json --results .test-impact/safety-integration-results.json` passed on rebased implementation `8b6cad316c48b6dfa9697675f9a7cda9ae6521e2`: 1,532 total, 1,527 passed and five optional local screenshot skips. Runtime was 162.915 seconds, 174.747 including selection and reporting. Source fingerprint: `63ff0efef6888d35714da71a6eabfa0bde4ce7184f97c052bf07633993e10256`.
- All five skips report an unavailable optional local screenshot: three Chat fixtures, one Home-city fixture, and one shifted-popup fixture. Contract and architecture tests ran.
- `git diff --check` passed.

Claim reconciliation and mutation-loop behavior are covered by deterministic tests. No live claim or resource-changing execution is authorized or claimed by this integration.

## Read-only live proof

Root ran `.local-data/artifacts/replacement_core/workflow_safety_live.py:run_workflow_safety_proof()` on the user-selected `serious_stuff` instance, validating its configured `live_testing` role. The existing exclusive process lease remained held across the whole implementation phase; the pre-existing instance was kept warm. This was a bounded investigation on the current castle, not a smoke-role substitution or a new castle selection.

The cross-API implicit call was rejected before dispatch. An implicit `POPUP_RECOVERY` call through the owning API then succeeded on Home, using trace `artifacts/2026-09-12/serious_stuff/20260912T171628Z_f7aae9e0_core_trace.jsonl`. Core World navigation and pure planning produced six addressable points within the two tested bounds, with zero movement actions. The existing read-only Daily survey completed eight viewport observations, retained 36 fingerprint-distinct row observations and two unknown titles, and returned Home. These are viewport observations, not a claim of 36 unique quests. This survey does not prove live mutation-loop execution or claim reconciliation; their changed behavior is covered offline.

Result: `.local-data/artifacts/replacement_core/workflow_safety_result.json`. The core trace is `artifacts/2026-09-12/serious_stuff/20260912T171645Z_02700cd9_core_trace.jsonl`. Root inspected the final Daily viewport `20260912T172134Z_daily_scroll_7_adjusted_settled.png` and final Home `20260912T172202Z_core_20260912T171645Z_02700cd9_0012_core_route_source.png` in the same directory. No message, claim, purchase, resource spend, or castle switch occurred. The unchanged shared Home/World selectors had already passed the narrow validator on the Castle base; they were not rerun for the pure coordinate-bound change.
