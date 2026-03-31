# Review: `Complete PNC_KINGDOM_CHAT_UNSUPPORTED_ROW_SUBPLAN` (`a54505799711db60900b47c244f254b61fbb252d`)

## Validation performed
- Read the full commit diff and traced each touched production file in context.
- Ran `py -m unittest tests.test_automation_framework tests.test_capture_and_vision tests.test_chat_monitor tests.test_flows_and_tasks tests.test_mail_workflow` and the suite passed.
- Ran two focused repros in the workspace for the semantic-castle resolver and Manage Char classifier.

## Findings

### 1. High: single-castle Manage Char screens are no longer recognizable
- Files:
  - `pnc_automation/vision/pnc_observation_enricher.py:3322`
- Problem:
  - `_looks_like_castle_selection(...)` now returns `False` before checking the `Manage Char` anchor whenever fewer than two castle rows are extracted.
  - That regresses any account or screenshot where the Manage Char roster currently exposes only one castle.
- Why this is a bug:
  - The pre-change logic accepted the explicit `Manage Char` label as sufficient screen proof.
  - After this change, a valid one-castle Manage Char screen can be misclassified, which can break login verification, current-castle validation, and any flow that depends on reaching `PNC_CASTLE_SELECTION`.
- Repro:
  - A direct workspace repro with one `LABEL_MANAGE_CHAR` anchor and one castle entry returns `False`.
- Clean fix:
  - Restore the anchor fast-path before the `len(entries) < 2` guard, or explicitly allow `len(entries) == 1` when the `Manage Char` anchor is present.
  - Add a regression test that builds a one-castle Manage Char OCR snapshot and asserts `ScreenType.PNC_CASTLE_SELECTION`.

### 2. Medium: `preferred_name` does not actually prefer the exact castle name
- Files:
  - `pnc_automation/pnc/observation.py:648`
- Problem:
  - `resolve_unambiguous_castle_identity(...)` groups semantically equivalent castles correctly, but when `preferred_name` matches exactly inside one group it returns `exact_groups[0][0]`, not the exact-matching candidate.
- Why this matters:
  - If roster order is `["please bgentle", "please b gentle"]` and `preferred_name` is `"please b gentle"`, the resolver still returns `"please bgentle"`.
  - That can cache the wrong canonical identity, archive under the wrong castle spelling, and make downstream diagnostics or path naming unstable.
- Repro:
  - A direct workspace repro returns `CastleIdentity(... castle_name='please bgentle' ...)` even when `preferred_name='please b gentle'`.
- Clean fix:
  - When exactly one semantic group contains an exact `preferred_name` match, return the exact-matching candidate from that group, not the group head.
  - Keep the current fallback to the group head only when there is no exact text match inside the unique semantic group.
  - Add a regression test with the exact-match variant intentionally placed second in roster order.

### 3. Medium: castle-row matching is now duplicated in `ActionExecutor`
- Files:
  - `pnc_automation/automation/action_executor.py:180`
  - `pnc_automation/pnc/observation.py:620`
- Problem:
  - `_entry_title_matches(...)` adds a second castle-title matching policy in `ActionExecutor`.
  - The canonical castle-entry matching rules already live in the observation layer (`castle_entry_identity_matches`, `castle_entry_matches`, `castle_names_match`).
- Why this matters:
  - Matching behavior for castles now has multiple owners.
  - If castle matching evolves again, action execution can quietly drift away from task planning and observation matching.
- Clean fix:
  - Move dynamic-entry matching for castles onto one canonical helper in `pnc_automation.pnc.observation`.
  - Have `ActionExecutor._require_entry(...)` delegate to that helper instead of re-encoding castle-specific behavior locally.
  - Keep `ActionExecutor` responsible only for action execution, not castle identity policy.

### 4. Low: `open_lord_info` now contains redundant/overlapping settings-exit logic
- Files:
  - `pnc_automation/pnc/screen_flows.py:250`
- Problem:
  - The new branch checks `observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)` twice.
  - The settings-exit behavior is also split across two overlapping branches with the same reason and same follow-up request shape.
- Why this matters:
  - This is mostly a maintainability issue, but it makes the path harder to reason about and easier to regress during future flow changes.
- Clean fix:
  - Collapse the settings-screen escape logic into one branch.
  - Compute the shared follow-up request once and reuse it.
  - Keep the branch order explicit: full-screen settings -> overlay close -> generic More path.

### 5. Low: normalization ownership is still routed through `text_anchors`
- Files:
  - `pnc_automation/vision/pnc_observation_enricher.py:34`
  - `pnc_automation/vision/text_anchors.py:10`
  - `pnc_automation/text_normalization.py:1`
- Problem:
  - The commit introduced `pnc_automation.text_normalization.normalize_ocr_text` as the shared canonical helper, but `pnc_observation_enricher.py` still imports `normalize_ocr_text` from `vision.text_anchors`.
- Why this matters:
  - The dependency direction is now misleading: callers appear to depend on the anchor layer even though normalization has been extracted into a shared module.
  - This is a small architecture inconsistency that makes ownership less obvious.
- Clean fix:
  - Import `normalize_ocr_text` directly from `pnc_automation.text_normalization` everywhere outside `text_anchors.py`.
  - Keep `text_anchors.py` focused on anchor detection only.

## Recommended fix order
1. Fix `_looks_like_castle_selection(...)` and add the one-castle regression test.
2. Fix `resolve_unambiguous_castle_identity(...)` to return the exact preferred match when present, plus a reversed-order test.
3. Refactor castle-entry matching so `ActionExecutor` reuses one canonical matcher.
4. Apply the two low-risk cleanup items in the same patch if convenient.

## Overall assessment
- The unsupported-chat-row work itself is generally solid and well covered by tests.
- The main issues I found are on the surrounding castle-resolution/generalization changes that landed in the same commit, especially the one-castle Manage Char regression and the non-exact `preferred_name` resolution behavior.
