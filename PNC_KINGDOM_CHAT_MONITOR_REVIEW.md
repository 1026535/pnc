# Kingdom Chat Monitor Review

Reviewed commit `385c1b18b804e51a281e6ce096207cc51b5a7027` against the intended design in `PNC_KINGDOM_CHAT_MONITOR_IMPLEMENTATION.md`.

## Validation

- Ran `py -m unittest tests.test_app tests.test_capture_and_vision tests.test_chat_monitor tests.test_config_loader tests.test_flows_and_tasks tests.test_mail_workflow tests.test_runtime_castle_targeting tests.test_script_loader`
- Result: `241` tests passed
- Also did a static review of the changed runtime, capture, vision, config, and test surfaces

## Findings

### 1. High: per-day rollover does not reuse the previous day's overlap state

Files:

- `pnc_automation/capture/chat_archive_store.py:112-145`
- `pnc_automation/capture/chat_archive_store.py:166-170`

Problem:

`ChatArchiveStore.persist_heartbeat()` only loads `state.json` from the current day directory. On the first heartbeat after the local day changes, the new directory has no state yet, so the store treats the current visible snapshot as brand new even when it is the same window that was already archived a few minutes earlier.

Impact:

- The first post-midnight heartbeat can append duplicate player rows to the new day's `transcript.log`.
- It can also create an unnecessary durable screenshot for unchanged chat.
- This is a direct mismatch with the implementation plan, which explicitly called out per-day rollover and loading the previous day's state for overlap decisions.

Clean fix:

1. When the current day has no `state.json`, look up the previous local-day directory for the same account/castle/channel and load its snapshot as the overlap baseline.
2. Use that carry-over state only for delta detection; still write the new transcript, screenshot, and `state.json` into the new day directory.
3. Keep the current local-day directory layout exactly as-is.
4. Add a regression test that persists the same snapshot across a local midnight boundary and verifies the new day starts with `changed == False`.

### 2. High: ambiguous single-line chat rows are silently treated as announcements

Files:

- `pnc_automation/vision/pnc_observation_enricher.py:1423-1447`
- `pnc_automation/vision/pnc_observation_enricher.py:1542-1561`

Problem:

If `_try_build_player_chat_entry()` cannot prove a player row, `_build_chat_message_entry()` falls back to announcement-vs-unsupported classification. `_looks_like_announcement_chat_row()` currently returns `True` for any single-line row (`len(row_lines) == 1`), even when the text does not contain any announcement markers.

That means OCR breakage such as a sender-only row like `Enemy Bob`, or any other one-line malformed player row, is reclassified as `ANNOUNCEMENT` instead of `UNSUPPORTED`.

Impact:

- Player chat can be dropped silently instead of surfacing a safe task failure.
- `collect_kingdom_chat` never sees those rows in `visible_unsupported_chat_entries(...)`, so it cannot protect the archive from ambiguous OCR.
- This undermines the commit's central design goal of making player/announcement/unsupported classification explicit and fail-fast.

Clean fix:

1. Remove the unconditional `len(row_lines) == 1 => announcement` rule.
2. Only classify a row as `ANNOUNCEMENT` when it has explicit announcement tokens or stronger layout evidence that is genuinely specific to announcement chrome.
3. Classify all remaining unproven rows as `UNSUPPORTED`.
4. Add transcript-parser tests for:
   - sender-only single-line OCR (`Enemy Bob`)
   - malformed merged OCR that is not `Sender: message`
   - real announcement rows that still remain `ANNOUNCEMENT`

### 3. Medium: max-replan failures bypass the new persisted-failure-artifact path

Files:

- `pnc_automation/automation/runner.py:268-278`
- `pnc_automation/automation/runner.py:353-380`

Problem:

The commit added `_raise_task_verification_error()` so failures in `LIGHT` mode can still force one persisted debug screenshot when the active observation is ephemeral. That helper is used for "not applicable" and normal verification failures, but not for replan exhaustion. The `replans > max_replans` branch still raises `TaskVerificationError` directly.

Impact:

- A task that times out through repeated replans can fail without `artifact_path`.
- The failure also omits the last `screen_type`, even though it is available in `after`.
- This weakens exactly the diagnostic path that the new observation-mode work was supposed to strengthen.

Clean fix:

1. Route the replan-exhaustion branch through `_raise_task_verification_error(...)`.
2. Pass the last `after` observation, `after.screen_type`, and a dedicated failure label such as `"{task}_failure_replan_limit"`.
3. Add a runner test with a task that always returns `TaskResult.replan(...)` while observations are ephemeral, and assert that the raised error includes an `artifact_path`.

### 4. Medium: output-root validation still allows archive/artifact nesting

Files:

- `pnc_automation/config/validation.py:219-227`

Problem:

`_validate_distinct_output_roots()` only rejects exact path equality. It still accepts configurations where one root lives inside the other, for example:

- `artifacts.root: artifacts`
- `archives.root: artifacts/archives`

or the reverse.

Impact:

- Durable archives can still end up inside the runtime artifact tree.
- That violates the feature requirement that archives stay separate from runtime `artifacts/`.
- It also makes retention/cleanup riskier because removing runtime artifacts can accidentally remove durable chat and mail archives.

Clean fix:

1. Reject both exact equality and ancestor/descendant overlap after path resolution.
2. Implement the check symmetrically so neither root may contain the other.
3. Add config-loader tests for both invalid nesting directions.

## Lower-Priority Cleanup

### 5. Low: transcript observations are forced ephemeral even in `DEBUG` mode

Files:

- `pnc_automation/vision/observation_request.py:106-116`

Problem:

`ObservationRequest.chat_transcript_observation()` hardcodes `persist_artifact=False`. That means the exact observation used for transcript extraction is always ephemeral, even when the runtime is explicitly in `DEBUG` mode.

Impact:

- `LIGHT` mode behavior is correct, but `DEBUG` mode no longer preserves the highest-value screenshot for this feature.
- This bypasses the shared observation-mode contract and reintroduces a chat-specific persistence exception inside the request model.

Clean fix:

1. Let the request inherit the runtime mode by removing the hardcoded `persist_artifact=False`.
2. Keep `LIGHT` mode lean through the shared `ObservationService._resolve_persist_artifact(...)` policy instead of a chat-specific override.
3. If a special-case override is still needed later, pass `persist=` from the call site instead of baking it into the shared request type.
4. Add one test showing transcript capture stays ephemeral in `LIGHT` mode but persists in `DEBUG` mode.

## Recommended Fix Order

1. Fix the day-rollover state carry-over bug.
2. Tighten announcement classification so ambiguous rows become `UNSUPPORTED`.
3. Finish the runner's failure-artifact coverage for replan exhaustion.
4. Harden root validation against nested output directories.
5. Clean up the transcript observation persistence policy so it fully respects the shared mode contract.

## Overall Assessment

The implementation is close to the intended architecture and the new task/archive split is good. The main remaining issues are around edge-condition correctness and making the new runtime policy behave consistently in all failure paths. Once the four main findings above are fixed, the feature should align much more cleanly with the original plan.
