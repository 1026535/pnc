# Review: selector resolution follow-up implementation

Commit reviewed: `0bb15de11af11d91742270d7b1a7270807fcf2d4` (`completed PNC_SELECTOR_RESOLUTION_SUBPLAN.md`)

This review supersedes the previous resolution review document.

Scope reviewed:

- the new shared observed-action executor,
- staged observation requests and OCR gating,
- validator/reporting changes,
- runtime selector loading paths still exercised by the new flow.

## Findings

### 1. High: a successful OCR retry can still be reported as a failure because the second follow-up never settles

Evidence:

- [_execute_observed_navigation_tap()](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py#L160)
- [_settle_follow_up_observation()](/c:/Users/lebel/pnc/pnc_automation/automation/observed_action_executor.py#L230)
- [_validate_case()](/c:/Users/lebel/pnc/pnc_automation/vision/navigation_selector_validator.py#L284)

Why this is a problem:

- The primary tap runs through the bounded settle loop before any retry decision.
- After the OCR retry tap, the executor captures exactly one `ocr_retry_after` observation and returns it immediately.
- If that second follow-up lands on `PNC_LOADING` or `UNKNOWN` before the real destination appears, the executor returns the transient frame as final.
- The validator then evaluates that transient frame directly and can fail even though one more passive observation would have matched the reviewed destination.

I reproduced this locally with a small harness: `primary miss -> OCR retry source -> OCR retry after = PNC_LOADING -> next frame = PNC_MORE_MENU`. The executor returned `PNC_LOADING` and left the success frame unread.

Clean fix:

1. After the OCR retry tap, run the same bounded settle loop used for the primary tap before returning `final_after`.
2. Keep `initial_destination_artifact_path` pointing at the first post-primary frame, but make `final_destination_artifact_path` point at the fully settled retry result.
3. Add regression tests for `retry -> loading -> success` and `retry -> popup -> handoff`.

### 2. High: validator popup recovery no longer settles the destination after the popup is dismissed

Evidence:

- [_recover_destination_capture()](/c:/Users/lebel/pnc/pnc_automation/vision/navigation_selector_validator.py#L372)

Why this is a problem:

- The old destination-settle path waited through transient post-click states.
- The new validator path only loops while a popup is still blocking.
- As soon as the popup close action returns a non-popup frame, the validator returns immediately, even if that frame is still `PNC_LOADING` or `UNKNOWN`.
- That creates false failures for a common sequence: valid tap, blocking popup, close popup, short loading transition, real destination.

I reproduced this locally with `popup -> close -> PNC_LOADING -> PNC_WORLD_MAP`; the validator failed on `PNC_LOADING` and never consumed the success capture.

Clean fix:

1. After dismissing a popup, pass the resulting capture through a shared passive settle helper before matching the reviewed outcome.
2. Reuse the same reviewed-outcome matcher and transition predicates instead of keeping validator-only settling rules.
3. Add a regression test for `popup close -> loading -> reviewed destination`.

### 3. High: `ocr_region` selectors are still dead data at runtime

Evidence:

- [selector_registry.yaml](/c:/Users/lebel/pnc/pnc_automation/vision/data/selector_registry.yaml#L681)
- [_create_selector_from_catalog_entry()](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L206)
- [_create_selector()](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L232)
- [PillowSelectorEngine.detect()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_builder.py#L104)

Why this is a problem:

- The catalog still contains seven `detection_kind: ocr_region` selectors.
- Runtime selector construction never copies an `ocr_region` payload onto `SelectorDefinition`.
- `PillowSelectorEngine` silently skips `ocr_region` selectors when `selector.ocr_region is None`.
- That leaves screenshot-seeded selectors in the canonical catalog that can never resolve and never fail fast.

Clean fix:

1. Thread the raw catalog `ocr_region` into `SelectorDefinition`.
2. Reject any non-`planned` `ocr_region` selector that omits coordinates during catalog load.
3. Either populate the missing regions for the current catalog entries or demote them back to `planned`.
4. Add tests that `build_default_selector_registry()` fails on malformed `ocr_region` entries and that valid ones resolve through `PillowSelectorEngine`.

### 4. Medium: the new shared reviewed-outcome matcher still ignores `verification_texts`

Evidence:

- [match_reviewed_navigation_outcome()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_interactions.py#L29)
- [ClickOutcome](/c:/Users/lebel/pnc/pnc_automation/vision/selectors.py#L54)
- [load_selector_schema_click_outcomes()](/c:/Users/lebel/pnc/pnc_automation/vision/selector_catalog.py#L383)

Why this is a problem:

- `verification_texts` is still part of the typed selector contract and the catalog schema.
- The new canonical matcher only checks `target_screen` and `verification_selectors`.
- A text-only reviewed outcome will currently pass as soon as the screen matches, because the ignored text requirement never blocks the match.
- If future catalog work starts using `verification_texts`, both automation and validation will silently over-trust those outcomes.

Clean fix:

1. Either implement text verification from OCR/text-anchor evidence inside `match_reviewed_navigation_outcome()`.
2. Or reject `verification_texts` during catalog load and updater application until runtime support exists.
3. Add one positive and one negative test before any catalog entry relies on text-only verification.

## Duplication / simplification notes

- [observation_request.py](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L11) and [pnc_observation_enricher.py](/c:/Users/lebel/pnc/pnc_automation/vision/pnc_observation_enricher.py#L236) now both hard-code the set of OCR-capable screen families. That duplication will drift. One authoritative capability registry should own which screen-specific OCR builders exist.
- [ObservationRequest.runtime_default()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L45) still guarantees OCR on every default observation because [requires_ocr()](/c:/Users/lebel/pnc/pnc_automation/vision/observation_request.py#L74) returns `True` whenever `include_popup_guard` is enabled. The new cost control is therefore real only for explicit narrow requests, not for the default runner path. If that is intentional, the naming should reflect it; otherwise the default request should be narrowed.

## Validation performed

- Ran `py -3 -m unittest tests.test_automation_framework tests.test_capture_and_vision tests.test_navigation_selector_validator tests.test_runner_end_to_end`
- Result: `Ran 58 tests` / `OK`
- Also reproduced the retry-settle and popup-recovery-settle problems with small local harnesses.
