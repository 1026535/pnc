# Review: `completed PNC_MAIL_WORKFLOW_IMPLEMENTATION.md` (`7c052afb6ccc8e3b1835a3adcac9ca3d05399eb1`)

Review premise:

- The implementation added the right major building blocks: canonical mail params/models, mail tasks, OCR enrichers, archive persistence, and broad automated coverage.
- The findings below focus on places where the shipped behavior is weaker than the implementation plan, can mis-verify live behavior, or adds avoidable architectural drift.

## Findings

### 1. High: profile-route recipient verification can compare against the wrong name and can lock in a stale OCR read

Evidence:

- [_expected_target_name()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L290)
- [SendMailTask.verify()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L71)
- [_build_player_profile_additions()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L830)

Why this is a problem:

- The plan requires profile-route mail to verify the compose target against the visible remote profile name.
- The task does capture `before.profile_player_name`, but it stores it with `setdefault(...)`, so the first OCR read wins forever even if a later observation is cleaner.
- `_expected_target_name()` then prefers `profile_route.player_name` over the observed `expected_profile_target`.
- That means the compose-popup target can be compared against the route lookup key instead of the authoritative profile name that was actually opened.
- This is especially risky for alliance/rank/chat routes where the list row text and the profile header text do not have to match exactly.

Clean fix:

1. Replace `setdefault("expected_profile_target", ...)` with an unconditional refresh when `before.screen_type == PNC_PLAYER_PROFILE` and the observed name is non-empty.
2. In `_expected_target_name()`, prefer the observed `expected_profile_target` over `profile_route.player_name` once a profile has actually been opened.
3. Add a regression test where the route lookup name differs from the profile header name and the compose target matches the profile header.

### 2. High: `send_mail` never performs the planned thread-level verification, so ambiguous mailbox evidence is accepted or rejected too early

Evidence:

- [_plan_send_verification()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L237)
- [_verify_send_verification()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L246)
- [test_send_mail_verify_mail_plan_keeps_visible_matching_row_in_mailbox()](/c:/Users/lebel/pnc/tests/test_mail_workflow.py#L639)
- [test_send_mail_verify_succeeds_when_matching_sent_row_is_visible()](/c:/Users/lebel/pnc/tests/test_mail_workflow.py#L667)

Why this is a problem:

- The plan explicitly requires thread-level confirmation when mailbox-row evidence is not strong enough on its own.
- In the shipped task, `verify_mail` planning can only reopen the mailbox. Once the requested mailbox is visible, planning stops.
- The `PNC_MAIL_THREAD` verification branch exists, but there is no `verify_mail` planning path that ever taps a thread row to reach it.
- The tests currently codify mailbox-only success, so this weaker behavior is now the intended implementation rather than an accidental omission.
- That creates live false positives when an older row already looks similar enough.
- That also creates live false negatives when the mailbox preview is too weak even though the sent thread would confirm correctly.

Clean fix:

1. Split verification into explicit sub-phases, for example `verify_mailbox` and `verify_thread`.
2. In the mailbox phase, classify the match strength and only succeed immediately on strong row evidence.
3. When the row evidence is ambiguous or weak, tap the matching row and move to `verify_thread`.
4. When there is no plausible row, fail or replan as today.
5. Keep the existing `_thread_matches_sent_mail()` logic, but make it reachable from the canonical task flow.
6. Add tests for `row ambiguous -> open thread -> succeed` and `row ambiguous -> open wrong thread -> fail`.

### 3. High: direct player-mail verification can false-positive on any pre-existing thread with the same recipient

Evidence:

- [_find_matching_sent_thread()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L306)

Why this is a problem:

- For player mail, the first match condition is `title_text == expected_target`, and it returns immediately.
- That means any already-visible historical conversation with the same player can satisfy send verification even if the newly sent subject/body is not present.
- This is weaker than the plan and weaker than the alliance path, which at least tries subject/body preview matching before succeeding.
- Combined with the missing thread-confirm phase, this can incorrectly report success without proving the just-sent mail exists.

Clean fix:

1. Remove the unconditional recipient-name early return from `_find_matching_sent_thread()`.
2. Treat recipient-name equality as a candidate signal, not a terminal proof.
3. Require preview/body/subject evidence for mailbox-only success, or escalate same-recipient matches to thread confirmation.
4. Add a regression test where the mailbox already contains an older thread for the same recipient and the new message text is different.

### 4. Medium: `collect_mail.limit_per_mailbox` does not mean what the API and plan say, because mailbox iteration never scrolls

Evidence:

- [CollectMailTask.plan()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_mail_task.py#L42)
- [_current_visible_thread_entry()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_mail_task.py#L163)
- [_collection_progress_result()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/collect_mail_task.py#L250)
- [CollectMailParams.limit_per_mailbox](/c:/Users/lebel/pnc/pnc_automation/pnc/mail.py#L68)

Why this is a problem:

- `limit_per_mailbox` is exposed as if it controls how many mailbox items can be collected.
- The task only indexes `observation.entries(ListEntryKind.MAIL_THREAD)` from the current viewport and never plans a mailbox-list swipe.
- Once the visible rows are exhausted, the task reports success for the "visible thread window" and advances.
- So a caller can request `limit_per_mailbox=25`, but the task will silently stop after the currently visible rows.
- That is a real behavior gap, not just a naming nit, because the parameter currently over-promises collection depth.

Clean fix:

1. Either implement canonical mailbox scrolling with task state that tracks progress across multiple viewport windows.
2. Or intentionally narrow the contract now and rename the parameter/message to visible-window semantics.
3. If the contract is narrowed, validate that requested limits do not exceed the supported viewport behavior.
4. If the contract is narrowed, update the implementation plan/review docs to reflect that bounded first-slice scope.
5. Add tests for multi-page mailboxes before claiming the current `limit_per_mailbox` contract is complete.

### 5. Medium: the live-proven profile-route search heuristics are implemented in the wrong ownership layer and currently rely on brittle execution-side compromises

Evidence:

- [_plan_profile_route_search()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L176)
- [_plan_profile_route_search_swipes()](/c:/Users/lebel/pnc/pnc_automation/automation/tasks/send_mail_task.py#L402)
- [ScreenFlowPlanner.open_player_profile()](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py#L443)
- [StepExecutionPolicy.max_replans_per_step](/c:/Users/lebel/pnc/pnc_automation/automation/runner.py#L47)
- [test_send_mail_plan_searches_list_backed_profile_route_before_failing_missing_target()](/c:/Users/lebel/pnc/tests/test_mail_workflow.py#L855)

Why this is a problem:

- If this search behavior was validated in the real environment, it should be favored over the earlier narrower plan.
- The problem is therefore not that the heuristic exists, but that it currently lives in `SendMailTask` rather than in reusable screen-flow/list-navigation ownership.
- The reset phase emits two swipes in one task increment, so a target that becomes visible after the first swipe can be skipped by the second before verification gets a chance to inspect it.
- To accommodate the extra replans, the commit also raised the global runner cap from `5` to `15` for every task, which broadens the blast radius of any unrelated loop.

Clean fix:

1. Keep the heuristic search if it is the live-proven behavior.
2. Move it into `ScreenFlowPlanner` (or another shared list-navigation abstraction) so it is not task-local navigation logic.
3. Emit at most one swipe per plan/verify cycle so newly visible targets cannot be skipped inside a single action batch.
4. Replace the runner-wide replan-cap increase with a more local budget or stateful route-search limit owned by the mail/profile-navigation logic itself.
5. Add regression coverage that reflects the real validated behavior instead of the earlier fail-fast-only plan.

## Simplification notes

- The selector surface added several ids that are not actually consumed by the runtime yet, including `PNC_ALLIANCE_MEMBER_MANAGE_BUTTON`, `PNC_MIGHT_RANK_PROFILE_BUTTON`, and the three `PNC_MAIL_THREAD_*_REGION` ids. Either wire them into parsing/flows or remove them for now so the selector catalog keeps one canonical implementation per concept.
- [mailbox_observation()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L131) currently ignores its `mailbox` argument. Either drop the parameter or use it to tighten follow-up validation so the API surface matches the actual behavior.

## Validation performed

- Ran `py -m unittest tests.test_mail_workflow tests.test_flows_and_tasks tests.test_capture_and_vision tests.test_screen_classifier tests.test_automation_framework tests.test_live_chat_workflow_smoke`
- Result: `Ran 194 tests` / `OK (skipped=3)`
- Ran `py -m unittest discover -s tests -p "test_*.py"`
- Result: `Ran 281 tests` / `OK (skipped=6)`
- Findings 1 through 5 are based on direct code-path review against the implementation plan and the committed tests. I did not run live in-game smoke validation for this review.
