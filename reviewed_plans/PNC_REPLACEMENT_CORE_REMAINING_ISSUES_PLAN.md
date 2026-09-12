# Replacement core remaining-issues implementation plan

## Context

The read-only Daily Quest status workflow passed on the configured account carrying the `daily_canary` role and returned to Home City. At plan authoring time, two defects remained before this replacement-core slice could be considered merge-ready:

1. a visible blue Go button can be missed by full-screen OCR, leaving a row as `unknown_action`; and
2. the generic upper-right Close-X detector can mistake an animated Home City HUD sparkle for a blocking popup.

Both failures are preserved in the validation ledger and live artifacts. This plan fixes them in their canonical perception owners without weakening the replacement core's fail-closed navigation rules.

The implementation and role-selected validation rows are now complete: the current `daily_canary` and `smoke_test` accounts passed their bounded proofs on 2026-09-12. Historical failure artifacts remain in the ledger, including the Savannah recovery failure and the later deterministic semantic guard; the final live run did not reobserve Savannah.

## Goals

- Classify a visually clear Daily Quest Go button when full-screen OCR omits its text.
- Keep genuinely unclear Daily action states as `unknown_action`.
- Reject the observed Home City HUD sparkle as popup evidence.
- Continue recognizing real generic, OCR-backed, reconnect, update, VIP, and task-owned popups.
- Re-prove Daily status on the current `daily_canary` account and explicit recovery on the current `smoke_test` account, using each account's active castle without switching castles or spending resources.

## Non-goals

- Do not add quest-row clicks, claims, scrolling, or resource-changing behavior.
- Do not add automatic popup dismissal to `NavigationCore` or replay a failed navigation action.
- Do not special-case `Train Cavalry x250`, either role-selected account, or one screenshot filename in production code.
- Do not redesign the replacement runtime, workflow protocol, or Daily Quest catalog.
- Do not merge the feature branch as part of these fixes.

## Current state

### Daily Quest action state

`pnc_automation/app/pnc/vision/daily_quest_rows.py:_resolve_row_state` uses exact normalized OCR tokens: `CLAIM`, `GO`, `CLAIMED`, `COMPLETED`, or text containing `REQUIRED`. The row action point already comes from visual row geometry, so OCR does not own click coordinates.

The live Daily frame contains five rows. Full-screen OCR returned `Go` for the first four blue buttons but omitted the fifth button text entirely. The parser therefore returned `unknown_action` for `Train Cavalry x250`. The same failure shape is reproducible in the committed `tests/data/screen_recognition/quest_daily.png`: full-screen OCR omits the blue Go label for `Upgrade building 1x`, while `quest_daily_sep09.png` recognizes comparable Go buttons.

### Popup interruption detection

`pnc_automation/app/pnc/vision/pnc_observation_enricher.py:_find_visual_popup_close_bounds` searches the upper-right 27 percent of the frame for a bright, nearly square component with two diagonals. `_build_visual_popup_close_additions` promotes any accepted component directly to `PNC_POPUP` with `visual_upper_right_close_x` evidence.

The recovery trace reached Home City, then a normal animation at `(508, 267, 26, 30)` in the 540-by-960 normalized frame satisfied that X-shape test. `NavigationPerception` correctly stopped because its guard reported a blocking popup. The defect belongs to popup classification, not to navigation completion or recovery policy.

Existing tests cover synthetic generic X geometry, crossed artwork outside the search band, a wide crossed HUD badge, typed OCR popups, reconnect, VIP reset, and modal ownership. The current positive generic-X test is synthetic and does not establish that a real popup surface surrounds the X.

## Target design

### Canonical Daily action classifier

Keep `daily_quest_rows.py` as the only owner of row action state. Change the row-state classifier to receive the row image and bounds in addition to its OCR lines.

Classification order remains explicit:

1. exact OCR `CLAIM`;
2. exact OCR `GO`;
3. exact OCR `CLAIMED`;
4. OCR requirement/completed text;
5. a conservative visual fallback for a blue Go button inside the row's existing right-side action region;
6. `UNKNOWN_ACTION`.

The visual fallback must prove the blue button body and its expected rectangular extent within the current row. It must not infer `CLAIM`, `COMPLETED`, or `REQUIREMENT` from color alone. OCR remains the semantic owner when it supplies a known state, and existing visual row geometry remains the sole owner of any action point.

Put the visual predicate in one private helper beside `_resolve_row_state`; do not add a second parser in the workflow or enricher. Derive its normalized region and thresholds from both committed Daily fixtures and the saved live frame. Require a strong blue-fill ratio plus horizontal button structure so isolated blue artwork cannot create a Go state.

### Canonical popup ownership predicate

Keep `PncObservationEnricher.detect_interruption` and `_find_visual_popup_close_bounds` as the interruption owners. Do not teach `NavigationCore` to ignore `PNC_POPUP`.

Split generic visual popup evidence into two requirements:

- an X-shaped close candidate, using the existing connected-component geometry; and
- supporting popup-surface evidence around and below that candidate.

The supporting predicate should verify a coherent modal panel or dimmed-overlay relationship, measured from real positive popup artifacts and the false-positive City frame. An isolated X-shaped component over a normally recognized HUD is insufficient. Known OCR-backed popups continue through `_build_popup_additions`; reviewed modal controls continue to use `owned_dismiss_bounds`; task-owned upgrade warnings keep their existing request-specific path.

Return one canonical `ObservationAdditions` only when both visual requirements pass. Preserve the measured X center as the selector action point. Avoid a source-screen allowlist: a real popup can cover Home, World, or a modal, so popup ownership must come from the overlay itself rather than the background screen name.

## Implementation phases

### Phase 1: close the Daily Go-classification gap

Expected files:

- `pnc_automation/app/pnc/vision/daily_quest_rows.py`
- `tests/test_daily_quest_vision.py`

Work:

1. Pass `image` and the detected row `bounds` into the canonical state classifier.
2. Add the conservative blue-button visual fallback after all known OCR states.
3. Add a screenshot-backed regression using `tests/data/screen_recognition/quest_daily.png` and deterministic OCR lines that intentionally omit the affected Go token.
4. Add negative tests for a row with no action button, a non-blue right-side decoration, and a claim row. Confirm that OCR `CLAIM` wins and that action-point geometry is unchanged.

Acceptance:

- The missed `Upgrade building 1x` fixture row and the live failure shape classify as `go`.
- Clear OCR states retain their current results.
- Ambiguous or absent buttons remain `unknown_action`.
- No selector, action point, workflow, or mutation behavior changes.

### Phase 2: require popup-surface ownership

Expected files:

- `pnc_automation/app/pnc/vision/pnc_observation_enricher.py`
- `tests/test_capture_and_vision.py`
- a sanitized regression fixture and provenance entry under `tests/data/screen_recognition/` if the current local fixture mechanism cannot carry the live frame without changing protected local configuration

Work:

1. Preserve the false-positive City frame as a deterministic regression. Remove or mask account-specific text and resource counts without changing the close-candidate area, Home identity anchors, or surrounding HUD geometry; record its source hash and crop/masking provenance.
2. Select at least two real generic-X popup artifacts with different popup layouts as positive fixtures. Keep the existing synthetic geometry test as a unit test, but do not use it as the only positive proof.
3. Add one shared popup-surface predicate and require it in `_build_visual_popup_close_additions`.
4. Keep OCR update, reconnect, VIP reset, promotional popup, modal-owned X, and task-owned warning paths intact.
5. Add a direct `NavigationPerception` regression proving that the sanitized City frame remains `PNC_HOME_CITY`, has `blocking_popup=False`, and retains its reviewed Home controls.

Acceptance:

- The saved City failure frame no longer emits `visual_upper_right_close_x`.
- Each real generic-X popup fixture still emits a blocking popup with a measured Close action point.
- Existing OCR and owned-modal popup tests still pass.
- Navigation behavior is unchanged: any confirmed interruption still stops without a repeated tap.

### Phase 3: integrate, review, and promote the two fixes

Expected files:

- `reviewed_plans/PNC_CORE_PORTING_VALIDATION.md`
- `instructions/CORE_WORKFLOW_PORTING.md` only if the implemented ownership or operational guidance differs from the current guide

Work:

1. Run focused parser, perception, popup, workflow, and navigation tests.
2. Run `py -m unittest discover -s tests` because popup perception is shared across workflows.
3. Review the final diff for duplicate predicates, accidental action authorization, altered selector coordinates, and weakened interruption stops.
4. Resolve the current accounts carrying `daily_canary` and `smoke_test`, reserve both instances exclusively for their respective bounded proofs, and run the two live proofs below.
5. Update the validation ledger with observed outcomes and artifact paths. Remove the merge-readiness blocker only if both live matrix cells pass.

## Slice-by-slice live validation matrix

| Slice | Target | Precondition | Bounded actions | Required postcondition | Evidence | Current / required disposition |
| --- | --- | --- | --- | --- | --- | --- |
| Daily Go fallback | Current account carrying `daily_canary`, currently active castle | Exact active identity is visible or prepared by a bounded read-only roster scroll; Home is confirmed | Run `daily-quest-status`; no row action, scroll, claim, or castle selection | Fresh Daily viewport has no `unknown_action` for a visually clear blue Go button and the workflow confirms Home | Daily content frame, typed JSON result, final Home frame, core trace | **Passed 2026-09-12:** `mega_old_acc` returned five `go` rows, zero unknown titles, and `PNC_HOME_CITY`. |
| Popup ownership | Current account carrying `smoke_test`, currently active castle | Daily or another reviewed screen with a route to Home; no blocking popup at source | Call the explicit reviewed `recover_to_home` proof once; no unsafe popup dismissal and no repeated navigation tap | Two fresh Home frames remain `PNC_HOME_CITY`, unblocked | Source frame, both Home frames, core trace | **Passed 2026-09-12:** `testing` SMOKE_TEST recovery smoke passed one test in 14.994 seconds. |

There is no mutation boundary in either slice. Stop immediately on unknown identity, an unsupported popup, a stale frame, a source change, or an unexpected destination. Preserve the latest screenshot and trace. Recovery may consume only a typed safe popup control authorized by the canonical decision owner.

The exact Daily command is:

```powershell
py -m pnc_automation.app.entrypoints.cli daily-quest-status --config C:/Users/lebel/pnc/config/accounts.yaml --account <current-daily-canary-account>
```

Add a small opt-in live test for explicit recovery if no existing entry point can emit and assert both Home confirmation frames. Follow the repository convention:

```powershell
$env:PNC_RUN_LIVE_SMOKE="1"
$env:PNC_LIVE_SMOKE_CONFIG="C:/Users/lebel/pnc/config/accounts.yaml"
$env:PNC_LIVE_SMOKE_ACCOUNT="<current-smoke-test-account>"
py -m unittest tests.test_live_core_workflow_smoke
```

That test must skip unless explicitly enabled, use `build_core_runtime`, keep the active castle, and perform no generic popup close.

## Validation plan

Run in this order:

```powershell
py -m unittest tests.test_daily_quest_vision
py -m unittest tests.test_capture_and_vision tests.test_navigation_core tests.test_core_runtime tests.test_core_workflow tests.test_popup_recovery
py tools/validate_navigation_selectors.py --config C:/Users/lebel/pnc/config/accounts.yaml --account <current-live-testing-account> --selector PNC_BOTTOM_NAV_QUEST --output-dir C:/Users/lebel/pnc/artifacts/replacement_core/core_port_selectors
py -m unittest discover -s tests
```

Resolve the account IDs from current role assignments, then reserve the `daily_canary` instance for the Daily proof and the `smoke_test` instance for the recovery proof. Resolve the separate current `live_testing` account for selector validation because the validator's role gate requires that role; it must not overlap either proof. Record `passed`, `applicability_skip`, or `blocked` for both matrix rows; a pass in one row cannot substitute for the other.

## Data, config, and migration notes

- Do not modify `config/accounts.yaml`, `config/castles.yaml`, `config/daily_maintenance.yaml`, or `tests/data/local_fixture_artifacts.json`.
- Add no account IDs, castle names, resource values, or credentials to committed fixtures or logs.
- Record provenance for any derived regression image. Keep the original live artifact outside the commit.
- No persisted schema or authored automation migration is required.
- The Daily workflow and popup detector already have canonical callers; update them in place and add no compatibility path.

## Risks and mitigations

- **Blue artwork becomes a false Go button.** Require button-region geometry and blue-fill structure; keep negative visual fixtures and leave claim inference to OCR.
- **A stricter popup predicate misses a real popup.** Build the predicate from multiple real positive layouts and rerun every typed popup test before live validation.
- **A background-screen allowlist hides overlays.** Do not use one; require overlay ownership from visual or OCR evidence.
- **Animated live state makes one frame misleading.** Require two fresh Home frames and preserve both artifacts.
- **Another task controls the emulator.** Reserve exclusive instance use; a source change is `blocked`, not a retry or pass.
- **A Daily row changes between runs.** Judge the live row against its visible button evidence and typed output, not a hard-coded quest title or row count.

## Open questions

No blocking product decision remains. During implementation, measure the popup-surface and blue-button thresholds from the named positive and negative fixtures; keep those measurements inside the canonical helpers and tests rather than configuration.

## Execution checklist

- [ ] Add the Daily visual Go fallback in `daily_quest_rows.py`.
- [ ] Add deterministic positive, precedence, and negative Daily tests.
- [ ] Sanitize and register the City false-positive regression fixture with provenance.
- [ ] Select at least two real generic-X popup positives.
- [ ] Add the shared popup-surface ownership predicate.
- [x] Prove all typed popup paths and navigation stop behavior offline.
- [x] Run the full offline suite.
- [x] Review the diff for duplicated ownership or broader action authority.
- [x] Resolve the current `daily_canary` account and run the Daily live matrix row (2026-09-12: passed on `mega_old_acc`).
- [x] Resolve the current `smoke_test` account and run the explicit recovery matrix row (2026-09-12: passed on `testing`).
- [x] Update the validation ledger and reassess merge readiness after both rows passed.
