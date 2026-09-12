# Non-YOLO integration review — 2026-09-12

## Verdict

No new actionable code findings remain in the reviewed integration at `6f3f732207dcdc98c55f2482114e0d0e371cf085`. This is an offline-validated feature-branch improvement, not confirmation that the entire recognition plan or its live promotion gates are complete.

The feature was pushed as a fast-forward from published `5c4ce6b` to `6f3f732`. It includes mainline through `c7dfdd5` via merge commits `e6df3bb` and `8697789`, preserving both histories. Review covered the integration's canonical model/import ownership, capture and input provenance, global interruption guards, shared OCR context, appearance versus layout identity, asset/hash migration, task recognition requirements, test migration, and scoped runtime cleanup.

## Corrections verified

- Multiple compatible Home appearance profiles previously produced conflicting layout IDs. Catalog v3 supplies an explicit shared layout identity; screenshot regressions prove Home remains actionable, and competing layouts still abstain.
- New mainline mail/Chat fixtures used PNG-byte hashes while the feature's manifest contract uses dimension-prefixed decoded RGB. All 35 manifest entries and 29 profile sources now use the canonical hash, with metadata tests linking source and manifest evidence.
- The bounded live probe now validates the smoke-test role, reserves its account before runtime construction, and releases the connected bundle and reservation on failure or success. Mainline quiescent shutdown remains the lifecycle owner; frame provenance remains the input owner.
- Canonical modular test owners retain the feature regressions and mainline workflow coverage. The seven obsolete monoliths are removed; mainline shutdown tests are included in the portable inventory.

## Validation

All paths below are relative to `C:/Users/lebel/pnc/artifacts/worktrees/non-yolo-integration-current`.

| Command/check | Result |
| --- | --- |
| `py -u tools/run_tests.py full` | Passed: 1,642 tests, 5 skips. `.local-data/reports/non_yolo_integration/full_final.log` |
| `py -3 -m unittest tests.unit.bluestacks_management.test_instance_shutdown` | Passed: 8 tests. This newly relocated module was verified separately because the full run selected its inventory before the rename |
| Visual catalog/layout regression modules | Passed: 16 tests; `artifacts/non_yolo_recognition/integration_20260912/layout_variants.log` |
| Emulator, frame provenance, live-probe lifecycle modules | Passed: 62 tests; `artifacts/non_yolo_recognition/integration_20260912/shutdown_provenance.log` |
| `py tools/benchmark_screen_recognition.py --coverage-audit --root . --output artifacts/non_yolo_recognition/integration_20260912/coverage_audit.json` (worker used the equivalent absolute root) | Passed on the tracked manifest/catalog after hash migration |
| Compile checks and `git diff --check` | Passed |
| Python 3.13 wheel build without build isolation | Failed: host lacks `setuptools.build_meta`; no dependencies installed |
| Bundled-runtime wheel build and isolated Python 3.13 loading | Passed: catalog v3, 29 profiles, 95 declared anchor images, zero missing assets, required Gift Center template present |
| `py artifacts/non_yolo_recognition/integration_20260912/check_readiness.py` | Blocked: `GameLaunchError`, before game navigation |
| Same readiness command with `--capture-only` | Blocked: `DeviceConnectionError`, before screenshot capture |

The initial full attempts exposed migration errors and were not accepted as passing validation. Their logs remain alongside the targeted evidence. The final suite's expected mocked host-management error output is test coverage, not a live restart.

## Remaining acceptance limits

1. **Live proof is still required before promotion.** Neither current active-castle verification nor final Home was observed in this continuation. No castle switch, resource action, or game-navigation input occurred. After Android/PNC readiness is restored, run the bounded `artifacts/non_yolo_recognition/integration_20260912/run_core_probe.py`, then the documented selector canary, preserving the configured testing role and scoped reservation.
2. **The full plan remains incomplete.** Research, Gathering/March and Campaign producer evidence remains missing. The audit records 56 unsupported selectors, 59 orphan enum IDs, and 83 guarded full-frame families out of 90. They are not promoted by these passing tests or the packaged assets.
3. **Main advanced during validation.** `origin/main` reached `b0ba590` after the included `c7dfdd5` baseline, adding roster and authored-Chat dispatch changes. Per the user's request to push first and then review, those newer commits were not folded into this publication. A read-only `git merge-tree --write-tree HEAD origin/main` preview was clean at review time, but that is not runtime validation of the combination. Reconcile task recognition requirements, typed dispatch and outer cleanup propagation and rerun the affected/full checks before merging the feature into that newer main. Preview: `.local-data/reports/non_yolo_integration/latest_main_merge_preview.txt`.

The original feature worktree and unrelated main-worktree changes were preserved. Generated local build metadata is not part of the feature publication.

## 2026-09-12 Institute increment and latest-main synchronization

Reviewed increment `0cd24ad` and integration with `origin/main` at `328e000`. The new Institute controls use the existing visual catalog, bounded matches and existing selector IDs; no alternative recognizer, OCR backend, or coordinate fallback was added. The Research Queue ownership fix requires independent visual screen identity and a measured dismiss control, preserves the generic OCR-only fallback, and continues other interruption checks. Queue registrations now reach the canonical action executor with frame provenance. Regression coverage includes missing/wrong controls, blocking update ownership, missing visual/dismiss proof, supported registry entries, and actual fake-session dispatch.

The source merge retains both strict focused-window parsing from main and frame identity/replay protection from the feature. Typed readiness replaces the retired legacy task. Its tests must preserve passive unknown handling and the feature's refusal to dispatch unsupported Research Start. No source conflict was resolved by dropping an entire changeset.

Live proof for the increment passed with active-castle verification, Institute entry, all four category matches and final Home; 10 non-spending navigation inputs. The newly merged readiness/foreground path separately passed with zero inputs and final Home at `artifacts/2026-09-12/testing/20260912T162132Z_core_20260912T162122Z_b8b372be_0003_final_home.png`. The pre-existing testing instance was preserved.

Residual plan gaps: five other reviewed navigation selectors remain unregistered (More Rank, Settings Rank, Settings Preferences, Settings Notifications, World HUD Toggle). These pre-existing routes need their own registration/dispatch and live proof before broad navigation promotion. No category transition, Research Tree row, Research Start, or resource-changing workflow was validated by this increment. Build/locale generalization remains unqualified.

Integration through main `328e000`: full portable suite passed 1,709 tests with five skips (`.local-data/reports/non_yolo_resume_20260912/full_latest_main_merge.log`); 51 core/session/queue, eight bootstrap/unknown-root, four loading and two end-to-end tests passed. Whitespace check passed.
