# Review: `completed PNC_CHAT_WORKFLOW_SUBPLAN.md` (`1e26877fb8e6599d7fc19d736168c5db4ac9f117`)

Review premise:

- Geometry-first remains the correct primary design.
- The findings below only flag places where the geometry-first path has no usable OCR fallback after a confirmed miss, or where the OCR fallback path does not return enough state to continue safely.

## Findings

### 1. High: when chat falls back to OCR, the resulting observation can still leave `send_chat_message()` unusable

Evidence:

- [navigation_follow_up()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L47)
- [_build_chat_additions()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L1189)
- [_clear_existing_text()](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py#L175)

Why this is a problem:

- `open_chat()` uses `ObservationRequest.navigation_follow_up(...)`, which does allow OCR fallback for `PNC_CHAT`.
- This is not a geometry-first issue. The problem starts after geometry has already failed and OCR has already been used.
- When the geometry heuristic misses, `_build_chat_additions()` only proves that the screen is chat. It does not populate `active_chat_channel`, `chat_draft_empty`, or `chat_draft_text`.
- The next `InputTextAction(replace_existing=True)` fails fast when `chat_draft_empty is None`.
- I reproduced this locally with `artifacts/2026-03-13/testing_live_selector_recalibrated/chat_after.png`: the navigation follow-up built `screen_type=pnc_chat` but `chat_draft_empty=None`, and the next input action raised `SelectorResolutionError("Chat draft state must be observed before typing into the shared chat input field.")`.

Clean fix:

1. Move chat-state extraction behind one shared helper that runs whenever a request has already proven `PNC_CHAT` and `include_chat_state=True`.
2. Call that helper from both the geometry-first path and the OCR fallback path so `active_chat_channel` and `chat_draft_*` are always present on a successful chat observation.
3. Add a regression test that starts from an OCR-only chat frame and verifies `send_chat_message()` can still type with `replace_existing=True`.

### 2. High: the post-send follow-up never escalates to OCR after a confirmed geometry miss, so valid chat frames can come back as `UNKNOWN`

Evidence:

- [chat_send_follow_up()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L74)
- [_build_chat_geometry_additions()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L416)

Why this is a problem:

- `chat_send_follow_up()` only sets `candidate_screen_types={PNC_CHAT}`. Its `ocr_screen_types` set is empty.
- That makes the post-send confirmation geometry-first and geometry-only.
- With the current builder flow, that means a geometry miss has no escalation path at all during this narrow follow-up.
- If the warmth/brightness heuristic misses one legitimate chat frame, the observation stays `UNKNOWN`.
- I reproduced this with the committed artifact `artifacts/2026-03-13/testing_live_selector_recalibrated/chat_after.png`: `ObservationRequest.chat_send_follow_up()` returned `UNKNOWN`, while `ObservationRequest.source_screen_retry(PNC_CHAT)` and `ObservationRequest.full_runtime_default()` both classified the same frame as `PNC_CHAT`.

Clean fix:

1. Keep `chat_send_follow_up()` geometry-first, but allow OCR escalation after a geometry miss by also setting `ocr_screen_types={PNC_CHAT}`.
2. Keep `include_chat_state=True`; consider `include_popup_guard` and `include_loading_guard` as well if unattended recovery after send still matters.
3. Add a regression test using a real or synthetic frame where geometry misses but OCR still proves chat.

### 3. Medium: channel changes are never re-observed, so the workflow can send in the wrong tab or clear the wrong draft

Evidence:

- [send_chat_message()](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py#L305)
- [execute_actions()](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py#L44)
- [execute_actions()](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py#L91)

Why this is a problem:

- `send_chat_message()` emits `SelectChatChannelAction(...)` and immediately follows it with `InputTextAction(...)`.
- The channel-select action does not request a follow-up observation, so the next step still uses the pre-switch `active_chat_channel` and `chat_draft_*` values.
- If the tab tap misses, the message is typed and sent to the previous channel.
- Even when the tap succeeds, any per-channel draft state is stale because the input step is still looking at the observation from the old tab.

Clean fix:

1. Re-observe after an actual tab change with a narrow chat request before typing.
2. Prefer one canonical path that can skip both the tap and the follow-up when the requested channel is already active, rather than always emitting an unobserved state-changing action.
3. Add tests for `tab tap misses -> do not send` and `different channels carry different draft state`.

### 4. Medium: empty chat placeholders are matched too literally, so empty drafts are frequently treated as non-empty

Evidence:

- [_CHAT_EMPTY_INPUT_TEXTS](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L193)
- [_read_chat_draft_state()](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L453)
- [_chat_delete_budget()](/c:/Users/lebel/pnc/pnc_automation/automation/action_executor.py#L221)

Why this is a problem:

- Empty detection currently accepts only `""` or exact normalized `PLEASEENTERCONTENT`.
- Real OCR on committed chat screenshots is noisier than that. On both `artifacts/manual_testing_chat_20260313/02_chat_open.png` and `artifacts/2026-03-13/k287_pine_cobaye_1/20260313T134419Z_live_send_chat_helper_post_action_1.png`, the input placeholder was read as `Pleaseter content`.
- That value misses the exact set check, so `_clear_existing_text()` treats an already-empty field as non-empty and sends a large burst of `KEYCODE_DEL` events.
- That adds avoidable ADB work to the optimized chat path and makes the draft-state signal much noisier than it needs to be.

Clean fix:

1. Replace the exact placeholder set with one tolerant predicate, for example normalized text that contains `ENTERCONTENT` and optionally starts with a fuzzy `PLEASE` prefix.
2. Keep exact-empty as the fastest path.
3. Add tests for common OCR variants such as `Pleaseter content` and `Please enter conteni`.

### 5. Medium: `PNC_DAILY_TO_DO` was added to classification but not to recovery flows

Evidence:

- [PNC_DAILY_TO_DO](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_type.py#L31)
- [ScreenClassifier](/c:/Users/lebel/pnc/pnc_automation/vision/screen_classifier.py#L165)
- [return_to_safe_root_screen()](/c:/Users/lebel/pnc/pnc_automation/pnc/screen_flows.py#L65)

Why this is a problem:

- The commit introduced a new concrete screen type and classifier rule for the Daily To-Do overlay.
- `ensure_home_city()` routes non-root screens through `return_to_safe_root_screen()`.
- `return_to_safe_root_screen()` never learned how to leave `PNC_DAILY_TO_DO`, so a newly recognized Daily To-Do screen now raises `SelectorResolutionError` instead of dismissing itself with back navigation.

Clean fix:

1. Treat `PNC_DAILY_TO_DO` like the other dismissible overlays in `return_to_safe_root_screen()`.
2. Add one flow test proving `ensure_home_city()` can recover from `PNC_DAILY_TO_DO`.
3. If Daily To-Do is not meant to ship yet, remove the unrelated screen additions from this chat commit and land them separately.

## Simplification notes

- Chat state now has two partially separate implementations: the geometry path sets `active_chat_channel/chat_draft_*`, while the OCR path only proves `PNC_CHAT`. One shared `extract_chat_state()` helper would remove the drift that caused findings 1, 2, and 4.
- The intended policy should be encoded explicitly in the code and tests: geometry first, OCR only after a confirmed miss. Right now that policy exists implicitly, which made the missing escalation path easy to miss.
- This commit also mixes chat workflow work with Daily To-Do detection and stricter config validation. Splitting unrelated surface area into separate commits and review documents would make regressions much easier to isolate.

## Validation performed

- Ran `py -3 -m unittest tests.test_flows_and_tasks tests.test_automation_framework tests.test_capture_and_vision tests.test_config_loader tests.test_screen_classifier tests.test_selectors`
- Result: `Ran 116 tests` / `OK`
- Ran `py -3 -m unittest discover -s tests -p "test_*.py"`
- Result: `Ran 170 tests` / `OK (skipped=6)`
- Reproduced findings 1 and 2 with `artifacts/2026-03-13/testing_live_selector_recalibrated/chat_after.png`.
- Reproduced finding 4 with OCR reads from `artifacts/manual_testing_chat_20260313/02_chat_open.png` and `artifacts/2026-03-13/k287_pine_cobaye_1/20260313T134419Z_live_send_chat_helper_post_action_1.png`.
